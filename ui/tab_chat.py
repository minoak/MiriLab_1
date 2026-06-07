# -*- coding: utf-8 -*-
"""SNS 채팅방 탭.

view['interactions']를 round별 대화 타임라인으로 바꾼 뒤, 참고용 talk.html과 같은
다크 채팅 패널로 렌더링한다. 라이브 모드는 Streamlit rerun 루프가 아니라 iframe
내부 JavaScript가 메시지를 순차 공개하는 방식이라 탭 이동/입력 상태와 덜 충돌한다.
"""
from __future__ import annotations

import base64
import hashlib
import html as html_lib
import json
from typing import Literal

from pydantic import BaseModel, Field
import streamlit as st

from graph.llm import has_real_key, structured_call


_LIVE_KEY = "miri_chat_live_mode"
_REPLAY_KEY = "miri_chat_replay_nonce"
_DEBATE_KEY = "miri_chat_debate_messages"
_FOCUS_KEY = "miri_chat_focus_persona"

_STANCE_LABEL = {
    "support": "찬성",
    "oppose": "반대",
    "mixed": "혼합",
}

_STANCE_CLASS = {
    "support": "stance-support",
    "oppose": "stance-oppose",
    "mixed": "stance-neutral",
}

_TOPIC_LABEL = {
    "eligibility": "대상 기준",
    "amount": "지원 금액",
    "documents": "서류 부담",
    "access": "신청 경로",
    "deadline": "신청 기간",
    "general": "정책 문구",
}

_TOPIC_SUGGESTION = {
    "eligibility": "대상·소득·원가구 기준을 사례표로 풀어 안내",
    "amount": "지원 금액·기간·지급 시점을 한 줄 요약으로 명확화",
    "documents": "필수 서류 체크리스트와 대체 서류 예시 제공",
    "access": "온라인 신청과 방문 신청 경로를 같은 비중으로 노출",
    "deadline": "상시 접수와 예산 소진 시 조기 마감 가능성을 분리 안내",
    "general": "정책 목적보다 신청자가 바로 판단할 조건을 먼저 배치",
}

_TOPIC_PROBLEM = {
    "eligibility": "부모·원가구·소득 기준이 한 문장에 묶여 자격 여부를 스스로 판단하기 어렵습니다.",
    "amount": "지원 금액은 긍정적으로 받아들여지지만 실제 지급 시점과 체감 효과가 충분히 설명되지 않습니다.",
    "documents": "임대차계약서, 소득 증빙, 통장 사본처럼 준비해야 할 서류에서 신청 포기가 생길 수 있습니다.",
    "access": "온라인 신청 안내가 앞에 놓이면 디지털 접근성이 낮은 시민은 방문 경로를 놓치기 쉽습니다.",
    "deadline": "상시 접수와 예산 소진 시 조기 마감 가능성이 함께 보여 신청 가능 상태를 불안하게 만듭니다.",
    "general": "정책 취지는 보이지만 신청자가 바로 행동할 조건과 다음 단계가 흩어져 있습니다.",
}

_FAILED_TEXTS = {"(응답 생성 실패)", "응답 생성 실패", "(상호작용 생성 실패)", "상호작용 생성 실패", "상호작용 실패"}


class _LLMStanceChange(BaseModel):
    name: str = Field(description="입장이 바뀐 시민 이름")
    before: Literal["support", "oppose", "mixed"] = Field(description="변화 전 입장")
    after: Literal["support", "oppose", "mixed"] = Field(description="변화 후 입장")
    reason: str = Field(description="정책 원문과 대화에 근거한 변화 이유")
    influenced_by: str = Field(description="영향을 준 시민 또는 집단")
    message: str = Field(description="근거가 되는 대표 발언")


class _LLMIssue(BaseModel):
    issue: str = Field(description="정책 원문에서 직접 도출한 구체 쟁점명")
    count: int = Field(ge=1, le=999, description="SNS 대화에서 관련 발언이 언급된 횟수")
    pressure: Literal["논쟁", "불만/우려", "수용/기대", "관찰"] = Field(description="쟁점의 토론 압력")
    problem: str = Field(description="정책 원문과 대화에 근거한 문제 원인")
    suggestion: str = Field(description="정책 원문을 어떻게 고치거나 보완할지에 대한 실행안")
    sample: str = Field(description="근거가 되는 대표 시민 발언")


class _LLMDebateInsights(BaseModel):
    key_issues: list[_LLMIssue] = Field(description="중요 쟁점 3~5개")
    stance_changes: list[_LLMStanceChange] = Field(default_factory=list, description="입장 변화 사례")
    verdict: str = Field(description="정책 토론의 종합 판정 한 문장")

_DOMAIN_TOPIC = {
    "housing": {
        "amount": ("월세 지원 내용", "지원 한도·기간·지급 시점을 한 줄 요약과 예시로 분리 안내", "월세 부담 완화 효과는 보이지만 한도·기간·지급 시점이 함께 보이지 않으면 체감 판단이 어렵습니다."),
        "eligibility": ("주거·소득 기준", "나이·무주택·원가구 소득 기준을 대상 판정표로 제공", "부모·원가구·무주택 기준이 복합적으로 묶여 신청자가 스스로 대상 여부를 판단하기 어렵습니다."),
        "documents": ("임대차 서류", "임대차계약서·소득 증빙·통장 사본 체크리스트와 대체 서류 예시 제공", "계약 형태나 소득 증빙이 애매한 시민은 서류 단계에서 신청을 포기할 수 있습니다."),
        "access": ("신청 창구", "복지로 온라인과 행정복지센터 방문 신청 경로를 같은 비중으로 노출", "온라인과 방문 경로가 분리되어 보이면 접근성이 낮은 시민이 창구를 놓치기 쉽습니다."),
        "deadline": ("접수·예산 상태", "상시 접수와 예산 소진 가능성을 별도 상태 표시로 안내", "상시 접수와 조기 마감 가능성이 같이 보여 신청 가능 상태가 불안하게 느껴집니다."),
        "general": ("정책 문구", "정책 목적보다 신청자가 바로 판단할 조건을 먼저 배치", "정책 취지는 보이지만 신청자가 바로 행동할 조건과 다음 단계가 흩어져 있습니다."),
    },
    "digital": {
        "amount": ("교육·기기 지원", "교육 내용·수료 조건·기기 또는 통신비 지원 범위를 한 표로 안내", "교육과 기기 지원이 함께 제시되어 실제로 무엇을 받을 수 있는지 한눈에 잡히지 않습니다."),
        "eligibility": ("어르신 대상 기준", "연령 기준과 디지털 사용 어려움 판단 기준을 쉬운 사례로 설명", "나이는 명확하지만 디지털 어려움을 어떻게 판단하는지 모호하면 신청을 망설일 수 있습니다."),
        "documents": ("대리 신청 서류", "자녀 등 대리 신청 시 필요한 확인 서류와 위임 절차를 따로 안내", "대리 신청이 가능하다고 해도 필요한 확인 절차가 없으면 가족이 대신 신청하기 어렵습니다."),
        "access": ("방문·전화 접수", "전화·방문 접수 위치와 상담 가능 시간을 첫 화면에 크게 배치", "디지털 취약층 대상 정책인데 온라인 정보만 앞서면 정작 대상자가 접근하기 어렵습니다."),
        "deadline": ("분기 모집·정원", "분기별 모집 일정, 정원, 대기자 처리 방식을 함께 공개", "분기별 정원 제한이 있으면 늦게 알게 된 어르신은 탈락 불안을 크게 느낄 수 있습니다."),
        "general": ("교육 운영", "교육 장소·난이도·반복 실습 여부를 신청 전에 확인 가능하게 안내", "정책 취지는 좋지만 교육 난이도와 현장 운영 방식이 보이지 않으면 참여 결정을 하기 어렵습니다."),
    },
    "birth": {
        "amount": ("바우처 금액·사용처", "첫째·둘째 금액, 사용 가능 업종, 사용 기한을 카드형 요약으로 제공", "바우처 금액은 크지만 어디서 언제까지 쓸 수 있는지 바로 보이지 않으면 체감이 떨어집니다."),
        "eligibility": ("아동·보호자 기준", "출생신고·주민등록·보호자 요건을 사례별로 구분", "출생 아동과 보호자 기준이 행정 절차와 얽혀 있어 예외 가구가 헷갈릴 수 있습니다."),
        "documents": ("출생신고 연계", "출생신고와 동시 신청 시 필요한 확인 항목을 체크리스트로 제공", "출생신고, 주민등록, 카드 신청이 연결되어 있어 초보 보호자가 절차를 놓칠 수 있습니다."),
        "access": ("온라인·주민센터 신청", "복지로와 주민센터, 행복출산 원스톱 서비스의 차이를 비교 안내", "신청 경로가 여러 개라 어느 경로가 빠른지 판단하기 어렵습니다."),
        "deadline": ("사용 기한", "출생일 기준 신청·사용 마감일을 자동 계산해 보여주기", "출생일로부터 1년이라는 기준은 명확하지만 실제 마감일을 놓칠 위험이 있습니다."),
        "general": ("예외 확인", "주소가 다른 보호자·아동의 별도 확인 절차를 먼저 안내", "가구 상황이 표준 사례와 다르면 추가 확인 절차에서 막힐 수 있습니다."),
    },
    "emergency": {
        "amount": ("생계·의료 지원", "가구원 수별 지원 금액과 의료·주거비 추가 지원 조건을 분리 안내", "긴급 지원 범위가 넓어 실제로 어떤 항목을 받을 수 있는지 판단하기 어렵습니다."),
        "eligibility": ("위기 사유·소득 기준", "실직·질병·휴폐업 등 위기 사유와 중위소득 기준을 사례로 제시", "위기 사유와 소득 기준을 동시에 충족해야 해 대상 판단이 어렵습니다."),
        "documents": ("증빙 부담", "위기 사유 증빙과 소득·재산 확인 자료를 사전 체크리스트로 제공", "긴급 상황인데 증빙 자료가 복잡하면 신청 전 포기나 지연이 생길 수 있습니다."),
        "access": ("센터·129 상담", "행정복지센터 방문과 129 전화 신청 중 상황별 첫 경로를 안내", "어디로 먼저 연락해야 하는지 모르면 긴급성이 높은 시민이 시간을 잃을 수 있습니다."),
        "deadline": ("상시 접수", "위기 발생 즉시 접수 가능 여부와 처리 예상 기간을 같이 안내", "상시 접수라도 처리 기간과 우선순위가 보이지 않으면 불안이 남습니다."),
        "general": ("환수 위험", "사후 조사와 환수 가능성을 신청 전 확인 문구로 명확히 안내", "사후 조사에서 환수될 수 있다는 조건은 신청 의향을 크게 흔들 수 있습니다."),
    },
    "asset": {
        "amount": ("매칭 적립", "본인 저축액, 정부 매칭액, 3년 만기 수령 예시를 숫자로 보여주기", "목돈 마련 효과는 보이지만 매칭 구조와 만기 수령액이 바로 계산되지 않습니다."),
        "eligibility": ("근로·소득 기준", "근로·사업소득 유지 조건과 가구 소득 기준을 함께 판정", "근로 상태와 가구 소득 기준이 동시에 걸려 경계선 청년이 헷갈릴 수 있습니다."),
        "documents": ("소득 증빙", "근로·사업소득 증빙 방식과 갱신 주기를 신청 전에 안내", "소득 증빙과 유지 확인이 반복되면 중도 포기 가능성이 커집니다."),
        "access": ("복지로·센터 신청", "온라인 신청과 행정복지센터 상담을 저축 유지 안내와 연결", "계좌 개설과 행정 신청 흐름이 분리되어 보이면 시작 단계에서 막힐 수 있습니다."),
        "deadline": ("모집 공고 기간", "모집 공고 일정과 다음 모집 알림 신청을 제공", "모집 기간을 놓치면 정책 효과가 있어도 참여할 수 없습니다."),
        "general": ("중도 중지 조건", "근로 중단·소득 초과 시 지원 중지 조건을 먼저 안내", "중도 중지 조건이 늦게 보이면 신청자가 위험을 과소평가할 수 있습니다."),
    },
}


def _esc(value) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def _policy_text(view) -> str:
    if isinstance(view, dict):
        return str(view.get("policy") or view.get("policy_text") or "")
    return ""


def _clip_chars(text: str, limit: int) -> str:
    clean = str(text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _session_policy_documents() -> list:
    """게시판 탭에서 업로드·인덱싱한 문서를 SNS 분석 근거로 공유한다."""
    try:
        documents = st.session_state.get("standalone_board_documents", [])
    except Exception:
        documents = []
    return list(documents or []) if isinstance(documents, (list, tuple)) else []


def _session_policy_chunks() -> list:
    try:
        chunks = st.session_state.get("standalone_board_chunks", [])
    except Exception:
        chunks = []
    return list(chunks or []) if isinstance(chunks, (list, tuple)) else []


def _policy_context_text(view) -> str:
    """LLM 분석에 넣을 정책 원문/첨부 문서 컨텍스트."""
    parts = []
    policy = _policy_text(view)
    if policy:
        parts.append("[미리랩 설정 정책 원문]\n" + policy)

    if isinstance(view, dict):
        for idx, doc in enumerate(view.get("policy_documents") or [], start=1):
            if isinstance(doc, dict):
                name = doc.get("name") or f"첨부 문서 {idx}"
                text = doc.get("text") or ""
            else:
                name = getattr(doc, "name", f"첨부 문서 {idx}")
                text = getattr(doc, "text", "")
            if str(text or "").strip():
                parts.append(f"[첨부 문서: {name}]\n{str(text).strip()}")

    for idx, doc in enumerate(_session_policy_documents(), start=1):
        name = getattr(doc, "name", f"게시판 첨부 문서 {idx}")
        text = getattr(doc, "text", "")
        if str(text or "").strip():
            parts.append(f"[게시판 인덱싱 문서: {name}]\n{str(text).strip()}")

    if len(parts) <= 1:
        chunk_texts = []
        for chunk in _session_policy_chunks()[:16]:
            text = getattr(chunk, "text", "")
            source = getattr(chunk, "source_label", "") or getattr(chunk, "document_name", "")
            if str(text or "").strip():
                chunk_texts.append(f"- {source}: {str(text).strip()}")
        if chunk_texts:
            parts.append("[게시판 인덱싱 근거 조각]\n" + "\n".join(chunk_texts))

    return _clip_chars("\n\n".join(parts), 14000)


def _debate_context_text(view, messages: list[dict]) -> str:
    personas = _build_persona_index(view)
    lines = []
    for idx, msg in enumerate(messages[:40], start=1):
        from_id = msg.get("from_id")
        persona = personas.get(str(from_id)) if from_id is not None else None
        name = msg.get("name") or _speaker_name(persona, from_id)
        stance = _message_stance(view, msg)
        stage = msg.get("stage_title") or msg.get("stage") or f"{msg.get('round', '-') }턴"
        text = str(msg.get("text") or "").strip()
        if not text or _is_failed_interaction_text(text):
            continue
        lines.append(f"{idx}. [{stage}] {name} / {_STANCE_LABEL.get(stance, stance)}: {text}")
    return _clip_chars("\n".join(lines), 10000)


def _policy_domain(view_or_policy) -> str:
    if isinstance(view_or_policy, dict):
        text = _policy_text(view_or_policy)
        spec = view_or_policy.get("policy_spec") if isinstance(view_or_policy.get("policy_spec"), dict) else {}
        hint = " ".join(str(spec.get(k) or "") for k in ("category", "support_type", "name"))
        text = f"{hint} {text}"
    else:
        text = str(view_or_policy or "")
    if any(k in text for k in ("월세", "임대료", "무주택", "임차", "주택")):
        return "housing"
    if any(k in text for k in ("디지털", "스마트폰", "키오스크", "교육", "기기", "복지관")):
        return "digital"
    if any(k in text for k in ("출산", "출생", "아동", "보호자", "바우처", "국민행복카드", "행복출산")):
        return "birth"
    if any(k in text for k in ("긴급", "위기", "생계", "의료비", "휴폐업", "환수", "129")):
        return "emergency"
    if any(k in text for k in ("저축", "계좌", "자산", "근로", "적립", "만기")):
        return "asset"
    return "general"


def _domain_topic(view, topic: str) -> tuple[str, str, str]:
    domain = _policy_domain(view)
    domain_map = _DOMAIN_TOPIC.get(domain) or {}
    if topic in domain_map:
        return domain_map[topic]
    if topic in _DOMAIN_TOPIC.get("housing", {}):
        return _DOMAIN_TOPIC["housing"][topic]
    return (
        _TOPIC_LABEL.get(topic, _TOPIC_LABEL["general"]),
        _TOPIC_SUGGESTION.get(topic, _TOPIC_SUGGESTION["general"]),
        _TOPIC_PROBLEM.get(topic, _TOPIC_PROBLEM["general"]),
    )


def _topic_label_for(view, topic: str) -> str:
    return _domain_topic(view, topic)[0]


def _topic_suggestion_for(view, topic: str) -> str:
    return _domain_topic(view, topic)[1]


def _topic_problem_for(view, topic: str) -> str:
    return _domain_topic(view, topic)[2]


def _preferred_topics_for_policy(view) -> list[str]:
    domain = _policy_domain(view)
    return {
        "housing": ["eligibility", "amount", "documents", "access", "deadline"],
        "digital": ["access", "amount", "deadline", "documents", "eligibility"],
        "birth": ["amount", "access", "deadline", "eligibility", "documents"],
        "emergency": ["eligibility", "documents", "access", "general", "deadline"],
        "asset": ["amount", "eligibility", "documents", "deadline", "access"],
    }.get(domain, ["eligibility", "amount", "access", "documents", "deadline"])


def _build_persona_index(view):
    """view['personas']를 id -> persona dict로 인덱싱한다."""
    personas = (view or {}).get("personas")
    index = {}
    if isinstance(personas, dict):
        for pid, persona in personas.items():
            if isinstance(persona, dict):
                index[str(pid)] = persona
    elif isinstance(personas, (list, tuple)):
        for persona in personas:
            if isinstance(persona, dict) and persona.get("id") is not None:
                index[str(persona["id"])] = persona
    return index


def _build_reaction_index(view):
    """persona_id -> reaction dict."""
    by_id = (view or {}).get("reactions_by_id")
    if isinstance(by_id, dict):
        return {str(k): v for k, v in by_id.items() if isinstance(v, dict)}

    reactions = (view or {}).get("reactions") or []
    index = {}
    if isinstance(reactions, (list, tuple)):
        for reaction in reactions:
            if isinstance(reaction, dict) and reaction.get("persona_id") is not None:
                index[str(reaction["persona_id"])] = reaction
    return index


def _speaker_name(persona, from_id):
    if isinstance(persona, dict) and persona.get("name"):
        return str(persona["name"])
    fid = str(from_id) if from_id is not None else "익명"
    return f"시민 {fid[:6]}"


def _speaker_meta(persona):
    if isinstance(persona, dict) and persona.get("description"):
        desc = str(persona["description"])
        return desc if len(desc) <= 54 else desc[:53] + "..."
    return ""


def _persona_list(view) -> list[dict]:
    personas = (view or {}).get("personas") or []
    if isinstance(personas, dict):
        return [p for p in personas.values() if isinstance(p, dict)]
    if isinstance(personas, (list, tuple)):
        return [p for p in personas if isinstance(p, dict)]
    return []


def _normalize_stance(value):
    """support/oppose/mixed를 안전하게 정규화한다."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    aliases = {
        "support": "support",
        "찬성": "support",
        "positive": "support",
        "oppose": "oppose",
        "반대": "oppose",
        "negative": "oppose",
        "mixed": "mixed",
        "neutral": "mixed",
        "중립": "mixed",
        "혼합": "mixed",
    }
    return aliases.get(raw)


def _parse_stance_shift(value):
    """stance_shift 값을 (이전, 이후)로 파싱한다.

    지원 형식:
    - "mixed→support"
    - "mixed -> oppose"
    - "support"  # 이후 입장만 있는 경우
    """
    if not value:
        return None, None
    raw = str(value).strip()
    for arrow in ("→", "->", "=>", ">"):
        if arrow in raw:
            before, after = raw.split(arrow, 1)
            return _normalize_stance(before), _normalize_stance(after)
    return None, _normalize_stance(raw)


def _stance_badge(stance) -> str:
    key = _normalize_stance(stance) or "mixed"
    cls = _STANCE_CLASS.get(key, "stance-neutral")
    return f'<span class="{cls}">{_esc(_STANCE_LABEL.get(key, "혼합"))}</span>'


def _avatar_for(persona, stance=None):
    """연령/성별 기반 프로필 아바타. 못 찾으면 입장 기반 표정으로 폴백."""
    demographics = persona.get("demographics") if isinstance(persona, dict) else {}
    demographics = demographics if isinstance(demographics, dict) else {}
    sex = str(demographics.get("sex") or "")
    try:
        age = int(demographics.get("age"))
    except (TypeError, ValueError):
        age = 0

    if age >= 65:
        return "👵" if "여" in sex else "👴"
    if "여" in sex:
        return "👩"
    if "남" in sex:
        return "👨"

    key = _normalize_stance(stance)
    if key == "support":
        return "🙂"
    if key == "oppose":
        return "😟"
    return "🧑"


def _group_by_round(interactions):
    groups = {}
    for item in interactions:
        if not isinstance(item, dict):
            continue
        try:
            round_no = int(item.get("round", 0) or 0)
        except (TypeError, ValueError):
            round_no = 0
        groups.setdefault(round_no, []).append(item)
    return [(round_no, groups[round_no]) for round_no in sorted(groups)]


def _is_outgoing(from_id, focus_id) -> bool:
    return focus_id is not None and from_id is not None and str(from_id) == str(focus_id)


def _is_failed_interaction_text(text: str) -> bool:
    clean = str(text or "").strip()
    return clean in _FAILED_TEXTS


def _fallback_reaction_text(view, persona: dict, reaction: dict, offset: int = 0) -> str:
    """기존 결과에 실패 문구가 들어온 경우 SNS 화면에서 쓸 자연스러운 대체 반응."""
    stance = _normalize_stance((reaction or {}).get("stance")) or "mixed"
    domain = _policy_domain(view)
    topic_cycle = {
        "housing": ["eligibility", "amount", "documents", "access", "deadline"],
        "digital": ["access", "amount", "deadline", "documents", "eligibility"],
        "birth": ["amount", "access", "deadline", "eligibility", "documents"],
        "emergency": ["eligibility", "documents", "access", "general", "deadline"],
        "asset": ["amount", "eligibility", "documents", "deadline", "access"],
    }.get(domain, ["eligibility", "amount", "access", "documents", "deadline"])
    topic = topic_cycle[int(offset or 0) % len(topic_cycle)]
    label = _topic_label_for(view, topic)
    detail = _policy_lived_detail(view, persona or {}, topic)
    if stance == "support":
        return f"{label}만 분명하면 필요한 사람에게 도움이 될 것 같아요. {detail}."
    if stance == "oppose":
        return f"{label}이 지금처럼 애매하면 현장에서 빠지는 사람이 생길 수 있어요. {detail}."
    return f"{label}을 먼저 확인해야 판단할 수 있을 것 같아요. {detail}."


def _build_reaction_messages(view, personas: dict, focus_id=None) -> list[dict]:
    """interactions가 없을 때 시민 1차 반응을 채팅 메시지처럼 보여준다."""
    items = []
    raw_reactions = (view or {}).get("reactions") or []
    if not isinstance(raw_reactions, (list, tuple)):
        return items

    for index, reaction in enumerate(raw_reactions):
        if not isinstance(reaction, dict):
            continue
        text = str(reaction.get("text") or "").strip()
        from_id = reaction.get("persona_id")
        persona = personas.get(str(from_id)) if from_id is not None else None
        stance = _normalize_stance(reaction.get("stance")) or "mixed"
        if not text or _is_failed_interaction_text(text):
            text = _fallback_reaction_text(view, persona or {}, reaction, index)
        items.append(
            {
                "type": "message",
                "round": 1,
                "index": index,
                "from_id": from_id,
                "to_id": None,
                "name": _speaker_name(persona, from_id),
                "meta": _speaker_meta(persona),
                "avatar": _avatar_for(persona or {}, stance),
                "text": text,
                "target": "초기 반응",
                "stance": stance,
                "base_stance": stance,
                "shift_before": None,
                "shift_after": None,
                "outgoing": _is_outgoing(from_id, focus_id),
            }
        )

    return items


def _build_chat_timeline(view, focus_id=None, source_messages=None) -> list[dict]:
    """view를 HTML 렌더용 타임라인으로 변환한다."""
    interactions = source_messages
    if interactions is None:
        interactions = (view or {}).get("interactions") or []
    personas = _build_persona_index(view)
    reactions = _build_reaction_index(view)
    timeline: list[dict] = []

    if isinstance(interactions, (list, tuple)):
        interactions = [
            item for item in interactions
            if isinstance(item, dict)
            and not _is_failed_interaction_text(item.get("text"))
        ]
    else:
        interactions = []

    if not interactions:
        reaction_messages = _build_reaction_messages(view, personas, focus_id)
        if reaction_messages:
            return [
                {
                    "type": "turn",
                    "round": 1,
                    "title": "정책 발표 및 시민 초기 반응",
                },
                *reaction_messages,
            ]
        return []

    for round_no, messages in _group_by_round(interactions):
        title = _turn_title(round_no, messages)
        timeline.append({"type": "turn", "round": round_no, "title": title})

        for msg_index, msg in enumerate(messages):
            text = str(msg.get("text") or "").strip()
            if not text:
                continue

            from_id = msg.get("from_id")
            to_id = msg.get("to_id")
            persona = personas.get(str(from_id)) if from_id is not None else None
            reaction = reactions.get(str(from_id)) if from_id is not None else {}
            base_stance = (
                _normalize_stance(msg.get("base_stance"))
                or _normalize_stance((reaction or {}).get("stance"))
                or "mixed"
            )
            before, after = _parse_stance_shift(msg.get("stance_shift"))
            current_stance = after or _normalize_stance(msg.get("stance")) or before or base_stance
            target = personas.get(str(to_id)) if to_id is not None else None
            target_name = _speaker_name(target, to_id) if target else "전체 채팅방"

            timeline.append(
                {
                    "type": "message",
                    "round": round_no,
                    "index": msg_index,
                    "from_id": from_id,
                    "to_id": to_id,
                    "name": _speaker_name(persona, from_id),
                    "meta": _speaker_meta(persona),
                    "avatar": _avatar_for(persona or {}, current_stance),
                    "text": text,
                    "target": target_name,
                    "stance": current_stance,
                    "base_stance": base_stance,
                    "shift_before": before,
                    "shift_after": after,
                    "influence_from": msg.get("influence_from"),
                    "influence_reason": msg.get("influence_reason"),
                    "issue_topic": msg.get("issue_topic"),
                    "outgoing": _is_outgoing(from_id, focus_id),
                }
            )

    return timeline


def _turn_title(round_no: int, messages: list[dict]) -> str:
    for msg in messages or []:
        title = msg.get("stage_title") if isinstance(msg, dict) else None
        if title:
            return str(title)
    titles = {
        1: "정책 발표 및 시민 초기 반응",
        2: "쟁점 충돌",
        3: "집단 영향 및 입장 변화",
        4: "개선 포인트 정리",
    }
    return titles.get(int(round_no or 0), "토론 정리")


def _first_sentence(text: str, limit: int = 78) -> str:
    clean = str(text or "").strip().replace("\n", " ")
    if not clean or _is_failed_interaction_text(clean):
        return ""
    first = clean.split(".")[0].strip()
    if len(first) > limit:
        return first[:limit].rstrip() + "..."
    return first


def _persona_context(persona: dict) -> str:
    demographics = persona.get("demographics") or {}
    parts = []
    age = demographics.get("age")
    occupation = demographics.get("occupation")
    housing = demographics.get("housing_type")
    if age:
        parts.append(f"{age}세")
    if occupation:
        parts.append(str(occupation))
    if housing:
        parts.append(str(housing))
    return " · ".join(parts)


def _persona_angle(persona: dict, reaction: dict) -> str:
    demographics = persona.get("demographics") or {}
    signals = persona.get("signals") or {}
    actions = reaction.get("actions") if isinstance(reaction.get("actions"), list) else []
    try:
        digital_literacy = float(signals.get("digital_literacy", 0.5))
    except (TypeError, ValueError):
        digital_literacy = 0.5
    try:
        trust = float(signals.get("government_trust", 0.5))
    except (TypeError, ValueError):
        trust = 0.5

    if digital_literacy < 0.35:
        return "온라인 신청만 있으면 저는 중간에 막힐 것 같아요. 방문해서 물어볼 곳이 같이 적혀 있어야 해요."
    if trust < 0.4:
        return "기준이 애매하면 또 말만 좋은 정책처럼 보일 수 있어서 심사 기준을 더 분명히 써줬으면 해요."
    if actions:
        return f"저는 일단 {actions[0]}부터 해볼 것 같아요."
    if "1인" in str(demographics.get("family_type") or ""):
        return "혼자 사는 사람은 서류를 다 혼자 챙겨야 하니까 절차가 단순해야 해요."
    return "조건이랑 예외를 한눈에 보이게 해주면 훨씬 덜 헷갈릴 것 같아요."


def _stable_variant(*parts) -> int:
    payload = "|".join(str(part or "") for part in parts)
    return int(hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8], 16)


def _persona_lived_detail(persona: dict, topic: str) -> str:
    demographics = persona.get("demographics") or {}
    occupation = str(demographics.get("occupation") or "")
    housing = str(demographics.get("housing_type") or "")
    marital = str(demographics.get("marital_status") or "")
    family_type = str(demographics.get("family_type") or "")
    age = demographics.get("age")
    try:
        age_no = int(age)
    except (TypeError, ValueError):
        age_no = 0

    if topic == "eligibility":
        if "고시원" in housing:
            return "고시원 계약도 인정되는지부터 확인해야 해요"
        if "기숙" in housing:
            return "기숙사나 자취 전환 같은 경우가 애매해 보여요"
        if "부모" in family_type:
            return "부모와 같이 사는 청년은 원가구 기준에서 바로 헷갈려요"
        if "자영" in occupation:
            return "사업소득은 월급처럼 딱 떨어지지 않아서 산정 기준이 궁금해요"
        if "보건" in occupation or "의료" in occupation or "간호" in occupation:
            return "직장 후배나 자녀에게 설명하려면 대상 기준이 사례로 보여야 해요"
        if "배우자" in marital or "부부" in family_type:
            return "부부가 월세로 사는 경우도 되는지 따로 써줘야 해요"
        if "IT" in occupation or "개발" in occupation:
            return "소득은 있어도 월세 부담이 큰 청년도 경계선에 걸릴 수 있어요"
        if "전세" in housing:
            return "전세나 반전세처럼 월세가 섞인 집은 어디에 해당하는지 봐야 해요"
        if "프리랜서" in occupation:
            return "소득 증빙이 들쭉날쭉한 사람은 기준에서 막힐 수 있어요"
        if "대학생" in occupation:
            return "부모 지원을 조금 받는 학생은 원가구 기준이 바로 걸려요"
        if "직장" in occupation or "계약" in occupation:
            return "월급은 있어도 월세 부담은 그대로라 경계선 기준이 중요해요"
        if "1인" in family_type and age_no and age_no <= 34:
            return "혼자 월세를 내는 청년은 대상 여부를 바로 확인하고 싶어요"
        if age_no >= 60:
            return "본인은 대상 밖이라도 자녀나 손주에게 설명할 기준이 쉬워야 해요"
        if age_no >= 45:
            return "중장년이 봐도 비대상 여부를 바로 알 수 있게 써줘야 해요"
        if age_no > 34:
            return "나이 기준에서 한 살 차이로 빠지는 사람도 생길 수 있어요"
        return "내가 대상인지 바로 판정할 수 있는 예시가 필요해요"

    if topic == "amount":
        if age_no and age_no >= 60:
            return "나는 대상이 아니어도 자녀나 손주가 실제로 얼마나 받는지가 궁금해요"
        if "월세" in housing or "원룸" in housing:
            return "매달 월세가 빠지는 사람한테는 지급 시점이 중요해요"
        if "전세" in housing:
            return "전세나 반전세처럼 월세가 섞인 경우도 설명이 필요해요"
        if "고시원" in housing:
            return "고시원비가 월세로 인정되는지가 먼저예요"
        return "금액보다 실제로 언제 받을 수 있는지가 궁금해요"

    if topic == "documents":
        if "고시원" in housing or "기숙" in housing:
            return "계약서 형태가 애매한 주거는 대체 서류가 필요해요"
        if "프리랜서" in occupation:
            return "소득 증빙 서류가 복잡하면 신청 전에 막힐 수 있어요"
        return "서류 이름만 말하면 준비 순서가 잘 안 잡혀요"

    if topic == "access":
        try:
            age_no = int(age)
        except (TypeError, ValueError):
            age_no = 0
        if age_no >= 60:
            return "온라인 화면보다 주민센터에서 바로 물어볼 수 있어야 해요"
        if "직장" in occupation or "계약" in occupation:
            return "근무 중에도 확인할 수 있게 신청 경로가 짧아야 해요"
        return "복지로와 방문 신청 중 어디부터 가야 할지 먼저 보여줘야 해요"

    if topic == "deadline":
        return "상시 접수라고 해도 예산이 얼마나 남았는지 보여줘야 해요"

    return "좋은 취지보다 내가 바로 판단할 수 있는 안내가 먼저예요"


def _policy_lived_detail(view, persona: dict, topic: str) -> str:
    """정책 분야와 시민 배경을 섞어 구체적인 생활 맥락 문장을 만든다."""
    domain = _policy_domain(view)
    demographics = persona.get("demographics") or {}
    occupation = str(demographics.get("occupation") or "")
    housing = str(demographics.get("housing_type") or "")
    family_type = str(demographics.get("family_type") or "")
    age = demographics.get("age")
    try:
        age_no = int(age)
    except (TypeError, ValueError):
        age_no = 0

    if domain == "digital":
        if topic == "access":
            return "대상자가 어르신이면 온라인보다 전화나 방문 창구가 먼저 보여야 해요"
        if topic == "amount":
            return "교육만 있는지, 기기 대여나 통신비까지 이어지는지 구분돼야 해요"
        if topic == "deadline":
            return "분기 모집이면 정원과 대기자 안내가 없을 때 바로 불안해져요"
        if topic == "documents":
            return "자녀가 대신 신청할 때 필요한 확인 절차가 따로 보여야 해요"
        return "디지털을 어려워하는 사람이 신청 과정에서 또 디지털 장벽을 만나면 안 돼요"

    if domain == "birth":
        if topic == "amount":
            return "첫째와 둘째 이상 금액, 사용처, 사용 기한을 한눈에 봐야 해요"
        if topic == "access":
            return "출생신고와 동시에 신청되는지, 따로 복지로에 들어가야 하는지 헷갈릴 수 있어요"
        if topic == "deadline":
            return "출생일 기준 1년이면 실제 마감일을 자동으로 계산해줘야 해요"
        if topic == "eligibility":
            return "보호자와 아동 주소가 다른 경우가 먼저 설명돼야 해요"
        return "아이를 막 낳은 가구는 절차를 길게 읽을 여유가 없어요"

    if domain == "emergency":
        if topic == "eligibility":
            return "실직이나 질병 같은 위기 사유가 어디까지 인정되는지 사례가 필요해요"
        if topic == "documents":
            return "긴급 상황인데 증빙을 오래 준비해야 하면 도움을 제때 못 받을 수 있어요"
        if topic == "access":
            return "먼저 129에 전화해야 하는지 주민센터로 가야 하는지 바로 보여야 해요"
        if topic == "general":
            return "사후 조사와 환수 가능성은 신청 전에 분명히 알아야 해요"
        return "상시 접수라도 처리 기간이 보이지 않으면 막막해요"

    if domain == "asset":
        if topic == "amount":
            return "매월 얼마를 넣으면 3년 뒤 얼마가 되는지 숫자로 보여줘야 해요"
        if topic == "eligibility":
            return "근로 소득과 가구 소득을 동시에 보는 기준이 경계선 청년에게 중요해요"
        if topic == "documents":
            return "근로가 끊기거나 소득이 바뀔 때 어떤 증빙을 다시 내야 하는지 봐야 해요"
        if topic == "deadline":
            return "모집 공고 기간을 놓치면 다음 기회가 언제인지 알 수 있어야 해요"
        return "계좌 개설과 복지 신청 절차가 따로 놀면 시작부터 막힐 수 있어요"

    if domain == "housing":
        return _persona_lived_detail(persona, topic)

    if topic == "eligibility":
        if age_no:
            return f"{age_no}세인 제 상황이 대상 기준에 들어가는지 바로 확인하고 싶어요"
        return "내가 대상인지 바로 확인할 수 있는 예시가 필요해요"
    if topic == "amount":
        return "지원 내용이 실제 생활에 얼마나 도움이 되는지 숫자와 기간으로 보여줘야 해요"
    if topic == "documents":
        return "필요 서류와 대체 서류가 같이 있어야 신청 전에 막히지 않아요"
    if topic == "access":
        return "온라인과 방문 중 어디로 먼저 가야 하는지 한 번에 보여야 해요"
    if topic == "deadline":
        return "신청 가능 기간과 마감 위험을 첫 화면에서 확인하고 싶어요"
    if "1인" in family_type or "혼자" in family_type:
        return "혼자 준비하는 사람도 절차를 따라갈 수 있게 안내가 단순해야 해요"
    if occupation:
        return f"{occupation}으로 일하는 사람도 시간 내 확인할 수 있게 절차가 짧아야 해요"
    if housing:
        return f"{housing} 거주자도 해당되는지 사례가 있으면 판단하기 쉬워요"
    return "정책 목적보다 내가 지금 무엇을 해야 하는지가 먼저 보여야 해요"


def _compose_initial_text(view, persona: dict, reaction: dict, influence: dict, offset: int) -> str:
    topic = influence.get("issue_topic") or _message_topic_for_policy((reaction or {}).get("text"), view)
    stance = influence.get("base_stance") or _normalize_stance((reaction or {}).get("stance")) or "mixed"
    summary = _first_sentence((reaction or {}).get("text"), 64).rstrip(".")
    if not summary:
        summary = f"{_topic_label_for(view, topic)}부터 확인해야 할 것 같아요"
    detail = _policy_lived_detail(view, persona, topic).rstrip(".")
    if stance == "support":
        templates = [
            f"{summary}. {detail}.",
            f"저는 찬성 쪽이에요. {detail}.",
            f"저한테는 이 부분이 제일 먼저 보여요. {detail}.",
            f"조건만 맞으면 바로 확인해보고 싶어요. {detail}.",
            f"정책 방향은 좋아 보여요. 다만 {detail}.",
            f"이건 실제 대상자한테 꽤 와닿을 것 같아요. {detail}.",
            f"주변에도 알려볼 만해요. {detail}.",
            f"혜택 자체는 필요해 보여요. {detail}.",
        ]
    elif stance == "oppose":
        templates = [
            f"{summary}. {detail}.",
            f"저는 이 부분이 걸려요. {detail}.",
            f"그냥 좋다고만 보긴 어려워요. {detail}.",
            f"이 부분은 먼저 짚고 가야 해요. {detail}.",
            f"신청 전에 여기서 막힐 사람이 있을 것 같아요. {detail}.",
            f"이대로 안내되면 오해가 생길 것 같아요. {detail}.",
            f"좋은 말보다 빠지는 사람을 먼저 봐야 해요. {detail}.",
            f"저는 기준이 더 분명해야 한다고 봐요. {detail}.",
        ]
    else:
        templates = [
            f"{summary}. {detail}.",
            f"아직 판단이 갈려요. {detail}.",
            f"저는 여기부터 확인하고 싶어요. {detail}.",
            f"좋은 점은 있는데 먼저 확인할 게 있어요. {detail}.",
            f"찬반보다 대상 확인이 먼저예요. {detail}.",
            f"바로 찬성이나 반대라고 말하긴 어렵네요. {detail}.",
            f"설명만 보면 아직 헷갈리는 부분이 있어요. {detail}.",
            f"정책은 좋아 보여도 실제 적용이 궁금해요. {detail}.",
        ]
    variant = int(offset or 0) % len(templates)
    return " ".join(templates[variant].replace(" .", ".").split())


def _history_count_for_persona(history: list[dict], persona_id) -> int:
    pid = str(persona_id)
    return sum(1 for msg in history if str(msg.get("from_id")) == pid)


def _message_stance(view, msg: dict) -> str:
    stance = _normalize_stance((msg or {}).get("stance"))
    if stance:
        return stance
    before, after = _parse_stance_shift((msg or {}).get("stance_shift"))
    if after or before:
        return after or before
    from_id = (msg or {}).get("from_id")
    reaction = _build_reaction_index(view).get(str(from_id)) if from_id is not None else {}
    return _normalize_stance((reaction or {}).get("stance")) or "mixed"


def _message_topic(text: str) -> str:
    raw = str(text or "")
    topic_words = {
        "eligibility": {
            "부모": 4,
            "원가구": 5,
            "무주택": 5,
            "자격": 4,
            "나이": 3,
            "소득 기준": 4,
            "대상": 2,
            "조건": 1,
            "기준": 1,
        },
        "amount": {
            "20만": 5,
            "12개월": 4,
            "월세": 4,
            "임대료": 4,
            "지원 금액": 5,
            "지원비": 4,
            "금액": 3,
            "지급": 3,
        },
        "documents": {
            "임대차": 5,
            "계약서": 5,
            "서류": 4,
            "통장": 4,
            "증빙": 4,
            "제출": 3,
            "체크리스트": 3,
        },
        "access": {
            "복지로": 5,
            "행정복지": 5,
            "주민센터": 5,
            "센터": 3,
            "온라인": 4,
            "방문": 4,
            "창구": 4,
            "신청 경로": 5,
            "신청 창구": 5,
            "신청": 1,
        },
        "deadline": {
            "예산": 5,
            "소진": 5,
            "조기": 4,
            "마감": 4,
            "상시": 4,
            "접수": 3,
            "신청 기간": 4,
        },
    }
    scores = {}
    for topic, words in topic_words.items():
        score = sum(weight for word, weight in words.items() if word in raw)
        if score:
            scores[topic] = score
    if scores:
        priority = {
            "documents": 5,
            "deadline": 4,
            "access": 3,
            "amount": 2,
            "eligibility": 1,
        }
        return max(scores, key=lambda topic: (scores[topic], priority.get(topic, 0)))
    return "general"


def _message_topic_for_policy(text: str, view=None) -> str:
    """발언 텍스트를 정책 분야까지 고려해 쟁점 키로 분류한다."""
    raw = str(text or "")
    if _is_failed_interaction_text(raw):
        return "general"
    domain = _policy_domain(view)
    domain_words = {
        "digital": {
            "amount": ("교육", "수료", "기기", "태블릿", "통신비", "실습"),
            "eligibility": ("65세", "어르신", "고령", "디지털 기기 사용", "어려움"),
            "documents": ("대리", "자녀", "위임", "확인 절차"),
            "access": ("전화", "방문", "복지관", "주민센터", "행정복지", "온라인"),
            "deadline": ("분기", "정원", "모집", "대기"),
        },
        "birth": {
            "amount": ("200만", "300만", "바우처", "국민행복카드", "사용처", "포인트"),
            "eligibility": ("출생", "아동", "보호자", "주민등록", "주소"),
            "documents": ("출생신고", "확인 절차", "카드 신청"),
            "access": ("복지로", "주민센터", "행복출산", "원스톱"),
            "deadline": ("1년", "사용 기한", "출생일", "마감"),
        },
        "emergency": {
            "amount": ("생계비", "의료비", "주거비", "가구원 수", "추가 지원"),
            "eligibility": ("위기", "실직", "질병", "휴폐업", "중위소득", "저소득"),
            "documents": ("증빙", "소득", "재산", "조사", "자료"),
            "access": ("129", "전화", "행정복지", "주민센터", "방문"),
            "deadline": ("상시", "위기 상황", "처리 기간", "접수"),
            "general": ("환수", "사후 조사"),
        },
        "asset": {
            "amount": ("저축", "매칭", "적립", "만기", "목돈", "10만"),
            "eligibility": ("근로", "사업소득", "가구 소득", "청년", "소득 기준"),
            "documents": ("소득 증빙", "근로 확인", "재직", "제출"),
            "access": ("복지로", "행정복지", "계좌", "상담"),
            "deadline": ("모집", "공고", "기간", "다음 모집"),
            "general": ("중지", "중단", "초과"),
        },
    }
    scores = {}
    for topic, words in (domain_words.get(domain) or {}).items():
        score = sum(4 for word in words if word in raw)
        if score:
            scores[topic] = score
    base = _message_topic(raw)
    if base != "general":
        scores[base] = scores.get(base, 0) + 2
    if scores:
        priority = {"documents": 5, "deadline": 4, "access": 3, "amount": 2, "eligibility": 1, "general": 0}
        return max(scores, key=lambda topic: (scores[topic], priority.get(topic, 0)))
    return base


def _topic_label(topic: str) -> str:
    return _TOPIC_LABEL.get(topic, _TOPIC_LABEL["general"])


def _topic_suggestion(topic: str) -> str:
    return _TOPIC_SUGGESTION.get(topic, _TOPIC_SUGGESTION["general"])


def _topic_problem(topic: str) -> str:
    return _TOPIC_PROBLEM.get(topic, _TOPIC_PROBLEM["general"])


def _base_reaction_stance(view, persona_id) -> str:
    reaction = _build_reaction_index(view).get(str(persona_id))
    return _normalize_stance((reaction or {}).get("stance")) or "mixed"


def _recent_group_pressure(view, history: list[dict], persona_id, window: int = 6) -> dict:
    """최근 대화에서 특정 시민에게 작용하는 집단 압력을 계산한다."""
    pid = str(persona_id)
    recent = [
        msg for msg in list(history or [])[-window:]
        if isinstance(msg, dict) and str(msg.get("from_id")) != pid
    ]
    counts = {"support": 0, "oppose": 0, "mixed": 0}
    names_by_stance = {"support": [], "oppose": [], "mixed": []}
    personas = _build_persona_index(view)
    topic_counts = {}

    for msg in recent:
        stance = _message_stance(view, msg)
        counts[stance] = counts.get(stance, 0) + 1
        from_id = msg.get("from_id")
        persona = personas.get(str(from_id)) if from_id is not None else None
        name = _speaker_name(persona, from_id)
        if name not in names_by_stance.setdefault(stance, []):
            names_by_stance[stance].append(name)
        topic = msg.get("issue_topic") or _message_topic_for_policy(msg.get("text"), view)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    if topic_counts:
        topic = max(topic_counts, key=lambda key: (topic_counts[key], key != "general"))
    elif history:
        topic = _message_topic_for_policy(history[-1].get("text"), view)
    else:
        topic = "general"

    return {
        "counts": counts,
        "names_by_stance": names_by_stance,
        "topic": topic,
    }


def _join_names(names: list[str], limit: int = 2) -> str:
    clean = [name for name in names if name]
    if not clean:
        return ""
    if len(clean) <= limit:
        return "·".join(clean)
    return "·".join(clean[:limit]) + f" 외 {len(clean) - limit}명"


def _group_influence_context(view, persona: dict, reaction: dict, history: list[dict]) -> dict:
    """초기 입장과 최근 집단 대화를 비교해 현재 입장을 정한다."""
    pid = str(persona.get("id"))
    base_stance = _normalize_stance((reaction or {}).get("stance")) or "mixed"
    pressure = _recent_group_pressure(view, history, pid)
    counts = pressure["counts"]
    current_stance = base_stance
    influence_stance = None

    if base_stance == "mixed":
        if counts["support"] >= counts["oppose"] and counts["support"] >= 1:
            current_stance = "support"
            influence_stance = "support"
        elif counts["oppose"] > counts["support"] and counts["oppose"] >= 1:
            current_stance = "oppose"
            influence_stance = "oppose"
    elif base_stance == "support":
        if counts["oppose"] >= counts["support"] and counts["oppose"] >= 2:
            current_stance = "mixed"
            influence_stance = "oppose"
    elif base_stance == "oppose":
        if counts["support"] >= counts["oppose"] and counts["support"] >= 2:
            current_stance = "mixed"
            influence_stance = "support"

    influence_from = ""
    if influence_stance:
        influence_from = _join_names(pressure["names_by_stance"].get(influence_stance, []))

    topic = pressure["topic"]
    reaction_topic = _message_topic_for_policy((reaction or {}).get("text"), view)
    speaker_count = _history_count_for_persona(history, pid)
    if reaction_topic != "general" and (
        topic == "general"
        or speaker_count % 2 == 0
        or (base_stance == "mixed" and counts["support"] == counts["oppose"])
    ):
        topic = reaction_topic
    return {
        "base_stance": base_stance,
        "current_stance": current_stance,
        "influence_stance": influence_stance,
        "influence_from": influence_from,
        "influence_reason": _topic_label_for(view, topic),
        "issue_topic": topic,
        "counts": counts,
    }


def _topic_point(topic: str, stance: str, variant: int, angle: str, summary: str, view=None) -> str:
    if view is not None and _policy_domain(view) != "housing":
        label = _topic_label_for(view, topic)
        suggestion = _topic_suggestion_for(view, topic)
        problem = _topic_problem_for(view, topic)
        support_lines = [
            f"{label}이 잘 정리되면 실제 대상자가 움직이기 쉬워요",
            f"이 정책은 {label}만 더 선명하면 취지가 살아날 것 같아요",
            f"{suggestion}이 붙으면 주변에도 설명하기 쉬워요",
            f"좋은 점은 분명해요. {label}을 먼저 보여주면 체감이 커질 거예요",
        ]
        oppose_lines = [
            f"{problem}",
            f"{label}이 흐리면 필요한 사람이 신청 전에 포기할 수 있어요",
            f"{suggestion} 없이는 현장에서 같은 질문이 반복될 것 같아요",
            f"취지는 좋아도 {label}이 정리되지 않으면 불만이 먼저 나올 수 있어요",
        ]
        mixed_lines = [
            f"{label}은 필요하지만 지금 안내만으로는 판단이 갈려요",
            f"{suggestion}이 있으면 찬반보다 실제 신청 판단이 쉬워질 것 같아요",
            f"정책 방향은 이해되는데 {label}을 더 구체적으로 봐야 해요",
            f"{problem}",
        ]
        bank = {"support": support_lines, "oppose": oppose_lines, "mixed": mixed_lines}.get(stance, mixed_lines)
        point = bank[variant % len(bank)]
        if variant % 5 == 4 and angle:
            point = angle.rstrip(".")
        return point.rstrip(".")

    points = {
        "eligibility": {
            "support": [
                "대상 기준이 맞는 청년한테는 바로 체감될 수 있어요",
                "부모랑 따로 살면서 월세 내는 사람을 잡아내는 기준은 필요해요",
                "조건표만 더 쉽게 풀면 신청할 사람은 꽤 많을 것 같아요",
                "무주택 기준이 분명하면 지원 취지가 흔들리지는 않을 거예요",
            ],
            "oppose": [
                "부모 소득까지 묶으면 실제로 독립해서 버티는 사람을 놓칠 수 있어요",
                "조건이 길수록 필요한 사람이 중간에 포기할 가능성이 커요",
                "무주택이나 소득 확인을 어떻게 하는지 먼저 보여줘야 믿을 수 있어요",
                "대상 기준이 현실 생활하고 안 맞으면 불만이 바로 나올 거예요",
            ],
            "mixed": [
                "대상 기준은 필요하지만 부모 소득까지 보는 방식은 설명이 더 필요해요",
                "조건 자체보다 내가 해당되는지 바로 확인할 수 있는 안내가 중요해요",
                "청년 지원이라는 방향은 맞는데 예외 사례가 많이 생길 것 같아요",
                "소득 기준을 쉬운 예시로 보여주면 오해가 줄 것 같아요",
            ],
        },
        "amount": {
            "support": [
                "월세는 매달 빠져나가니까 20만 원도 숨통이 트여요",
                "12개월이면 급한 시기를 버티는 데는 확실히 도움이 돼요",
                "보증금보다 매달 월세가 부담인 사람한테는 바로 와닿는 금액이에요",
                "금액이 아주 크지 않아도 고정 지출을 줄여주는 게 중요해요",
            ],
            "oppose": [
                "금액만 앞세우면 누가 받을 수 있는지 더 흐려져요",
                "20만 원이 도움은 되지만 선정 기준이 불분명하면 체감이 갈릴 거예요",
                "지원 기간이 끝난 뒤 부담이 다시 커지는 부분도 같이 봐야 해요",
                "월세가 높은 지역에서는 이 금액만으로는 부족하다는 말이 나올 수 있어요",
            ],
            "mixed": [
                "금액은 반갑지만 내가 실제로 받을 수 있는지가 먼저예요",
                "12개월 지원은 좋지만 신청 과정이 복잡하면 체감이 확 줄어요",
                "월세 부담을 줄이는 방향은 맞고, 기준 안내가 같이 쉬워야 해요",
                "금액보다 지급 시점이 늦어지지 않는지도 중요해 보여요",
            ],
        },
        "documents": {
            "support": [
                "계약서랑 통장 사본 정도면 준비 가능한 사람도 많을 거예요",
                "서류 목록이 짧고 명확하면 신청 장벽은 많이 낮아져요",
                "필수 서류만 딱 정리해주면 바로 움직일 수 있어요",
                "증빙 방식이 간단하면 행정 부담도 줄어들 것 같아요",
            ],
            "oppose": [
                "서류가 하나씩 늘어나면 바쁜 사람은 신청을 포기해요",
                "계약 형태가 애매한 사람은 서류에서 바로 막힐 수 있어요",
                "통장 사본까지 내야 한다면 개인정보 안내도 분명해야 해요",
                "제출 서류 기준이 애매하면 현장에서 민원이 많이 생길 거예요",
            ],
            "mixed": [
                "서류는 필요하지만 예시 화면이 있어야 덜 헷갈릴 것 같아요",
                "계약서가 없는 경우를 어떻게 처리하는지도 같이 알려줘야 해요",
                "제출 목록만 보지 말고 준비 순서를 같이 보여주면 좋겠어요",
                "증빙은 하되 빠지는 사람이 없도록 대체 서류 안내가 필요해요",
            ],
        },
        "access": {
            "support": [
                "복지로와 주민센터가 같이 열려 있으면 접근성은 괜찮아 보여요",
                "온라인으로 먼저 확인하고 필요하면 방문하는 흐름이면 편해요",
                "신청 창구가 두 개면 디지털에 익숙한 사람과 아닌 사람이 나뉘어도 대응돼요",
                "행정복지센터에서 안내를 받게 해두면 현장 혼란은 줄 수 있어요",
            ],
            "oppose": [
                "온라인 화면만 믿으면 중간에 막히는 사람이 분명히 생겨요",
                "방문 안내가 작게 적혀 있으면 실제로는 모르는 사람이 많을 거예요",
                "신청 경로가 복잡하면 지원이 있어도 못 쓰는 사람이 생겨요",
                "센터마다 안내가 다르면 같은 정책인데도 체감이 달라질 수 있어요",
            ],
            "mixed": [
                "온라인과 방문을 같이 두는 건 좋지만 첫 안내가 더 쉬워야 해요",
                "신청 버튼보다 내가 어디서 확인해야 하는지가 먼저 보여야 해요",
                "디지털에 익숙한 사람은 빠르게, 아닌 사람은 방문으로 이어지게 해야 해요",
                "복지로 안내와 주민센터 안내가 같은 말로 정리되면 좋겠어요",
            ],
        },
        "deadline": {
            "support": [
                "상시 접수면 준비하는 사람 입장에서는 부담이 덜해요",
                "예산이 남아 있을 때 바로 신청할 수 있다는 점은 좋아요",
                "마감 압박이 덜하면 서류를 차분히 챙길 수 있어요",
                "기간이 열려 있으면 정보가 늦게 닿은 사람도 기회가 있어요",
            ],
            "oppose": [
                "예산 소진이라는 말만 있으면 언제 끝날지 몰라 불안해요",
                "상시 접수라도 남은 예산을 보여주지 않으면 불공정하게 느껴질 수 있어요",
                "조기 마감 가능성이 있으면 안내를 더 크게 해야 해요",
                "신청 기간이 애매하면 늦게 알게 된 사람은 손해를 봐요",
            ],
            "mixed": [
                "상시 접수는 좋은데 예산 상황을 같이 보여줘야 해요",
                "기간보다 지금 신청 가능한지 확인하는 화면이 필요해요",
                "마감 가능성을 숨기지 말고 처음부터 알려주는 게 나아요",
                "접수 상태가 바뀌면 문자나 알림으로 알려주면 좋겠어요",
            ],
        },
        "general": {
            "support": [
                "정책 방향은 필요한 쪽을 보고 있다고 느껴져요",
                "월세 부담을 직접 건드린다는 점은 현실적이에요",
                "조건만 맞으면 실제 생활비에 바로 도움이 될 수 있어요",
                "청년 주거비를 따로 다룬다는 점은 의미가 있어요",
            ],
            "oppose": [
                "취지는 좋아도 빠지는 사람이 생기면 논란이 클 거예요",
                "현장 기준이 불분명하면 지원보다 불만이 먼저 나올 수 있어요",
                "정책 문장만 보면 쉬워 보여도 실제 신청은 다를 수 있어요",
                "대상과 절차가 선명하지 않으면 체감이 약할 거예요",
            ],
            "mixed": [
                "방향은 이해되지만 안내 방식이 승부처 같아요",
                "지원 자체보다 내가 해당되는지 확인하는 과정이 중요해요",
                "좋은 정책으로 보이려면 예외 상황까지 같이 설명해야 해요",
                "찬반보다 신청자가 헷갈리지 않게 만드는 게 먼저예요",
            ],
        },
    }
    bank = points.get(topic, points["general"]).get(stance, points["general"]["mixed"])
    point = bank[variant % len(bank)]
    if variant % 5 == 4 and angle:
        point = angle.rstrip(".")
    return point.rstrip(".")


def _natural_debate_line(
    *,
    stance: str,
    summary: str,
    angle: str,
    context: str,
    history_len: int,
    speaker_count: int = 0,
    previous_name: str = "",
    previous_stance: str | None = None,
    topic: str = "general",
    view=None,
) -> str:
    """반복적인 AI 말투 대신 짧은 시민 채팅 문장으로 조립한다."""
    summary = summary.rstrip(".")
    angle = angle.rstrip(".")
    context = context.strip()
    variant = history_len * 2 + speaker_count * 5
    point = _topic_point(topic, stance, variant, angle, summary, view=view)

    if not previous_name:
        openers = {
            "support": [
                f"{summary}. {point}.",
                f"저는 이 정책 찬성 쪽이에요. {point}.",
                f"{point}. 그래서 조건만 맞으면 바로 확인해볼 것 같아요.",
            ],
            "oppose": [
                f"{summary}. {point}.",
                f"저는 먼저 걸리는 부분이 있어요. {point}.",
                f"{point}. 이 부분이 정리되지 않으면 말이 나올 것 같아요.",
            ],
            "mixed": [
                f"{summary}. {point}.",
                f"좋은 점은 보이는데 아직 판단이 갈려요. {point}.",
                f"{point}. 그래서 안내가 더 쉬워야 한다고 봐요.",
            ],
        }.get(stance, [])
        line = openers[variant % len(openers)]
    elif previous_stance == stance:
        prefixes = [
            f"{previous_name}님 말 맞아요.",
            f"{previous_name}님이 말한 그 부분은 저도 비슷하게 봐요.",
            f"{previous_name}님 얘기에 이어서,",
            f"{previous_name}님 말에 저도 가까워요.",
            f"{previous_name}님이 말한 지점에서 하나 더 보태면,",
            f"{previous_name}님과 같은 쪽으로 봐요.",
        ]
        line = f"{prefixes[variant % len(prefixes)]} {point}."
    elif stance == "support":
        prefixes = [
            f"{previous_name}님, 저는 그건 다르게 봐요.",
            f"{previous_name}님 말과 반대로 저는 지원 자체가 먼저 보여요.",
            f"{previous_name}님 걱정은 알겠는데,",
            f"{previous_name}님 말만 보면 너무 조심스럽게 보는 것 같아요.",
            f"{previous_name}님 얘기대로만 판단하긴 어려워요.",
            f"{previous_name}님이 짚은 대목에서 오히려 필요성이 더 보여요.",
        ]
        line = f"{prefixes[variant % len(prefixes)]} {point}."
    elif stance == "oppose":
        prefixes = [
            f"{previous_name}님, 그 말은 조금 불안해요.",
            f"{previous_name}님, 저는 반대로 봐요.",
            f"{previous_name}님 말대로만 가면 빠지는 사람이 생길 수 있어요.",
            f"{previous_name}님이 말한 그 부분에서 저는 생각이 달라요.",
            f"{previous_name}님처럼 좋게만 보기엔 기준이 아직 걸려요.",
            f"{previous_name}님처럼 보면 편하지만 현장에서는 더 복잡할 수 있어요.",
        ]
        line = f"{prefixes[variant % len(prefixes)]} {point}."
    else:
        prefixes = [
            f"{previous_name}님 말도 맞는데 한쪽만 보긴 어려워요.",
            f"{previous_name}님 얘기를 중간에서 보면 둘 다 걸리는 지점이 있어요.",
            f"{previous_name}님이 짚은 부분은 조금 나눠서 봐야 할 것 같아요.",
            f"{previous_name}님 말처럼 찬반보다 실제 신청 과정이 더 신경 쓰여요.",
            f"{previous_name}님 말에 보태면, 지원과 기준을 같이 봐야 해요.",
            f"{previous_name}님 얘기에서 결국 확인 절차가 핵심으로 보여요.",
        ]
        line = f"{prefixes[variant % len(prefixes)]} {point}."

    return " ".join(line.replace("..", ".").split())


def _influenced_debate_line(
    *,
    base_stance: str,
    current_stance: str,
    point: str,
    influence_from: str,
    reason: str,
    variant: int,
) -> str:
    source = f"{influence_from}님 얘기를 듣다 보니" if influence_from else "다른 사람들 얘기를 듣다 보니"
    point = point.rstrip(".")
    reason_part = f"{reason} 부분"

    if base_stance == "mixed" and current_stance == "support":
        templates = [
            f"처음엔 애매했는데 {source} 찬성 쪽으로 기울어요. {reason_part}만 정리되면 {point}.",
            f"{source} 이 정책을 조금 더 긍정적으로 보게 돼요. 핵심은 {reason_part}을 쉽게 설명하는 거예요.",
            f"처음엔 판단을 못 했는데 {source} 필요성이 보이네요. {point}.",
        ]
        return templates[variant % len(templates)]
    if base_stance == "mixed" and current_stance == "oppose":
        templates = [
            f"처음엔 중립에 가까웠는데 {source} 반대 쪽으로 기울어요. {reason_part}에서 빠지는 사람이 생길 수 있어요.",
            f"{source} 걱정이 커졌어요. {reason_part}을 고치지 않으면 신청 전에 포기할 사람이 나올 것 같아요.",
            f"처음엔 괜찮아 보였는데 {source} 걸리는 점이 더 크게 보여요. {point}.",
        ]
        return templates[variant % len(templates)]
    if current_stance == "mixed":
        if base_stance == "support":
            templates = [
                f"처음엔 찬성했는데 {source} 조건부로 보게 돼요. {reason_part}을 더 분명히 해야 해요.",
                f"{source} 찬성만 하긴 어렵겠어요. {point}.",
                f"지원 취지는 동의하지만 {source} 보완이 먼저라는 생각도 들어요. {reason_part}이 핵심이에요.",
            ]
            return templates[variant % len(templates)]
        if base_stance == "oppose":
            templates = [
                f"처음엔 반대였는데 {source} 일부는 받아들일 수 있겠어요. 그래도 {reason_part}은 보완해야 해요.",
                f"{source} 무조건 반대만 하긴 어렵네요. 다만 {point}.",
                f"처음보다 조금 누그러졌어요. {source} 정책 취지는 이해되지만 {reason_part}은 남아 있어요.",
            ]
            return templates[variant % len(templates)]
    return f"{source} 생각이 조금 바뀌었어요. {point}."


def _select_debate_speaker(view, history: list[dict], stage: dict | None = None) -> dict | None:
    personas = _persona_list(view)
    reactions = _build_reaction_index(view)
    candidates = [
        p for p in personas
        if p.get("id") is not None and str(p.get("id")) in reactions
    ]
    if not candidates:
        return None

    last_id = history[-1].get("from_id") if history else None
    last_stance = None
    if last_id is not None:
        last_stance = _normalize_stance((reactions.get(str(last_id)) or {}).get("stance"))
    recent_ids = {str(m.get("from_id")) for m in history[-3:] if m.get("from_id") is not None}
    stage_round = int((stage or {}).get("round", 0) or 0)
    stage_spoken = {
        str(m.get("from_id"))
        for m in history
        if m.get("from_id") is not None
        and int(m.get("round", 0) or 0) == stage_round
    }
    has_stage_unspoken = any(
        str(persona.get("id")) not in stage_spoken
        for persona in candidates
    )
    cursor = len(history)
    counts = {
        str(persona.get("id")): _history_count_for_persona(history, persona.get("id"))
        for persona in candidates
    }

    def score(persona: dict) -> tuple:
        pid = str(persona.get("id"))
        reaction = reactions.get(pid) or {}
        stance = _normalize_stance(reaction.get("stance")) or "mixed"
        scores = reaction.get("scores") if isinstance(reaction.get("scores"), dict) else {}
        shareability = int(scores.get("shareability", 50) or 50)
        contrast = 45 if last_stance and stance != last_stance else 0
        repeat_penalty = -1000 if len(candidates) > 1 and pid == str(last_id) else 0
        stage_repeat_penalty = -900 if has_stage_unspoken and pid in stage_spoken else 0
        recent_penalty = -55 if pid in recent_ids and pid != str(last_id) else 0
        usage_penalty = -12 * counts.get(pid, 0)
        rotation = -abs((candidates.index(persona) % len(candidates)) - (cursor % len(candidates)))
        return (
            repeat_penalty + stage_repeat_penalty + recent_penalty + usage_penalty + contrast + shareability,
            rotation,
        )

    return max(candidates, key=score)


def _debate_candidates(view) -> list[dict]:
    reactions = _build_reaction_index(view)
    return [
        persona for persona in _persona_list(view)
        if persona.get("id") is not None and str(persona.get("id")) in reactions
    ]


def _debate_stage_plan(view) -> list[dict]:
    """SNS 토론을 무한 확산이 아닌 4단계 종료 구조로 계획한다."""
    persona_count = len(_debate_candidates(view))
    if persona_count <= 0:
        return []
    initial = min(persona_count, 12)
    conflict = min(6, max(2, persona_count))
    shift = min(6, max(2, persona_count))
    improvement = min(4, max(2, persona_count))
    return [
        {
            "round": 1,
            "key": "initial",
            "title": "정책 발표 및 시민 초기 반응",
            "count": initial,
        },
        {
            "round": 2,
            "key": "conflict",
            "title": "쟁점 충돌",
            "count": conflict,
        },
        {
            "round": 3,
            "key": "shift",
            "title": "집단 영향 및 입장 변화",
            "count": shift,
        },
        {
            "round": 4,
            "key": "improvement",
            "title": "개선 포인트 정리",
            "count": improvement,
        },
    ]


def _debate_stage_for_index(view, index: int) -> dict | None:
    cursor = 0
    for stage in _debate_stage_plan(view):
        next_cursor = cursor + stage["count"]
        if cursor <= index < next_cursor:
            item = dict(stage)
            item["offset"] = index - cursor
            return item
        cursor = next_cursor
    return None


def _debate_stage_limit(view) -> int:
    return sum(stage["count"] for stage in _debate_stage_plan(view))


def _select_initial_speaker(view, history: list[dict], stage: dict) -> dict | None:
    candidates = _debate_candidates(view)
    if not candidates:
        return None
    spoken = {
        str(msg.get("from_id")) for msg in history
        if isinstance(msg, dict) and int(msg.get("round", 0) or 0) == int(stage["round"])
    }
    for persona in candidates:
        if str(persona.get("id")) not in spoken:
            return persona
    return candidates[stage.get("offset", 0) % len(candidates)]


def _select_stage_speaker(view, history: list[dict], stage: dict) -> dict | None:
    if stage["key"] == "initial":
        return _select_initial_speaker(view, history, stage)
    return _select_debate_speaker(view, history, stage)


def _compose_improvement_text(
    view,
    persona: dict,
    reaction: dict,
    history: list[dict],
    influence: dict,
) -> str:
    topic = influence.get("issue_topic") or _message_topic_for_policy((reaction or {}).get("text"), view)
    suggestion = _topic_suggestion_for(view, topic)
    reason = _topic_label_for(view, topic)
    previous = history[-1] if history else None
    previous_name = ""
    if previous:
        personas = _build_persona_index(view)
        previous_id = previous.get("from_id")
        previous_name = _speaker_name(personas.get(str(previous_id)), previous_id)
    prefixes = [
        f"그럼 {reason}은 이렇게 고치면 좋겠어요.",
        f"{previous_name}님 말까지 보면 결론은 {reason} 보완 같아요." if previous_name else f"결론은 {reason} 보완 같아요.",
        f"정책 문구를 다듬는다면 {reason}부터 손봐야 해요.",
        f"토론을 정리하면 {reason}이 개선 포인트로 보여요.",
    ]
    variant = len(history) + _history_count_for_persona(history, persona.get("id"))
    return f"{prefixes[variant % len(prefixes)]} {suggestion}."


def _improvement_topic_for_offset(view, history: list[dict], offset: int) -> str:
    stats: dict[str, int] = {}
    for msg in history:
        if not isinstance(msg, dict):
            continue
        topic = msg.get("issue_topic") or _message_topic_for_policy(msg.get("text"), view)
        if topic:
            stats[topic] = stats.get(topic, 0) + 1
    if not stats:
        for reaction in (view or {}).get("reactions") or []:
            if isinstance(reaction, dict):
                topic = _message_topic_for_policy(reaction.get("text"), view)
                stats[topic] = stats.get(topic, 0) + 1
    for preferred in _preferred_topics_for_policy(view):
        stats.setdefault(preferred, 1)
    ordered = [
        topic for topic, _count in sorted(
            stats.items(),
            key=lambda item: (item[1], item[0] != "general"),
            reverse=True,
        )
    ]
    if not ordered:
        ordered = ["general"]
    return ordered[int(offset or 0) % len(ordered)]


def _compose_debate_text(
    view,
    persona: dict,
    reaction: dict,
    history: list[dict],
    *,
    influence: dict | None = None,
) -> str:
    influence = influence or {}
    base_stance = influence.get("base_stance") or _normalize_stance(reaction.get("stance")) or "mixed"
    stance = influence.get("current_stance") or base_stance
    summary = _first_sentence(reaction.get("text")) or f"{_topic_label_for(view, influence.get('issue_topic') or 'general')}을 다시 확인해 봤습니다"
    angle = _persona_angle(persona, reaction)
    context = _persona_context(persona)
    previous = history[-1] if history else None
    previous_name = ""
    previous_stance = None
    topic = influence.get("issue_topic") or _message_topic_for_policy(summary, view)
    if previous:
        personas = _build_persona_index(view)
        previous_id = previous.get("from_id")
        previous_persona = personas.get(str(previous_id)) if previous_id is not None else None
        previous_name = _speaker_name(previous_persona, previous_id)
        previous_stance = _message_stance(view, previous)
        topic = influence.get("issue_topic") or _message_topic_for_policy(previous.get("text"), view) or topic

    if base_stance != stance:
        variant = len(history) * 2 + _history_count_for_persona(history, persona.get("id")) * 5
        point = _topic_point(topic, stance, variant, angle, summary, view=view)
        return _influenced_debate_line(
            base_stance=base_stance,
            current_stance=stance,
            point=point,
            influence_from=influence.get("influence_from") or previous_name,
            reason=influence.get("influence_reason") or _topic_label_for(view, topic),
            variant=variant,
        )

    return _natural_debate_line(
        stance=stance,
        summary=summary,
        angle=angle,
        context=context,
        history_len=len(history),
        speaker_count=_history_count_for_persona(history, persona.get("id")),
        previous_name=previous_name,
        previous_stance=previous_stance,
        topic=topic,
        view=view,
    )


def _make_debate_message(view, history: list[dict]) -> dict | None:
    stage = _debate_stage_for_index(view, len(history))
    if not stage:
        return None
    speaker = _select_stage_speaker(view, history, stage)
    if not speaker:
        return None
    reactions = _build_reaction_index(view)
    pid = str(speaker.get("id"))
    reaction = reactions.get(pid) or {}
    influence = _group_influence_context(view, speaker, reaction, history)
    base_stance = influence["base_stance"]
    stance = influence["current_stance"]
    if stage["key"] in {"initial", "conflict", "improvement"}:
        stance = base_stance
    previous = history[-1] if history else None
    round_no = stage["round"]
    stance_shift = f"{base_stance}→{stance}" if base_stance != stance else None
    if stage["key"] == "initial":
        text = _compose_initial_text(
            view,
            speaker,
            reaction,
            {
                **influence,
                "current_stance": base_stance,
                "base_stance": base_stance,
            },
            stage.get("offset", 0),
        )
        to_id = None
    elif stage["key"] == "improvement":
        improvement_topic = _improvement_topic_for_offset(
            view,
            history,
            stage.get("offset", 0),
        )
        text = _compose_improvement_text(
            view,
            speaker,
            reaction,
            history,
            {
                **influence,
                "current_stance": stance,
                "issue_topic": improvement_topic,
            },
        )
        to_id = previous.get("from_id") if previous else None
    else:
        text = _compose_debate_text(view, speaker, reaction, history, influence={
            **influence,
            "current_stance": stance,
            "base_stance": base_stance,
        })
        to_id = previous.get("from_id") if previous else None
    return {
        "round": round_no,
        "from_id": pid,
        "to_id": to_id,
        "text": text,
        "stance_shift": stance_shift,
        "name": _speaker_name(speaker, pid),
        "base_stance": base_stance,
        "stance": stance,
        "influence_from": influence.get("influence_from"),
        "influence_reason": (
            _topic_label_for(view, improvement_topic)
            if stage["key"] == "improvement"
            else influence.get("influence_reason")
        ),
        "issue_topic": (
            improvement_topic
            if stage["key"] == "improvement"
            else influence.get("issue_topic")
        ),
        "stage": stage["key"],
        "stage_title": stage["title"],
    }


def _build_debate_messages(
    view,
    count: int,
    *,
    seed_history: list[dict] | None = None,
) -> list[dict]:
    """라이브 재생용 토론 메시지를 한 번에 만든다."""
    try:
        target_count = int(count)
    except (TypeError, ValueError):
        target_count = 0
    stage_limit = _debate_stage_limit(view)
    target_count = max(0, min(target_count, stage_limit))

    history = [
        item for item in list(seed_history or [])
        if isinstance(item, dict) and item.get("from_id") is not None
    ]
    while len(history) < target_count:
        msg = _make_debate_message(view, history)
        if not msg:
            break
        _ensure_unique_debate_text(msg, history, view)
        history.append(msg)
    return history[:target_count]


def _ensure_unique_debate_text(msg: dict, history: list[dict], view=None) -> None:
    """긴 라이브 토론에서 같은 문장이 반복 표시되지 않도록 보정한다."""
    used = {str(item.get("text") or "") for item in history if isinstance(item, dict)}
    text = str(msg.get("text") or "")
    if text not in used:
        return

    topic = msg.get("issue_topic") or _message_topic_for_policy(text, view)
    additions = {
        "eligibility": [
            "특히 예외 사례를 같이 보여줘야 오해가 줄 것 같아요.",
            "대상 여부를 바로 확인하는 작은 표가 있으면 좋겠어요.",
            "나이·소득·가구 기준을 따로 묻는 화면이 필요해 보여요.",
        ],
        "amount": [
            "지원 범위와 지급 시점까지 같이 알려줘야 실제 계획을 세울 수 있어요.",
            "지원 내용이 실제 생활에서 얼마나 체감되는지도 따로 봐야 해요.",
            "지원이 끝난 뒤나 조건이 바뀌는 경우도 같이 안내해야 할 것 같아요.",
        ],
        "documents": [
            "서류 이름만 쓰지 말고 예시 이미지를 붙이면 덜 막힐 거예요.",
            "증빙이 애매한 사람을 위한 대체 서류도 필요해요.",
            "체크리스트가 있으면 신청 전 포기하는 사람이 줄 것 같아요.",
        ],
        "access": [
            "복지로와 주민센터 중 어디로 가야 하는지 첫 화면에서 갈라줘야 해요.",
            "방문 신청 안내가 작게 숨어 있으면 실제로는 모르는 사람이 많아요.",
            "온라인이 어려운 사람을 위한 전화나 창구 안내도 같이 보여야 해요.",
        ],
        "deadline": [
            "남은 예산이나 접수 상태를 볼 수 있으면 불안이 줄 것 같아요.",
            "조기 마감 가능성은 작은 주석이 아니라 본문에 있어야 해요.",
            "신청 가능 상태가 바뀌면 알림을 받을 수 있으면 좋겠어요.",
        ],
        "general": [
            "이 부분은 정책 개선 탭에서 따로 문구를 고쳐볼 만해요.",
            "결국 시민이 바로 판단할 수 있는 안내가 필요해 보여요.",
            "좋은 취지보다 신청자가 막히는 지점을 먼저 보여줘야 해요.",
        ],
    }
    for addition in additions.get(topic, additions["general"]):
        candidate = f"{text} {addition}"
        if candidate not in used:
            msg["text"] = candidate
            return
    msg["text"] = f"{text} ({len(used) + 1}번째 쟁점)"


def _default_debate_count(view) -> int:
    """4단계 종료형 토론의 기본 발언 수."""
    return _debate_stage_limit(view)


def _prepare_debate_source_messages(
    view,
    stored_messages: list[dict] | None,
    *,
    live_mode: bool,
    target_count: int,
) -> list[dict] | None:
    """라이브/정지 상태에서 사용할 토론 소스를 결정한다."""
    stored = [
        item for item in list(stored_messages or [])
        if isinstance(item, dict) and item.get("from_id") is not None
    ]
    if live_mode:
        return _build_debate_messages(
            view,
            target_count,
            seed_history=stored,
        )
    return stored if stored else None


def _fallback_debate_insights(view, messages: list[dict] | None) -> dict:
    """키 없음/LLM 실패 시 쓰는 결정론 폴백 분석."""
    messages = [msg for msg in list(messages or []) if isinstance(msg, dict)]
    personas = _build_persona_index(view)
    stance_changes = []
    topic_stats: dict[str, dict] = {}

    for msg in messages:
        topic = msg.get("issue_topic") or _message_topic_for_policy(msg.get("text"), view)
        stats = topic_stats.setdefault(
            topic,
            {
                "count": 0,
                "support": 0,
                "oppose": 0,
                "mixed": 0,
                "samples": [],
            },
        )
        stats["count"] += 1
        stance = _message_stance(view, msg)
        stats[stance] = stats.get(stance, 0) + 1
        sample = str(msg.get("text") or "").strip()
        if sample and len(stats["samples"]) < 2:
            stats["samples"].append(sample)

        before, after = _parse_stance_shift(msg.get("stance_shift"))
        if before and after and before != after:
            from_id = msg.get("from_id")
            persona = personas.get(str(from_id)) if from_id is not None else None
            stance_changes.append(
                {
                    "name": _speaker_name(persona, from_id),
                    "before": before,
                    "after": after,
                    "reason": msg.get("influence_reason") or _topic_label_for(view, topic),
                    "influenced_by": msg.get("influence_from") or "집단 대화",
                    "message": sample,
                }
            )

    ranked_topics = []
    for topic, stats in sorted(
        topic_stats.items(),
        key=lambda item: (item[1]["count"], item[1].get("oppose", 0), item[0] != "general"),
        reverse=True,
    ):
        if topic == "general" and len(ranked_topics) >= 4:
            continue
        pressure = "논쟁"
        if stats.get("oppose", 0) > stats.get("support", 0):
            pressure = "불만/우려"
        elif stats.get("support", 0) > stats.get("oppose", 0):
            pressure = "수용/기대"
        ranked_topics.append(
            {
                "issue": _topic_label_for(view, topic),
                "topic": topic,
                "count": stats["count"],
                "pressure": pressure,
                "problem": _topic_problem_for(view, topic),
                "suggestion": _topic_suggestion_for(view, topic),
                "sample": stats["samples"][0] if stats["samples"] else "",
            }
        )
        if len(ranked_topics) >= 5:
            break

    return {
        "analysis_mode": "fallback",
        "stance_changes": stance_changes[:5],
        "key_issues": ranked_topics[:5],
        "problem_points": ranked_topics[:4],
        "improvement_points": ranked_topics[:4],
    }


def _normalise_llm_issue(issue: _LLMIssue, idx: int) -> dict:
    return {
        "issue": _clip_text(issue.issue, 36) or f"쟁점 {idx}",
        "topic": f"llm_{idx}",
        "count": max(1, int(issue.count or 1)),
        "pressure": issue.pressure or "논쟁",
        "problem": _clip_text(issue.problem, 180),
        "suggestion": _clip_text(issue.suggestion, 180),
        "sample": _clip_text(issue.sample, 160),
    }


def _normalise_llm_change(change: _LLMStanceChange) -> dict:
    return {
        "name": _clip_text(change.name, 28),
        "before": _normalize_stance(change.before) or "mixed",
        "after": _normalize_stance(change.after) or "mixed",
        "reason": _clip_text(change.reason, 120),
        "influenced_by": _clip_text(change.influenced_by, 40) or "집단 대화",
        "message": _clip_text(change.message, 160),
    }


@st.cache_data(show_spinner=False)
def _cached_llm_debate_insights(policy_context: str, debate_context: str, cache_key: str) -> dict:
    """정책 원문/첨부 문서/SNS 발언을 OpenAI 구조화 출력으로 분석한다."""
    del cache_key  # cache_data 키 안정화를 위한 인자. 본문에서는 쓰지 않는다.
    system = (
        "당신은 정책 토론 분석가입니다. 반드시 제공된 정책 원문/첨부 문서와 SNS 발언만 "
        "근거로 분석하세요. 정책 분야를 미리 정해진 템플릿에 끼워 맞추지 말고, 원문에서 "
        "대상·지원 내용·신청 절차·제외/유의 조건·첨부 문서의 세부 내용을 읽어 구체적인 "
        "문제점과 개선안을 도출하세요. 근거가 부족하면 일반론을 만들지 말고 '관찰'로 "
        "낮춰 쓰세요."
    )
    user = (
        "■ 정책 원문 및 첨부 문서\n"
        f"{policy_context or '(정책 원문 없음)'}\n\n"
        "■ SNS 토론 발언\n"
        f"{debate_context or '(토론 발언 없음)'}\n\n"
        "■ 요청\n"
        "1) 정책 원문/첨부 문서 기준으로 핵심 쟁점 3~5개를 뽑으세요.\n"
        "2) 각 쟁점은 일반적인 '대상/서류/신청' 표현보다 원문에 나온 실제 조건과 명칭을 쓰세요.\n"
        "3) 문제 원인, 실행안, 대표 발언을 각각 작성하세요.\n"
        "4) 시민 입장 변화가 있으면 0~5건만 작성하세요."
    )
    out: _LLMDebateInsights = structured_call(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        _LLMDebateInsights,
        temperature=0.2,
    )
    issues = [
        _normalise_llm_issue(issue, idx)
        for idx, issue in enumerate((out.key_issues or [])[:5], start=1)
        if (issue.issue or "").strip()
    ]
    changes = [
        _normalise_llm_change(change)
        for change in (out.stance_changes or [])[:5]
        if (change.name or "").strip()
    ]
    return {
        "analysis_mode": "openai",
        "verdict": _clip_text(out.verdict, 120),
        "stance_changes": changes,
        "key_issues": issues,
        "problem_points": issues[:4],
        "improvement_points": issues[:4],
    }


def _analyze_debate_insights(view, messages: list[dict] | None, *, use_llm: bool = False) -> dict:
    """토론 로그에서 입장 변화와 정책 개선 포인트를 추출한다.

    앱 렌더에서는 OpenAI 키가 있으면 정책 원문/첨부 문서 기반 LLM 분석을 우선하고,
    키가 없거나 실패하면 결정론 폴백을 사용한다. 테스트 기본값은 네트워크 호출 방지를
    위해 use_llm=False 이다.
    """
    messages = [msg for msg in list(messages or []) if isinstance(msg, dict)]
    fallback = _fallback_debate_insights(view, messages)
    if not use_llm or not has_real_key():
        return fallback

    policy_context = _policy_context_text(view)
    debate_context = _debate_context_text(view, messages)
    if not policy_context.strip() or not debate_context.strip():
        return fallback

    cache_key = hashlib.sha1(
        json.dumps(
            {"policy": policy_context, "debate": debate_context},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    try:
        llm = _cached_llm_debate_insights(policy_context, debate_context, cache_key)
        if llm.get("key_issues"):
            return llm
    except Exception as exc:
        fallback["analysis_error"] = str(exc)
    return fallback


def _can_use_llm_debate_insights(view, messages: list[dict] | None) -> bool:
    """렌더 전에 OpenAI 분석 로딩 상태를 보여줄지 판단한다."""
    messages = [msg for msg in list(messages or []) if isinstance(msg, dict)]
    if not messages or not has_real_key():
        return False
    return bool(_policy_context_text(view).strip() and _debate_context_text(view, messages).strip())


def _timeline_signature(timeline: list[dict]) -> str:
    payload = json.dumps(timeline, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _message_count(timeline: list[dict]) -> int:
    return sum(1 for item in timeline if item.get("type") == "message")


def _render_insight_panel(insights: dict | None) -> str:
    insights = insights or {}
    points = insights.get("improvement_points") or []
    changes = insights.get("stance_changes") or []
    if not points and not changes:
        return ""

    point_items = []
    for point in points[:3]:
        point_items.append(
            '<li>'
            f'<strong>{_esc(point.get("issue"))}</strong>'
            f'<span>{_esc(point.get("suggestion"))}</span>'
            f'<em>{_esc(point.get("pressure"))} · {int(point.get("count") or 0)}회 언급</em>'
            '</li>'
        )

    change_items = []
    for change in changes[:2]:
        before = _STANCE_LABEL.get(change.get("before"), "혼합")
        after = _STANCE_LABEL.get(change.get("after"), "혼합")
        change_items.append(
            '<li>'
            f'<strong>{_esc(change.get("name"))}</strong>'
            f'<span>{_esc(before)} → {_esc(after)}</span>'
            f'<em>{_esc(change.get("reason"))} · {_esc(change.get("influenced_by"))}</em>'
            '</li>'
        )

    points_html = "".join(point_items) or '<li><span>아직 충분한 개선 포인트가 없습니다.</span></li>'
    changes_html = "".join(change_items) or '<li><span>아직 뚜렷한 입장 변화가 없습니다.</span></li>'

    return f"""
    <div class="insight-panel">
      <div class="insight-column">
        <div class="insight-title">토론에서 도출된 개선 포인트</div>
        <ul>{points_html}</ul>
      </div>
      <div class="insight-column compact">
        <div class="insight-title">입장 변화</div>
        <ul>{changes_html}</ul>
      </div>
    </div>
    """


def _clip_text(value, limit: int = 92) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _render_debate_summary_html(insights: dict | None) -> str:
    """채팅방 아래에 표시할 토론 분석 요약 HTML."""
    insights = insights or {}
    issues = insights.get("key_issues") or []
    problems = insights.get("problem_points") or []
    improvements = insights.get("improvement_points") or []
    changes = insights.get("stance_changes") or []
    if not issues and not problems and not improvements and not changes:
        return ""

    total_mentions = sum(int(item.get("count") or 0) for item in issues)
    concern_mentions = sum(
        int(item.get("count") or 0)
        for item in issues
        if item.get("pressure") in {"불만/우려", "논쟁"}
    )
    top_issue = issues[0] if issues else {}
    top_issue_label = top_issue.get("issue") or "쟁점 없음"
    change_count = len(changes)
    if insights.get("verdict"):
        verdict = str(insights.get("verdict"))
    elif concern_mentions >= max(1, total_mentions * 0.45):
        verdict = "조건 설명과 신청 절차 보강이 우선입니다."
    elif change_count:
        verdict = "대화 과정에서 입장이 움직여 안내 방식 개선 효과가 큽니다."
    else:
        verdict = "큰 반발은 적지만 신청자가 바로 판단할 정보 보강이 필요합니다."

    def kpi_html() -> str:
        return f"""
  <div class="debate-summary-kpis">
    <div class="summary-kpi">
      <span>종합 판정</span>
      <strong>{_esc(verdict)}</strong>
      <p>혜택 기대와 조건 불확실성이 동시에 나타난 상태입니다.</p>
    </div>
    <div class="summary-kpi">
      <span>최우선 쟁점</span>
      <strong>{_esc(top_issue_label)}</strong>
      <p>{int(top_issue.get("count") or 0)}회 언급 · {_esc(top_issue.get("pressure") or "관찰")}</p>
    </div>
    <div class="summary-kpi">
      <span>관찰 지표</span>
      <strong>{total_mentions}개 발언 / {len(issues)}개 쟁점</strong>
      <p>입장 변화 {change_count}명 · 우려성 언급 {concern_mentions}회</p>
    </div>
  </div>
"""

    def issue_items(items: list[dict]) -> str:
        html = []
        for item in items[:4]:
            sample = _clip_text(item.get("sample"), 74)
            sample_html = f'<p>{_esc(sample)}</p>' if sample else ""
            html.append(
                "<li>"
                f'<strong>{_esc(item.get("issue"))}</strong>'
                f'<span>{int(item.get("count") or 0)}회 언급 · {_esc(item.get("pressure"))}</span>'
                f"{sample_html}"
                "</li>"
            )
        return "".join(html) or "<li><span>아직 뚜렷한 쟁점이 없습니다.</span></li>"

    def problem_items(items: list[dict]) -> str:
        html = []
        for item in items[:4]:
            html.append(
                "<li>"
                f'<strong>{_esc(item.get("issue"))}</strong>'
                f'<span>{_esc(item.get("problem"))}</span>'
                "</li>"
            )
        return "".join(html) or "<li><span>아직 정리할 문제점이 없습니다.</span></li>"

    def improvement_items(items: list[dict]) -> str:
        html = []
        for item in items[:4]:
            html.append(
                "<li>"
                f'<strong>{_esc(item.get("issue"))}</strong>'
                f'<span>{_esc(item.get("suggestion"))}</span>'
                "</li>"
            )
        return "".join(html) or "<li><span>아직 충분한 개선점이 없습니다.</span></li>"

    def change_items(items: list[dict]) -> str:
        html = []
        for item in items[:4]:
            before = _STANCE_LABEL.get(item.get("before"), "혼합")
            after = _STANCE_LABEL.get(item.get("after"), "혼합")
            reason = item.get("reason") or "집단 대화"
            html.append(
                "<li>"
                f'<strong>{_esc(item.get("name"))}</strong>'
                f'<span>{_esc(before)} → {_esc(after)}</span>'
                f'<p>{_esc(reason)}</p>'
                "</li>"
            )
        return "".join(html) or "<li><span>아직 뚜렷한 입장 변화가 없습니다.</span></li>"

    def detailed_issue_items(items: list[dict]) -> str:
        html = []
        for idx, item in enumerate(items[:4], start=1):
            sample = _clip_text(item.get("sample"), 130) or "해당 쟁점의 대표 발언이 아직 충분하지 않습니다."
            html.append(
                '<div class="issue-report-row">'
                '<div class="issue-report-head">'
                f'<strong>{idx}. {_esc(item.get("issue"))}</strong>'
                f'<span>{int(item.get("count") or 0)}회 언급 · {_esc(item.get("pressure"))}</span>'
                '</div>'
                '<div class="issue-report-grid">'
                '<div>'
                '<b>문제 원인</b>'
                f'<p>{_esc(item.get("problem"))}</p>'
                '</div>'
                '<div>'
                '<b>근거 발언</b>'
                f'<p>{_esc(sample)}</p>'
                '</div>'
                '<div>'
                '<b>실행안</b>'
                f'<p>{_esc(item.get("suggestion"))}</p>'
                '</div>'
                '</div>'
                '</div>'
            )
        return "".join(html)

    def next_action_items(items: list[dict]) -> str:
        actions = []
        for item in items[:3]:
            actions.append(
                "<li>"
                f'<strong>{_esc(item.get("issue"))}</strong>'
                f'<span>{_esc(item.get("suggestion"))}</span>'
                "</li>"
            )
        fallback_actions = [
            ("정책 원문", "신청자가 바로 판단할 수 있게 대상·금액·신청 경로를 첫 화면에 재배치"),
            ("재검증", "수정 문구로 SNS 토론을 다시 실행해 쟁점 수와 우려성 언급 변화를 비교"),
            ("게시판 반영", "토론에서 반복된 질문을 게시판 예상 질문과 자동응답 근거에 추가"),
        ]
        used_titles = {str(item.get("issue") or "") for item in items}
        target_total = max(3, min(5, len(actions) + len(fallback_actions)))
        for title, body in fallback_actions:
            if len(actions) >= target_total:
                break
            if title in used_titles:
                continue
            actions.append(
                "<li>"
                f"<strong>{_esc(title)}</strong>"
                f"<span>{_esc(body)}</span>"
                "</li>"
            )
        return "".join(actions)

    mode_label = (
        "OpenAI 정책 원문·첨부문서 분석"
        if insights.get("analysis_mode") == "openai"
        else "정책 키워드 폴백 분석"
    )

    return f"""
<style>
  .debate-summary {{
    margin-top: 18px;
    padding: 18px;
    border: 1px solid #d9dee7;
    border-radius: 8px;
    background: #ffffff;
  }}
  .debate-summary-head {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }}
  .debate-summary-head strong {{
    font-size: 1.08rem;
    color: #242938;
  }}
  .debate-summary-head span {{
    color: #687386;
    font-size: 0.86rem;
  }}
  .debate-summary-kpis {{
    display: grid;
    grid-template-columns: 1.2fr 0.9fr 1fr;
    gap: 12px;
    margin-bottom: 14px;
  }}
  .summary-kpi {{
    border: 1px solid #e4e8ef;
    border-radius: 8px;
    background: #f7f9fc;
    padding: 13px 14px;
  }}
  .summary-kpi span {{
    display: block;
    color: #687386;
    font-size: 0.78rem;
    margin-bottom: 5px;
  }}
  .summary-kpi strong {{
    display: block;
    color: #202938;
    font-size: 0.98rem;
    line-height: 1.42;
  }}
  .summary-kpi p {{
    color: #5c6575;
    font-size: 0.81rem;
    line-height: 1.45;
    margin: 6px 0 0;
  }}
  .debate-summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }}
  .debate-summary-card {{
    border: 1px solid #e4e8ef;
    border-radius: 8px;
    padding: 13px 14px;
    background: #f9fafc;
    min-width: 0;
  }}
  .debate-summary-card h4 {{
    margin: 0 0 10px;
    font-size: 0.94rem;
    color: #242938;
  }}
  .debate-summary-card ul {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 10px;
  }}
  .debate-summary-card li {{
    border-top: 1px solid #e8ebf1;
    padding-top: 9px;
  }}
  .debate-summary-card li:first-child {{
    border-top: 0;
    padding-top: 0;
  }}
  .debate-summary-card strong {{
    display: block;
    color: #1f2937;
    font-size: 0.88rem;
    margin-bottom: 3px;
  }}
  .debate-summary-card span,
  .debate-summary-card p {{
    display: block;
    color: #5c6575;
    font-size: 0.81rem;
    line-height: 1.5;
    margin: 0;
  }}
  .issue-report {{
    margin-top: 14px;
    border: 1px solid #e4e8ef;
    border-radius: 8px;
    background: #ffffff;
    overflow: hidden;
  }}
  .issue-report h4 {{
    margin: 0;
    padding: 13px 14px;
    color: #242938;
    font-size: 0.95rem;
    background: #f7f9fc;
    border-bottom: 1px solid #e4e8ef;
  }}
  .issue-report-row {{
    padding: 14px;
    border-top: 1px solid #edf0f5;
  }}
  .issue-report-row:first-of-type {{
    border-top: 0;
  }}
  .issue-report-head {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }}
  .issue-report-head strong {{
    color: #1f2937;
    font-size: 0.92rem;
  }}
  .issue-report-head span {{
    color: #687386;
    font-size: 0.8rem;
  }}
  .issue-report-grid {{
    display: grid;
    grid-template-columns: 1fr 1.1fr 1fr;
    gap: 12px;
  }}
  .issue-report-grid div {{
    background: #fbfcfe;
    border: 1px solid #edf0f5;
    border-radius: 7px;
    padding: 10px 11px;
  }}
  .issue-report-grid b {{
    display: block;
    color: #334155;
    font-size: 0.78rem;
    margin-bottom: 5px;
  }}
  .issue-report-grid p {{
    margin: 0;
    color: #5c6575;
    font-size: 0.81rem;
    line-height: 1.55;
  }}
  .next-actions {{
    margin-top: 14px;
    border: 1px solid #dbe6f6;
    border-radius: 8px;
    background: #f6f9ff;
    padding: 14px;
  }}
  .next-actions h4 {{
    margin: 0 0 10px;
    color: #1f3b63;
    font-size: 0.95rem;
  }}
  .next-actions ol {{
    margin: 0;
    padding-left: 21px;
    display: grid;
    gap: 8px;
  }}
  .next-actions li {{
    color: #334155;
    font-size: 0.84rem;
    line-height: 1.5;
  }}
  .next-actions li strong {{
    margin-right: 6px;
  }}
  .next-actions li span {{
    color: #526070;
  }}
  @media (max-width: 1100px) {{
    .debate-summary-kpis,
    .issue-report-grid {{
      grid-template-columns: 1fr;
    }}
    .debate-summary-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
  }}
  @media (max-width: 720px) {{
    .debate-summary-grid {{
      grid-template-columns: 1fr;
    }}
    .debate-summary-head {{
      display: block;
    }}
  }}
</style>
<section class="debate-summary">
  <div class="debate-summary-head">
    <strong>토론 분석 요약</strong>
    <span>{_esc(mode_label)} · SNS 대화에서 나온 쟁점과 보완 방향</span>
  </div>
  {kpi_html()}
  <div class="debate-summary-grid">
    <div class="debate-summary-card">
      <h4>주요 쟁점</h4>
      <ul>{issue_items(issues)}</ul>
    </div>
    <div class="debate-summary-card">
      <h4>드러난 문제점</h4>
      <ul>{problem_items(problems)}</ul>
    </div>
    <div class="debate-summary-card">
      <h4>개선점</h4>
      <ul>{improvement_items(improvements)}</ul>
    </div>
    <div class="debate-summary-card">
      <h4>입장 변화</h4>
      <ul>{change_items(changes)}</ul>
    </div>
  </div>
  <div class="issue-report">
    <h4>쟁점별 상세 리포트</h4>
    {detailed_issue_items(issues)}
  </div>
  <div class="next-actions">
    <h4>다음 액션</h4>
    <ol>{next_action_items(improvements)}</ol>
  </div>
</section>
"""


def _render_debate_summary(insights: dict | None) -> None:
    html = _render_debate_summary_html(insights)
    if html:
        st.markdown(html, unsafe_allow_html=True)


def _render_debate_loading_html(view, messages: list[dict] | None) -> str:
    """OpenAI 분석 대기 중 채팅 탭이 비어 보이지 않도록 표시할 상태 UI."""
    message_count = len([msg for msg in list(messages or []) if isinstance(msg, dict)])
    attached_docs = 0
    if isinstance(view, dict):
        attached_docs += len(view.get("policy_documents") or [])
    attached_docs += len(_session_policy_documents())
    source_label = f"{attached_docs}개 첨부 문서" if attached_docs else "정책 원문"

    return f"""
<style>
  .debate-loading {{
    margin-top: 14px;
    border: 1px solid #d6e1ef;
    border-radius: 8px;
    background: #f8fafc;
    color: #1f2937;
    overflow: hidden;
    box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
  }}
  .debate-loading-head {{
    display: flex;
    justify-content: space-between;
    gap: 18px;
    align-items: flex-start;
    padding: 18px 22px 14px;
    border-bottom: 1px solid #e2e8f0;
    background: #ffffff;
  }}
  .debate-loading-title {{
    display: grid;
    gap: 5px;
  }}
  .debate-loading-title strong {{
    font-size: 1.04rem;
    font-weight: 900;
    color: #111827;
  }}
  .debate-loading-title span {{
    font-size: 0.86rem;
    color: #64748b;
  }}
  .debate-loading-badge {{
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 999px;
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
    font-size: 0.78rem;
    font-weight: 900;
    white-space: nowrap;
  }}
  .debate-loading-dot {{
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: #10b981;
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.42);
    animation: debateLoadingPulse 1.25s infinite;
  }}
  .debate-loading-track {{
    height: 4px;
    background: #e5edf7;
    overflow: hidden;
  }}
  .debate-loading-track span {{
    display: block;
    width: 38%;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #2563eb, #10b981, #2563eb);
    animation: debateLoadingSweep 1.6s ease-in-out infinite;
  }}
  .debate-loading-body {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    padding: 16px 22px 20px;
  }}
  .debate-loading-step {{
    min-height: 96px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: #ffffff;
    padding: 14px;
    display: grid;
    align-content: start;
    gap: 10px;
  }}
  .debate-loading-step strong {{
    color: #111827;
    font-size: 0.9rem;
    font-weight: 900;
  }}
  .debate-loading-step span {{
    color: #64748b;
    font-size: 0.8rem;
    line-height: 1.45;
  }}
  .debate-loading-skeleton {{
    display: grid;
    gap: 7px;
    margin-top: 2px;
  }}
  .debate-loading-line {{
    height: 8px;
    border-radius: 999px;
    background: linear-gradient(90deg, #e2e8f0 0%, #f8fafc 45%, #e2e8f0 90%);
    background-size: 220% 100%;
    animation: debateLoadingShimmer 1.45s linear infinite;
  }}
  .debate-loading-line.short {{
    width: 64%;
  }}
  @keyframes debateLoadingPulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.42); }}
    72% {{ box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
  }}
  @keyframes debateLoadingSweep {{
    0% {{ transform: translateX(-105%); }}
    55% {{ transform: translateX(170%); }}
    100% {{ transform: translateX(270%); }}
  }}
  @keyframes debateLoadingShimmer {{
    0% {{ background-position: 120% 0; }}
    100% {{ background-position: -120% 0; }}
  }}
  @media (max-width: 860px) {{
    .debate-loading-head {{
      display: grid;
    }}
    .debate-loading-body {{
      grid-template-columns: 1fr;
    }}
  }}
</style>
<section class="debate-loading" aria-live="polite">
  <div class="debate-loading-head">
    <div class="debate-loading-title">
      <strong>SNS 채팅 구성 중</strong>
      <span>OpenAI가 정책 원문·첨부 문서와 시민 발언을 대조해 토론 리포트를 작성하고 있습니다.</span>
    </div>
    <div class="debate-loading-badge">
      <span class="debate-loading-dot"></span>
      분석 진행 중
    </div>
  </div>
  <div class="debate-loading-track"><span></span></div>
  <div class="debate-loading-body">
    <div class="debate-loading-step">
      <strong>정책 근거 확인</strong>
      <span>{_esc(source_label)}에서 대상, 지원 내용, 제외 조건을 읽는 중입니다.</span>
      <div class="debate-loading-skeleton">
        <div class="debate-loading-line"></div>
        <div class="debate-loading-line short"></div>
      </div>
    </div>
    <div class="debate-loading-step">
      <strong>시민 발언 정렬</strong>
      <span>{message_count}개 SNS 발언을 쟁점, 충돌, 입장 변화 흐름으로 묶고 있습니다.</span>
      <div class="debate-loading-skeleton">
        <div class="debate-loading-line"></div>
        <div class="debate-loading-line short"></div>
      </div>
    </div>
    <div class="debate-loading-step">
      <strong>개선안 작성</strong>
      <span>토론에서 드러난 문제점과 바로 실행할 보완 방향을 정리하고 있습니다.</span>
      <div class="debate-loading-skeleton">
        <div class="debate-loading-line"></div>
        <div class="debate-loading-line short"></div>
      </div>
    </div>
  </div>
</section>
"""


def _render_message(item: dict) -> str:
    outgoing = bool(item.get("outgoing"))
    side_class = " outgoing" if outgoing else ""
    align_style = ' style="justify-content: flex-end;"' if outgoing else ""
    target = item.get("target") or "전체 채팅방"
    text = _esc(item.get("text"))

    shift_before = item.get("shift_before")
    shift_after = item.get("shift_after")
    if shift_after:
        if shift_before:
            status = (
                f'입장 변화: {_stance_badge(shift_before)}'
                '<span class="arrow">→</span>'
                f'{_stance_badge(shift_after)}'
            )
        else:
            status = f'입장 변화: {_stance_badge(shift_after)}'
    else:
        status = f'현재 입장: {_stance_badge(item.get("stance"))}'

    influence = ""
    if item.get("influence_from") and item.get("influence_reason"):
        influence = (
            '<span class="influence-note">'
            f'영향: {_esc(item.get("influence_from"))} · {_esc(item.get("influence_reason"))}'
            '</span>'
        )

    return f"""
      <div class="msg-box{side_class}">
        <div class="msg-avatar">{_esc(item.get("avatar"))}</div>
        <div class="msg-content">
          <div class="msg-header"{align_style}>
            <span class="msg-name">{_esc(item.get("name"))}</span>
            <span class="msg-desc">{_esc(item.get("meta"))}</span>
          </div>
          <div class="msg-text" data-full-text="{text}">
            <span class="msg-text-body">{text}</span>
          </div>
          <div class="msg-footer"{align_style}>
            <span class="reply-target">↪ {_esc(target)}</span>
            <span class="msg-reply">{status}</span>
            {influence}
          </div>
        </div>
      </div>
    """


def _render_chat_html(
    timeline: list[dict],
    *,
    live_mode: bool = False,
    replay_nonce: int = 0,
    delay_ms: int = 650,
    char_delay_ms: int = 42,
    state_key: str = "",
    insights: dict | None = None,
) -> str:
    """채팅 타임라인을 독립 HTML로 렌더한다."""
    live_flag = "1" if live_mode else "0"
    delay_ms = max(250, min(int(delay_ms or 650), 4000))
    char_delay_ms = max(12, min(int(char_delay_ms or 42), 140))
    total = _message_count(timeline)

    parts = []
    for item in timeline:
        if item.get("type") == "turn":
            parts.append(
                '<div class="thread-turn">'
                f'<span class="turn-badge">{_esc(item.get("round"))}턴</span>'
                f'{_esc(item.get("title"))}'
                '</div>'
            )
        elif item.get("type") == "message":
            parts.append(_render_message(item))

    body = "\n".join(parts)
    if not body:
        body = '<div class="empty">표시할 대화가 없습니다.</div>'

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #e6edf3;
    }}
    .thread-shell {{
      background: #0e1117;
      border: 1px solid #30363d;
      border-radius: 8px;
      overflow: hidden;
      height: 710px;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }}
    .thread-topbar {{
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 14px 18px;
      background: #111827;
      border-bottom: 1px solid #30363d;
    }}
    .room-title {{
      font-weight: 800;
      color: #fafafa;
      font-size: 1rem;
    }}
    .room-meta {{
      color: #8b949e;
      font-size: 0.78rem;
      white-space: nowrap;
    }}
    .live-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #56d364;
      border: 1px solid rgba(86, 211, 100, 0.35);
      background: rgba(86, 211, 100, 0.08);
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 800;
    }}
    .live-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #56d364;
      box-shadow: 0 0 0 0 rgba(86, 211, 100, 0.5);
      animation: pulse 1.2s infinite;
    }}
    @keyframes pulse {{
      0% {{ box-shadow: 0 0 0 0 rgba(86, 211, 100, 0.5); }}
      70% {{ box-shadow: 0 0 0 8px rgba(86, 211, 100, 0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(86, 211, 100, 0); }}
    }}
    .thread-wrap {{
      flex: 1 1 auto;
      background: #0e1117;
      padding: 20px 25px;
      box-sizing: border-box;
      overflow-y: auto;
      scroll-behavior: smooth;
    }}
    .thread-turn {{
      font-size: 1.05rem;
      font-weight: 800;
      margin: 6px 0 25px;
      padding-bottom: 12px;
      border-bottom: 2px solid #1f242c;
      color: #fafafa;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .turn-badge {{
      background: #388bfd;
      color: #fff;
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 0.78rem;
      font-weight: 800;
    }}
    .msg-box {{
      display: flex;
      gap: 15px;
      margin-bottom: 24px;
      opacity: 1;
      transform: translateY(0);
    }}
    .msg-avatar {{
      font-size: 1.55rem;
      background: #1f242c;
      border-radius: 14px;
      width: 48px;
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      border: 1px solid #30363d;
      box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }}
    .msg-content {{
      flex: 1;
      min-width: 0;
      max-width: 82%;
    }}
    .msg-header {{
      margin-bottom: 6px;
      display: flex;
      align-items: baseline;
      gap: 10px;
    }}
    .msg-name {{
      font-weight: 800;
      font-size: 0.95rem;
      color: #fafafa;
      white-space: nowrap;
    }}
    .msg-desc {{
      font-size: 0.76rem;
      color: #8b949e;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .msg-text {{
      font-size: 0.96rem;
      line-height: 1.55;
      background: #1f242c;
      padding: 15px 18px;
      border-radius: 0 12px 12px 12px;
      border: 1px solid #30363d;
      color: #e6edf3;
      word-break: keep-all;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }}
    .msg-box.outgoing {{
      flex-direction: row-reverse;
    }}
    .msg-box.outgoing .msg-text {{
      background: rgba(56, 139, 253, 0.08);
      border-color: rgba(56, 139, 253, 0.4);
      border-radius: 12px 0 12px 12px;
    }}
    .msg-footer {{
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      font-size: 0.82rem;
    }}
    .reply-target {{
      color: #8b949e;
    }}
    .influence-note {{
      color: #79c0ff;
      font-weight: 700;
    }}
    .msg-reply {{
      display: inline-flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      font-weight: 800;
      color: #c9d1d9;
    }}
    .stance-support,
    .stance-oppose,
    .stance-neutral {{
      display: inline-flex;
      align-items: center;
      padding: 4px 8px;
      border-radius: 4px;
      line-height: 1.1;
    }}
    .stance-support {{
      color: #56d364;
      background: rgba(86, 211, 100, 0.1);
    }}
    .stance-oppose {{
      color: #f85149;
      background: rgba(248, 81, 73, 0.1);
    }}
    .stance-neutral {{
      color: #e3b341;
      background: rgba(227, 179, 65, 0.1);
    }}
    .arrow {{
      color: #8b949e;
      font-weight: 700;
    }}
    .typing-indicator {{
      display: none;
      align-items: center;
      gap: 7px;
      color: #8b949e;
      font-size: 0.86rem;
      padding: 5px 0 2px 63px;
    }}
    .typing-dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #8b949e;
      animation: blink 1.2s infinite;
    }}
    .typing-dot:nth-child(2) {{ animation-delay: 0.16s; }}
    .typing-dot:nth-child(3) {{ animation-delay: 0.32s; }}
    @keyframes blink {{
      0%, 80%, 100% {{ opacity: 0.25; transform: translateY(0); }}
      40% {{ opacity: 1; transform: translateY(-2px); }}
    }}
    .empty {{
      color: #8b949e;
      padding: 40px 0;
      text-align: center;
    }}
    .insight-panel {{
      flex: 0 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(220px, 0.65fr);
      gap: 12px;
      padding: 12px 18px;
      background: #0f1723;
      border-bottom: 1px solid #30363d;
    }}
    .insight-column {{
      min-width: 0;
    }}
    .insight-title {{
      color: #fafafa;
      font-size: 0.82rem;
      font-weight: 900;
      margin-bottom: 7px;
    }}
    .insight-panel ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 6px;
    }}
    .insight-panel li {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      color: #c9d1d9;
      font-size: 0.76rem;
      line-height: 1.35;
    }}
    .insight-panel li strong {{
      color: #79c0ff;
      white-space: nowrap;
    }}
    .insight-panel li span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .insight-panel li em {{
      color: #8b949e;
      font-style: normal;
      white-space: nowrap;
    }}
    .thread-shell[data-live="1"] .thread-turn,
    .thread-shell[data-live="1"] .msg-box {{
      display: none;
      opacity: 0;
      transform: translateY(12px);
      transition: opacity 0.25s ease-out, transform 0.25s ease-out;
    }}
    .thread-shell[data-live="1"] .thread-turn.show,
    .thread-shell[data-live="1"] .msg-box.show {{
      display: flex;
      opacity: 1;
      transform: translateY(0);
    }}
    @media (max-width: 720px) {{
      .thread-shell {{ height: 650px; }}
      .thread-wrap {{ padding: 16px 14px; }}
      .msg-content {{ max-width: 86%; }}
      .msg-desc {{ display: none; }}
      .room-meta {{ display: none; }}
      .insight-panel {{
        grid-template-columns: 1fr;
      }}
      .insight-panel li {{
        grid-template-columns: auto minmax(0, 1fr);
      }}
      .insight-panel li em {{
        grid-column: 2;
      }}
    }}
  </style>
</head>
<body>
  <!-- replay:{replay_nonce} -->
  <div class="thread-shell" data-live="{live_flag}" data-delay="{delay_ms}" data-char-delay="{char_delay_ms}" data-state-key="{_esc(state_key)}">
    <div class="thread-topbar">
      <div class="room-title">SNS 정책 전파 채팅방</div>
      <div class="room-meta">
        {'<span class="live-pill"><span class="live-dot"></span>LIVE</span>' if live_mode else ''}
        메시지 {total}개
      </div>
    </div>
    <div class="thread-wrap" id="threadWrap">
      {body}
      <div class="typing-indicator" id="typingIndicator">
        <span>다음 시민이 입력 중</span>
        <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
      </div>
    </div>
  </div>
  <script>
    (function() {{
      const shell = document.querySelector('.thread-shell');
      const wrap = document.getElementById('threadWrap');
      const typing = document.getElementById('typingIndicator');
      const live = shell && shell.dataset.live === '1';
      const delay = Number(shell && shell.dataset.delay || 650);
      const charDelay = Number(shell && shell.dataset.charDelay || 42);
      const stateKey = shell && shell.dataset.stateKey;
      const items = Array.from(document.querySelectorAll('.thread-turn, .msg-box'));

      function scrollBottom() {{
        if (wrap) wrap.scrollTop = wrap.scrollHeight;
      }}

      function sleep(ms) {{
        return new Promise((resolve) => window.setTimeout(resolve, ms));
      }}

      function readState() {{
        if (!stateKey) return null;
        try {{
          const raw = window.localStorage.getItem(stateKey);
          return raw ? JSON.parse(raw) : null;
        }} catch (err) {{
          return null;
        }}
      }}

      function writeState(itemIndex, charIndex, done) {{
        if (!stateKey) return;
        try {{
          window.localStorage.setItem(stateKey, JSON.stringify({{
            itemIndex,
            charIndex,
            done: Boolean(done),
            total: items.length
          }}));
        }} catch (err) {{}}
      }}

      async function typeMessage(box, itemIndex, startCharIndex = 0) {{
        const body = box.querySelector('.msg-text-body');
        const textEl = box.querySelector('.msg-text');
        if (!body || !textEl) return;
        const fullText = textEl.dataset.fullText || body.textContent || '';
        const chars = Array.from(fullText);
        const startIndex = Math.max(0, Math.min(Number(startCharIndex || 0), chars.length));
        body.textContent = chars.slice(0, startIndex).join('');
        for (let charIndex = startIndex; charIndex < chars.length; charIndex += 1) {{
          const ch = chars[charIndex];
          body.textContent += ch;
          scrollBottom();
          writeState(itemIndex, charIndex + 1, false);
          await sleep(charDelay);
        }}
      }}

      function restoreFrozenState() {{
        const saved = readState();
        const hasProgress = saved && Number.isFinite(saved.itemIndex);
        if (!hasProgress || saved.done || saved.total !== items.length) {{
          items.forEach((item) => item.classList.add('show'));
          return;
        }}

        const visibleIndex = Math.max(-1, Math.min(Number(saved.itemIndex), items.length - 1));
        items.forEach((item, index) => {{
          if (index <= visibleIndex) {{
            item.classList.add('show');
          }} else {{
            item.style.display = 'none';
          }}
        }});

        const active = items[visibleIndex];
        if (active && active.classList.contains('msg-box')) {{
          const body = active.querySelector('.msg-text-body');
          const textEl = active.querySelector('.msg-text');
          const fullText = textEl ? (textEl.dataset.fullText || '') : '';
          const chars = Array.from(fullText);
          const charIndex = Math.max(0, Math.min(Number(saved.charIndex || chars.length), chars.length));
          if (body && charIndex < chars.length) {{
            body.textContent = chars.slice(0, charIndex).join('');
          }}
        }}
      }}

      if (!live) {{
        restoreFrozenState();
        if (typing) typing.style.display = 'none';
        scrollBottom();
        return;
      }}

      function resumeLiveState() {{
        const saved = readState();
        if (!saved || saved.done || saved.total !== items.length || !Number.isFinite(saved.itemIndex)) {{
          return null;
        }}
        const activeIndex = Math.max(0, Math.min(Number(saved.itemIndex), items.length - 1));
        const activeCharIndex = Math.max(0, Number(saved.charIndex || 0));
        items.forEach((item, index) => {{
          const body = item.querySelector('.msg-text-body');
          const textEl = item.querySelector('.msg-text');
          const fullText = textEl ? (textEl.dataset.fullText || '') : '';
          const chars = Array.from(fullText);
          if (index < activeIndex) {{
            item.classList.add('show');
            if (body) body.textContent = fullText;
          }} else if (index === activeIndex) {{
            item.classList.add('show');
            if (body) body.textContent = chars.slice(0, Math.min(activeCharIndex, chars.length)).join('');
          }} else {{
            item.classList.remove('show');
            if (body) body.textContent = '';
          }}
        }});
        scrollBottom();
        return {{
          itemIndex: activeIndex,
          charIndex: activeCharIndex
        }};
      }}

      const resumed = resumeLiveState();
      if (!resumed) {{
        writeState(-1, 0, false);
        items.forEach((item) => {{
          item.classList.remove('show');
          const body = item.querySelector('.msg-text-body');
          if (body) body.textContent = '';
        }});
      }}

      async function playLive() {{
        if (typing) typing.style.display = 'none';
        const startItemIndex = resumed ? resumed.itemIndex : 0;
        for (let itemIndex = startItemIndex; itemIndex < items.length; itemIndex += 1) {{
          const item = items[itemIndex];
          const startCharIndex = resumed && itemIndex === startItemIndex ? resumed.charIndex : 0;
          item.classList.add('show');
          writeState(itemIndex, startCharIndex, false);
          scrollBottom();
          if (item.classList.contains('msg-box')) {{
            if (typing) typing.style.display = 'flex';
            await typeMessage(item, itemIndex, startCharIndex);
            if (typing) typing.style.display = 'none';
            await sleep(delay);
          }} else {{
            await sleep(220);
          }}
        }}
        if (typing) typing.style.display = 'none';
        writeState(items.length - 1, 0, true);
        scrollBottom();
      }}

      playLive();
    }})();
  </script>
</body>
</html>"""


def _render_chat_frame(html: str) -> None:
    """독립 HTML을 iframe srcdoc으로 렌더한다."""
    payload = base64.b64encode(str(html or "").encode("utf-8")).decode("ascii")
    st.iframe(f"data:text/html;charset=utf-8;base64,{payload}", height=730)


def _default_focus_id(view):
    personas = _persona_list(view)
    return str(personas[0].get("id")) if personas and personas[0].get("id") is not None else None


def _debate_state_key(sig: str, focus_id) -> str:
    focus = str(focus_id or "none")
    return f"{_DEBATE_KEY}_{sig}_{focus}"


def render_chat_tab(view):
    """전파 채팅방 탭 본체."""
    if view is None:
        st.info("아직 시뮬레이션 결과가 없어요. 먼저 정책을 입력하고 시뮬레이션을 실행해 주세요.")
        return

    st.subheader("SNS 채팅방")

    personas = _persona_list(view)
    persona_options = [
        str(persona.get("id"))
        for persona in personas
        if persona.get("id") is not None
    ]
    persona_index = _build_persona_index(view)

    raw_sig = hashlib.sha1(
        json.dumps(
            {
                "policy": (view or {}).get("policy", ""),
                "personas": persona_options,
                "reactions": [
                    {
                        "id": r.get("persona_id"),
                        "stance": r.get("stance"),
                        "text": r.get("text"),
                    }
                    for r in ((view or {}).get("reactions") or [])
                    if isinstance(r, dict)
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]

    default_focus = _default_focus_id(view)
    if persona_options:
        current_focus = st.session_state.get(f"{_FOCUS_KEY}_{raw_sig}", default_focus)
        if current_focus not in persona_options:
            current_focus = default_focus
        focus_id = st.selectbox(
            "오른쪽 기준 시민",
            persona_options,
            index=persona_options.index(current_focus) if current_focus in persona_options else 0,
            format_func=lambda pid: _speaker_name(persona_index.get(str(pid)), pid),
            key=f"{_FOCUS_KEY}_{raw_sig}",
        )
    else:
        focus_id = None

    debate_key = _debate_state_key(raw_sig, focus_id)
    st.session_state.setdefault(debate_key, [])
    debate_messages = st.session_state[debate_key]
    default_debate_count = _default_debate_count(view)
    min_debate_count = min(default_debate_count, max(4, len(_debate_candidates(view))))

    c1, c2, c3, c4, c5, c6 = st.columns([0.9, 1.05, 1.05, 1.05, 0.9, 0.9])
    with c1:
        live_mode = st.toggle("라이브 모드", value=False, key=f"{_LIVE_KEY}_{raw_sig}")
    with c2:
        debate_count = st.slider(
            "토론 길이",
            min_value=min_debate_count,
            max_value=max(min_debate_count, default_debate_count),
            value=default_debate_count,
            step=1,
            key=f"{_DEBATE_KEY}_stage_count_{raw_sig}",
        )
    with c3:
        char_delay = st.slider(
            "글자 입력 간격",
            min_value=18,
            max_value=90,
            value=45,
            step=3,
            disabled=not live_mode,
        )
    with c4:
        reply_gap = st.slider(
            "답변 간격",
            min_value=0.3,
            max_value=2.5,
            value=0.9,
            step=0.1,
            disabled=not live_mode,
        )
    with c5:
        if st.button("다음 발언", width="stretch", disabled=live_mode):
            msg = _make_debate_message(view, debate_messages)
            if msg:
                debate_messages.append(msg)
                st.session_state[debate_key] = debate_messages
                st.rerun()
    with c6:
        if st.button("토론 초기화", width="stretch"):
            st.session_state[debate_key] = []
            st.rerun()

    source_messages = _prepare_debate_source_messages(
        view,
        debate_messages,
        live_mode=live_mode,
        target_count=debate_count,
    )
    if live_mode and source_messages is not None and source_messages != debate_messages:
        st.session_state[debate_key] = source_messages
        debate_messages = source_messages

    timeline = _build_chat_timeline(
        view,
        focus_id=focus_id,
        source_messages=source_messages,
    )
    if not timeline:
        st.info("표시할 시민 반응이나 전파 메시지가 없습니다. 시뮬레이션을 다시 실행해 주세요.")
        return
    analysis_messages = source_messages
    if not analysis_messages:
        analysis_messages = _build_debate_messages(view, default_debate_count)

    sig = _timeline_signature(timeline)
    replay_key = f"{_REPLAY_KEY}_{sig}"
    st.session_state.setdefault(replay_key, 0)

    html = _render_chat_html(
        timeline,
        live_mode=live_mode,
        replay_nonce=st.session_state[replay_key],
        delay_ms=int(reply_gap * 1000),
        char_delay_ms=int(char_delay),
        state_key=f"miri-chat:{raw_sig}:{focus_id or 'none'}:{sig}",
    )
    _render_chat_frame(html)

    summary_slot = st.empty()
    if _can_use_llm_debate_insights(view, analysis_messages or []):
        summary_slot.markdown(
            _render_debate_loading_html(view, analysis_messages or []),
            unsafe_allow_html=True,
        )

    insights = _analyze_debate_insights(view, analysis_messages or [], use_llm=True)
    summary_html = _render_debate_summary_html(insights)
    if summary_html:
        summary_slot.markdown(summary_html, unsafe_allow_html=True)
    else:
        summary_slot.empty()
