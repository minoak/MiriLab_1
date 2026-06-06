# -*- coding: utf-8 -*-
"""_migrate_demo_snapshots.py — 데모 녹화본의 selection 결정론 재계산 (LLM 0콜).

용도: contrast 의 라벨 로직(_outcome_headline 등)이 바뀌면, 녹화본 안에 저장된
selection(헤드라인·그룹·노트)이 옛 문구를 그대로 갖고 있다. 시뮬 원본(village
타임라인·personas·specs)은 그대로 두고 selection 만 현행 코드로 다시 만든다.
run_contrast 의 3)~ 끝 단계(select_trio_from_outcomes + 다리 가드 노트)를 미러링.

실행: python _migrate_demo_snapshots.py        # 전체
      python _migrate_demo_snapshots.py --dry  # 변경될 헤드라인만 미리보기
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from contrast import select_trio_from_outcomes  # noqa: E402
from ui.state_helpers import restore_snapshot, DEMO_SNAPSHOT_DIR  # noqa: E402


def rebuild_selection(snap: dict) -> dict:
    """저장된 시뮬 원본에서 selection 을 현행 코드로 재계산(run_contrast 미러)."""
    contrast_out = snap.get("contrast") or {}
    village = contrast_out.get("village") or {}
    personas = (snap.get("sim") or {}).get("personas") or []
    specs = contrast_out.get("specs") or []

    selection = select_trio_from_outcomes(
        village.get("residents") or [], personas, specs
    )
    # 다리 가드 정직 노트 재부착(run_contrast 와 동일).
    bg = (village.get("aggregate") or {}).get("bridge_guard") or {}
    if bg.get("retries"):
        selection.setdefault("notes", []).append(
            f"ⓘ 다리 가드: 경로(reached_via)·막힌 지점(barrier) 누락 "
            f"{bg['retries']}건을 그 주민·그 시점만 재생성했습니다."
        )
    if bg.get("residuals"):
        selection.setdefault("notes", []).append(
            f"⚠ 다리 가드: 모순 감지 {bg['residuals']}건 — 재생성 후에도 경로가 비어 "
            f"직전 경로 상속/'(기록 누락)' 표기로 교정했습니다(라벨은 뒤집지 않음)."
        )
    return selection


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="쓰지 않고 변경 미리보기만")
    args = ap.parse_args()

    paths = sorted(DEMO_SNAPSHOT_DIR.glob("*.json"))
    assert paths, f"녹화본 없음: {DEMO_SNAPSHOT_DIR}"
    for path in paths:
        snap = json.loads(path.read_text(encoding="utf-8"))
        old_sel = (snap.get("contrast") or {}).get("selection") or {}
        new_sel = rebuild_selection(snap)

        old_h = {(t.get("persona") or {}).get("id"): t.get("headline")
                 for t in old_sel.get("trio") or []}
        new_h = {(t.get("persona") or {}).get("id"): t.get("headline")
                 for t in new_sel.get("trio") or []}
        print(f"[{path.name}]")
        for pid, h in new_h.items():
            mark = "*" if old_h.get(pid) != h else " "
            print(f"  {mark} {pid}: {h}")

        # 불변식: 선별 입력(시뮬 원본)이 같으니 trio 구성원도 같아야 한다.
        assert set(old_h) == set(new_h), f"trio 구성원이 달라짐: {path.name}"

        if not args.dry:
            snap["contrast"]["selection"] = new_sel
            snap["contrast"]["trio_ids"] = [
                (t.get("persona") or {}).get("id") for t in new_sel.get("trio", [])
            ]
            path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            # 재생 가능 자가검증(_record_demo 와 동일 기준).
            re_snap = json.loads(path.read_text(encoding="utf-8"))
            _sim, r_view, _ckpt = restore_snapshot(re_snap)
            assert (r_view.get("selection") or {}).get("outcomes"), "복원 실패"
            print("  -> 저장+복원검증 OK")

    if args.dry:
        print("\n(--dry: 파일 미변경)")


if __name__ == "__main__":
    main()
