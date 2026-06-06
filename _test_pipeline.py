# -*- coding: utf-8 -*-
"""_test_pipeline.py — §8-1 실행 묶기(run_full_pipeline/rerun_from_axis2) 스모크.

mock 경로(외부 호출 0)로 검증:
1) run_full_pipeline 1회 = 축1→축2 완주 — sim/view/층1 체크포인트가 채워진다.
2) rerun_from_axis2 = 축1(run_simulation) 재호출 0 으로 축2 산출물만 갱신.
3) 단방향(역류 금지) — 재실행 후에도 t0 기록(sim·reactions)은 같은 객체.
실행: python _test_pipeline.py
"""
import sys

import streamlit as st

import ui.state_helpers as sh


def main():
    fails = []

    def check(name: str, ok: bool, detail: str = ""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    # ── 1) 전체 파이프라인 1회(mock) — 축1→축2 완주 + 체크포인트 ──
    sim, view = sh.run_full_pipeline(
        "[태그: 청년] 청년 월세 지원", policy="청년 월세 지원", spec=None, mock=True
    )
    ckpt = st.session_state.get(sh.PIPELINE_CKPT_KEY) or {}
    check("축1 sim 반환(reactions 존재)", bool(sim and sim.get("reactions")))
    check("view.reactions_by_id 시딩 준비", bool(view.get("reactions_by_id")))
    check("축2 selection.outcomes 채움",
          bool((view.get("selection") or {}).get("outcomes")))
    check("축2 village.residents 채움",
          bool((view.get("village") or {}).get("residents")))
    check("층1 체크포인트 axis1", bool((ckpt.get("axis1") or {}).get("sim")))
    check("층1 체크포인트 axis2", bool((ckpt.get("axis2") or {}).get("contrast")))
    check("표시 정책 = 원문(태그 접두 제거)", sim.get("policy") == "청년 월세 지원")
    check("session_state sim/view 저장",
          st.session_state.get("sim") is sim and st.session_state.get("view") is view)

    sel1 = view.get("selection")
    reactions1 = sim.get("reactions")

    # ── 2) 축2부터 재실행 — 축1 호출 0 (전수 react 절약) ──
    calls = {"n": 0}
    orig = sh.run_simulation

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    sh.run_simulation = counting
    try:
        out = sh.rerun_from_axis2()
    finally:
        sh.run_simulation = orig

    check("rerun_from_axis2 동작(체크포인트 재사용)", out is not None)
    check("재실행 중 축1 호출 0", calls["n"] == 0, f"calls={calls['n']}")
    if out:
        sim2, view2 = out
        check("t0 기록 보존(단방향 — sim 동일 객체)", sim2 is sim)
        check("t0 reactions 보존(동일 객체)", sim2.get("reactions") is reactions1)
        check("축2 산출물 갱신(selection 교체)",
              view2.get("selection") is not sel1 and bool(view2.get("selection")))
        ckpt2 = st.session_state.get(sh.PIPELINE_CKPT_KEY) or {}
        check("axis2 체크포인트 갱신", bool((ckpt2.get("axis2") or {}).get("contrast")))

    # ── 3) 체크포인트 없을 때 None(안내 경로) ──
    st.session_state.pop(sh.PIPELINE_CKPT_KEY, None)
    check("체크포인트 없으면 None 반환", sh.rerun_from_axis2() is None)

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
