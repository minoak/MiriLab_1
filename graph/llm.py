"""graph/llm.py — LLM 클라이언트 래퍼 및 동시 실행 유틸.

- import 시점에는 절대 네트워크 호출을 하지 않는다(키 없어도 import 되어야 함).
- 실제 네트워크 호출은 함수가 실행될 때만 발생한다.
- 공개 API: MODEL, PROVIDER, set_provider(), available_providers(),
  has_real_key(), get_client(), structured_call(...), run_threaded(...)

프로바이더 스위치(2026-06-06, 질감 프로브 후 도입):
  openai(기본) / gemini(구글 OpenAI 호환 엔드포인트) — 같은 코드 경로
  (client.beta.chat.completions.parse) 그대로(프로브 48/48 스키마 통과).
  기본값은 .env 의 `MIRILAB_LLM`(없으면 openai)이고, 앱 사이드바의
  '시민 모델' 선택기가 set_provider() 로 런타임에 전환한다.
  시민 시뮬 축(react/interact/aggregate/캐스팅/인생극장/리포트)이 이 모듈을 쓰고,
  미리마을 gen 스크립트는 같은 분기를 독립 복제(tab_minivillage 가 동기화).
  게시판 RAG(standalone_board, OpenAI 임베딩)는 별도 — OpenAI 고정.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

# .env 로드는 import 시점에 1회만 수행(네트워크 호출 아님 — 환경변수만 읽음).
load_dotenv()

# LLM 프로바이더: openai(기본) / gemini.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# 프로바이더별 사용 모델. 환경변수로 덮어쓸 수 있고, 없으면 기본값.
PROVIDER_MODELS = {
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": os.getenv("MIRILAB_GEMINI_MODEL", "gemini-3-flash-preview"),
}

# 시작 프로바이더 = .env 의 MIRILAB_LLM(없거나 오타면 openai).
# 런타임 전환은 set_provider() — PROVIDER/MODEL 은 항상 짝으로 갱신된다.
PROVIDER = (os.getenv("MIRILAB_LLM") or "openai").strip().lower()
if PROVIDER not in PROVIDER_MODELS:
    PROVIDER = "openai"
MODEL = PROVIDER_MODELS[PROVIDER]


def set_provider(name: str) -> None:
    """런타임 프로바이더 전환(앱 '시민 모델' 선택기용).

    PROVIDER/MODEL 모듈 전역을 짝으로 갱신한다. 클라이언트는 프로바이더별로
    캐시되므로(_clients) 전환을 왕복해도 재생성되지 않는다.
    잘못된 이름은 ValueError(조용히 다른 모델로 호출 나가는 사고 방지).
    """
    global PROVIDER, MODEL
    name = (name or "").strip().lower()
    if name not in PROVIDER_MODELS:
        raise ValueError(f"알 수 없는 프로바이더: {name!r} (가능: {tuple(PROVIDER_MODELS)})")
    PROVIDER = name
    MODEL = PROVIDER_MODELS[name]

logger = logging.getLogger("mirilab.llm")

# 층2 prefix 캐시 실측 준비(설계방향서 §6·§8-6): 세션 누적 사용량.
# 이틀엔 로깅·집계만(무해) — 프롬프트 레이아웃 최적화는 발표 후 이 실측을 근거로.
# (스레드 동시 갱신은 통계용이라 엄밀한 원자성 불요.)
LLM_USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "cached_tokens": 0}


def _log_usage(resp) -> None:
    """응답 usage 의 cached_tokens 를 누적·로깅한다. 실패해도 본 호출은 무해."""
    try:
        u = resp.usage
        if u is None:  # usage 미제공 응답 — 부분 누적 없이 통째로 건너뜀
            return
        cached = getattr(
            getattr(u, "prompt_tokens_details", None), "cached_tokens", 0
        ) or 0
        LLM_USAGE["calls"] += 1
        LLM_USAGE["prompt_tokens"] += u.prompt_tokens or 0
        LLM_USAGE["completion_tokens"] += u.completion_tokens or 0
        LLM_USAGE["cached_tokens"] += cached
        logger.info(
            "usage: prompt=%s (cached=%s) completion=%s | 누적 calls=%s cached/prompt=%s/%s",
            u.prompt_tokens, cached, u.completion_tokens,
            LLM_USAGE["calls"], LLM_USAGE["cached_tokens"],
            LLM_USAGE["prompt_tokens"],
        )
    except Exception:  # noqa: BLE001 — 로깅은 절대 본 호출을 깨뜨리지 않는다.
        pass

# get_client() 클라이언트 캐시(프로바이더별 1개 — 전환 왕복에도 재생성 없음).
_clients: dict = {}


def _key_for(provider: str) -> str | None:
    """해당 프로바이더의 실제 사용 가능한 API 키(없거나 플레이스홀더면 None)."""
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY") or None
    key = os.getenv("OPENAI_API_KEY")
    # 'sk-your-key...' 같은 예시/플레이스홀더 키는 실제 키로 취급하지 않는다.
    if not key or key.startswith("sk-your-key"):
        return None
    return key


def has_real_key() -> bool:
    """현재 프로바이더 기준으로 실제 사용 가능한 API 키가 있는지 판정한다.

    - openai(기본): OPENAI_API_KEY 존재 + 플레이스홀더('sk-your-key') 아님.
    - gemini      : GEMINI_API_KEY 존재.
    키가 없으면 False(이 경우 호출측은 mock 등으로 대체).
    """
    return bool(_key_for(PROVIDER))


def available_providers() -> list:
    """키가 실제로 설정된 프로바이더 목록(앱 '시민 모델' 선택기의 선택지 재료)."""
    return [p for p in PROVIDER_MODELS if _key_for(p)]


def get_client() -> OpenAI:
    """현재 프로바이더의 LLM 클라이언트 반환(엔드포인트만 다름, 코드 경로 동일).

    프로바이더별 최초 호출 시에만 인스턴스를 만들어 _clients 에 캐시한다.
    (생성자 호출 자체는 네트워크 통신을 하지 않으므로 import 제약과 무관하나,
     안전하게 함수 실행 시점에만 생성한다.)
    """
    client = _clients.get(PROVIDER)
    if client is None:
        if PROVIDER == "gemini":
            client = OpenAI(api_key=_key_for("gemini"),
                            base_url=GEMINI_BASE_URL)
        else:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        _clients[PROVIDER] = client
    return client


def _is_reasoning_model(model: str) -> bool:
    return (model or "").startswith(REASONING_PREFIXES)


@retry(
    # 일시적 오류(레이트리밋/타임아웃/API오류)에 대해 지수 백오프 + 지터로 재시도.
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
)
def structured_call(messages, schema, temperature=0.7):
    """구조화 출력(structured output) 호출.

    messages    : OpenAI chat messages 리스트 [{'role':..,'content':..}, ...]
    schema      : pydantic BaseModel 서브클래스(response_format 으로 사용)
    temperature : 샘플링 온도

    반환: 파싱된 pydantic 객체(resp.choices[0].message.parsed).
    일시적 오류는 tenacity 가 자동 재시도한다.
    """
    client = get_client()
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "response_format": schema,
    }
    if not _is_reasoning_model(MODEL):
        kwargs["temperature"] = temperature
    resp = client.beta.chat.completions.parse(**kwargs)
    _log_usage(resp)  # 층2 캐시 실측(§8-6) — cached_tokens 누적·로깅
    return resp.choices[0].message.parsed


def run_threaded(items, fn, max_workers=8):
    """items 각 원소에 fn 을 스레드풀로 동시 적용하고, 입력 순서대로 결과 리스트 반환.

    - executor.map 을 사용하므로 결과는 입력 순서가 보존된다.
    - 예외 처리는 호출측/ fn 내부 책임이다(여기서 None 으로 삼키지 않는다).
      fn 내부에서 자체적으로 try/except 하도록 설계하고, 여기서는 map 결과를 그대로 돌려준다.
    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(fn, items))
