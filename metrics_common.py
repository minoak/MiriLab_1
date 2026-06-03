# -*- coding: utf-8 -*-
"""핵심 지표 공통 공식 — 모드(real/demo/fallback) 간 일관성을 위해 한 곳에 둔다.

지금은 '사회혼란도'만 공유한다(정책수용도/신청의향지수는 각 경로 공식 유지).

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
