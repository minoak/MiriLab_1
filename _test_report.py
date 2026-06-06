# -*- coding: utf-8 -*-
"""종합 리포트(report.py) 단위 테스트 — 키리스·외부 호출 0.

    python _test_report.py

검증:
- collect_report_data: mock view 에서 두 축 + 개선안 재료가 결정론으로 수집되는가
- compose_report / generate_report(use_llm=False): 고정 양식 6개 절이 전부 나오는가
- 인생극장 결과(selection) 유무에 따른 3절 분기(사례 vs 미실행 안내)
- 빈 view 방어(죽지 않음) / 결정론(같은 입력 → 같은 출력)
- LLM 경로: 성공(mode=llm) / 실패 시 폴백(mode=fallback) — 전부 monkeypatch, 네트워크 0
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import report as report_mod
from report import collect_report_data, compose_report, fallback_sections, generate_report
from ui.mock import sample_simstate, sample_village
from ui.model import build_view
from contrast import select_trio_from_outcomes

SECTION_HEADERS = [
    "## 1. 요약",
    "## 2. 시민 반응 진단 (시민반응축)",
    "## 3. 접근 여정 사례 (인생극장축)",
    "## 4. 개선 제안",
    "## 5. 수정안 전문",
    "## 6. 한계 노트",
]


def _mock_view() -> dict:
    return build_view(sample_simstate())


def _mock_view_with_theater() -> dict:
    view = _mock_view()
    village = sample_village(view["personas"], view["policy"])
    # specs=[] → 전원 대상(graceful) — 분포·사례 구조 검증에는 충분.
    view["selection"] = select_trio_from_outcomes(
        village["residents"], view["personas"], specs=[]
    )
    view["village"] = village
    return view


def test_collect_basic():
    data = collect_report_data(_mock_view())
    assert data["n"] == 12, data["n"]
    assert set(data["metrics"]) == {"정책수용도", "신청의향지수", "사회혼란도"}
    assert data["funnel"]["base_n"] == 12
    assert sum(data["stance"].values()) == 12
    assert data["quotes"], "시민 목소리 인용이 비어 있음"
    for q in data["quotes"]:
        assert q["name"] and q["text"], q
    assert data["theater"] is None, "인생극장 미실행인데 theater 가 채워짐"
    assert data["easy_text"], "mock 수정안(easy_text)이 비어 있음"
    assert data["date"], "날짜 없음"
    print("ok  collect_report_data 기본 수집(12명·지표·퍼널·인용)")


def test_fallback_report_no_theater():
    out = generate_report(_mock_view(), use_llm=False)
    assert out["mode"] == "fallback"
    md = out["markdown"]
    for h in SECTION_HEADERS:
        assert h in md, f"양식 절 누락: {h}"
    assert md.startswith("# 📋 정책 개선 리포트"), md.splitlines()[0]
    assert "인생극장 미실행" in md, "3절 미실행 안내가 없음"
    assert "한 줄 진단" in md
    assert "재실험" in md, "수정안 재실험 안내(수동 루프)가 없음"
    assert "실제 여론조사가 아닙니다" in md, "한계 노트 누락"
    print("ok  generate_report 폴백 — 고정 양식 6절 + 미실행 안내 + 재실험 안내")


def test_with_theater():
    view = _mock_view_with_theater()
    data = collect_report_data(view)
    th = data["theater"]
    assert th is not None
    assert th["n"] == 12
    assert sum(th["dist"].values()) == 12, th["dist"]

    md = generate_report(view, use_llm=False)["markdown"]
    assert "결과 분포" in md, "3절 결과 분포가 없음"
    assert "인생극장 미실행" not in md, "실행했는데 미실행 안내가 나옴"
    # 사례(수혜/사각 대표)가 있으면 이름이 본문에 들어간다.
    for c in th["cases"]:
        assert c["name"] in md, f"사례 인물({c['name']})이 리포트에 없음"
    print(f"ok  인생극장 종합 — 분포 {th['dist']} + 사례 {len(th['cases'])}건")


def test_empty_view_safe():
    out = generate_report({}, use_llm=False)
    md = out["markdown"]
    for h in SECTION_HEADERS:
        assert h in md, f"빈 view 에서 양식 절 누락: {h}"
    assert out["data"]["n"] == 0
    out2 = generate_report(None, use_llm=False)
    assert out2["markdown"], "None view 에서 리포트가 비어 있음"
    print("ok  빈/None view 방어 (양식 유지·예외 없음)")


def test_deterministic():
    view = _mock_view_with_theater()
    a = generate_report(view, use_llm=False)["markdown"]
    b = generate_report(view, use_llm=False)["markdown"]
    assert a == b, "같은 입력인데 폴백 리포트가 다름(비결정)"
    print("ok  폴백 모드 결정론 (같은 입력 → 같은 리포트)")


def test_llm_mode_mocked():
    """LLM 성공 경로: structured 4칸이 리포트에 들어가고 mode=llm. (네트워크 0)"""
    import graph.llm as llm_mod

    orig_key, orig_llm = llm_mod.has_real_key, report_mod._llm_sections
    try:
        llm_mod.has_real_key = lambda: True
        report_mod._llm_sections = lambda data: {
            "headline": "테스트 한 줄 진단입니다.",
            "diagnosis": "테스트 진단 해석입니다.",
            "proposals": ["테스트 제안 1", "테스트 제안 2"],
            "revised_policy": "테스트 수정안 전문입니다.",
        }
        out = generate_report(_mock_view(), use_llm=True)
        assert out["mode"] == "llm", out["mode"]
        assert "테스트 한 줄 진단입니다." in out["markdown"]
        assert "1. 테스트 제안 1" in out["markdown"]
        assert "테스트 수정안 전문입니다." in out["markdown"]
    finally:
        llm_mod.has_real_key, report_mod._llm_sections = orig_key, orig_llm
    print("ok  LLM 경로(mock) — 4칸 주입 + mode=llm")


def test_llm_failure_falls_back():
    """LLM 호출이 죽어도 리포트는 완성된다(mode=fallback)."""
    import graph.llm as llm_mod

    def _boom(data):
        raise RuntimeError("simulated LLM outage")

    orig_key, orig_llm = llm_mod.has_real_key, report_mod._llm_sections
    try:
        llm_mod.has_real_key = lambda: True
        report_mod._llm_sections = _boom
        out = generate_report(_mock_view(), use_llm=True)
        assert out["mode"] == "fallback", out["mode"]
        for h in SECTION_HEADERS:
            assert h in out["markdown"], f"폴백 리포트 절 누락: {h}"
    finally:
        llm_mod.has_real_key, report_mod._llm_sections = orig_key, orig_llm
    print("ok  LLM 실패 → 폴백 (리포트는 항상 완성)")


def test_partial_llm_fields_kept():
    """LLM 이 일부 칸만 채우면 빈 칸은 폴백이 유지된다."""
    import graph.llm as llm_mod

    orig_key, orig_llm = llm_mod.has_real_key, report_mod._llm_sections
    try:
        llm_mod.has_real_key = lambda: True
        report_mod._llm_sections = lambda data: {
            "headline": "부분 응답 진단.", "diagnosis": "",
            "proposals": [], "revised_policy": "",
        }
        view = _mock_view()
        out = generate_report(view, use_llm=True)
        fb = fallback_sections(collect_report_data(view))
        assert "부분 응답 진단." in out["markdown"]
        assert fb["revised_policy"][:30] in out["markdown"], "빈 칸이 폴백으로 안 채워짐"
    finally:
        llm_mod.has_real_key, report_mod._llm_sections = orig_key, orig_llm
    print("ok  부분 LLM 응답 — 빈 칸은 폴백 유지")


def test_quote_markdown_injection_flattened():
    """반응문의 개행·헤딩이 리포트 고정 양식을 깨지 못한다(한 칸으로 접힘)."""
    view = _mock_view()
    for r in view["reactions"]:
        r["text"] = "한 줄\n## 7. 주입된 절\n> 인용 깨기"
    data = collect_report_data(view)
    assert data["quotes"], "인용이 비어 검증 불가"
    for q in data["quotes"]:
        assert "\n" not in q["text"], q["text"]
    md = generate_report(view, use_llm=False)["markdown"]
    # 마크다운 헤딩은 '줄 시작'에서만 성립 — 개행이 접혔으니 줄 시작에 나오면 안 됨.
    assert not any(line.startswith("## 7.") for line in md.splitlines()), \
        "반응문이 새 절(##)을 주입함"
    print("ok  반응문 마크다운 주입 방어 (개행 접기)")


def test_theater_provenance_gate():
    """패키지 데모(다정책) 결과는 리포트 3절에 섞이지 않는다(출처 게이트)."""
    view = _mock_view_with_theater()
    view["policies"] = ["정책A", "정책B"]          # 패키지 데모 출처 흉내
    data = collect_report_data(view)
    assert data["theater"] is None, "다정책 결과가 게이트를 통과함"
    assert data["theater_foreign"] is True
    md = generate_report(view, use_llm=False)["markdown"]
    assert "패키지 데모" in md, "출처 불일치 안내가 없음"

    view["policies"] = [view["policy"]]            # 단일 정책 출처(정상)
    data2 = collect_report_data(view)
    assert data2["theater"] is not None and data2["theater_foreign"] is False
    view["policies"] = []                          # 출처 기록 없음 → 관대
    assert collect_report_data(view)["theater"] is not None
    print("ok  인생극장 출처 게이트 (패키지 데모 차단·단일 정책 통과)")


def test_llm_mode_keeps_deterministic_sections():
    """LLM 모드에서도 결정론 칸(퍼널·분포·인용·한계노트)은 코드 산출 그대로다."""
    import graph.llm as llm_mod

    orig_key, orig_llm = llm_mod.has_real_key, report_mod._llm_sections
    try:
        llm_mod.has_real_key = lambda: True
        report_mod._llm_sections = lambda data: {
            "headline": "LLM 진단.", "diagnosis": "LLM 해석.",
            "proposals": ["LLM 제안"], "revised_policy": "LLM 수정안.",
        }
        view = _mock_view_with_theater()
        out = generate_report(view, use_llm=True)
        md = out["markdown"]
        data = out["data"]
        assert "응답 시민 12명" in md, "퍼널(결정론)이 사라짐"
        assert "결과 분포" in md, "인생극장 분포(결정론)가 사라짐"
        assert data["quotes"][0]["name"] in md, "시민 인용(결정론)이 사라짐"
        assert "실제 여론조사가 아닙니다" in md, "한계 노트(고정문구)가 사라짐"
    finally:
        llm_mod.has_real_key, report_mod._llm_sections = orig_key, orig_llm
    print("ok  LLM 모드에서 결정론 칸 보존 (계약 1)")


def test_no_helpdesk_duplication():
    """policy_fixes 가 비어도 4절에 도움창구 제안이 두 번 나오지 않는다."""
    view = _mock_view()
    view["improvements"]["policy_fixes"] = []
    data = collect_report_data(view)
    assert data["helpdesk"], "도움창구 제안이 없어 검증 불가"
    md = generate_report(view, use_llm=False)["markdown"]
    for rec in data["helpdesk"]:
        assert md.count(rec) == 1, f"도움창구 제안 중복: {rec}"
    print("ok  4절 도움창구 제안 중복 없음 (policy_fixes 빈 경우)")


def test_stale_helper():
    """신선도 판정: 분포가 같아도 사례 인물이 바뀌면 stale 로 잡는다."""
    import copy
    from ui.tab_improve import _report_theater_stale

    view = _mock_view_with_theater()
    rep = generate_report(view, use_llm=False)
    assert _report_theater_stale(rep, view) is False, "같은 결과인데 stale 판정"

    view2 = copy.deepcopy(view)
    for t in view2["selection"]["trio"]:           # 분포 동일·인물명만 변경
        (t.get("persona") or {})["name"] = "바뀐사람"
    assert _report_theater_stale(rep, view2) is True, "사례 변경을 못 잡음"

    rep_plain = generate_report(_mock_view(), use_llm=False)   # 미실행 시점 리포트
    assert _report_theater_stale(rep_plain, view) is True, "미실행→실행 전환을 못 잡음"
    print("ok  신선도 스냅샷 비교 (분포 동일·사례 변경 / 미실행→실행)")


def main():
    test_collect_basic()
    test_fallback_report_no_theater()
    test_with_theater()
    test_empty_view_safe()
    test_deterministic()
    test_llm_mode_mocked()
    test_llm_failure_falls_back()
    test_partial_llm_fields_kept()
    test_quote_markdown_injection_flattened()
    test_theater_provenance_gate()
    test_llm_mode_keeps_deterministic_sections()
    test_no_helpdesk_duplication()
    test_stale_helper()
    print("\n전부 통과")


if __name__ == "__main__":
    main()
