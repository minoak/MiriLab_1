# -*- coding: utf-8 -*-
"""axis3.py — 축3 요약·개선: t0(축1) × 시계열(축2) 읽기 전용 집계.

설계방향서 v1.1 §3 축3 계약: 입력은 t0 기록과 시계열뿐(읽기 전용). 코드는 세고
(판단 0), LLM 은 문장만. 새 판정·사후 재라벨 금지 — 결과는 축2 종점(가드 통제)
에서 이미 확정됐고, 여기서는 그것을 세어 수치로 만들 뿐이다.

핵심 규율(§5): **같은 모수(대상자 is_target), 같은 단위(인원 비율).**
- 낙차 = t0 적극 의향 비율(intent≥60) − 종점 수령 비율   [둘 다 대상자 모수]
- 깔때기 = 의향 → 도달 → 신청 → 수령                     [대상자 모수]
- 전향 = t0 의향 없음(intent<50) ∧ 종점 수령 — 모순이 아니라 추적된 변화(§2).
  계산만 하고 어디에도 저장하지 않는다(§10).
- (v1.2 §8-13) **t0 지표(정책수용도·신청의향지수·사회혼란도)도 여기서 센다** — 전원
  모수, 공식은 metrics_common 단일 소스. 게이지 포함 화면의 모든 지표가 이 모듈 산출.

기존 재료 재사용(§8-4 — 신규 판정 0):
- contrast._resident_outcome : 사다리 종점 범주(out/received/blocked/unaware/inprogress)
- data.personas.is_target    : 결정론 대상 판정(_resident_outcome 내부에서 사용)

주의(§10): graph.nodes._compute_metrics 의 high_intent_ratio 와
graph.village._aggregate_village 의 received_rate 는 **전원 모수**라 낙차에 못 쓴다
— 여기서 대상자 모수로 다시 센다. 화면(대시보드·카드)은 이 모듈 값만 쓴다(단일 진실원).

순수 모듈: streamlit 무의존, LLM 0, import 시 네트워크 0, 같은 입력 → 같은 출력.
"""
from __future__ import annotations

from contrast import _resident_outcome
from metrics_common import application_index, policy_acceptance, social_unrest

# t0 의향 임계 — 설문 intent 이산값 {100,75,50,25,0} 기준(prompts.SURVEY_ITEMS).
INTENT_ACTIVE = 60  # 적극 의향(낙차 좌변): surely(100)·probably(75)만 통과
INTENT_NONE = 50    # 의향 없음(전향 좌변): probably_not(25)·no_need(0)만. unsure(50) 제외

# 깔때기 단계 (key, 라벨). 단계 정의는 _funnel_flags 참조.
FUNNEL_STAGES = [
    ("intent", "t0 적극 의향"),
    ("reached", "도달(알게 됨)"),
    ("applied", "신청"),
    ("received", "수령"),
]


def is_application_policy(policy_spec: dict | None) -> bool:
    """신청형 정책인가(§5 비신청형 분기). 비신청형이면 낙차·깔때기가 무의미하다.

    이틀 규칙(보수적): 지원 형태(support_type)에 '감면'이 있을 때만 비신청형.
    만 나이 통일처럼 지원 형태 자체가 없는 정책은 태그로 구분할 신호가 없어
    신청형으로 처리된다 — 직접 입력 시 지원 형태를 '감면'으로 지정하면 분기된다.
    (발표 후: spec 에 policy_kind 필드 추가 검토.)
    """
    st = ((policy_spec or {}).get("support_type") or "").strip()
    return "감면" not in st


def _t0_intent(reaction: dict | None):
    """t0 reaction 에서 intent 점수(0~100)를 꺼낸다. 없으면 None(기록 누락)."""
    sc = (reaction or {}).get("scores") or {}
    v = sc.get("intent")
    return float(v) if isinstance(v, (int, float)) else None


def _funnel_flags(timeline: list) -> dict:
    """시계열에서 깔때기 도달 여부(ever 기준)를 뽑는다 — 종점이 아니라 통과 이력.

    reached : unaware 아닌 상태가 한 번이라도 등장(정책이 닿음 — blocked 포함).
    applied : applied/received 가 한 번이라도 등장(신청 증거). blocked 단독은
              신청 미달로 보수 분류 — 도달→신청 갭(진입 처방)으로 잡힌다.
    received: received 가 한 번이라도 등장(_resident_outcome 의 ever_received 와 동일).
    """
    statuses = {(s.get("policy_status") or "unaware") for s in (timeline or [])}
    return {
        "reached": bool(statuses - {"unaware"}),
        "applied": bool(statuses & {"applied", "received"}),
        "received": "received" in statuses,
    }


def t0_metrics(reactions_by_id: dict | None) -> dict | None:
    """t0 기록만으로 게이지 3지표를 센다(전원 모수 — v1.2 §8-13).

    공식 = metrics_common(실모드 공식 단일 소스 — demo/real 동일 값).
    기록이 없으면 None("측정 불가"는 0 과 다르다 — 화면은 이때 구 metrics 폴백).
    village 가 필요 없으므로 미래의 '축1 직후 부분 표시'(2단 rerun)에도 그대로 쓴다.
    """
    rx = [r for r in (reactions_by_id or {}).values() if r]
    if not rx:
        return None
    return {
        "정책수용도": policy_acceptance(rx),
        "신청의향지수": application_index(rx),
        "사회혼란도": social_unrest(rx),
        "n": len(rx),
    }


def aggregate_axis3(
    reactions_by_id: dict | None,
    village: dict | None,
    personas: list | None,
    specs: list | None = None,
) -> dict:
    """t0 × 시계열 → 결과 범주·수령률·사각·낙차·전향·깔때기 (전부 대상자 모수).

    Args:
        reactions_by_id: 축1 t0 기록 {persona_id: Reaction(보정본)} — 읽기만.
        village: 축2 산출물 {steps, residents, aggregate} — 읽기만.
        personas: 전체 페르소나(대상 판정용).
        specs: 정책 타깃 명세 리스트(없으면 전원 대상 — is_target 의 graceful).

    Returns: {
        n, n_target,
        t0_metrics: {정책수용도, 신청의향지수, 사회혼란도, n} | None,  # 전원 모수(v1.2)
        outcomes: {received, blocked, unaware, aware_stalled, applied_pending, out},
            # §4 사다리 종점 5범주(대상자) + out(비대상). aware_stalled/applied_pending
            # 은 _resident_outcome 의 inprogress 를 raw_final 로 나눈 것 — 신규 판정 아님.
        received_rate, blindspot_rate, intent_rate_t0, gap,   # 대상자 모수 비율(0~1).
            # 대상자가 없으면 전부 None("측정 불가"는 0%와 다르다). gap>0 = 의향이
            # 어딘가서 샜다(깔때기로 위치 추적), gap<0 = 전파가 의향을 끌어올렸다.
        funnel: [{key, label, count}×4],                       # 대상자 모수 인원수.
        conversions: [{id, name, intent_t0}], n_conversion,    # 전향자(표시용 계산값).
        missing_t0: int,   # 대상자 중 t0 기록 없는 수(정직 노트 재료 — 분모는 유지).
        guard: 축2 bridge_guard 통계 패스스루(정직 노트 단일 진실원).
    }
    """
    personas = personas or []
    residents = (village or {}).get("residents") or []
    rx = reactions_by_id or {}
    by_id = {p.get("id"): p for p in personas}

    # 축2 종점 범주 — contrast 와 같은 함수(단일 진실원), 새 판정 없음.
    rows = [_resident_outcome(r, by_id.get(r.get("id")), specs) for r in residents]
    res_by_id = {r.get("id"): r for r in residents}

    outcomes = {"received": 0, "blocked": 0, "unaware": 0,
                "aware_stalled": 0, "applied_pending": 0, "out": 0}
    funnel_counts = {k: 0 for k, _ in FUNNEL_STAGES}
    conversions = []
    n_target = 0
    missing_t0 = 0
    n_intent_active = 0

    for row in rows:
        if not row["is_target"]:
            outcomes["out"] += 1
            continue
        n_target += 1

        # ── 결과 5범주(§4): inprogress 만 raw_final 로 세분(알고도 멈춤 vs 대기) ──
        k = row["dist_key"]
        if k == "inprogress":
            k = "applied_pending" if row["raw_final"] == "applied" else "aware_stalled"
        outcomes[k] += 1

        # ── 깔때기(ever 기준) + t0 의향 ──
        flags = _funnel_flags((res_by_id.get(row["id"]) or {}).get("timeline"))
        intent = _t0_intent(rx.get(row["id"]))
        if intent is None:
            missing_t0 += 1
        elif intent >= INTENT_ACTIVE:
            n_intent_active += 1
            funnel_counts["intent"] += 1
        for fk in ("reached", "applied", "received"):
            if flags[fk]:
                funnel_counts[fk] += 1

        # ── 전향(§2): t0 의향 없음 → 종점 수령. 추적된 변화 — 계산만. ──
        if intent is not None and intent < INTENT_NONE and row["ever_received"]:
            conversions.append(
                {"id": row["id"], "name": row["name"], "intent_t0": intent}
            )

    # ── 비율(대상자 모수·인원 비율 — §5 규율). 대상자 0 이면 None(측정 불가). ──
    if n_target:
        received_rate = outcomes["received"] / n_target
        blindspot_rate = (outcomes["blocked"] + outcomes["unaware"]) / n_target
        intent_rate_t0 = n_intent_active / n_target
        gap = intent_rate_t0 - received_rate
    else:
        received_rate = blindspot_rate = intent_rate_t0 = gap = None

    return {
        "n": len(rows),
        "n_target": n_target,
        "t0_metrics": t0_metrics(reactions_by_id),  # 게이지 3지표(전원 모수, v1.2)
        "outcomes": outcomes,
        "received_rate": received_rate,
        "blindspot_rate": blindspot_rate,
        "intent_rate_t0": intent_rate_t0,
        "gap": gap,
        "funnel": [
            {"key": k, "label": label, "count": funnel_counts[k]}
            for k, label in FUNNEL_STAGES
        ],
        "conversions": conversions,
        "n_conversion": len(conversions),
        "missing_t0": missing_t0,
        "guard": ((village or {}).get("aggregate") or {}).get("bridge_guard") or {},
    }
