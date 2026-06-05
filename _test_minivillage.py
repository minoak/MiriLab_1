# -*- coding: utf-8 -*-
"""_test_minivillage.py — 미리마을 탭 조립(assemble_village_html) 회귀 테스트.

streamlit 무의존(순수 함수만 검증). 실행: python _test_minivillage.py
Windows cp949 콘솔 대비 — print 에 이모지/em대시 금지(ASCII 만).
"""
import re
import sys
from pathlib import Path

from ui.tab_minivillage import (
    MINIVILLAGE_ROOT,
    assemble_village_html,
    _DATA_SCRIPTS,
    _SPRITE_IDS,
)

FAILS = []


def check(cond, label):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {label}")
    if not cond:
        FAILS.append(label)


def main():
    root = MINIVILLAGE_ROOT
    check(root.exists(), f"미리마을 루트 존재: {root}")
    check((root / "index.html").exists(), "index.html 존재")

    html = assemble_village_html(root)

    # 1) 외부 참조 0 -------------------------------------------------------
    ext_attr = re.findall(r'(?:src|href)\s*=\s*["\']\s*(?:\./)?(?:assets|data)/[^"\']*', html)
    check(not ext_attr, f"src/href 외부 참조 0 (잔존={ext_attr[:3]})")
    check("assets/map.png" not in html, "map.png 경로 잔존 0")
    check(not re.search(r'assets/sprites/[A-Za-z0-9_]+\.png', html), "스프라이트 경로 잔존 0")
    check('<script src=' not in html, "<script src= 잔존 0 (전부 인라인)")

    # 2) 자산이 실제로 인라인됐는지 ---------------------------------------
    n_pngs = html.count("data:image/png;base64,")
    check(n_pngs >= 11, f"PNG data URI >= 11개 (map+스프라이트10), 실제={n_pngs}")

    # 3) 데이터 JS 내용이 인라인됐는지 (각 파일의 고유 토큰으로 확인) -------
    check("const MEETINGS" in html, "meetings.js 인라인 (const MEETINGS)")
    check("ANCHORS_DEFAULT" in html, "anchors.js 인라인 (ANCHORS_DEFAULT)")
    # village_data.js 의 산출물은 index.html 자체 PATH_DATA 와 겹칠 수 있어,
    # 단순히 3개 src 태그가 모두 사라졌는지로 확인한다.
    for rel in _DATA_SCRIPTS:
        check(f'src="{rel}"' not in html, f"{rel} src 태그 제거됨")

    # 4) 크기 정상 (base64 map 3MB -> 4MB+) -------------------------------
    size_mb = len(html.encode("utf-8")) / (1024 * 1024)
    check(size_mb > 3.0, f"조립 HTML 크기 > 3MB (실제 {size_mb:.1f}MB)")

    # 5) 결정론 — 같은 입력 두 번 조립 시 동일 ----------------------------
    check(html == assemble_village_html(root), "조립 결정론(2회 동일)")

    # 6) 스프라이트 id 개수 = 10 ------------------------------------------
    check(len(_SPRITE_IDS) == 10, f"스프라이트 id 10개 (실제 {len(_SPRITE_IDS)})")

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
