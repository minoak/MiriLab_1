# -*- coding: utf-8 -*-
"""핵심 지표 공통 공식 — 모드(real/demo/fallback) 간 일관성을 위해 한 곳에 둔다.

v1.2(설계방향서 §8 항목 12): 게이지 3지표(정책수용도·신청의향지수·사회혼란도) 전부
여기가 단일 소스다. 수용도·의향지수 공식은 graph/nodes 실모드 것을 '이전'한 것
(재정의 아님) — 집계 노드와 화면(축3 t0 지표)이 같은 함수를 호출해 같은 값을 본다.

사회혼란도 정의(2026-06-03 사용자 합의): **반발 강도 — 시민이 얼마나 들고 일어날 만큼 불만인가.**
= 시민 불만(dissatisfaction) 점수의 평균(0~100).
  - 다들 무덤덤/만족 → 낮음 (잠잠한 정책)
  - 다 같이 강하게 반대·분노 → 높음 (전쟁 정책처럼 합의된 반발도 높게 잡힘)

이름=측정이 일치한다: '불만의 평균'이 곧 '사회적으로 시끄러워질 정도'.

이 숫자는 반발의 '세기'만 요약한다. *왜* 화났는지(형평성·박탈감 등 정성적 사연)는
페르소나 반응 서사/인생극장이 맡는다. (찬반 갈림은 시민 반응의 stance 분포 바가 직접 보여줌.)

배경(왜 '양극화' 버전을 버렸나): 한때 혼란도를 양극화(찬반 갈림)로 계산했으나
(1)'전쟁=다 같이 반대'인데 양극화가 낮게 나와 직관과 어긋났고 (2)양극화는 stance
분포 바와 중복이었다. → 반발의 '세기'(불만 평균)로 단순화해 둘 다 해결함.
"""


def social_unrest(reactions: list) -> float:
    """반응 리스트 → 사회혼란도 지수(0~100). 시민 불만(dissatisfaction) 평균."""
    reactions = reactions or []
    n = len(reactions)
    if n == 0:
        return 0.0

    total = 0.0
    for r in reactions:
        sc = r.get("scores") or {}
        try:
            d = float(sc.get("dissatisfaction", 50))
        except (TypeError, ValueError):
            d = 50.0
        total += d

    return round(max(0.0, min(100.0, total / n)), 1)


def _axis_values(reactions: list, key: str) -> list:
    """reactions 의 scores[key] 값 목록(float).

    키가 없으면 50(집계 노드와 동일 기본값), None/비숫자는 건너뛴다.
    아래 공식 함수들의 공용 헬퍼.
    """
    vals = []
    for r in reactions or []:
        v = (r.get("scores") or {}).get(key, 50)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return vals


def _mean(vals: list) -> float:
    """빈 리스트면 0.0 을 반환하는 안전한 평균(집계 노드 _mean 과 동일 동작)."""
    return sum(vals) / len(vals) if vals else 0.0


def policy_acceptance(reactions: list) -> float:
    """정책수용도(0~100) = 0.45·신청의향 + 0.30·이해도 + 0.25·(100−불만) — 평균 블렌드.

    공식 출처: graph/nodes._compute_metrics (v1.2 에서 이곳으로 이전 — 값 불변).
    """
    val = (
        0.45 * _mean(_axis_values(reactions, "intent"))
        + 0.30 * _mean(_axis_values(reactions, "understanding"))
        + 0.25 * (100.0 - _mean(_axis_values(reactions, "dissatisfaction")))
    )
    return round(max(0.0, min(100.0, val)), 1)


def application_index(reactions: list) -> float:
    """신청의향지수(0~100) = 0.6·의향 평균 + 0.4·(적극층 비율×100).

    적극층 = intent ≥ 60 (설문 이산값 기준 surely(100)·probably(75)만 통과).
    공식 출처: graph/nodes._compute_metrics (v1.2 에서 이곳으로 이전 — 값 불변).
    """
    vals = _axis_values(reactions, "intent")
    high_ratio = (sum(1 for v in vals if v >= 60) / len(vals)) if vals else 0.0
    val = 0.6 * _mean(vals) + 0.4 * (high_ratio * 100.0)
    return round(max(0.0, min(100.0, val)), 1)
