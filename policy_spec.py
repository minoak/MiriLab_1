# -*- coding: utf-8 -*-
"""policy_spec.py — 정책 → 타깃 명세(TargetSpec) 변환.

각 정책이 '누구를 대상으로 하는가'를 구조화한다. 이 명세로 data/personas.py 의
select_contrast_trio() 가 적합도(fit)를 점수화한다.

두 경로:
  - 샘플 정책: sample_policies.SPECS 사용 (손으로 검증, 데모 100% 재현, 키 불필요).
  - 임의 정책: LLM 1회 추출(graph.llm). 키 없음/실패 시 키워드 폴백(순수).

멀티 정책 가정: resolve_specs() 는 '정책 패키지'(list)를 받아 명세 list 를 돌려준다.

import 시점에는 어떤 네트워크/LLM 호출도 하지 않는다(함수 실행 시에만).

공개 API:
    resolve_specs(policies, use_llm=True) -> list[spec dict]
    resolve_spec(policy, use_llm=True)    -> spec dict
    keyword_spec(text, name="")           -> spec dict (순수 폴백)

spec dict 형태(plain dict, pydantic 비의존):
    {name, text, age:(min,max), income:(레벨...), family_kw:str|None, channel:str}
"""
from __future__ import annotations

import re

from graph.spaces import PLACE_KEYS, PLACE_LABELS

# 유효 소득 레벨 / 채널 (검증용)
_INCOME_LEVELS = ("low", "mid", "high")
_DEFAULT_CHANNEL = "community_center"  # 보편 오프라인 창구


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
def resolve_specs(policies, use_llm: bool = True) -> list[dict]:
    """정책 패키지(여러 정책)를 타깃 명세 리스트로 변환한다.

    Args:
        policies: 다음 중 하나의 list (또는 단일 값 — 자동으로 list 화):
            - str: 샘플 정책명(SAMPLES 키) 또는 정책 원문 텍스트
            - dict: {"name": str, "text": str}
        use_llm: True 면 임의 정책에 LLM 추출 시도(실패 시 키워드 폴백).
                 False 면 항상 키워드 폴백(키 없는 데모/테스트용).

    Returns:
        list[spec dict]. 각 dict 에 name/text/age/income/family_kw/channel 포함.
    """
    if policies is None:
        return []
    # 단일 값이면 list 로 감싼다.
    if isinstance(policies, (str, dict)):
        policies = [policies]
    return [resolve_spec(p, use_llm=use_llm) for p in policies]


def package_text(specs) -> str:
    """정책 패키지(여러 spec/정책)를 프롬프트 주입용 한 덩어리 텍스트로 만든다.

    각 정책을 번호·제목으로 구분해, LLM(시뮬)이 '동시에 시행되는 여러 정책'으로
    인식하고 한 사람의 삶에 각각 어떻게 닿는지(또는 안 닿는지) 함께 고려하게 한다.

    Args:
        specs: resolve_specs() 결과(list[spec dict]) 또는 정책 텍스트 list.
               단일 dict/str 도 허용.
    """
    if not specs:
        return ""
    if isinstance(specs, (str, dict)):
        specs = [specs]

    blocks = []
    for i, sp in enumerate(specs, 1):
        if isinstance(sp, dict):
            name = sp.get("name") or f"정책 {i}"
            text = (sp.get("text") or "").strip()
            line = tag_line(sp)          # 태그 한 줄(있으면) — 모델에 함께 전달
        else:
            name, text, line = f"정책 {i}", str(sp).strip(), ""
        # [정책 i/N] 제목  /  #태그…  /  원문  ← 빈 줄은 자동 생략
        parts = [f"[정책 {i}/{len(specs)}] {name}"]
        if line:
            parts.append(line)
        if text:
            parts.append(text)
        blocks.append("\n".join(parts).strip())

    if len(blocks) == 1:
        return blocks[0]

    header = (
        f"다음 {len(blocks)}개 정책이 동시에 시행됩니다. 이 사람의 처지에서 각 정책이 "
        "어떻게 다가오는지(수혜·간접·무관·사각) 함께 고려해 한 삶으로 묘사하세요.\n\n"
    )
    return header + "\n\n".join(blocks)


def resolve_spec(policy, use_llm: bool = True) -> dict:
    """정책 1개를 타깃 명세로 변환한다(샘플이면 SPECS, 아니면 추출)."""
    name, text = _name_and_text(policy)

    # 1) 샘플 정책이면 검증된 SPECS 를 그대로 쓴다(데모 안정).
    sample = _sample_spec(name)
    if sample is not None:
        return _finalize(sample, name, text)

    # 2) 임의 정책: LLM 추출 시도 → 실패/비활성 시 키워드 폴백.
    if use_llm:
        llm_spec = _extract_with_llm(text)
        if llm_spec is not None:
            return _finalize(llm_spec, name or _auto_name(text), text)

    return keyword_spec(text, name=name or _auto_name(text))


# ---------------------------------------------------------------------------
# 입력 정규화
# ---------------------------------------------------------------------------
def _name_and_text(policy) -> tuple[str, str]:
    """정책 입력에서 (name, text) 를 뽑는다.

    - dict: name/text 키 사용.
    - str: SAMPLES 키면 (그 이름, 원문), 아니면 ("", 원문).
    """
    from sample_policies import SAMPLES

    if isinstance(policy, dict):
        name = (policy.get("name") or "").strip()
        text = (policy.get("text") or "").strip()
        if not text and name in SAMPLES:
            text = SAMPLES[name]
        return name, text

    s = (str(policy) if policy is not None else "").strip()
    if s in SAMPLES:                       # 샘플 정책명으로 들어온 경우
        return s, SAMPLES[s]
    return "", s                           # 원문 텍스트로 들어온 경우


def _sample_spec(name: str):
    """이름이 검증된 샘플이면 SPECS 사본을 반환, 아니면 None."""
    if not name:
        return None
    from sample_policies import SPECS

    spec = SPECS.get(name)
    return dict(spec) if spec else None


def _auto_name(text: str) -> str:
    """원문에서 짧은 표시 이름을 만든다([제목] 또는 첫 줄 앞부분)."""
    text = (text or "").strip()
    if not text:
        return "정책"
    m = re.search(r"\[([^\]]{1,40})\]", text)   # [제목] 패턴 우선
    if m:
        return m.group(1).strip()
    first = text.splitlines()[0].strip()
    return (first[:24] + "…") if len(first) > 24 else (first or "정책")


def _finalize(spec: dict, name: str, text: str) -> dict:
    """spec 에 name/text 를 채우고 필드를 정규화(검증)한다."""
    out = dict(spec)
    out["name"] = name or out.get("name") or "정책"
    out["text"] = text or out.get("text") or ""
    out["age"] = _norm_age(out.get("age"))
    out["income"] = _norm_income(out.get("income"))
    out["family_kw"] = (out.get("family_kw") or None)
    ch = out.get("channel")
    out["channel"] = ch if ch in PLACE_KEYS else _DEFAULT_CHANNEL
    return out


def _norm_age(age) -> tuple:
    """age 를 (min,max) 정수 튜플로 정규화(범위 보정)."""
    try:
        lo, hi = int(age[0]), int(age[1])
    except (TypeError, ValueError, IndexError):
        return (0, 120)
    lo = max(0, min(120, lo))
    hi = max(0, min(120, hi))
    return (lo, hi) if lo <= hi else (hi, lo)


def _norm_income(income) -> tuple:
    """income 을 유효 레벨 튜플로 정규화(빈 값이면 전체 허용)."""
    if not income:
        return _INCOME_LEVELS
    levels = tuple(x for x in income if x in _INCOME_LEVELS)
    return levels or _INCOME_LEVELS


# ---------------------------------------------------------------------------
# 키워드 폴백 (순수 — 키 없이 항상 동작)
# ---------------------------------------------------------------------------
# (키워드 묶음, age, income, family_kw, channel)
_RULES = [
    (("청년", "대학생", "사회초년"), (19, 34), ("low", "mid"), None, "online_portal"),
    (("어르신", "노인", "고령", "경로"), (65, 120), ("low", "mid"), None, "welfare_center"),
    (("출산", "영아", "신생아", "육아", "양육", "보육", "아동"), (25, 45),
     ("low", "mid", "high"), "자녀", "online_portal"),
    (("장애", "취약", "저소득", "기초생활", "차상위"), (0, 120),
     ("low",), None, "community_center"),
]

# 채널 키워드 (원문에 등장하면 주 채널로 override)
_CHANNEL_KW = [
    (("복지로", "온라인", "누리집", "앱", "홈페이지"), "online_portal"),
    (("복지관", "사랑방"), "welfare_center"),
    (("주민센터", "행정복지센터", "방문 신청", "민원"), "community_center"),
]


def keyword_spec(text: str, name: str = "") -> dict:
    """정책 원문을 키워드/정규식으로 훑어 타깃 명세를 추정한다(LLM 없이).

    명시적 연령 표기(예: '만 19~34세', '만 65세 이상')를 먼저 파싱하고,
    없으면 규칙 키워드로 age/income/family/channel 을 채운다.
    """
    text = text or ""
    age = _parse_age(text)
    income = None
    family_kw = None
    channel = None

    for kws, a, inc, fam, ch in _RULES:
        if any(k in text for k in kws):
            if age is None:
                age = a
            income = income or inc
            family_kw = family_kw or fam
            channel = channel or ch
            break  # 첫 매칭 규칙을 주 타깃으로

    # 채널은 원문의 명시 채널이 있으면 그것을 우선.
    for kws, ch in _CHANNEL_KW:
        if any(k in text for k in kws):
            channel = ch
            break

    spec = {
        "age": age if age is not None else (0, 120),
        "income": income,           # _finalize 에서 None→전체 허용 정규화
        "family_kw": family_kw,
        "channel": channel or _DEFAULT_CHANNEL,
    }
    return _finalize(spec, name or _auto_name(text), text)


def _parse_age(text: str):
    """원문에서 명시적 연령 범위를 파싱한다. 실패 시 None.

    지원: '만 19~34세' / '19-34세' / '만 65세 이상' / '34세 이하'.
    """
    m = re.search(r"만?\s*(\d{1,3})\s*[~\-–]\s*(\d{1,3})\s*세", text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"만?\s*(\d{1,3})\s*세\s*이상", text)
    if m:
        return (int(m.group(1)), 120)
    m = re.search(r"만?\s*(\d{1,3})\s*세\s*이하", text)
    if m:
        return (0, int(m.group(1)))
    return None


# ---------------------------------------------------------------------------
# LLM 추출 (graph.llm 지연 import — 키/패키지 없어도 모듈 import 는 됨)
# ---------------------------------------------------------------------------
def _extract_with_llm(text: str):
    """LLM 으로 타깃 명세를 1회 추출한다. 실패하면 None(폴백 유도)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        from pydantic import BaseModel, Field
        from typing import Literal
        from graph.llm import structured_call

        class _TargetSpecOut(BaseModel):
            age_min: int = Field(ge=0, le=120, description="타깃 최소 연령")
            age_max: int = Field(ge=0, le=120, description="타깃 최대 연령(상한 없으면 120)")
            income_levels: list[Literal["low", "mid", "high"]] = Field(
                description="혜택이 닿는 소득 수준들. 소득 무관이면 셋 다."
            )
            family_keyword: str = Field(
                description="가구형태에 반드시 필요한 키워드(예:'자녀'). 무관하면 빈 문자열."
            )
            primary_channel: Literal[
                "online_portal", "community_center", "welfare_center", "work_market", "home"
            ] = Field(description="주 신청·접근 채널")

        messages = [
            {"role": "system", "content": (
                "당신은 정책 분석가입니다. 정책 원문에서 '대상 집단'을 구조화해 추출하세요. "
                "원문에 적힌 연령·소득·가구 조건에 충실하게, 추측을 최소화하세요."
            )},
            {"role": "user", "content": (
                "■ 정책 원문\n" + text + "\n\n"
                "위 정책의 타깃을 지정된 형식으로 추출하세요. "
                "연령 상한이 없으면 age_max=120, 소득 조건이 없으면 income_levels=[low,mid,high]."
            )},
        ]
        out: _TargetSpecOut = structured_call(messages, _TargetSpecOut, temperature=0.0)
        fam = (out.family_keyword or "").strip()
        return {
            "age": (out.age_min, out.age_max),
            "income": tuple(out.income_levels),
            "family_kw": fam or None,
            "channel": out.primary_channel,
        }
    except Exception:
        return None  # 키 없음/네트워크/파싱 실패 → 키워드 폴백


# ===========================================================================
# 사용자 태그 → spec (결정론, LLM 우회) + 직렬화/표시  [슬라이스 1]
# ---------------------------------------------------------------------------
# 사이드바에서 사용자가 직접 고른 '정책 태그'를 결정론 spec 으로 만든다(LLM/IO 0).
# 분류 태그(category/support_type)는 매칭(policy_fit)엔 쓰이지 않고, 프롬프트
# 힌트와 미래 RAG 라벨로만 spec 에 additive 로 함께 실린다.
#
# 공개 API:
#     spec_from_tags(...) -> spec dict     # 태그 → 결정론 명세
#     tag_line(spec)      -> str           # "#저소득 #전연령 ..." (모델 주입/표시)
#     prompt_with_tags(text, spec) -> str  # 태그 한 줄 + 정책 원문
#     describe_spec(spec) -> dict          # 표시용 라벨→값
# ===========================================================================

# 소득 레벨 한글 라벨
_INCOME_LABEL = {"low": "저소득", "mid": "중간소득", "high": "고소득"}


def _channel_tag(channel) -> str:
    """채널 키 → 짧은 태그 라벨('복지로(온라인)' → '복지로')."""
    label = PLACE_LABELS.get(channel, str(channel or ""))
    return label.split("(")[0].strip() or str(channel or "")


def _age_tag(age) -> str:
    """age (min,max) → 한글 연령 태그. 실패 시 ''."""
    try:
        lo, hi = int(age[0]), int(age[1])
    except (TypeError, ValueError, IndexError):
        return ""
    if lo <= 0 and hi >= 120:
        return "전연령"
    if hi >= 120:
        return f"{lo}세이상"
    if lo <= 0:
        return f"{hi}세이하"
    return f"{lo}~{hi}세"


def spec_from_tags(age=None, income=None, family_kw=None, channel=None,
                   category="", support_type="", name="", text="") -> dict:
    """사용자 태그 → 결정론 spec dict (LLM/네트워크 0).

    resolve_spec() 출력과 호환되는 {name,text,age,income,family_kw,channel} 에
    분류 태그(category/support_type)를 additive 로 더한다. policy_fit 은 앞 4개만
    소비하고, tag_line/RAG 는 분류 태그까지 본다.
    """
    spec = {
        "age": age,
        "income": tuple(income) if income else None,
        "family_kw": (family_kw or None),
        "channel": channel,
    }
    out = _finalize(spec, name, text)   # age/income/family_kw/channel 정규화 + name/text
    # 채널: 목록 밖 사용자 직접 입력은 라벨로 보존(_finalize 의 기본값 강제변환을 덮음).
    #       소비처(describe_spec/tag_line)는 PLACE_LABELS.get fallback 이라 graceful.
    #       매칭/선별 엔진은 채널을 안 쓰고, 인생극장 장소는 5개 공간에서 별도 선택된다.
    if isinstance(channel, str):
        ch = channel.strip()
        if ch and ch not in PLACE_KEYS:
            out["channel"] = ch
    out["category"] = (category or "").strip()
    out["support_type"] = (support_type or "").strip()
    return out


def tag_line(spec: dict) -> str:
    """spec → 프롬프트 주입/표시용 해시태그 한 줄(의미 있는 태그만)."""
    if not isinstance(spec, dict):
        return ""
    tags: list[str] = []

    # 분류(무엇을) 먼저
    cat = (spec.get("category") or "").strip()
    if cat:
        tags.append(cat)
    sup = (spec.get("support_type") or "").strip()
    if sup:
        tags.append(sup)

    # 연령
    at = _age_tag(spec.get("age"))
    if at:
        tags.append(at)

    # 소득
    income = spec.get("income")
    levels = tuple(income) if income else ()
    if not levels or set(levels) >= {"low", "mid", "high"}:
        tags.append("소득무관")
    else:
        tags.extend(_INCOME_LABEL.get(x, x) for x in levels)

    # 가구
    fam = (spec.get("family_kw") or "").strip()
    if fam:
        tags.append(f"{fam}가구")

    # 채널
    ch = _channel_tag(spec.get("channel"))
    if ch:
        tags.append(ch)

    return " ".join(f"#{t}" for t in tags)


def prompt_with_tags(text: str, spec: dict) -> str:
    """모델 주입용: 태그 한 줄 + 정책 원문. 태그가 없으면 원문 그대로."""
    line = tag_line(spec)
    body = (text or "").strip()
    if not line:
        return body
    return f"[정책 태그] {line}\n\n{body}".strip()


def describe_spec(spec: dict) -> dict:
    """spec → 사람이 읽을 표시용 항목(라벨→값) dict. 빈 분류는 생략."""
    if not isinstance(spec, dict):
        return {}
    out: dict[str, str] = {}
    out["대상 연령"] = _age_tag(spec.get("age")) or "전연령"

    income = spec.get("income")
    levels = tuple(income) if income else ()
    if not levels or set(levels) >= {"low", "mid", "high"}:
        out["소득 수준"] = "소득무관"
    else:
        out["소득 수준"] = "·".join(_INCOME_LABEL.get(x, x) for x in levels)

    fam = (spec.get("family_kw") or "").strip()
    out["가구 조건"] = f"{fam} 포함" if fam else "무관"
    out["주 신청 채널"] = PLACE_LABELS.get(spec.get("channel"), str(spec.get("channel") or "—"))

    cat = (spec.get("category") or "").strip()
    if cat:
        out["정책 분야"] = cat
    sup = (spec.get("support_type") or "").strip()
    if sup:
        out["지원 형태"] = sup
    return out
