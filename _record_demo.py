# -*- coding: utf-8 -*-
"""_record_demo.py — 데모 스냅샷 녹화(dev 섬): 샘플 정책을 실 LLM 으로 1회 완주해
data/demo_snapshots/<정책명>.json 에 저장한다. 데모 모드는 이 녹화본을 0콜 재생.

- 조립은 ui.state_helpers.run_full_pipeline 과 같은 순서(축1 그래프 invoke →
  축2 run_contrast)를 순수 계층으로 미러링한다 — streamlit 세션 불필요.
- 모델 = graph.llm 현재 프로바이더(.env 의 MIRILAB_LLM). 도장(llm_model)도 그 값.
- 비용: 정책당 약 100콜(react 24 + 인생극장 24x3 + 집계). 재녹화 = 재실행(덮어씀).
- 저장 직후 ui.state_helpers.restore_snapshot 으로 재구성 자가검증(재생 보장).

실행:
  python _record_demo.py                     # 샘플 전부
  python _record_demo.py --only "청년 월세 한시 특별지원"
  python _record_demo.py --n 24 --seed 42    # 기본값
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import graph.llm as gl  # noqa: E402
from graph.build import build_graph  # noqa: E402
from data.personas import load_personas  # noqa: E402
from sample_policies import SAMPLES, SPECS  # noqa: E402
from policy_spec import spec_from_tags, prompt_with_tags  # noqa: E402
from contrast import run_contrast  # noqa: E402
from ui.model import build_view  # noqa: E402
from ui.state_helpers import restore_snapshot, DEMO_SNAPSHOT_DIR  # noqa: E402


def build_spec(name: str, policy: str) -> dict:
    """app.py 사이드바가 샘플 선택 시 만드는 spec 과 동일(SPECS 프리필 + 분류 미지정)."""
    sp = SPECS.get(name) or {}
    return spec_from_tags(
        age=tuple(sp["age"]) if sp.get("age") else None,
        income=list(sp.get("income") or ()) or None,
        family_kw=sp.get("family_kw"),
        channel=sp.get("channel"),
        category="", support_type="",
        name=name, text=policy,
    )


def record_one(app, personas, name: str, policy: str, n: int, seed: int) -> Path:
    """정책 1개 완주(축1→축2) 후 스냅샷 저장 + 재구성 자가검증. 경로 반환."""
    spec = build_spec(name, policy)
    model_policy = prompt_with_tags(policy, spec)

    # ── 축1: run_simulation 실모드와 동일한 initial_state 로 그래프 invoke ──
    initial_state = {
        "policy": model_policy,
        "personas": personas,
        "reactions": [],
        "interactions": [],
        "summary": "",
        "grounded": True,
        "rounds": 1,
        "edges": [],
        "metrics": {},
        "improvements": {},
    }
    t0 = time.time()
    sim = app.invoke(initial_state)
    sim["policy"] = policy            # 표시는 원문(태그 접두 제거) — run_full_pipeline 동일
    sim["policy_spec"] = dict(spec)
    sim["llm_model"] = f"{gl.PROVIDER}:{gl.MODEL}"
    print(f"  axis1 OK ({time.time() - t0:.0f}s, reactions={len(sim.get('reactions') or [])})")

    # ── 축2: run_full_pipeline 실모드와 동일(spec 전달 = 명세 재추출 생략) ──
    view = build_view(sim)
    axis2_spec = dict(spec)
    axis2_spec.setdefault("text", policy)
    t0 = time.time()
    contrast_out = run_contrast(
        personas, [policy], simulate=None,
        grounded=True, use_llm_spec=True,
        specs=[axis2_spec], reactions_by_id=view.get("reactions_by_id"),
    )
    print(f"  axis2 OK ({time.time() - t0:.0f}s, "
          f"residents={len((contrast_out.get('village') or {}).get('residents') or [])})")

    snap = {
        "format": "demo_snapshot_v1",
        "name": name,
        "policy": policy,
        "model_policy": model_policy,
        "spec": dict(spec),
        "n": n,
        "seed": seed,
        "llm_model": sim["llm_model"],
        "sim": sim,
        "contrast": contrast_out,
    }
    DEMO_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_SNAPSHOT_DIR / f"{name}.json"
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    # ── 자가검증: 저장본을 로더의 순수 복원으로 돌려 재생 가능을 보증 ──
    re_snap = json.loads(path.read_text(encoding="utf-8"))
    r_sim, r_view, r_ckpt = restore_snapshot(re_snap)
    assert r_view.get("axis3", {}).get("t0_metrics"), "복원 실패: axis3 t0_metrics 없음"
    assert r_view.get("village"), "복원 실패: village 없음"
    assert r_view.get("selection"), "복원 실패: selection 없음"
    assert "(녹화 재생)" in (r_sim.get("llm_model") or ""), "복원 실패: 도장 라벨"
    assert (r_ckpt.get("axis1") or {}).get("sig", {}).get("mock") is True, \
        "복원 실패: ckpt 데모 취급(mock=True) 아님"
    print(f"  저장+복원검증 OK -> {path} ({path.stat().st_size // 1024}KB)")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="이 정책명만 녹화(기본: 샘플 전부)")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    assert gl.has_real_key(), f"실키 없음 — 프로바이더 {gl.PROVIDER} 키를 .env 에 설정"

    targets = {args.only: SAMPLES[args.only]} if args.only else dict(SAMPLES)
    print(f"[record_demo] model={gl.PROVIDER}:{gl.MODEL}, "
          f"n={args.n}, seed={args.seed}, 정책 {len(targets)}건")

    personas = load_personas(args.n, args.seed)
    app = build_graph()
    done = []
    for i, (name, policy) in enumerate(targets.items(), 1):
        print(f"[{i}/{len(targets)}] {name}")
        done.append(record_one(app, personas, name, policy, args.n, args.seed))

    print()
    print(f"완료: {len(done)}건 -> {DEMO_SNAPSHOT_DIR}")


if __name__ == "__main__":
    main()
