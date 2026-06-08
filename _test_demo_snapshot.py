# -*- coding: utf-8 -*-
"""_test_demo_snapshot.py — 데모 녹화 재생(스냅샷) 키리스 테스트 (외부 호출 0).

가짜 스냅샷(합성 mock 재료 + JSON 라운드트립)으로:
1) restore_snapshot 순수 복원: 도장 라벨 '(녹화 재생)' / 지표 소유권(게이지 3키
   == axis3 t0_metrics) / selection·village 복원 / ckpt 데모 취급(mock=True).
2) has_demo_snapshot / load 폴백: 없는 정책 → False(합성 mock 경로 유지).
3) AppTest 통합: 임시 스냅샷 디렉터리 주입 → 데모 체크 + 실행 클릭 →
   재생 경로 진입(성공 메시지 '녹화') + view.llm_model 라벨 확인.
4) 원문 수정 가드: 정책 텍스트를 고치면 스냅샷이 있어도 합성 경로로.
실행: python _test_demo_snapshot.py
"""
import json
import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

import ui.state_helpers as sh
from sample_policies import SAMPLES
from contrast import run_contrast
from ui.mock import sample_simstate, sample_village
from ui.model import build_view
from _record_demo import build_spec

fails = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def make_fake_snapshot(name: str, policy: str) -> dict:
    """합성 mock 재료로 스냅샷 dict 구성(_record_demo.record_one 의 키리스 미러)."""
    spec = build_spec(name, policy)
    sim = sample_simstate(policy)
    sim["policy"] = policy
    sim["policy_spec"] = dict(spec)
    sim["llm_model"] = "gemini:gemini-3-flash-preview"
    view = build_view(sim)
    axis2_spec = dict(spec)
    axis2_spec.setdefault("text", policy)
    contrast_out = run_contrast(
        view.get("personas") or [], [policy],
        simulate=lambda ps, pol, sl=None: sample_village(ps, pol, step_labels=sl),
        grounded=True, use_llm_spec=False,
        specs=[axis2_spec], reactions_by_id=view.get("reactions_by_id"),
    )
    return {
        "format": "demo_snapshot_v1", "name": name, "policy": policy,
        "model_policy": policy, "spec": dict(spec), "n": 12, "seed": 42,
        "llm_model": sim["llm_model"], "sim": sim, "contrast": contrast_out,
    }


def main():
    name = "청년 월세 한시 특별지원"
    policy = SAMPLES[name].strip()
    # 파일 저장본과 같은 조건으로: JSON 라운드트립(튜플→리스트 등 직렬화 영향 포함)
    snap = json.loads(json.dumps(make_fake_snapshot(name, policy), ensure_ascii=False))

    # ── 1) 순수 복원 ────────────────────────────────────────────────
    sim, view, ckpt = sh.restore_snapshot(snap)
    check("도장 라벨 (녹화 재생)", "(녹화 재생)" in (sim.get("llm_model") or ""),
          sim.get("llm_model", ""))
    check("view 에 도장 통과", "(녹화 재생)" in (view.get("llm_model") or ""))
    t0m = (view.get("axis3") or {}).get("t0_metrics") or {}
    vm = view.get("metrics") or {}
    check("지표 소유권: 게이지 3키 == axis3 t0_metrics",
          bool(t0m) and all(vm.get(k) == t0m.get(k)
                            for k in ("정책수용도", "신청의향지수", "사회혼란도")))
    check("selection 복원", bool((view.get("selection") or {}).get("outcomes")))
    check("village 복원", bool((view.get("village") or {}).get("residents")))
    check("policies = [원문]", view.get("policies") == [policy])
    check("ckpt 데모 취급(axis1 mock=True)",
          (ckpt.get("axis1") or {}).get("sig", {}).get("mock") is True)
    check("ckpt axis2 contrast 보존",
          bool((ckpt.get("axis2") or {}).get("contrast")))

    # ── 2) 없는 스냅샷 → False / None (합성 경로 유지) ────────────────
    orig_dir = sh.DEMO_SNAPSHOT_DIR
    tmp = Path(tempfile.mkdtemp(prefix="demo_snap_"))
    try:
        sh.DEMO_SNAPSHOT_DIR = tmp
        check("빈 디렉터리: has=False", sh.has_demo_snapshot(name) is False)

        # ── 3) AppTest 통합: 임시 디렉터리에 스냅샷 → 재생 경로 ────────
        (tmp / f"{name}.json").write_text(
            json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        check("스냅샷 생성 후 has=True", sh.has_demo_snapshot(name) is True)

        at = AppTest.from_file("app.py", default_timeout=120)
        at.run()
        check("초기 렌더 예외 0", not at.exception)
        at.sidebar.checkbox[0].set_value(True)   # 데모 모드
        at.sidebar.button[0].click()             # 시뮬레이션 실행
        at.run()
        check("재생 실행 예외 0", not at.exception,
              str([str(e.value)[:120] for e in at.exception]) if at.exception else "")
        succ = "\n".join(s.value or "" for s in at.success)
        check("성공 메시지 = 녹화 재생", "녹화" in succ, succ[:120])
        v = at.session_state["view"] if "view" in at.session_state else {}
        check("세션 view 도장 = 녹화 재생",
              "(녹화 재생)" in ((v or {}).get("llm_model") or ""))
        check("세션 view selection 채워짐",
              bool(((v or {}).get("selection") or {}).get("outcomes")))

        # ── 4) 원문 수정 가드: 텍스트 고치면 합성 경로로 ────────────────
        at2 = AppTest.from_file("app.py", default_timeout=120)
        at2.run()
        ta_key = next((t.key for t in at2.sidebar.text_area
                       if (t.key or "").startswith("policy_text::")), None)
        check("정책 원문 위젯 존재", ta_key is not None)
        if ta_key:
            at2.sidebar.text_area(key=ta_key).set_value(policy + "\n(한 줄 수정)")
            at2.sidebar.checkbox[0].set_value(True)
            at2.sidebar.button[0].click()
            at2.run()
            check("수정 실행 예외 0", not at2.exception)
            v2 = at2.session_state["view"] if "view" in at2.session_state else {}
            check("수정 시 합성 경로(mock 도장)",
                  ((v2 or {}).get("llm_model") or "") == "mock",
                  (v2 or {}).get("llm_model", ""))
    finally:
        sh.DEMO_SNAPSHOT_DIR = orig_dir


if __name__ == "__main__":
    main()
    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")
