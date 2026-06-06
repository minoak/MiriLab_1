# -*- coding: utf-8 -*-
"""_test_axis3.py — §8-4 축3 집계(aggregate_axis3) 스모크 (순수, LLM 0).

손계산 가능한 작은 풀로 검증:
- 결과 5범주(대상자) + out 분리, inprogress 의 aware멈춤/applied대기 세분
- 낙차 = t0 적극 의향 비율 − 종점 수령 비율 (둘 다 대상자 모수·인원 비율)
- 깔때기(의향→도달→신청→수령, ever 기준) / 전향(intent<50 ∧ 수령)
- 대상자 0 이면 비율 None / mock 통합에서 죽지 않음 / 비신청형 분기 헬퍼
실행: python _test_axis3.py
"""
import sys

from axis3 import aggregate_axis3, is_application_policy


def _resident(pid, name, statuses):
    """status 시퀀스로 최소 timeline 을 만든다(다리 가드 충족: 경로·barrier 채움)."""
    tl = []
    for i, s in enumerate(statuses):
        tl.append({
            "step": i + 1, "label": f"{i+1}개월", "place": "welfare_center",
            "reached_via": "" if s == "unaware" else "복지사 안내",
            "action": "...", "policy_status": s,
            "barrier": "서류 미비" if s == "blocked" else "",
            "economic": 50, "wellbeing": 50, "note": "",
        })
    return {"id": pid, "name": name, "timeline": tl,
            "policy_status": statuses[-1], "economic": 50, "wellbeing": 50}


def _persona(pid, age):
    return {"id": pid, "name": pid, "demographics": {"age": age},
            "signals": {"income_level": "low"}}


def _reaction(intent):
    return {"persona_id": "x", "scores": {"intent": intent}}


def main():
    fails = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    # 대상 = 19~34세(spec). A·B·C·E 대상(25세), D 비대상(70세).
    specs = [{"name": "청년 정책", "age": (19, 34), "income": ("low", "mid"),
              "family_kw": None, "channel": "online_portal"}]
    personas = [_persona(p, 25) for p in ("A", "B", "C", "E")] + [_persona("D", 70)]
    residents = [
        _resident("A", "A", ["unaware", "aware", "received"]),   # 적극 의향 → 수령
        _resident("B", "B", ["unaware", "aware", "received"]),   # 의향 없음 → 수령 = 전향
        _resident("C", "C", ["unaware", "unaware", "unaware"]),  # 적극 의향 → 못 닿음
        _resident("E", "E", ["aware", "aware", "aware"]),        # 적극 의향 → 알고도 멈춤
        _resident("D", "D", ["unaware", "aware", "received"]),   # 비대상 → out (수령해도)
    ]
    rx = {"A": _reaction(75), "B": _reaction(25), "C": _reaction(100),
          "E": _reaction(75), "D": _reaction(100)}
    village = {"steps": ["1", "3", "6"], "residents": residents,
               "aggregate": {"bridge_guard": {"retries": 1, "residuals": 0}}}

    a3 = aggregate_axis3(rx, village, personas, specs)

    check("모수: n=5, n_target=4", (a3["n"], a3["n_target"]) == (5, 4))
    check("5범주: received=2", a3["outcomes"]["received"] == 2)
    check("5범주: unaware=1", a3["outcomes"]["unaware"] == 1)
    check("5범주: aware멈춤=1", a3["outcomes"]["aware_stalled"] == 1)
    check("5범주: out=1(비대상 수령은 모수 밖)", a3["outcomes"]["out"] == 1)
    check("수령률 = 2/4 (대상자 모수)", abs(a3["received_rate"] - 0.5) < 1e-9)
    check("t0 적극 의향 = 3/4 (A·C·E)", abs(a3["intent_rate_t0"] - 0.75) < 1e-9)
    check("낙차 = 0.75-0.5 = +0.25", abs(a3["gap"] - 0.25) < 1e-9)
    check("사각 = (0+1)/4", abs(a3["blindspot_rate"] - 0.25) < 1e-9)
    fc = {f["key"]: f["count"] for f in a3["funnel"]}
    check("깔때기: 의향3 → 도달3 → 신청2 → 수령2",
          (fc["intent"], fc["reached"], fc["applied"], fc["received"]) == (3, 3, 2, 2),
          f"got={fc}")
    check("전향 = B 1명 (intent25 → 수령)",
          a3["n_conversion"] == 1 and a3["conversions"][0]["id"] == "B")
    check("guard 패스스루", a3["guard"] == {"retries": 1, "residuals": 0})
    check("missing_t0 = 0", a3["missing_t0"] == 0)

    # ── blocked 단독은 신청 깔때기 미달(보수) + blocked 범주 ──
    residents2 = [_resident("A", "A", ["aware", "blocked", "blocked"])]
    a3b = aggregate_axis3({"A": _reaction(75)}, {"residents": residents2},
                          [_persona("A", 25)], specs)
    fc2 = {f["key"]: f["count"] for f in a3b["funnel"]}
    check("blocked 단독: 도달1·신청0", (fc2["reached"], fc2["applied"]) == (1, 0))
    check("blocked 범주 집계", a3b["outcomes"]["blocked"] == 1)

    # ── 대상자 0 → 비율 None(0%와 구분) ──
    a3z = aggregate_axis3({}, {"residents": [_resident("D", "D", ["unaware"])]},
                          [_persona("D", 70)], specs)
    check("대상자 0: received_rate=None", a3z["received_rate"] is None)
    check("대상자 0: gap=None", a3z["gap"] is None)

    # ── t0 기록 누락 → missing_t0 카운트(분모는 대상자 유지) ──
    a3m = aggregate_axis3({}, {"residents": [_resident("A", "A", ["aware"])]},
                          [_persona("A", 25)], specs)
    check("t0 누락 카운트", a3m["missing_t0"] == 1)
    check("t0 누락이어도 분모는 대상자", a3m["n_target"] == 1)

    # ── t0 지표(v1.2 §8-13): 공통 공식과 일치 + village 없이도 산출 ──
    from metrics_common import application_index, policy_acceptance, social_unrest
    rx_list = list(rx.values())
    t0 = a3["t0_metrics"]
    check("t0 지표: metrics_common 공식과 일치",
          bool(t0) and t0["정책수용도"] == policy_acceptance(rx_list)
          and t0["신청의향지수"] == application_index(rx_list)
          and t0["사회혼란도"] == social_unrest(rx_list) and t0["n"] == 5)
    # 손계산: intent 75·25·100·75·100 → 평균 75, 적극층(≥60) 4/5 → 0.6·75+0.4·80 = 77.0
    check("t0 의향지수 손계산 = 77.0", t0["신청의향지수"] == 77.0,
          f"got={t0['신청의향지수']}")
    a3t = aggregate_axis3(rx, None, personas, specs)
    check("village=None: t0 지표는 산출(2단 표시 대비)",
          (a3t["t0_metrics"] or {}).get("n") == 5)
    check("village=None: 결과율은 None(측정 불가)", a3t["received_rate"] is None)
    check("t0 기록 없음 → t0_metrics=None",
          aggregate_axis3({}, None, personas, specs)["t0_metrics"] is None)

    # ── 비신청형 분기 헬퍼 ──
    check("감면 → 비신청형", not is_application_policy({"support_type": "감면"}))
    check("현금 → 신청형", is_application_policy({"support_type": "현금"}))
    check("미지정 → 신청형(보수)", is_application_policy({"support_type": ""}))
    check("spec 없음 → 신청형", is_application_policy(None))

    # ── mock 통합: 실제 mock 풀에서 죽지 않고 모수 합 일치 ──
    from ui.mock import sample_simstate, sample_village
    from ui.model import build_view
    sim = sample_simstate("청년 월세 지원")
    view = build_view(sim)
    mock_village = sample_village(view["personas"], "청년 월세 지원")
    a3mock = aggregate_axis3(view["reactions_by_id"], mock_village,
                             view["personas"], specs)
    total = sum(a3mock["outcomes"].values())
    check("mock 통합: 범주 합 = 전원", total == a3mock["n"],
          f"sum={total}, n={a3mock['n']}")
    check("mock 통합: 대상자+out = 전원",
          a3mock["n_target"] + a3mock["outcomes"]["out"] == a3mock["n"])

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
