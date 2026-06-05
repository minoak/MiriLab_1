# -*- coding: utf-8 -*-
"""access_analysis 단위 테스트(헤드리스, 결정론).

mock 12명 + '청년 월세'(만 19~34, 저/중간소득) spec 으로 손계산한 값을 못박는다.
windows cp949 대비: print 에 이모지/em대시 금지(ASCII 만).

실행: python _test_access.py   (성공 시 종료코드 0, "ALL PASS")
"""
import sys

from ui.mock import sample_simstate
from ui.model import build_view
import access_analysis as AA


YOUTH_SPEC = {
    "name": "청년 월세 한시 특별지원",
    "age": (19, 34),
    "income": ("low", "mid"),
    "family_kw": None,
    "channel": "online_portal",
}


def _view(n=12, spec=YOUTH_SPEC):
    sim = sample_simstate(n=n)
    view = build_view(sim)
    if spec is not None:
        view["policy_spec"] = spec
    return view


def _persona(pid, age, dl=0.6, trust=0.5, income="mid"):
    """합성 페르소나(나이/신호만 — policy_access·access_by_age 검증용)."""
    return {
        "id": pid, "name": pid,
        "demographics": {"age": age, "family_type": ""},
        "signals": {"digital_literacy": dl, "government_trust": trust,
                    "income_level": income},
    }


def _react(pid, understanding=60, benefit=40, intent=40):
    return {
        "persona_id": pid, "stance": "mixed", "actions": [],
        "scores": {"understanding": understanding, "benefit": benefit,
                   "intent": intent, "dissatisfaction": 50, "shareability": 50},
    }


def test_funnel_spec_path():
    """청년월세 spec 퍼널 = [12, 8, 4, 4, 3] (손계산 못박기)."""
    view = _view()
    f = AA.application_funnel(
        view["personas"], view["reactions_by_id"], AA.specs_from_view(view)
    )
    counts = [s["count"] for s in f["stages"]]
    assert f["base_n"] == 12, f["base_n"]
    assert counts == [12, 8, 4, 4, 3], counts
    # 단조 감소 + drop/pct 일관성
    for i, s in enumerate(f["stages"]):
        assert 0 <= s["count"] <= f["base_n"]
        assert s["pct"] == round(s["count"] / 12 * 100)
        if i > 0:
            assert s["drop"] == f["stages"][i - 1]["count"] - s["count"]
            assert s["count"] <= f["stages"][i - 1]["count"]
    print("[OK] funnel spec path = [12,8,4,4,3]")


def test_funnel_no_spec_proxy():
    """spec 없으면 자격 단계가 benefit>=50 근사. 여전히 단조 감소."""
    view = _view(spec=None)
    assert AA.specs_from_view(view) == []
    f = AA.application_funnel(view["personas"], view["reactions_by_id"], [])
    counts = [s["count"] for s in f["stages"]]
    assert counts[0] == 12
    assert all(counts[i] <= counts[i - 1] for i in range(1, len(counts))), counts
    print("[OK] funnel no-spec proxy monotonic:", counts)


def test_barriers():
    """병목 요인: 디지털4 / 이해4 / 기준혼란1 / 신청포기1, 주요병목=디지털 장벽."""
    view = _view()
    specs = AA.specs_from_view(view)
    bars = AA.barrier_factors(view["personas"], view["reactions_by_id"], specs)
    by_key = {b["key"]: b["count"] for b in bars}
    assert by_key.get("digital") == 4, by_key
    assert by_key.get("understand") == 4, by_key
    assert by_key.get("criteria") == 1, by_key
    assert by_key.get("giveup") == 1, by_key
    # 내림차순 정렬
    cnts = [b["count"] for b in bars]
    assert cnts == sorted(cnts, reverse=True), cnts
    assert AA.main_bottleneck(bars) == "디지털 장벽", AA.main_bottleneck(bars)
    print("[OK] barriers digital/understand=4, criteria/giveup=1, main=디지털 장벽")


def test_age_access():
    """연령대별 접근성: 나이 들수록 접근도 하락(19~24 > 55+), 밴드 인원 합=나이있는 시민수."""
    view = _view()
    rows = AA.access_by_age(view["personas"])
    assert [r["band"] for r in rows] == ["24세 이하", "25~34세", "35~54세", "55세 이상"]
    pcts = [r["pct"] for r in rows]
    # 단조 비증가(나이 ↑ → 접근 ↓). mock 분포가 그렇게 설계됨.
    assert pcts == sorted(pcts, reverse=True), pcts
    assert pcts[0] >= 70 and pcts[-1] <= 40, pcts   # 청년 높고 고령 낮음
    assert sum(r["n"] for r in rows) == 12, rows     # mock 전원 나이 있음
    print("[OK] age access decreasing with age:", pcts)


def test_barriers_no_spec_omits_target_factors():
    """specs 없으면 대상 기반 병목(criteria/giveup)을 0으로 위장하지 않고 생략(F1)."""
    personas = [_persona("a", 30), _persona("b", 40)]
    rbi = {"a": _react("a", understanding=60, benefit=40, intent=40),
           "b": _react("b", understanding=30, benefit=80, intent=80)}
    bars = AA.barrier_factors(personas, rbi, [])  # specs 없음
    keys = {b["key"] for b in bars}
    assert "criteria" not in keys, keys
    assert "giveup" not in keys, keys
    assert keys <= {"digital", "understand"}, keys
    print("[OK] no-spec barriers omit target-dependent factors (criteria/giveup)")


def test_age_access_out_of_band_no_drop():
    """밴드 밖 나이(18세)도 무음 누락 없이 '24세 이하'에 흡수(F3)."""
    personas = [_persona("x", 18), _persona("y", 30), _persona("z", 70)]
    rows = AA.access_by_age(personas)
    assert sum(r["n"] for r in rows) == 3, rows
    first = next(r for r in rows if r["band"] == "24세 이하")
    assert first["n"] == 1, first
    print("[OK] age access absorbs out-of-band age (18 -> 24세 이하), no silent drop")


def test_priority_and_helpdesk():
    """우선 지원(접근<40%)=4명, 도움창구 제안에 오프라인 병행 + 40% 미만 보조 포함."""
    view = _view()
    pri = AA.priority_citizens(view["personas"], view["reactions_by_id"])
    assert pri["count"] == 4, pri
    assert pri["threshold_pct"] == 40, pri
    specs = AA.specs_from_view(view)
    bars = AA.barrier_factors(view["personas"], view["reactions_by_id"], specs)
    recs = AA.helpdesk_recommendations(bars, pri)
    joined = " ".join(recs)
    assert "병행" in joined, recs                 # 디지털 장벽 → 오프라인 병행
    assert "40% 미만" in joined and "4명" in joined, recs
    print("[OK] priority=4, helpdesk recs include offline + 40% support")


def test_analyze_bundle_and_empty():
    """analyze 묶음 키 + 빈 view 안전."""
    view = _view()
    a = AA.analyze(view)
    for k in ("funnel", "age_access", "barriers", "priority", "helpdesk", "main_bottleneck"):
        assert k in a, k
    assert a["funnel"]["base_n"] == 12
    assert a["main_bottleneck"] == "디지털 장벽"
    # 빈 입력 방어
    empty = AA.analyze({})
    assert empty["funnel"]["base_n"] == 0
    assert empty["barriers"] == []
    assert empty["priority"]["count"] == 0
    assert empty["main_bottleneck"] == ""
    print("[OK] analyze bundle keys + empty-view safe")


def main():
    tests = [
        test_funnel_spec_path,
        test_funnel_no_spec_proxy,
        test_barriers,
        test_barriers_no_spec_omits_target_factors,
        test_age_access,
        test_age_access_out_of_band_no_drop,
        test_priority_and_helpdesk,
        test_analyze_bundle_and_empty,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print("[FAIL]", t.__name__, "->", repr(e))
        except Exception as e:
            failed += 1
            print("[ERROR]", t.__name__, "->", repr(e))
    if failed:
        print(f"\n{failed} test(s) failed.")
        sys.exit(1)
    print("\nALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
