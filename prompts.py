# -*- coding: utf-8 -*-
"""
prompts.py — 한글 프롬프트 빌더 모음

미리랩(정책 반응 시뮬레이터)에서 OpenAI 구조화 출력을 호출하기 위한
chat messages 를 조립한다. 세 가지 단계가 있다.

- build_react_messages   : 한 시민(페르소나)이 정책에 1차 반응
- build_interact_messages : 다른 시민들의 반응 요약(digest)을 보고 2차 상호작용
- build_aggregate_messages: 분석가가 전체 반응을 집계해 요약/쉬운글/개선안 작성

각 함수는 [{'role':'system','content':..},{'role':'user','content':..}] 형태의
리스트를 반환한다. 네트워크 호출/로직 없이 순수 문자열 조립만 수행한다.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# 내부 헬퍼: 페르소나 dict 에서 사람이 읽기 좋은 텍스트 조각을 만든다.
# (state.py 의 Persona 계약을 그대로 따르되, 키가 없어도 죽지 않게 .get 사용)
# ---------------------------------------------------------------------------

# 인구통계 항목의 한글 라벨 매핑
_DEMO_LABELS = {
    "sex": "성별",
    "age": "나이",
    "marital_status": "결혼 상태",
    "family_type": "가구 형태",
    "housing_type": "주거 형태",
    "education_level": "학력",
    "occupation": "직업",
    "district": "거주 시군구",
    "province": "거주 광역시·도",
}

# 인구통계를 출력할 순서 (계약상 주요 항목)
_DEMO_ORDER = [
    "sex", "age", "marital_status", "family_type", "housing_type",
    "education_level", "occupation", "district", "province",
]


def _demographics_text(persona: dict) -> str:
    """인구통계 dict 를 '항목: 값' 줄 목록 문자열로 변환한다."""
    demo = persona.get("demographics") or {}
    lines = []
    for key in _DEMO_ORDER:
        value = demo.get(key)
        if value is None or value == "":
            continue
        label = _DEMO_LABELS.get(key, key)
        lines.append(f"- {label}: {value}")
    # 정의되지 않은 추가 항목이 있으면 뒤에 덧붙인다.
    for key, value in demo.items():
        if key in _DEMO_ORDER:
            continue
        if value is None or value == "":
            continue
        lines.append(f"- {key}: {value}")
    if not lines:
        return "- (제공된 인구통계 정보 없음)"
    return "\n".join(lines)


def _signals_text(persona: dict) -> str:
    """상황 신호(signals) dict 를 부드러운 서술 문장으로 바꾼다."""
    signals = persona.get("signals") or {}
    parts = []

    # 디지털 활용 능력 (0~1)
    dl = signals.get("digital_literacy")
    if isinstance(dl, (int, float)):
        if dl >= 0.75:
            parts.append("스마트폰이나 인터넷 같은 디지털 기기를 아주 능숙하게 다루는 편입니다.")
        elif dl >= 0.45:
            parts.append("디지털 기기를 무리 없이 쓰는 보통 수준입니다.")
        elif dl >= 0.2:
            parts.append("디지털 기기에 다소 서툴러 익숙하지 않은 편입니다.")
        else:
            parts.append("디지털 기기 사용을 매우 어려워하고 거의 익숙하지 않습니다.")

    # 소득 수준 (문자열)
    income = signals.get("income_level")
    if income:
        parts.append(f"소득 수준은 대체로 '{income}'에 해당합니다.")

    # 정부 신뢰도 (0~1)
    trust = signals.get("government_trust")
    if isinstance(trust, (int, float)):
        if trust >= 0.7:
            parts.append("정부 정책과 행정에 대한 신뢰가 높은 편입니다.")
        elif trust >= 0.4:
            parts.append("정부에 대해 반신반의하는 중립적인 태도를 보입니다.")
        else:
            parts.append("정부 정책에 대한 불신이 강하고 회의적인 편입니다.")

    # 사회 연결망 (목록)
    network = signals.get("social_network")
    if isinstance(network, (list, tuple)) and len(network) > 0:
        joined = ", ".join(str(x) for x in network)
        parts.append(f"평소 가깝게 교류하는 사람들은 {joined} 등입니다.")

    if not parts:
        return "- (특기할 만한 상황 신호 정보 없음)"
    return " ".join(parts)


def _persona_brief(persona: dict) -> str:
    """인물 요약(description + persona_text)을 합쳐 한 덩어리로 만든다."""
    description = (persona.get("description") or "").strip()
    persona_text = (persona.get("persona_text") or "").strip()
    chunks = []
    if description:
        chunks.append(description)
    if persona_text:
        chunks.append(persona_text)
    if not chunks:
        return "(인물 배경 설명 없음)"
    return "\n\n".join(chunks)


def _short_intro(persona: dict) -> str:
    """상호작용 단계에서 쓸 한 줄짜리 간단 인물 소개."""
    name = persona.get("name") or persona.get("id") or "한 시민"
    demo = persona.get("demographics") or {}
    bits = []
    if demo.get("age"):
        bits.append(f"{demo.get('age')}")
    if demo.get("occupation"):
        bits.append(f"{demo.get('occupation')}")
    if demo.get("district"):
        bits.append(f"{demo.get('district')} 거주")
    desc = (persona.get("description") or "").strip()
    head = f"{name}"
    if bits:
        head += "(" + ", ".join(str(b) for b in bits) + ")"
    if desc:
        # 설명이 너무 길면 앞부분만 사용
        snippet = desc.replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "…"
        head += " — " + snippet
    return head


def _metrics_text(metrics: dict) -> str:
    """집계 단계에서 metrics dict 를 '항목: 값' 줄 목록으로 변환한다."""
    if not metrics:
        return "- (집계 수치 없음)"
    lines = []
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1단계: 정책에 대한 1차 반응
# ---------------------------------------------------------------------------

def build_react_messages(persona: dict, policy: str, grounded: bool = True) -> list:
    """
    한 시민(페르소나)이 정책 원문을 읽고 보이는 1차 반응을 요청하는 messages.

    grounded=True  : 인물 정보(요약/인구통계/상황신호)를 모두 주입한 실험군
    grounded=False : 배경 정보를 제거한 ablation 대조군
    """
    system = (
        "당신은 대한민국의 한 시민입니다. 인물 정보에 완전히 몰입해 그 사람의 "
        "말투·지식수준·관심사로 정책에 반응하세요.\n\n"
        "■ 가장 중요한 원칙 — 현실적으로 판단할 것:\n"
        "실제 시민은 정책을 들으면 '나한테 이득인가'만 보지 않고, 본능적으로 현실성을 "
        "함께 따집니다. 이 정책이 실현 가능한가, 재원은 어디서 나오는가, 물가·증세·재정·"
        "형평성 같은 부작용이 결국 내 삶에 어떻게 돌아오는가, 지나치게 좋게 들리는 공약은 "
        "아닌가(의심). 본인의 처지에서 이 현실 감각을 가지고 반응하세요. 단, 합리적이고 "
        "실현 가능한 정책까지 무조건 냉소하지는 말고, 무리하거나 비현실적인 정책일수록 "
        "우려·불신이 커지도록 균형 있게 판단하세요.\n\n"
        "점수는 그 사람 입장에서 0~100으로. 반드시 지정된 구조화 형식으로만 답하세요."
    )

    policy_text = (policy or "").strip()

    if grounded:
        brief = _persona_brief(persona)
        demo = _demographics_text(persona)
        sig = _signals_text(persona)
        user = (
            "■ 인물 요약\n"
            f"{brief}\n\n"
            "■ 인구통계\n"
            f"{demo}\n\n"
            "■ 상황 신호\n"
            f"{sig}\n\n"
            "■ 정책 원문\n"
            f"{policy_text}\n\n"
            "■ 요청\n"
            "위 인물의 입장에서 이 정책에 대해 다음을 작성하세요.\n"
            "1) 입장: 찬성(support) / 반대(oppose) / 혼합(mixed) 중 하나를 고르세요.\n"
            "2) 반응: 그 사람의 말투로 한두 문단의 솔직한 반응을 쓰세요.\n"
            "3) 점수(각 0~100, 그 사람 기준): "
            "이해도(understanding, 정책을 얼마나 이해했는가), "
            "수혜 가능성(benefit, 본인이 혜택을 받을 가능성), "
            "신청 의향(intent, 실제로 신청·참여할 의향), "
            "불만도(dissatisfaction, 정책에 대한 불만·우려·불안 — 본인 손해뿐 아니라 "
            "실현 가능성·부작용에 대한 걱정 포함), "
            "공유 가능성(shareability, 주변에 알리고 공유할 가능성).\n"
            "4) 예상 행동(actions): 이 사람이 실제로 취할 법한 구체적 행동을 목록으로."
        )
    else:
        # ablation 대조군: 인물 정보를 제거하고 평범한 시민으로 가정
        user = (
            "당신은 특별한 배경 정보가 없는 평범한 대한민국 시민입니다.\n\n"
            "■ 정책 원문\n"
            f"{policy_text}\n\n"
            "■ 요청\n"
            "평범한 시민의 입장에서 이 정책에 대해 다음을 작성하세요.\n"
            "1) 입장: 찬성(support) / 반대(oppose) / 혼합(mixed) 중 하나를 고르세요.\n"
            "2) 반응: 솔직한 반응을 한두 문단으로 쓰세요.\n"
            "3) 점수(각 0~100): "
            "이해도(understanding), 수혜 가능성(benefit), 신청 의향(intent), "
            "불만도(dissatisfaction, 불만·우려·불안 — 실현 가능성·부작용 걱정 포함), "
            "공유 가능성(shareability).\n"
            "4) 예상 행동(actions): 실제로 취할 법한 구체적 행동을 목록으로."
        )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 2단계: 다른 시민들 반응을 보고 상호작용
# ---------------------------------------------------------------------------

def build_interact_messages(persona: dict, policy: str, digest: str) -> list:
    """
    한 시민이 다른 시민들의 반응 요약(digest)을 보고, 자신의 사회 연결망을
    고려해 짧게 반응하고 (있다면) 입장 변화를 표시하도록 요청하는 messages.
    """
    system = (
        "당신은 대한민국의 한 시민입니다. 같은 정책에 대한 다른 시민들의 반응 "
        "요약을 보았습니다. 당신의 사회 연결망(평소 영향을 주고받는 사람들)을 "
        "고려해 한두 문장으로 반응하세요. 만약 다른 사람의 말 때문에 생각이나 "
        "입장이 바뀌었다면 그 변화를 분명히 표시하세요. 반드시 지정된 구조화 "
        "형식으로만 답하세요."
    )

    intro = _short_intro(persona)
    policy_line = (policy or "").strip().replace("\n", " ")
    # 정책 한 줄: 너무 길면 앞부분만
    if len(policy_line) > 160:
        policy_line = policy_line[:160] + "…"

    digest_text = (digest or "").strip() or "(다른 시민들의 반응 요약 없음)"

    user = (
        "■ 당신(인물)\n"
        f"{intro}\n\n"
        "■ 다른 시민들의 반응 요약\n"
        f"{digest_text}\n\n"
        "■ 정책 한 줄 소개\n"
        f"{policy_line}\n\n"
        "■ 요청\n"
        "1) 위 반응들을 보고 당신이 보일 한두 문장의 반응을 쓰세요.\n"
        "2) 입장이 바뀌었다면 바뀐 입장(support/oppose/mixed)을, 그대로면 변화 없음을 표시하세요.\n"
        "3) 누구(어떤 사람)의 말을 참고했는지 밝히세요."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 3단계: 전체 집계 → 분석가 요약/쉬운글/개선안
# ---------------------------------------------------------------------------

def build_aggregate_messages(policy: str, metrics: dict, digest: str) -> list:
    """
    정책 분석가가 시민 반응 집계(metrics)와 반응 요약(digest)을 보고
    갈등/합의 요약, 쉬운글 변환, 구체적 개선안을 작성하도록 요청하는 messages.
    """
    system = (
        "당신은 숙련된 정책 분석가입니다. 시민 반응 집계 결과를 바탕으로 "
        "(1) 어디서 갈등이 생기고 어디서 합의가 이루어지는지 요약하고, "
        "(2) 정책 원문을 누구나 이해할 수 있는 쉬운 글로 다시 풀어 쓰고, "
        "(3) 시민 반응에 근거한 구체적이고 실행 가능한 개선안을 제시합니다. "
        "반드시 지정된 구조화 형식으로만 답하세요."
    )

    policy_text = (policy or "").strip()
    metrics_text = _metrics_text(metrics or {})
    digest_text = (digest or "").strip() or "(시민 반응 요약 없음)"

    user = (
        "■ 정책 원문\n"
        f"{policy_text}\n\n"
        "■ 반응 집계 수치(metrics)\n"
        f"{metrics_text}\n\n"
        "■ 시민 반응 요약(digest)\n"
        f"{digest_text}\n\n"
        "■ 요청\n"
        "1) 요약: 시민들 사이의 갈등 지점과 합의 지점을 균형 있게 정리하세요.\n"
        "2) 쉬운 글: 정책 원문을 어려운 용어 없이 누구나 이해할 수 있는 쉬운 글로 바꾸세요.\n"
        "3) 개선안: 시민 반응에 근거한 구체적이고 실행 가능한 정책 개선안을 목록으로 제시하세요."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 4단계: 미리 마을 — 정책 시행 후 시간 경과별 주민의 삶
# ---------------------------------------------------------------------------

def _reaction_text(reaction: Optional[dict]) -> str:
    """주민의 1차 반응(react 단계 결과)을 마을 시뮬 프롬프트용 블록으로 만든다.

    인생극장이 '시민 반응'과 같은 출발점을 갖게 하는 grounding(슬라이스 A-2). reaction
    이 없으면 빈 문자열(블록 생략). 점수·텍스트는 그 사람이 스스로 매긴 1차 인상이며,
    이후 6개월 궤적이 이 지점에서 자연스럽게 이어지도록 모델에 함께 전달한다.
    """
    if not reaction:
        return ""
    stance_kr = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}.get(
        (reaction.get("stance") or "").strip(), "혼합"
    )
    # 개행 제거 + 섹션 마커(■) 중화: 자유 서술이 프롬프트 섹션 경계를 흉내내 모델을
    # 혼란시키지 않도록(방어 심층). 인용은 시민의 말일 뿐 지시가 아님.
    txt = (reaction.get("text") or "").strip().replace("\n", " ").replace("■", "·")
    if len(txt) > 200:
        txt = txt[:200].rstrip() + "…"
    sc = reaction.get("scores") or {}

    def _s(key):
        v = sc.get(key)
        return v if isinstance(v, (int, float)) else "?"

    # actions 는 list 계약이나 _reaction_text 는 공용 빌더라 방어한다:
    # 리스트/튜플이 아니면(문자열 등) 글자 단위 분해되지 않게 단일 항목으로 감싼다.
    raw_actions = reaction.get("actions")
    if isinstance(raw_actions, (list, tuple)):
        acts = list(raw_actions)
    elif raw_actions:
        acts = [raw_actions]
    else:
        acts = []
    act = ", ".join(str(a) for a in acts[:4])

    lines = [
        "■ 이 주민의 1차 반응 (시뮬 시작점 — 이 입장·심정에서 6개월을 이어가세요)",
        f"- 입장: {stance_kr}",
    ]
    if txt:
        lines.append(f'- 한 말: "{txt}"')
    lines.append(
        f"- 스스로 매긴 점수: 수혜 가능성 {_s('benefit')} / 신청 의향 {_s('intent')} / "
        f"이해도 {_s('understanding')} / 불만 {_s('dissatisfaction')} (각 0~100)"
    )
    if act:
        lines.append(f"- 예상 행동: {act}")
    return "\n".join(lines) + "\n\n"


def build_village_messages(
    persona: dict,
    policy: str,
    history: str,
    step_label: str,
    grounded: bool = True,
    space_menu: str = "",
    reaction: Optional[dict] = None,
) -> list:
    """가상 마을 주민 1명이 '이 시점'에 어떻게 살아가는지 묘사하도록 요청.

    history  : 지금까지 시점들의 한 줄 요약 누적(연속성 유지용).
    step_label: 이번 시점 라벨(예: "시행 3개월 후").
    grounded : True 면 인물 정보를 주입(실험군), False 면 익명 주민(ablation 대조군).
    space_menu: 마을 장소(정책 접근 채널) 메뉴 문자열(graph/spaces.space_menu_text()).
                비면 장소 선택 안내를 생략한다.
    """
    system = (
        "당신은 사회 시뮬레이션 작가입니다. 가상 마을 '미리 마을'의 한 주민이 특정 "
        "정책 시행 뒤 시간이 흐르며 실제로 어떻게 살아가는지를, 그 사람의 처지에 충실하게 "
        "구체적으로 묘사합니다. 과장 없이 현실적으로, 그 사람의 특징(나이·직업·지역·디지털 "
        "능력·소득·정부 신뢰)이 정책 체감에 그대로 반영되게 하세요. 정책 정보는 '어느 장소에 "
        "닿느냐'에 따라 전해집니다. 그 사람이 현실적으로 닿을 수 있는 장소를 골라야 하며, "
        "어디에도 닿지 못하면 정책을 모른 채(unaware) 집에 머뭅니다. 정책을 모르거나 신청에 "
        "실패할 수도 있습니다. 주민의 '1차 반응'(입장·심정·점수)이 주어지면 그 지점을 "
        "출발점으로 삼아 이야기가 거기서 자연스럽게 이어지게 하세요. "
        "반드시 지정된 구조화 형식으로만 답하세요."
    )

    policy_text = (policy or "").strip()
    hist_text = (history or "").strip() or "(아직 이전 기록 없음 — 정책 시행 직후입니다.)"

    if grounded:
        brief = _persona_brief(persona)
        demo = _demographics_text(persona)
        sig = _signals_text(persona)
        person_block = (
            "■ 주민 정보\n"
            f"{brief}\n\n"
            "■ 인구통계\n"
            f"{demo}\n\n"
            "■ 상황 신호\n"
            f"{sig}\n\n"
        )
    else:
        person_block = (
            "■ 주민 정보\n"
            "(배경 정보가 주어지지 않은 평범한 마을 주민입니다.)\n\n"
        )

    # 장소 메뉴 블록(주어졌을 때만). 각 장소는 정책 접근 채널을 뜻한다.
    if (space_menu or "").strip():
        places_block = (
            "■ 마을 장소(정책 접근 채널) — 이 주민이 닿을 만한 곳을 하나 고르세요\n"
            f"{space_menu.strip()}\n\n"
        )
        place_item = (
            "1) 장소(place): 이번 시점에 이 주민이 정책과 관련해 실제로 닿은 장소를 "
            "위 목록의 key 중 하나로 고르세요. 그 사람의 디지털 능력·나이·거동·연결망에 "
            "비춰 현실적인 곳이어야 합니다. 어디에도 닿지 못하면 home 을 고르고 unaware 로 두세요.\n"
        )
    else:
        places_block = ""
        place_item = ""

    # 1차 반응 블록(A-2 grounding) — grounded 일 때만, reaction 이 주어지면.
    reaction_block = _reaction_text(reaction) if grounded else ""

    user = (
        f"{person_block}"
        "■ 정책\n"
        f"{policy_text}\n\n"
        f"{reaction_block}"
        f"{places_block}"
        "■ 지금까지의 삶 (이전 시점 요약)\n"
        f"{hist_text}\n\n"
        f"■ 이번 시점: {step_label}\n\n"
        "■ 요청\n"
        "이 시점에서 이 주민의 삶을 다음으로 묘사하세요.\n"
        f"{place_item}"
        "2) 경로·계기(reached_via): 이 주민이 이 정책을 이번 시점에 어떻게/누구를 통해 "
        "알게 되거나 신청에 닿았는지 한 줄로 쓰세요(예: 딸이 대신 알려줌, 동료 입소문, "
        "복지사 안내, 주민센터 공지문, 직접 검색). 어느 경로로도 닿지 못했으면 그 사실을 "
        "그대로 쓰세요. 그 사람의 디지털 능력·연결망·거동에 비춰 현실적인 경로여야 합니다.\n"
        "3) 행동·사건(action): 이 기간 동안 이 사람이 이 정책과 관련해(또는 무관하게) "
        "실제로 한 행동과 겪은 일을, 고른 장소·경로와 자연스럽게 이어지게 2~4문장으로 쓰세요.\n"
        "4) 정책 관여 상태(policy_status): unaware(정책을 끝까지 알지도 못함) / "
        "aware(알게 됨) / applied(신청함) / received(수령·혜택 받음) / "
        "blocked(알거나 신청했으나 요건·서류·절차에 막혀 못 받고 포기) 중 이번 시점의 단계.\n"
        "   ★ 상태는 되돌아가지 않습니다: 한 번 aware 이상이 되면 다시 unaware 로 갈 수 "
        "없습니다. 신청·시도했다가 서류·요건 때문에 포기·실패하면 unaware 가 아니라 "
        "blocked 입니다. unaware 는 정책을 처음부터 끝까지 몰랐던 경우에만 쓰세요. "
        "(이전 시점 상태에서, 그리고 닿은 장소·경로에서 자연스럽게 이어지게)\n"
        "5) 막힌 지점(barrier): 신청·접근이 막혔다면(blocked) 정확히 어디서 막혔는지 "
        "한 줄로 쓰세요(예: 온라인 본인인증 단계, 소득 요건 초과, 서류 미비, 거동 불편으로 방문 불가). "
        "막히지 않았으면 빈 문자열로 두세요.\n"
        "6) 경제적 여유(economic, 0~100)와 심리적 안정·만족(wellbeing, 0~100)을 "
        "이번 시점 기준으로.\n"
        "7) 한 줄 요약(note): 이번 시점을 한 문장으로."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
