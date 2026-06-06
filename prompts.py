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

# ── 2026-06-06 react 전면 재설계 ─────────────────────────────────────────
# 원칙: 프롬프트는 무대만 깐다(인물·기사·형식). 판단 방법 지시는 0줄.
#   - 판단의 원천 = 인물 카드(데이터셋의 상세 서사 전부) — "판단은 데이터에서".
#   - 출력 분포가 마음에 안 들 때 지시문을 덧대는 것(패치) 금지. 데이터로 해결.
#   - '조향'(반응 공간을 좁히는 지시)은 금지, '허용'(공간을 넓히는 지시)은 절제.
# 구버전의 "현실적으로 판단하라" 공통 체크리스트는 24명 전원에게 같은 계산기를
# 배포해 만장일치 쏠림(재난 92:0, 종부세 0:100)을 만들었다 — 폐기.

# 소득 코드(영/한 혼용) → 자연어 표현
_INCOME_KO = {
    "low": "빠듯한", "mid": "먹고살 만한", "high": "넉넉한",
    "저소득": "빠듯한", "중간소득": "먹고살 만한", "고소득": "넉넉한",
}

# 인물 카드 서사 섹션: (meta 키, 섹션 제목) — 값이 있는 것만 출력.
# '삶'(persona 요약)은 persona_text 폴백이 있어 별도 처리.
_CARD_SECTIONS = [
    ("professional_persona", "일"),
    ("skills_and_expertise", "할 줄 아는 것"),
    ("cultural_background", "살아온 배경"),
    ("family_persona", "가족"),
    ("career_goals_and_ambitions", "꿈과 목표"),
    ("hobbies_and_interests", "관심사와 일상"),
    ("sports_persona", "운동"),
    ("arts_persona", "문화·예술 취향"),
    ("travel_persona", "여행"),
    ("culinary_persona", "음식"),
]


def _digital_sentence(dl) -> str:
    """digital_literacy(0~1) → 생활 문장. 값이 없으면 빈 문자열."""
    if not isinstance(dl, (int, float)):
        return ""
    if dl >= 0.75:
        return "스마트폰이나 인터넷 같은 디지털 기기를 아주 능숙하게 다룹니다."
    if dl >= 0.45:
        return "디지털 기기를 무리 없이 쓰는 보통 수준입니다."
    if dl >= 0.2:
        return "디지털 기기에 다소 서툴러 익숙하지 않은 편입니다."
    return "디지털 기기 사용을 매우 어려워하고 거의 익숙하지 않습니다."


def _card_header(persona: dict) -> str:
    """인물 카드 헤더 한 줄: 이름 — 나이·성별 · 결혼 · 직업 · 지역."""
    demo = persona.get("demographics") or {}
    name = (persona.get("name") or "").strip() or "이름 미상"
    age = demo.get("age")
    head_bits = []
    if age:
        head_bits.append(f"{age}세 {demo.get('sex') or ''}".strip())
    for key in ("marital_status", "occupation"):
        v = (demo.get(key) or "").strip()
        if v:
            head_bits.append(v)
    province = (demo.get("province") or "").strip()
    district = (demo.get("district") or "").strip()
    # 데이터셋 district 는 "경상북-예천군" 형태 — 광역 접두를 떼고 표시
    if "-" in district:
        district = district.split("-")[-1]
    region = " ".join(v for v in (province, district) if v)
    if region:
        head_bits.append(region)
    return f"{name} — " + " · ".join(head_bits) if head_bits else name


def _persona_card(persona: dict) -> str:
    """[이 사람] 인물 카드 — 데이터셋의 상세 서사를 전부 꺼내 주입한다(L1).

    값이 없는 섹션은 헤더째 생략한다(서사가 없는 mock 페르소나는
    ■ 삶 + ■ 형편으로 자연 축약). 가짜 신호였던 government_trust
    (uuid 해시 노이즈 — 전원에게 같은 '반신반의' 문장을 주입하던 균질화 장치)는
    넣지 않는다. signals 의 키 자체는 다른 모듈이 쓰므로 데이터는 유지.
    """
    demo = persona.get("demographics") or {}
    meta = persona.get("meta") or {}
    signals = persona.get("signals") or {}
    header = _card_header(persona)

    lines = [
        "[이 사람]",
        "(아래는 남이 정리해 둔 소개입니다. 당신의 말투는 이 소개글의 문체가 "
        "아니라, 이 사람이 평소 하는 말입니다.)",
        "",
        header,
    ]

    # ■ 삶 — meta.persona(원문) 우선, 없으면 persona_text(구 캐시/mock 호환)
    life = (meta.get("persona") or persona.get("persona_text") or "").strip()
    if life:
        lines += ["", "■ 삶", life]

    # 나머지 서사 섹션 — 있는 것만
    for key, title in _CARD_SECTIONS:
        v = (meta.get(key) or "").strip()
        if v:
            lines += ["", f"■ {title}", v]

    # ■ 형편 — 생활의 사실들(인구통계 잔여 + 소득 + 디지털 + 어울리는 사람들)
    facts = []
    base_bits = []
    for key, label in (("family_type", "가구"), ("housing_type", "사는 곳")):
        v = (demo.get(key) or "").strip()
        if v:
            base_bits.append(f"{label}: {v}")
    edu = (demo.get("education_level") or "").strip()
    if edu:
        major = (meta.get("bachelors_field") or "").strip()
        if major in ("해당없음", "해당 없음", "없음"):
            major = ""
        base_bits.append(f"학력: {edu}" + (f"({major})" if major else ""))
    mil = (meta.get("military_status") or "").strip()
    # '비현역/해당없음'은 정보가 아니라 소음(특히 여성) — 유의미한 상태만 표시
    if mil and mil not in ("해당없음", "해당 없음", "비현역"):
        base_bits.append(f"병역: {mil}")
    if base_bits:
        facts.append("- " + " / ".join(base_bits))
    income_ko = _INCOME_KO.get((signals.get("income_level") or "").strip())
    if income_ko:
        facts.append(f"- 형편이 {income_ko} 편입니다.")
    dl_line = _digital_sentence(signals.get("digital_literacy"))
    if dl_line:
        facts.append(f"- {dl_line}")
    network = signals.get("social_network")
    if isinstance(network, (list, tuple)) and network:
        facts.append("- 평소 어울리는 사람들: " + ", ".join(str(x) for x in network))
    if facts:
        lines += ["", "■ 형편"] + facts

    return "\n".join(lines)


def _persona_card_brief(persona: dict) -> str:
    """interact 용 축약 인물 카드 — 헤더 + 삶 요약 + 형편 한 줄.

    interact 의 본문은 '남들의 댓글'이라, 풀카드(~1.9천자)를 넣으면 자기 서사가
    digest 를 묻어버린다 — 핵심만 줄여 주입한다.
    """
    meta = persona.get("meta") or {}
    signals = persona.get("signals") or {}

    lines = ["[이 사람]", _card_header(persona)]
    life = (meta.get("persona") or persona.get("persona_text") or "").strip()
    if life:
        lines.append(life)
    bits = []
    income_ko = _INCOME_KO.get((signals.get("income_level") or "").strip())
    if income_ko:
        bits.append(f"형편이 {income_ko} 편")
    dl_line = _digital_sentence(signals.get("digital_literacy"))
    if dl_line:
        bits.append(dl_line.rstrip("."))
    if bits:
        lines.append("(" + " · ".join(bits) + ")")
    return "\n".join(lines)


# L0 — 최상위 시스템(실험군). 판단 지시 0줄: 몰입·무지 허용·입말만.
_REACT_SYSTEM_GROUNDED = (
    "당신은 [이 사람]에 소개된 바로 그 사람입니다.\n"
    "답변은 정해진 틀에 담되, 틀 안의 내용은 전부 이 사람의 것입니다.\n\n"
    "- 판단은 이 사람의 삶에서 나옵니다 — 살아온 배경, 하는 일, 형편, 가족, 꿈,\n"
    "  관심사, 그리고 그 삶에서 생긴 세상에 대한 평소 생각까지.\n"
    "  평론가나 조사원의 기준이 아니라 이 사람의 기준입니다.\n"
    "- 이 사람이 모를 법한 것은 모릅니다. 모르는 용어는 모르는 대로 말하고,\n"
    "  관심 밖의 일에는 시큰둥할 수도 있습니다.\n"
    "- 어느 쪽으로든, 그 사람답기만 하면 됩니다.\n"
    "- 말은 평소 그 사람이 하는 말 그대로. 잘 정리하지도, 꾸미지도 마세요.\n"
    "  짧고 무덤덤한 반응도 반응입니다. 나이·지역·직업을 말투로 연기하지 마세요.\n"
    "  사투리는 일부러 쓰지도, 일부러 감추지도 않습니다."
)

# L0 — ablation 대조군: 인물 참조 없이 무대·형식 규칙만 동일하게.
# (구버전은 system 의 "인물 정보에 완전히 몰입" 문장이 인물 정보 없는 대조군에도
#  남아 있었다 — 단일 변인(카드 유무) 실험으로 복원.)
_REACT_SYSTEM_ABLATION = (
    "당신은 대한민국의 한 시민입니다.\n"
    "답변은 정해진 틀에 담되, 틀 안의 내용은 당신 자신의 것입니다.\n\n"
    "- 말은 평소 쓰는 입말 그대로. 잘 정리하지도, 꾸미지도 마세요.\n"
    "  짧고 무덤덤한 반응도 반응입니다."
)


# ── 여론조사 설문 (단일 소스) ───────────────────────────────────────────────
# 5축 점수의 측정 도구. LLM 은 선택지 토큰만 고르고(graph.nodes.SurveyModel),
# 0~100 점수 변환은 코드가 한다(graph.nodes.survey_to_scores + SURVEY_SCORE_MAP).
#
# 왜 설문인가 (2026-06-06, 갭 원자료로 실증):
#   구버전 "그 마음을 숫자로 옮기기만 하세요"는 점수를 '반응문 분위기 번역'으로
#   격하시켜 정서 후광이 전 축에 번졌다 — 비대상 노인이 청년 정책에 benefit 70,
#   intent 57 (구 프롬프트에선 15/11). 문항을 명시적으로 묻면 모델은 맞게 답한다
#   (반응문에 "우리 세대는 해당 없는데"가 이미 나옴). 또한 갭 실험의 현실 앵커가
#   전부 여론조사라, 같은 형식으로 물어야 같은 단위로 비교된다.
# ⚠️ 문항·선택지·매핑은 측정 도구다 — 갭 실험 전후 비교를 위해 함부로 바꾸지 말 것.
SURVEY_ITEMS = [
    # eligibility = 응답 분기(skip logic): 효과 문항(benefit/intent)보다 먼저
    # '내가 대상인가'를 답하게 한다. 생성 순서상 자기 위치를 먼저 박아야
    # 정서 후광(긍정 기분 → 전 문항 2번째 선택지 서수 매칭)이 끊긴다
    # (2026-06-06 스모크: 라벨 앵커만으론 비대상 노인 some_help 잔존 → 분기 도입).
    # scored=False — Scores 로 변환하지 않는 보조 측정(자가인식 원본만 저장).
    # 부수 가치: 자가인식 vs 결정론 자격(is_target)의 어긋남 = '대상 기준 혼란' 재료.
    {
        "field": "eligibility",
        "scored": False,
        "question": "귀하가 이 정책의 지원·적용 대상에 해당한다고 보십니까?",
        "options": [
            ("target", "내가 대상이다", None),
            ("partial", "일부 조건만 해당되거나 애매하다", None),
            ("not_target", "나는 대상이 아니다", None),
            ("unsure", "잘 모르겠다", None),
        ],
    },
    {
        "field": "understanding",
        "question": "이 정책 내용을 얼마나 이해하셨습니까?",
        "options": [
            ("well", "잘 이해했다", 90),
            ("mostly", "대체로 이해했다", 65),
            ("partly", "일부만 이해했다", 35),
            ("barely", "거의 이해하지 못했다", 10),
        ],
    },
    # household_note = 주관식 프로브: benefit/intent 직전에 '우리 집과 무슨
    # 상관인지'를 말로 먼저 쓰게 한다(text→stance 교정과 동일 원리 — 말이 먼저,
    # 선택은 그 말에서). eligibility 토큰 하나로는 '찬성 기분 → 전 문항 2번째
    # 선택지' 끌개가 안 끊겼다(2026-06-06 스모크 2차: 비대상 3명 전원
    # not_target 답하고도 some_help/probably 동일 템플릿).
    {
        "field": "household_note",
        "scored": False,
        "open": True,
        "question": "(주관식) 이 정책이 귀하 집과는 어떤 상관이 있습니까? 한두 문장으로.",
        "options": [],
    },
    # benefit/intent 선택지에 '우리 집/나' 주어를 박은 이유(2026-06-06 스모크):
    # 주어 없는 라벨("도움이 된다")은 '청년들한테 도움이 된다'는 3자 호감과
    # 문구가 그대로 겹쳐 비대상자가 some_help 를 골랐다 — 자기 기준 앵커로 차단.
    {
        "field": "benefit",
        "question": "이 정책이 시행되면 귀하와 귀하 가구의 살림에 어떤 영향을 줄 것 같습니까?",
        "options": [
            ("big_help", "우리 집 살림에 큰 도움이 된다", 100),
            ("some_help", "우리 집 살림에 다소 도움이 된다", 75),
            ("no_effect", "우리 집 살림에는 별다른 영향이 없다", 50),
            ("some_harm", "우리 집 살림에 다소 손해다", 25),
            ("big_harm", "우리 집 살림에 크게 손해다", 0),
        ],
    },
    {
        "field": "intent",
        "question": "시행되면 귀하께서 직접 신청하거나 이용(참여)하실 생각이 있으십니까?",
        "options": [
            ("surely", "내가 반드시 신청(이용)할 것이다", 100),
            ("probably", "내가 아마 신청(이용)할 것이다", 75),
            ("unsure", "잘 모르겠다", 50),
            ("probably_not", "아마 하지 않을 것이다", 25),
            ("no_need", "나는 신청·이용할 일이 없다", 0),
        ],
    },
    {
        "field": "dissatisfaction",
        "question": "이 정책에 대해 불만스러운 점이 있으십니까?",
        "options": [
            ("very", "매우 불만이다", 100),
            ("somewhat", "다소 불만이다", 70),
            ("not_much", "별로 불만 없다", 30),
            ("none", "전혀 불만 없다", 0),
        ],
    },
    {
        "field": "shareability",
        "question": "이 정책 이야기를 주변 분들과 나누실 것 같습니까?",
        "options": [
            ("often", "자주 이야기할 것 같다", 100),
            ("sometimes", "기회가 되면 할 것 같다", 65),
            ("rarely", "별로 안 할 것 같다", 35),
            ("never", "전혀 안 할 것 같다", 0),
        ],
    },
]

# {field: {token: score}} — survey_to_scores 가 쓰는 결정론 변환표.
# scored=False 문항(eligibility)은 제외 — Scores 5축만 변환한다.
SURVEY_SCORE_MAP = {
    it["field"]: {tok: score for tok, _label, score in it["options"]}
    for it in SURVEY_ITEMS
    if it.get("scored", True)
}


def _survey_lines() -> str:
    """SURVEY_ITEMS → 과제 프롬프트의 설문 문항 블록(토큰+한글 선택지)."""
    lines = []
    for it in SURVEY_ITEMS:
        if it.get("open"):  # 주관식 — 선택지 없음
            lines.append(f"   - {it['field']}: {it['question']}")
            continue
        opts = " / ".join(f"{tok}({label})" for tok, label, _score in it["options"])
        lines.append(f"   - {it['field']}: \"{it['question']}\"\n     {opts}")
    return "\n".join(lines)


def _react_task(policy_text: str) -> str:
    """L2 — react 과제 프레임. 항목 순서 = 생성 순서(반응문 먼저, 입장은 거기서).

    점수 칸은 '반응문 분위기 번역'이 아니라 여론조사 설문 응답(SURVEY_ITEMS 참고).
    숫자는 LLM 이 만지지 않는다 — 선택지 토큰만 고르고 변환은 코드가.
    """
    return (
        "[오늘]\n"
        "뉴스에서 이런 기사를 봤습니다.\n\n"
        "[기사 내용]\n"
        f"{policy_text}\n\n"
        "기사를 얼마나 꼼꼼히 읽을지는 당신에게 달렸습니다 — 관심 밖이면\n"
        "제목과 앞부분만 보고 넘기는 것도 자연스럽습니다.\n\n"
        "[기록]\n"
        "가까운 사람이 \"이거 어떻게 생각해?\" 하고 물었습니다.\n"
        "1) 반응(text): 거기에 답한다 치고, 평소 말투로. 존댓말이 아니어도 되고,\n"
        "   한 마디로 끝나도 되고 길어져도 됩니다.\n"
        "2) 입장(stance): 방금 한 말을 굳이 하나로 고르면 — support(찬성) /\n"
        "   oppose(반대) / mixed(반반·글쎄·관심 없음)\n\n"
        "그날 저녁, 짧은 설문에 응하게 됐습니다. 응답은 완전히 익명으로 처리되어\n"
        "누가 어떻게 답했는지 아무도 알 수 없습니다 — 듣기 좋게 답할 필요도,\n"
        "체면을 차릴 필요도 없이 속마음 그대로 답하면 됩니다.\n"
        "문항은 각각 별개의 질문이고, 모두 귀하(당신 자신과 당신 집) 기준입니다 —\n"
        "아까 한 말의 분위기를 그대로 옮기지 말고, 문항 하나하나 따로 읽고 답합니다.\n"
        "3) 기울기(lean): \"찬성과 반대, 둘 중 하나만 골라야 한다면?\" —\n"
        "   support / oppose / none(그래도 못 고르겠음)\n"
        "4) 설문(survey): 각 문항에 선택지 하나로 답합니다.\n"
        f"{_survey_lines()}\n\n"
        "전화를 끊고, 일상으로 돌아갑니다.\n"
        "5) 행동(actions): 실제로 할 법한 행동 목록. 아무것도 안 할 것 같으면 그렇게 적기.\n\n"
        "밤이 되고, 혼자 남았습니다.\n"
        "6) 속내(behavior): 아무도 안 보는 머릿속 — 이 정책 앞에서 실제로 어떻게\n"
        "   움직일 생각인지. 곧이곧대로 신청(이용)하거나 무시하는 사람이 대부분이지만,\n"
        "   사람에 따라서는 요건의 틈을 찾아보거나(편법), 자격·서류를 꾸며볼까 하거나\n"
        "   (부정수급), 불만을 민원·항의·공론화로 옮기기도 합니다. 이 사람이 정말\n"
        "   그럴 법한 처지일 때만 솔직하게 적으세요 — 멋있으라고 지어내지 않습니다.\n"
        "   '무엇을 하려는지' 수준으로만 적고, 구체적인 위조·회피 요령은 적지 않습니다.\n"
        "   - behavior_text: 그 속내 한두 문장 (특별한 속내가 없으면 빈 문자열)\n"
        "   - behavior_tag: 행동에 붙일 짧은 이름표 — 자유롭게\n"
        "     (예: 위장 전입 검토 / 가족 명의 계약 / 집단 민원 / 온라인 공론화. 없으면 빈 문자열)\n"
        "   - behavior_class: comply(그대로 신청·이용) / workaround(합법적 틈새·편법 활용)\n"
        "     / exploit(자격·서류를 꾸미는 부정수급 시도) / complain(민원·항의·공론화)\n"
        "     / inaction(아무것도 안 함)"
    )


def _disposition_block(cast: dict) -> str:
    """[속사정] 블록 — 캐스팅 패스(DESIGN §9)가 발현시킨 인물에게만 주입한다.

    조향이 아니라 '허용'에 머문다: 일탈을 지시하지 않고, 이 사람의 처지에서
    그런 생각이 스칠 수 있음을 인물 정보의 일부로 알려줄 뿐이다. 할지 말지,
    어디까지 갈지는 — 다른 모든 판단과 마찬가지로 — 그 사람이 정한다.
    """
    tag = (cast.get("tag") or "").strip()
    rationale = (cast.get("rationale") or "").strip().replace("\n", " ").replace("■", "·")
    lines = ["", "■ 속사정"]
    if rationale:
        lines.append(rationale)
    if tag:
        lines.append(
            f"이 사람의 머릿속에는 요즘 '{tag}' 같은 생각이 스치곤 합니다. "
            "제도를 곧이곧대로만 따르는 쪽은 아닐 수 있습니다 — "
            "실제로 어떻게 할지는 이 사람이 정합니다."
        )
    return "\n".join(lines)


def build_react_messages(
    persona: dict, policy: str, grounded: bool = True, cast: Optional[dict] = None,
) -> list:
    """한 시민이 정책 발표 뉴스를 접하고 보이는 1차 반응을 요청하는 messages.

    grounded=True  : 인물 카드(데이터셋 상세 서사 전부)를 주입한 실험군
    grounded=False : 인물 정보를 제거한 ablation 대조군 (무대·형식은 동일)
    cast           : 캐스팅 패스가 발현시킨 경우 {'tag','rationale'} — 인물 카드 뒤에
                     [속사정] 블록을 덧붙인다(grounded 일 때만, DESIGN §9).
    """
    policy_text = (policy or "").strip()
    task = _react_task(policy_text)

    if grounded:
        system = _REACT_SYSTEM_GROUNDED
        card = _persona_card(persona)
        if cast:
            card += _disposition_block(cast)
        user = card + "\n\n" + task
    else:
        system = _REACT_SYSTEM_ABLATION
        user = task

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 1.5단계: 일탈 행동 캐스팅 (react 전 1회 — DESIGN §9)
# ---------------------------------------------------------------------------

_CASTING_SYSTEM = (
    "당신은 정책 레드팀 분석가입니다. 새 정책이 시행됐을 때, 각 인물이 제도를\n"
    "곧이곧대로 따르지 않을 가능성을 그 인물의 삶과 처지에서 평가합니다 —\n"
    "요건의 틈을 활용(편법), 자격·서류를 꾸밈(부정수급 시도), 불만을 행동으로\n"
    "옮김(민원·항의·공론화).\n\n"
    "- 과장하지 않습니다. 현실에서 대부분의 사람은 제도를 그대로 따르거나\n"
    "  무시합니다. 정말 그럴 법한 처지의 인물에게만 높은 점수를 주세요.\n"
    "- 점수의 근거는 인물의 처지(경제 압박, 요건과의 어긋남, 좌절 경험,\n"
    "  제도 이해도)여야 합니다. 직업·나이에 대한 고정관념만으로 올리지 않습니다.\n"
    "- '무엇을 할 법한가' 수준으로만 평가하고, 구체적인 위조·회피 요령은\n"
    "  쓰지 않습니다."
)


def _casting_roster(personas: list) -> str:
    """캐스팅용 인물 명단 — 번호. 한 줄 소개(+형편·디지털 힌트).

    LLM 이 uuid 를 옮겨 적다 틀리지 않도록 번호(1부터)로 참조하게 한다 —
    번호→persona 역매핑은 호출측(graph.nodes)이 한다.
    """
    lines = []
    for i, p in enumerate(personas or [], start=1):
        intro = _short_intro(p)
        signals = p.get("signals") or {}
        bits = []
        income_ko = _INCOME_KO.get((signals.get("income_level") or "").strip())
        if income_ko:
            bits.append(f"형편 {income_ko} 편")
        dl = signals.get("digital_literacy")
        if isinstance(dl, (int, float)) and dl < 0.3:
            bits.append("디지털 서툼")
        suffix = f" [{' · '.join(bits)}]" if bits else ""
        lines.append(f"{i}. {intro}{suffix}")
    return "\n".join(lines)


def build_casting_messages(personas: list, policy: str) -> list:
    """react 전 캐스팅 1회 — 인물 명단 전체를 보고 인물별 일탈 성향을 평가시킨다.

    출력(graph.nodes.CastingOut): 인물 번호별 {score 0~100, tag(자유), rationale}.
    임계값 이상만 발현(manifest)시키는 결정은 코드가 한다(graph.nodes) —
    고정 비율 없음: 정책에 따라 0명일 수도, 여럿일 수도 있다(자연 발생).
    """
    policy_text = (policy or "").strip()
    user = (
        "■ 새로 발표된 정책\n"
        f"{policy_text}\n\n"
        "■ 인물 명단\n"
        f"{_casting_roster(personas)}\n\n"
        "■ 요청\n"
        "명단의 모든 인물에 대해, 이 정책 앞에서 일탈 행동(편법·부정수급 시도·\n"
        "민원 등 불만의 행동화)으로 기울 성향을 평가하세요.\n"
        "- index: 인물 번호(명단의 번호 그대로)\n"
        "- score: 0~100. 0=제도를 그대로 따르거나 무시 / 60 이상=실제로 일탈을\n"
        "  저울질할 법함 / 85 이상=처지상 거의 확실히 시도할 법함.\n"
        "  대부분의 인물은 60 미만인 것이 자연스럽습니다.\n"
        "- tag: 60 이상인 인물만 — 그 사람이 할 법한 행동의 짧은 이름표(자유,\n"
        "  예: 위장 전입 검토 / 소득 축소 신고 / 집단 민원 / 온라인 공론화).\n"
        "  60 미만이면 빈 문자열.\n"
        "- rationale: 그 점수의 근거 한 줄 — 이 인물의 처지 어디에서 나오는가."
    )
    return [
        {"role": "system", "content": _CASTING_SYSTEM},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 2단계: 다른 시민들 반응을 보고 상호작용
# ---------------------------------------------------------------------------

# interact 도 react 와 같은 L0 골격 — 판단 지시 0줄. 남의 말에 흔들릴지,
# 굳어질지, 흘려들을지는 그 사람이 정한다.
_INTERACT_SYSTEM = (
    "당신은 [이 사람]에 소개된 바로 그 사람입니다.\n"
    "답변은 정해진 틀에 담되, 틀 안의 내용은 전부 이 사람의 것입니다.\n\n"
    "- 남들의 말을 듣고 끄덕일 수도, 생각이 더 굳어질 수도, 그냥 흘려들을 수도\n"
    "  있습니다 — 어느 쪽이든 그 사람답기만 하면 됩니다.\n"
    "- 말은 평소 그 사람이 하는 말 그대로. 댓글 한 줄이면 한 줄로 끝내도 됩니다."
)

_STANCE_KR = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}


def build_interact_messages(
    persona: dict, policy: str, digest: str, own: Optional[dict] = None,
) -> list:
    """한 시민이 게시판의 다른 댓글들을 보고 한마디 더 다는 messages.

    own = {"stance": 현재 입장, "text": 1차 반응문} — 자기 일관성 grounding.
    (구버전은 시민이 자기 1차 반응도 못 본 채 남의 말에만 반응했고, 인물 120자·
     정책 160자 절단으로 사실상 맹목 상태였다 — 2026-06-06 재설계.)
    """
    policy_text = (policy or "").strip()
    digest_text = (digest or "").strip() or "(아직 다른 댓글 없음)"

    own_block = ""
    if own:
        stance_kr = _STANCE_KR.get((own.get("stance") or "").strip(), "혼합")
        own_txt = (own.get("text") or "").strip().replace("\n", " ").replace("■", "·")
        if len(own_txt) > 200:
            own_txt = own_txt[:200].rstrip() + "…"
        if own_txt:
            own_block = (
                "[당신이 먼저 단 댓글]\n"
                f'({stance_kr}) "{own_txt}"\n\n'
            )
        # 속내(behavior) — 일탈 행동 축(DESIGN §9). 꺼낼지 감출지는 그 사람이 정한다:
        # 동네 게시판에 편법을 떠벌리는 사람도, 조용히 혼자 품는 사람도 있다.
        own_behavior = (own.get("behavior_text") or "").strip().replace("\n", " ").replace("■", "·")
        if own_behavior:
            if len(own_behavior) > 150:
                own_behavior = own_behavior[:150].rstrip() + "…"
            own_block += (
                "[당신만 아는 속내]\n"
                f'"{own_behavior}"\n'
                "(댓글에서 이걸 꺼낼지, 슬쩍 흘릴지, 감출지는 당신이 정합니다.)\n\n"
            )

    user = (
        f"{_persona_card_brief(persona)}\n\n"
        "[상황]\n"
        "동네 온라인 게시판에 이 정책 소식 글이 올라왔고, 사람들이 댓글을 달고 "
        "있습니다.\n\n"
        "[정책 글]\n"
        f"{policy_text}\n\n"
        f"{own_block}"
        "[최근 댓글들]\n"
        f"{digest_text}\n\n"
        "[기록]\n"
        "1) 댓글(reply): 최근 댓글들을 보고 지금 달 한마디. 평소 말투로.\n"
        "2) 입장(new_stance): 남의 말에 생각이 실제로 바뀌었을 때만 "
        "support/oppose/mixed 로 적고, 그대로면 비워두세요.\n"
        "3) 참고(references): 특정 누군가의 말에 반응한 거라면 그 이름(들)."
    )

    return [
        {"role": "system", "content": _INTERACT_SYSTEM},
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
        "(2) 시민이 겪은 문제를 해소하도록 개선안을 반영해 정책 원문을 다시 쓴 '수정안'을 작성하고, "
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
        "1) 요약: 시민들 사이의 갈등 지점과 합의 지점을 정리하세요. 위 반응 요약에 "
        "실제로 나타난 것만 쓰고, 나타나지 않은 갈등이나 합의를 지어내지 마세요.\n"
        "2) 수정안: 시민 반응에서 실제로 드러난 문제를 해소하도록 정책 원문을 다시 쓴 "
        "'수정안'을 작성하세요. 어려운 용어는 풀되, 그대로 공고·안내문으로 쓸 수 있는 "
        "정책 문서 형태로 작성하고, 아래 3)의 개선 방향을 본문에 반영하세요.\n"
        "3) 개선안: 시민 반응에 근거한 구체적이고 실행 가능한 정책 개선안을 목록으로 "
        "제시하세요. 각 항목이 어떤 시민 반응에서 나온 것인지 알 수 있게 쓰세요."
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
        "■ 이 주민의 1차 반응 (출발점 — 이야기는 여기서 출발합니다. "
        "입장·의향이 달라지려면 그럴 만한 계기가 기록에 있어야 합니다)",
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
    # 속내(behavior) — 일탈 행동 축(DESIGN §9). 이 사람이 품은 편법·민원 계획이
    # 있다면 6개월 궤적이 거기서 이어진다(실행할지, 들킬지, 접을지는 모델이 정한다).
    b_txt = (reaction.get("behavior_text") or "").strip().replace("\n", " ").replace("■", "·")
    if b_txt:
        if len(b_txt) > 150:
            b_txt = b_txt[:150].rstrip() + "…"
        b_tag = (reaction.get("behavior_tag") or "").strip()
        suffix = f" ({b_tag})" if b_tag else ""
        lines.append(f'- 마음에 품은 속내: "{b_txt}"{suffix}')
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
    # 관찰 기록자 프레임 + 충실성 규칙(2026-06-06 재설계).
    # 구버전의 "과장 없이 현실적으로 … 특징이 그대로 반영되게" 지시와
    # '정부 신뢰' 참조(카드에서 빠진 가짜 신호를 가리키는 죽은 참조)는 제거.
    # 비퇴행은 system 에 세계 규칙으로 1회 + 코드 가드(graph/village._guard_status)가 보증.
    system = (
        "당신은 관찰 기록자입니다. 가상 마을 '미리 마을'의 한 주민이 정책 시행 뒤 "
        "시간이 흐르며 실제로 어떻게 살아가는지를 기록합니다.\n\n"
        "- 이 주민의 행동·감정·판단은 [이 사람]에 소개된 삶에서 나옵니다. "
        "그 삶에서 일어날 법한 일만, 그 사람답게.\n"
        "- 정책 정보는 '어느 장소에 닿느냐'를 따라 전해집니다. 닿지 못하면 모른 채 "
        "지나가고, 알아도 신청하지 않거나 신청해도 막힐 수 있습니다 — 어느 쪽이든 "
        "그 사람의 삶이 정하는 대로.\n"
        "- 시간은 앞으로만 흐릅니다: 한 번 알게 된 사실이 없던 일이 되지는 않습니다.\n"
        "- 주민의 '1차 반응'이 주어지면 그것이 이 사람의 출발점입니다. 이야기는 "
        "반드시 그 입장·의향에서 출발하고, 거기서 달라지려면 그럴 만한 계기"
        "(만난 사람·닿은 경로·겪은 사건)가 이번 기록에 있어야 합니다 — "
        "계기 없는 돌변은 없습니다.\n\n"
        "답변은 정해진 틀에 담습니다."
    )

    policy_text = (policy or "").strip()
    hist_text = (history or "").strip() or "(아직 이전 기록 없음 — 정책 시행 직후입니다.)"

    if grounded:
        person_block = _persona_card(persona) + "\n\n"
    else:
        person_block = (
            "[이 사람]\n"
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
            "위 목록의 key 중 하나로 고르세요. 그 사람이 실제로 닿을 만한 곳이어야 "
            "합니다. 어디에도 닿지 못했으면 home 을 고르고 unaware 로 두세요.\n"
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
        "그대로 쓰세요.\n"
        "3) 행동·사건(action): 이 기간 동안 이 사람이 이 정책과 관련해(또는 무관하게) "
        "실제로 한 행동과 겪은 일을, 고른 장소·경로와 자연스럽게 이어지게 2~4문장으로 쓰세요.\n"
        "4) 정책 관여 상태(policy_status): unaware(끝까지 알지도 못함) / aware(알게 됨) / "
        "applied(신청함) / received(수령·혜택 받음) / blocked(알거나 신청했으나 "
        "요건·서류·절차에 막혀 못 받고 포기) 중 이번 시점의 단계. 신청·시도했다가 "
        "포기·실패한 것은 unaware 가 아니라 blocked 입니다(unaware = 처음부터 끝까지 "
        "몰랐던 경우만).\n"
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
