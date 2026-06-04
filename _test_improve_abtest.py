# -*- coding: utf-8 -*-
"""정책 개선 탭 ②(A/B) 비교 로직 단위 테스트(순수, streamlit 무의존).

    python _test_improve_abtest.py
"""

from ui.tab_abtest import compute_comparison, stance_counts


def _view(metrics, reactions=None):
    return {"metrics": metrics, "reactions": reactions or []}


def _m(acc, intent, unrest, **axes):
    """metrics dict 헬퍼."""
    base = {
        "정책수용도": acc, "신청의향지수": intent, "사회혼란도": unrest,
        "understanding": 50, "benefit": 50, "intent": intent,
        "dissatisfaction": unrest, "shareability": 50,
    }
    base.update(axes)
    return base


def test_stance_counts():
    v = _view({}, [
        {"stance": "support"}, {"stance": "support"},
        {"stance": "oppose"}, {"stance": "mixed"},
        {"stance": "UNKNOWN"},  # 알 수 없는 입장 → 혼합으로
    ])
    c = stance_counts(v)
    assert c == {"support": 2, "mixed": 2, "oppose": 1}, c
    print("ok  stance_counts (+미지 입장 혼합 처리)")


def test_comparison_structure():
    a = _view(_m(40, 30, 60), [{"stance": "oppose"}])
    b = _view(_m(55, 45, 50), [{"stance": "support"}])
    comp = compute_comparison(a, b)
    assert {"key_metrics", "axes", "stance", "verdict", "verdict_kind"} <= set(comp)
    # 핵심 지표 3종, 5축
    assert len(comp["key_metrics"]) == 3
    assert len(comp["axes"]) == 5
    # delta = 개선안 - 원문
    labels = {label: (a_, b_, d) for label, a_, b_, d, _ in comp["key_metrics"]}
    assert labels["정책수용도"] == (40.0, 55.0, 15.0)
    assert labels["사회혼란도"][2] == -10.0  # 60 -> 50
    print("ok  compute_comparison 구조/델타")


def test_verdict_good():
    # 수용도 크게↑ + 혼란도↓ → good
    a = _view(_m(40, 30, 70))
    b = _view(_m(60, 50, 55))
    comp = compute_comparison(a, b)
    assert comp["verdict_kind"] == "good", comp["verdict"]
    print("ok  verdict good (수용도↑·혼란도↓)")


def test_verdict_bad():
    # 수용도↓ + 혼란도↑ → bad
    a = _view(_m(60, 50, 40))
    b = _view(_m(45, 35, 60))
    comp = compute_comparison(a, b)
    assert comp["verdict_kind"] == "bad", comp["verdict"]
    print("ok  verdict bad (수용도↓·혼란도↑)")


def test_verdict_flat():
    # 거의 변화 없음 → mixed(변화 없음 문구)
    a = _view(_m(50, 50, 50))
    b = _view(_m(50.5, 50.5, 49.5))
    comp = compute_comparison(a, b)
    assert comp["verdict_kind"] == "mixed"
    assert "거의 없습니다" in comp["verdict"]
    print("ok  verdict flat (노이즈 무시)")


def test_missing_metrics_safe():
    # metrics 누락에도 0.0 으로 안전
    comp = compute_comparison({}, {})
    assert all(a == 0.0 and b == 0.0 for _, a, b, _, _ in comp["key_metrics"])
    print("ok  metrics 누락 방어")


def main():
    test_stance_counts()
    test_comparison_structure()
    test_verdict_good()
    test_verdict_bad()
    test_verdict_flat()
    test_missing_metrics_safe()
    print("\n전부 통과")


if __name__ == "__main__":
    main()
