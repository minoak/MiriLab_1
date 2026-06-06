# -*- coding: utf-8 -*-
"""_test_app_pipeline.py — §8-2·5 통합(AppTest) 스모크: 한 버튼 = 축1→축2→축3.

데모 모드 체크 후 사이드바 버튼 1회 클릭(외부 호출 0)으로:
- sim/view 채워짐 + view.axis3(낙차·깔때기) 존재
- 층1 체크포인트(axis1/axis2) 생성
- 전 탭 렌더 예외 0 (대시보드 축3 섹션 포함)
실행: python _test_app_pipeline.py
"""
import sys

from streamlit.testing.v1 import AppTest

from ui.state_helpers import PIPELINE_CKPT_KEY

# 데모 녹화 스냅샷 우회 — 이 테스트는 합성 mock 파이프라인 조립 자체를 검증한다
# (녹화본이 있으면 데모 실행이 재생 경로로 빠져 검증 대상이 바뀜).
import ui.state_helpers as _sh
_sh.DEMO_SNAPSHOT_DIR = _sh.DEMO_SNAPSHOT_DIR / "_disabled_for_tests"


def main():
    fails = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    at = AppTest.from_file("app.py", default_timeout=180)
    at.run()
    check("초기 렌더 예외 0", not at.exception,
          str([str(e.value)[:80] for e in at.exception]) if at.exception else "")

    # 데모 모드 강제(키 유무와 무관하게 외부 호출 0 보장) 후 실행 버튼 클릭.
    demo_cb = at.sidebar.checkbox[0]
    demo_cb.set_value(True)
    run_btn = at.sidebar.button[0]
    run_btn.click()
    at.run()

    check("실행 후 예외 0", not at.exception,
          str([str(e.value)[:120] for e in at.exception]) if at.exception else "")

    sim = at.session_state["sim"] if "sim" in at.session_state else None
    view = at.session_state["view"] if "view" in at.session_state else None
    ckpt = (at.session_state[PIPELINE_CKPT_KEY]
            if PIPELINE_CKPT_KEY in at.session_state else {}) or {}

    check("한 버튼: sim 채워짐", bool(sim and sim.get("reactions")))
    check("한 버튼: 축2 village 채워짐",
          bool(view and (view.get("village") or {}).get("residents")))
    check("한 버튼: 축2 selection 채워짐",
          bool(view and (view.get("selection") or {}).get("outcomes")))
    a3 = (view or {}).get("axis3") or {}
    check("한 버튼: 축3 집계 채워짐(낙차·깔때기)",
          bool(a3) and "gap" in a3 and len(a3.get("funnel") or []) == 4)

    # v1.2 지표 소유권: 게이지 3키(view.metrics) == axis3 t0_metrics (단일 진실원)
    t0m = a3.get("t0_metrics") or {}
    vm = (view or {}).get("metrics") or {}
    check("지표 소유권(v1.2): view.metrics 게이지 3키 == axis3 t0_metrics",
          bool(t0m) and all(vm.get(k) == t0m.get(k)
                            for k in ("정책수용도", "신청의향지수", "사회혼란도")),
          str({k: (vm.get(k), t0m.get(k))
               for k in ("정책수용도", "신청의향지수", "사회혼란도")}))
    check("층1 체크포인트 axis1+axis2",
          bool((ckpt.get("axis1") or {}).get("sim"))
          and bool((ckpt.get("axis2") or {}).get("contrast")))

    # 대시보드 축3 헤드라인 metric 4종이 그려졌는가(낙차 +사각 포함).
    metric_labels = [m.label for m in at.metric]
    check("대시보드 낙차 metric 표시",
          any("낙차" in (l or "") for l in metric_labels),
          f"metrics={metric_labels}")

    # ── 비신청형 분기(§5): 지원 형태 '감면' → 낙차 헤드라인이 숨는다 ──
    at2 = AppTest.from_file("app.py", default_timeout=180)
    at2.run()
    sup_key = next((sb.key for sb in at2.sidebar.selectbox
                    if (sb.key or "").startswith("tag_sup::")), None)
    check("지원 형태 셀렉터 존재", sup_key is not None)
    if sup_key:
        at2.sidebar.selectbox(key=sup_key).set_value("감면")
        at2.sidebar.checkbox[0].set_value(True)
        at2.sidebar.button[0].click()
        at2.run()
        check("비신청형 실행 예외 0", not at2.exception,
              str([str(e.value)[:120] for e in at2.exception]) if at2.exception else "")
        labels2 = [m.label for m in at2.metric]
        check("비신청형: 낙차 헤드라인 숨김",
              not any("낙차" in (l or "") for l in labels2), f"metrics={labels2}")

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
