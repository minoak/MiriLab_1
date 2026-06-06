# -*- coding: utf-8 -*-
"""핵심 지표 — 사회혼란도(반발 강도) 민감도 + 키/공식 통일 + 거울상 점검(LLM 없이).

사회혼란도 = 반발 강도 = 시민 불만(dissatisfaction) 평균 = mean(dissatisfaction).
검증:
  - 다들 만족 → 낮음, 다 같이 분노(합의 반발 포함) → 높음, 절반만 분노 → 중간.
  - _merge_metrics 가 social_unrest(영문) → 사회혼란도(한글 게이지 키) 매핑.
  - nodes/model/mock 가 같은 social_unrest 공식을 쓰는지(통일).
  - 수용도와 사회혼란도가 '거울상(100-X)'이 아님(무관심 vs 반발로 분리됨).
실행: python _test_metrics_sensitivity.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from graph.nodes import _compute_metrics as nodes_metrics
from ui.model import _merge_metrics
from metrics_common import social_unrest


def mk(n, dissat, understanding=50, benefit=50, intent=50, stance="mixed"):
    return [
        {"persona_id": f"p{k}",
         "scores": {"understanding": understanding, "benefit": benefit, "intent": intent,
                    "dissatisfaction": dissat, "shareability": 50},
         "stance": stance}
        for k in range(n)
    ]


SCENARIOS = [
    ("다들 만족(잠잠)",          mk(10, 10)),
    ("다 같이 분노(합의 반발)",    mk(10, 85, stance="oppose")),
    ("절반만 분노",             mk(5, 10) + mk(5, 85)),
    ("무덤덤",                 mk(10, 40)),
]

hdr = f"{'시나리오':<22} | {'사회혼란도':>10}"
print(hdr)
print("-" * len(hdr))
su = {}
for name, rx in SCENARIOS:
    nm = nodes_metrics(rx, [])
    su[name] = nm["social_unrest"]
    print(f"{name:<22} | {nm['social_unrest']:>10.1f}")

    # 키 통일: 집계(social_unrest 영문) → 게이지(사회혼란도 한글)
    merged = _merge_metrics(nm, rx)
    assert abs(merged["사회혼란도"] - nm["social_unrest"]) < 1e-6, (name, merged["사회혼란도"], nm["social_unrest"])
print("-" * len(hdr))

# 사회혼란도 의미 검증
assert su["다 같이 분노(합의 반발)"] > su["다들 만족(잠잠)"], su
assert su["다 같이 분노(합의 반발)"] > 80, su      # 다 같이 분노 = 높음(전쟁 케이스 해결)
assert su["다들 만족(잠잠)"] < 15, su             # 다들 만족 = 낮음
assert 40 < su["절반만 분노"] < 60, su            # 절반 분노 = 중간
print(f"\n✅ 사회혼란도 의미 검증: 합의반발({su['다 같이 분노(합의 반발)']}) ≫ 잠잠({su['다들 만족(잠잠)']}), 절반({su['절반만 분노']}) 중간")

# 공식 통일: 집계노드 == metrics_common.social_unrest
for name, rx in SCENARIOS:
    assert abs(nodes_metrics(rx, [])["social_unrest"] - social_unrest(rx)) < 1e-6, name
print("✅ 사회혼란도 공식 통일됨: 집계노드 == metrics_common.social_unrest")

# 거울상 점검: 수용도 ≠ 100 - 혼란도.
# '무관심'(낮은 의향·이해 + 낮은 불만) 은 수용도도 낮고 혼란도도 낮음 →
# 거울상이라면 불가능(낮은 수용 = 높은 혼란이어야 함). 둘이 독립 축임을 증명.
apathy = mk(10, dissat=15, understanding=30, intent=20, stance="mixed")
backlash = mk(10, dissat=85, understanding=30, intent=20, stance="oppose")
m_apathy = nodes_metrics(apathy, [])
m_backlash = nodes_metrics(backlash, [])
# 수용도는 둘 다 낮게(의향·이해가 같아서) — 불만만 다름.
assert abs(m_apathy["policy_acceptance"] - m_backlash["policy_acceptance"]) < 20, (
    m_apathy["policy_acceptance"], m_backlash["policy_acceptance"])
# 혼란도는 크게 갈림(불만 차이).
assert m_backlash["social_unrest"] - m_apathy["social_unrest"] > 50, (
    m_apathy["social_unrest"], m_backlash["social_unrest"])
# 무관심: 수용도 낮은데 혼란도도 낮음(거울상이 아님).
assert m_apathy["policy_acceptance"] < 60 and m_apathy["social_unrest"] < 30, (
    m_apathy["policy_acceptance"], m_apathy["social_unrest"])
print(f"✅ 거울상 아님: 무관심(수용 {m_apathy['policy_acceptance']}/혼란 {m_apathy['social_unrest']}) "
      f"vs 반발(수용 {m_backlash['policy_acceptance']}/혼란 {m_backlash['social_unrest']}) — 수용 비슷, 혼란만 갈림")

# 데모(mock 한글 키 직접) 는 그대로 우선되는지(회귀)
demo_given = {"정책수용도": 88.0, "사회혼란도": 42.0, "신청의향지수": 77.0}
md = _merge_metrics(demo_given, mk(3, 50))
assert md["사회혼란도"] == 42.0 and md["정책수용도"] == 88.0, md
print("✅ 데모(mock 한글 키 직접) 우선 — 회귀 없음")

# v1.2(§8-12): 수용도·의향지수도 공식 단일 소스 — 집계노드 == metrics_common
from metrics_common import policy_acceptance, application_index
for name, rx in SCENARIOS:
    nm = nodes_metrics(rx, [])
    assert abs(nm["policy_acceptance"] - policy_acceptance(rx)) < 1e-6, name
    assert abs(nm["application_index"] - application_index(rx)) < 1e-6, name
print("✅ v1.2 공식 단일 소스: 집계노드 == metrics_common (수용도·의향지수)")

# 값 불변(공식 '이전'이지 재정의 아님) — 손계산 고정값으로 박음
fixed = mk(10, dissat=10, understanding=50, intent=50)
m_fixed = nodes_metrics(fixed, [])
assert m_fixed["policy_acceptance"] == 60.0, m_fixed["policy_acceptance"]  # 0.45·50+0.30·50+0.25·90
assert m_fixed["application_index"] == 30.0, m_fixed["application_index"]  # 0.6·50+0.4·0 (50<60)
hot = mk(10, dissat=10, understanding=80, intent=80)
m_hot = nodes_metrics(hot, [])
assert m_hot["policy_acceptance"] == 82.5, m_hot["policy_acceptance"]      # 36+24+22.5
assert m_hot["application_index"] == 88.0, m_hot["application_index"]      # 0.6·80+0.4·100
print("✅ v1.2 값 불변: 손계산 고정값 일치 (60.0/30.0, 82.5/88.0)")
