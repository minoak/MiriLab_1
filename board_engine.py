# -*- coding: utf-8 -*-
"""정책 문의 게시판 — 답변 엔진(순수 로직, Streamlit 무의존).

게시판 탭(`ui/tab_board.py`)에서 화면(폼·말풍선)과 분리된 "답변을 만드는 로직"만
모아 둔 모듈이다. 여기엔 streamlit 도 session_state 도 없다. 그래서

  1) `python _test_board.py` 로 화면 없이 단위 테스트할 수 있고,
  2) `streamlit run _preview_board.py` 로 전체 시뮬레이션 없이 게시판만 띄워
     반복 작업할 수 있으며,
  3) **mock 을 진짜 API+RAG 로 갈아끼울 자리(seam)가 함수 하나로 모인다.**

──────────────────────────────────────────────────────────────────────
▣ 팀원 작업 지점 (API + RAG 통합)
──────────────────────────────────────────────────────────────────────
게시판 자동답변을 RAG/LLM 로 바꾸려면 **`answer_with_rag()` 하나만** 채우면 된다.
나머지(폼/말풍선/스레드 누적/폴백)는 건드릴 필요가 없다. 자세한 계약은
`answer_with_rag` 의 docstring 과 `BOARD.md` 참고.

import 시점에는 네트워크/OpenAI 호출이 절대 일어나지 않는다(키 없어도 import 가능).
실제 호출은 함수 실행 시점에만 발생하고, 실패하면 규칙 기반 답변으로 폴백한다.
"""

from __future__ import annotations

import os
import random
import re


# ── 규칙 기반 자동답변(mock)에 쓰는 키워드 사전 ──────────────────────
# 질문에 아래 키워드가 들어가면, 정책 원문에서 관련 문장을 우선적으로 끌어온다.
_TOPIC_KEYWORDS = {
    "대상": ["대상", "자격", "누가", "조건", "해당", "나이", "연령", "소득"],
    "내용": ["얼마", "금액", "지원", "혜택", "내용", "기간", "몇", "한도", "개월"],
    "방법": ["어떻게", "방법", "신청", "접수", "서류", "제출", "준비물", "어디"],
    "기간": ["언제", "기간", "마감", "기한", "접수", "모집"],
    "제외": ["제외", "안 되", "안되", "불가", "유의", "주의", "예외", "못"],
}

# 가상 시민 댓글 풀 — 질문 톤에 공감하거나 경험을 보태는 한두 줄짜리 반응.
_CITIZEN_COMMENTS = [
    "저도 같은 게 궁금했어요. 좋은 질문 감사합니다!",
    "지난주에 행정복지센터에 전화해보니 친절하게 안내해 주시더라고요.",
    "서류 준비가 생각보다 간단했어요. 통장 사본이랑 신분증만 챙기시면 돼요.",
    "예산이 빨리 소진된다는 얘기가 있어서 저는 서둘러 신청했습니다.",
    "부모님 대신 신청해 드렸는데 대리 신청도 가능했어요.",
    "온라인이 어려우면 직접 방문하는 게 마음 편하더라고요.",
    "조건이 헷갈리면 신청 전에 한 번 문의해보시는 걸 추천드려요.",
    "저는 자격이 안 돼서 아쉬웠는데, 해당되시면 꼭 받으세요!",
    "공유해 주셔서 감사해요. 주변 친구들한테도 알려줘야겠어요.",
    "후기 보니까 생각보다 빨리 처리된다고 하네요.",
]

# RAG 안내 꼬리말 — mock/RAG 답변 끝에 공통으로 붙이는 면책 문구.
_DISCLAIMER = (
    "\n\n더 정확한 내용은 거주지 행정복지센터 또는 복지로 누리집에서 "
    "확인해 주세요. (본 답변은 정책 원문을 기반으로 한 자동 안내이며, "
    "실제 심사 결과와 다를 수 있습니다.)"
)


# =====================================================================
# 공개 API — 게시판 탭이 호출하는 진입점
# =====================================================================
def answer_question(policy: str, question: str, *, mode: str = "auto",
                    k: int = 4) -> dict:
    """질문에 대한 게시판 자동답변을 만든다.

    이 함수가 mock 과 RAG 사이를 중재(dispatch)한다. **게시판 탭은 항상 이 함수만
    호출**하고, 내부에서 mode 에 따라 적절한 엔진을 고른다.

    Parameters
    ----------
    policy   : 현재 정책 원문(자동답변의 근거).
    question : 시민이 남긴 질문.
    mode     : "auto" | "mock" | "rag"
        - "auto": RAG 가 켜져 있으면(`_rag_enabled()`) RAG, 아니면 mock.
                  RAG 호출이 실패하거나 미구현이면 조용히 mock 으로 폴백한다.
        - "mock": 항상 규칙 기반 답변(키·네트워크 불필요).
        - "rag" : RAG 를 강제로 시도. 미구현/실패면 안내 문구와 함께 mock 폴백.
    k        : RAG 검색 시 끌어올 근거 청크 수(mock 은 정책 문장 2개 고정).

    Returns
    -------
    dict {
        "answer":  str,   # 표시용 답변 본문
        "sources": list,  # [{"text": .., "source": ..}] 근거(투명성/RAG 출처)
        "mode":    str,   # 실제로 답한 엔진 "mock" | "rag"
    }
    """
    policy = policy or ""
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": [], "mode": "mock"}

    want_rag = mode == "rag" or (mode == "auto" and _rag_enabled())
    if want_rag:
        try:
            res = answer_with_rag(policy, question, k=k)
            return {
                "answer": str(res.get("answer", "")),
                "sources": list(res.get("sources", [])),
                "mode": "rag",
            }
        except NotImplementedError:
            # RAG 가 아직 안 붙음. auto 면 조용히, rag(강제)면 사유를 덧붙여 mock.
            fallback = _answer_mock(policy, question)
            if mode == "rag":
                fallback["answer"] = (
                    "⚠️ RAG 엔진이 아직 연결되지 않아 규칙 기반 답변으로 "
                    "대체했습니다.\n\n" + fallback["answer"]
                )
            return fallback
        except Exception:
            # 네트워크/LLM 오류 등 — 화면이 죽지 않도록 mock 으로 폴백한다.
            return _answer_mock(policy, question)

    return _answer_mock(policy, question)


def make_comments(question: str = "", n: int | None = None) -> list:
    """가상 시민 댓글 1~2개를 무작위로 뽑는다(중복 없이).

    question 인자는 지금은 쓰지 않지만(랜덤 풀에서 추출), 나중에 질문 맥락에 맞춘
    LLM 댓글로 확장할 때를 위해 시그니처에 남겨 둔다.
    """
    count = n if n is not None else random.randint(1, 2)
    count = max(0, min(count, len(_CITIZEN_COMMENTS)))
    return random.sample(_CITIZEN_COMMENTS, k=count)


# =====================================================================
# ▣ RAG 시임(seam) — 팀원이 채울 자리
# =====================================================================
def _rag_enabled() -> bool:
    """"auto" 모드에서 RAG 를 쓸지 결정한다.

    기본은 False(=mock). 팀원이 `answer_with_rag` 를 구현한 뒤, 환경변수
    `MIRILAB_BOARD_RAG=1` 을 켜면 auto 모드에서도 RAG 가 동작한다. 코드 수정 없이
    스위치만으로 켜고 끌 수 있어, 데모(키 없음)는 그대로 mock 으로 안전하게 돈다.
    """
    flag = os.getenv("MIRILAB_BOARD_RAG", "").strip().lower()
    return flag not in ("", "0", "false", "no", "off")


def answer_with_rag(policy: str, question: str, k: int = 4) -> dict:
    """▣ 팀원 작업 지점 — 정책 문서 RAG + LLM 자동답변.

    여기에 API+RAG 파이프라인을 구현한다. 권장 흐름:

      1) 정책 원문(policy)을 청크로 분할 → 임베딩 → 벡터스토어 검색.
         (질문과 가장 관련 있는 청크 k개를 가져온다.)
      2) 검색된 청크 + 질문을 LLM 프롬프트에 넣어 답변 문장을 생성한다.
         (`graph.llm.get_client()` / `structured_call()` 재사용 가능,
          `graph.llm.has_real_key()` 로 키 존재 확인.)
      3) 아래 반환 계약을 지킨다.

    반환(계약)
    ----------
    dict {
        "answer":  str,    # 표시할 답변 본문(면책 문구는 호출측에서 안 붙임 — 직접 포함)
        "sources": list,   # [{"text": 근거청크, "source": 출처라벨}, ...] (없으면 [])
    }

    구현 전에는 NotImplementedError 를 던진다 → `answer_question` 이 mock 으로
    안전하게 폴백한다. 구현을 마치면 환경변수 `MIRILAB_BOARD_RAG=1` 로 켜거나,
    `_preview_board.py` 에서 엔진을 "rag" 로 골라 단독 테스트하면 된다.

    참고: import 시점 네트워크 호출 금지 규칙을 지키려면 openai/벡터스토어 import 를
    이 함수 안에서(지연 import) 수행할 것.
    """
    # 예시 골격(주석) — 실제 구현 시 아래를 채우고 raise 를 지운다.
    #
    #   from graph.llm import has_real_key, get_client, MODEL
    #   if not has_real_key():
    #       raise RuntimeError("OpenAI 키가 없습니다.")
    #   chunks = _retrieve_policy_chunks(policy, question, k=k)   # 팀원 RAG
    #   prompt = _build_rag_prompt(policy, question, chunks)
    #   answer = get_client().chat.completions.create(...)        # LLM 호출
    #   return {"answer": answer + _DISCLAIMER,
    #           "sources": [{"text": c, "source": "정책 원문"} for c in chunks]}
    raise NotImplementedError(
        "answer_with_rag 가 아직 구현되지 않았습니다. board_engine.py 의 이 함수에 "
        "정책 RAG + LLM 답변을 채워 주세요."
    )


# =====================================================================
# mock 엔진 — 규칙 기반 답변(키·네트워크 불필요). 기본 동작이자 폴백.
# =====================================================================
def _answer_mock(policy: str, question: str) -> dict:
    """정책 원문 기반 규칙형 자동답변을 만든다(mock).

    실제 LLM/RAG 호출 없이, 질문 주제와 관련된 정책 문장을 골라 안내 문구로 감싼다.
    근거로 쓴 문장은 sources 에 RAG 와 같은 모양({text, source})으로 함께 돌려줘서,
    UI 의 '근거 보기'가 mock/RAG 양쪽에서 동일하게 동작한다.
    """
    topic = _match_topic(question)
    relevant = _pick_relevant_sentences(policy, question, k=2)

    intro_map = {
        "대상": "신청 대상·자격 관련해서 안내드릴게요.",
        "내용": "지원 내용과 금액 관련해서 안내드릴게요.",
        "방법": "신청 방법·절차 관련해서 안내드릴게요.",
        "기간": "신청 기간·일정 관련해서 안내드릴게요.",
        "제외": "제외 대상·유의 사항 관련해서 안내드릴게요.",
    }
    intro = intro_map.get(topic, "문의하신 내용 관련해서 정책 안내를 정리해 드릴게요.")

    if relevant:
        body = "\n".join(f"- {s.rstrip('.')}." for s in relevant)
    else:
        body = "- 현재 등록된 정책 본문에서 관련 안내를 찾지 못했어요."

    answer = f"{intro}\n\n{body}{_DISCLAIMER}"
    sources = [{"text": s, "source": "정책 원문"} for s in relevant]
    return {"answer": answer, "sources": sources, "mode": "mock"}


# ── mock 내부 유틸(순수 함수) ────────────────────────────────────────
def _split_sentences(policy: str) -> list:
    """정책 원문을 문장 단위로 거칠게 분리한다.

    줄바꿈과 마침표(。/.)를 기준으로 나누고, 너무 짧은 조각·정책 제목 줄은 버린다.
    """
    if not policy:
        return []
    text = policy.replace("\n", ". ")
    raw = re.split(r"(?<=[.!?。])\s+", text)
    sentences = []
    for s in raw:
        s = s.strip()
        # 대괄호로 묶인 정책 제목 줄([청년 월세 …])은 제외
        if not s or s.startswith("["):
            continue
        if len(s) < 6:
            continue
        sentences.append(s)
    return sentences


def _match_topic(question: str) -> str:
    """질문에서 가장 많이 매칭되는 주제(대상/내용/방법/기간/제외)를 고른다.

    매칭되는 키워드가 하나도 없으면 빈 문자열을 반환한다.
    """
    q = (question or "").lower()
    best_topic = ""
    best_hits = 0
    for topic, kws in _TOPIC_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in q)
        if hits > best_hits:
            best_hits = hits
            best_topic = topic
    return best_topic


def _pick_relevant_sentences(policy: str, question: str, k: int = 2) -> list:
    """질문 주제와 가장 관련 있는 정책 문장 k개를 고른다.

    1순위: 질문에 등장한 단어가 직접 포함된 문장.
    2순위: 주제 키워드가 포함된 문장.
    아무것도 못 찾으면 앞쪽 문장으로 대체한다.
    """
    sentences = _split_sentences(policy)
    if not sentences:
        return []

    q_tokens = [t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", question or "")]

    topic = _match_topic(question)
    topic_kws = _TOPIC_KEYWORDS.get(topic, [])

    scored = []
    for s in sentences:
        score = 0
        for t in q_tokens:          # 질문 토큰 직접 매칭(가중치 높음)
            if t in s:
                score += 2
        for kw in topic_kws:        # 주제 키워드 매칭
            if kw in s:
                score += 1
        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [s for sc, s in scored if sc > 0][:k]

    if not picked:                  # 관련 문장을 못 찾으면 정책 앞부분으로 대체
        picked = sentences[:k]
    return picked
