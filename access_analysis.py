# -*- coding: utf-8 -*-
"""정책 접근성 분석 — 시민 반응(reactions) + 페르소나로부터 '신청 여정의 병목'을 낸다.

설계 원칙(사용자 합의):
- 모든 수치는 **시민 반응에서 정직하게 유도**한다. 별도 통계/가짜 데이터를 만들지 않는다.
  (퍼널·병목은 시민이 매긴 점수와 페르소나 접근도/대상 여부로 계산한 *추정*이다.)
- 순수 모듈: streamlit 무의존, 외부 호출 0. 같은 입력 → 같은 출력(결정론).
- data.personas.policy_access / is_target 를 재사용한다(중복 구현 금지).

핵심 산출물:
- application_funnel : 신청 단계별 병목 퍼널(대상자→이해→자격→서류→신청)
- access_by_age      : 연령대별 정책 접근성(평균 policy_access)
- barrier_factors    : 병목 요인(고칠 수 있는 진입 장벽) 카운트, 큰 순
- priority_citizens  : 우선 지원 시민(접근 가능성 임계 미만)
- helpdesk_recommendations : 병목에 맞춘 도움창구 운영 제안(결정론 템플릿)
- analyze(view)      : 위를 한 번에 묶어 주는 편의 함수

퍼널/병목은 정직성을 위해 '추정'임을 UI 캡션에 밝힌다. 실제 캐시 시민은 8~24명이라
목업(100명·48건)보다 절대 수가 작게 나오는 것이 정상이다.
"""
from __future__ import annotations

from data.personas import policy_access, is_target


# ─────────────────────────────────────────────────────────────────────────
# 임계값 (튜닝 대상 — 한 곳에 모아 둠). 모두 0~100 점수 또는 0~1 접근도 기준.
# ─────────────────────────────────────────────────────────────────────────
UNDERSTAND_MIN = 50   # 이해도 이 값 이상이면 '정책을 이해함'
# 설문 전환(2026-06-06) 후 intent=50 은 '잘 모르겠다(unsure)', benefit=50 은
# '별다른 영향 없음(무관)' — 정확히 50 은 의향/체감으로 세지 않도록 51 로 올림.
# (이해도 띠 점수 {90,65,35,10}엔 50 이 없어 UNDERSTAND_MIN 은 그대로.)
INTENT_MIN = 51       # 신청의향 이 값 이상이면 '신청 의향 있음' (unsure=50 제외)
BENEFIT_MIN = 51      # 수혜 체감 이 값 이상이면 '본인이 혜택을 본다고 느낌' (무관=50 제외)
ACCESS_OK = 0.50      # 접근도 이 값 이상이면 '서류·온라인 절차를 넘을 수 있음'
ACCESS_PRIORITY = 0.40  # 접근도 이 값 미만이면 '우선 지원 시민'(도움창구 "40% 미만")

# 연령대 밴드 (라벨, 하한, 상한). 하한 0·상한 200 으로 양끝을 열어 둬, 유효한 나이는
# 어느 밴드에도 빠지지 않게 한다(예: 18세도 '24세 이하'에 흡수 — 무음 누락 방지).
AGE_BANDS = [
    ("24세 이하", 0, 24),
    ("25~34세", 25, 34),
    ("35~54세", 35, 54),
    ("55세 이상", 55, 200),
]


# ─────────────────────────────────────────────────────────────────────────
# 작은 헬퍼 (순수)
# ─────────────────────────────────────────────────────────────────────────
def _score(reaction: dict, key: str, default: int = 50) -> float:
    """반응의 5축 점수 1개를 float 로 안전 추출(없으면 default)."""
    sc = (reaction or {}).get("scores") or {}
    v = sc.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _age_of(persona: dict):
    """페르소나 나이를 int 로(없으면 None)."""
    a = (persona.get("demographics") or {}).get("age")
    try:
        a = int(a)
    except (TypeError, ValueError):
        return None
    return a if a > 0 else None


def specs_from_view(view) -> list:
    """view 의 단일 policy_spec(dict)을 is_target 이 받는 list 로 감싼다.

    spec 이 없으면 [] → is_target 은 전원 대상(graceful). 의미 있는 dict 일 때만 [spec].
    """
    if not isinstance(view, dict):
        return []
    spec = view.get("policy_spec")
    return [spec] if isinstance(spec, dict) and spec else []


def _respondents(personas: list, reactions_by_id: dict) -> list:
    """반응이 있는 (persona, reaction) 쌍만 추린다(= 실제 응답 시민)."""
    reactions_by_id = reactions_by_id or {}
    pairs = []
    for p in personas or []:
        r = reactions_by_id.get(p.get("id"))
        if r:
            pairs.append((p, r))
    return pairs


def _eligible(persona: dict, reaction: dict, specs: list) -> bool:
    """이 사람이 정책 대상인가. specs 가 있으면 사실 게이트(is_target),
    없으면 본인 수혜 체감(benefit≥기준)으로 근사한다."""
    if specs:
        return is_target(persona, specs)
    return _score(reaction, "benefit") >= BENEFIT_MIN


# ─────────────────────────────────────────────────────────────────────────
# 1) 신청 단계별 병목 퍼널
# ─────────────────────────────────────────────────────────────────────────
def application_funnel(personas: list, reactions_by_id: dict, specs: list) -> dict:
    """대상자 → 정책 이해 → 자격 확인 → 서류 준비 → 최종 신청 순차 게이트 퍼널.

    각 단계는 앞 단계 생존자 중 그 단계의 조건을 통과한 사람만 남긴다(단조 감소).
    이탈은 '그 단계에서 처음 막힌' 사람으로 귀속된다(표준 퍼널 의미).

    Returns:
        {base_n:int, stages:[{key,label,count,pct,drop,drop_label}...]}
        pct 는 base_n 대비 백분율(100명 기준 정규화 표시용).
    """
    pairs = _respondents(personas, reactions_by_id)
    base_n = len(pairs)

    stages = [{"key": "target", "label": "대상자", "count": base_n, "drop_label": ""}]

    survivors = pairs
    survivors = [(p, r) for p, r in survivors if _score(r, "understanding") >= UNDERSTAND_MIN]
    stages.append({"key": "understand", "label": "정책 이해",
                   "count": len(survivors), "drop_label": "이해 부족"})

    survivors = [(p, r) for p, r in survivors if _eligible(p, r, specs)]
    stages.append({"key": "eligible", "label": "자격 확인",
                   "count": len(survivors), "drop_label": "자격 미해당"})

    survivors = [(p, r) for p, r in survivors if policy_access(p) >= ACCESS_OK]
    stages.append({"key": "docs", "label": "서류 준비",
                   "count": len(survivors), "drop_label": "서류·디지털 장벽"})

    survivors = [(p, r) for p, r in survivors if _score(r, "intent") >= INTENT_MIN]
    stages.append({"key": "apply", "label": "최종 신청",
                   "count": len(survivors), "drop_label": "신청의향 부족"})

    for i, s in enumerate(stages):
        s["pct"] = round(s["count"] / base_n * 100) if base_n else 0
        s["drop"] = (stages[i - 1]["count"] - s["count"]) if i > 0 else 0
    return {"base_n": base_n, "stages": stages}


# ─────────────────────────────────────────────────────────────────────────
# 2) 연령대별 정책 접근성
# ─────────────────────────────────────────────────────────────────────────
def access_by_age(personas: list) -> list:
    """연령 밴드별 평균 policy_access(0~100%). 표시·정직성 위해 인원수(n)도 함께.

    Returns: [{band, pct, n}...] (AGE_BANDS 순서). 인원 0인 밴드는 pct=0, n=0.
    """
    buckets = {label: [] for label, _, _ in AGE_BANDS}
    for p in personas or []:
        age = _age_of(p)
        if age is None:
            continue
        for label, lo, hi in AGE_BANDS:
            if lo <= age <= hi:
                buckets[label].append(policy_access(p))
                break
    out = []
    for label, _, _ in AGE_BANDS:
        vals = buckets[label]
        pct = round(sum(vals) / len(vals) * 100) if vals else 0
        out.append({"band": label, "pct": pct, "n": len(vals)})
    return out


# ─────────────────────────────────────────────────────────────────────────
# 3) 병목 요인 (고칠 수 있는 진입 장벽) — 플래그 집계, 큰 순
# ─────────────────────────────────────────────────────────────────────────
def barrier_factors(personas: list, reactions_by_id: dict, specs: list) -> list:
    """시민이 막히는 '고칠 수 있는' 장벽을 유형별로 센다(서로 겹칠 수 있음).

    '자격 미해당'(대상이 아님)은 고칠 수 있는 장벽이 아니므로 제외한다.

    Returns: [{key, label, short, count}...] count 내림차순, count>0 만.
    """
    pairs = _respondents(personas, reactions_by_id)

    factors = []

    # 온라인·디지털 장벽: 접근도가 낮아 온라인/서류 절차를 넘기 어려움(전원 기준).
    c = sum(1 for p, _ in pairs if policy_access(p) < ACCESS_OK)
    factors.append({"key": "digital", "label": "온라인·디지털 장벽",
                    "short": "디지털 장벽", "count": c})

    # 조건 이해 실패: 정책 자체를 이해하지 못함(전원 기준).
    c = sum(1 for _, r in pairs if _score(r, "understanding") < UNDERSTAND_MIN)
    factors.append({"key": "understand", "label": "조건 이해 실패",
                    "short": "이해 장벽", "count": c})

    # 아래 둘은 '정책 대상자'를 짚어야 의미가 있는 진단이라, 대상을 사실로 판정할
    # 명세(specs)가 있을 때만 측정한다. specs 가 없으면 누가 대상인지 알 수 없으므로
    # 0으로 위장하지 않고 항목 자체를 생략한다(정직성). 대상 판정은 is_target 으로 한다
    # (benefit 으로 근사하면 'benefit≥50 이면서 benefit<50' 같은 모순이 생긴다).
    if specs:
        # 대상 기준 혼란: 대상자인데 본인이 수혜 대상임을 체감 못 함(기준이 헷갈림).
        c = sum(1 for p, r in pairs
                if is_target(p, specs) and _score(r, "benefit") < BENEFIT_MIN)
        factors.append({"key": "criteria", "label": "대상 기준 혼란",
                        "short": "기준 혼란", "count": c})

        # 신청 중도 포기: 대상이고 이해도 했는데 신청 의향이 꺾인 사람(절차 부담).
        c = sum(1 for p, r in pairs
                if is_target(p, specs)
                and _score(r, "understanding") >= UNDERSTAND_MIN
                and _score(r, "intent") < INTENT_MIN)
        factors.append({"key": "giveup", "label": "신청 중도 포기",
                        "short": "신청 포기", "count": c})

    factors = [f for f in factors if f["count"] > 0]
    factors.sort(key=lambda f: f["count"], reverse=True)
    return factors


def main_bottleneck(factors: list) -> str:
    """병목 요인 1위의 짧은 라벨(없으면 빈 문자열)."""
    return factors[0]["short"] if factors else ""


# ─────────────────────────────────────────────────────────────────────────
# 4) 우선 지원 시민 (접근 가능성 임계 미만)
# ─────────────────────────────────────────────────────────────────────────
def priority_citizens(personas: list, reactions_by_id: dict,
                      threshold: float = ACCESS_PRIORITY) -> dict:
    """접근도가 임계 미만인 응답 시민(우선 지원 대상).

    Returns: {count, threshold_pct, names:[...]}
    """
    pairs = _respondents(personas, reactions_by_id)
    names = [p.get("name") or p.get("id") or "시민"
             for p, _ in pairs if policy_access(p) < threshold]
    return {"count": len(names), "threshold_pct": int(round(threshold * 100)),
            "names": names}


# ─────────────────────────────────────────────────────────────────────────
# 5) 도움창구 운영 제안 — 감지된 병목에 맞춘 결정론 템플릿(LLM 0)
# ─────────────────────────────────────────────────────────────────────────
def helpdesk_recommendations(factors: list, priority: dict) -> list:
    """병목 요인 + 우선 지원 인원에 따라 운영 제안 문장을 만든다(결정론).

    감지된 장벽에만 해당 제안을 켠다. 아무 장벽도 없으면 유지 안내 한 줄.
    """
    keys = {f["key"] for f in (factors or [])}
    recs = []
    if "digital" in keys:
        recs.append("온라인 신청 전용 안내가 아니라 주민센터·복지관·전화 상담을 병행합니다.")
    if "understand" in keys or "criteria" in keys:
        recs.append("자격 조건·소득 기준·필요 서류를 한 장짜리 체크리스트로 분리합니다.")
    cnt = (priority or {}).get("count", 0)
    pct = (priority or {}).get("threshold_pct", int(round(ACCESS_PRIORITY * 100)))
    if cnt > 0:
        recs.append(
            f"접근 가능성 {pct}% 미만 시민 {cnt}명에게는 신청서 작성 보조와 "
            "서류 확인을 먼저 제공합니다."
        )
    if "giveup" in keys:
        recs.append("신청 도중 포기하는 시민을 위해 진행 상황 저장과 안내 문자(SMS)를 제공합니다.")
    if not recs:
        recs.append("두드러진 접근 장벽이 발견되지 않았습니다. 기존 안내 채널을 유지하세요.")
    return recs


# ─────────────────────────────────────────────────────────────────────────
# 편의: 한 번에 묶기
# ─────────────────────────────────────────────────────────────────────────
def analyze(view) -> dict:
    """ViewModel(view)에서 접근성 분석 일체를 계산해 dict 로 돌려준다.

    Returns:
        {funnel, age_access, barriers, priority, helpdesk, main_bottleneck}
        view 가 비었으면 모든 값이 비어 있는(0/[]) 안전한 구조를 돌려준다.
    """
    if not isinstance(view, dict):
        view = {}
    personas = view.get("personas") or []
    reactions_by_id = view.get("reactions_by_id") or {}
    specs = specs_from_view(view)

    funnel = application_funnel(personas, reactions_by_id, specs)
    age_access = access_by_age(personas)
    barriers = barrier_factors(personas, reactions_by_id, specs)
    priority = priority_citizens(personas, reactions_by_id)
    helpdesk = helpdesk_recommendations(barriers, priority)

    return {
        "funnel": funnel,
        "age_access": age_access,
        "barriers": barriers,
        "priority": priority,
        "helpdesk": helpdesk,
        "main_bottleneck": main_bottleneck(barriers),
    }
