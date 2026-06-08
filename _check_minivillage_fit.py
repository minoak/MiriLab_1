# -*- coding: utf-8 -*-
"""미리마을 scale-to-fit 검증(일회용 dev).

1) assemble_village_html 통과(외부 참조 0 단언 포함) + fitMap 코드 포함 확인
2) 조립본을 임시 파일로 떨어뜨려 셀레늄 헤드리스로 두 가지 폭에서 스크린샷
   -> map-wrap 의 실표시 크기(getBoundingClientRect)가 가용 영역 안인지 assert
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ui.tab_minivillage import assemble_village_html, MINIVILLAGE_ROOT

html = assemble_village_html(MINIVILLAGE_ROOT)
assert "fitMap" in html, "fitMap JS missing"
assert "mapScale" in html, "mapScale wrapper missing"
assert "MAP_SCALE" in html, "MAP_SCALE missing"
print("[1/2] assemble OK (외부참조 0 단언 통과, fitMap 포함, %.1f MB)" % (len(html) / 1e6))

tmp = ROOT / "_ui_shots" / "_minivillage_fit_test.html"
tmp.parent.mkdir(exist_ok=True)
tmp.write_text(html, encoding="utf-8")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

results = []
for w, h, label in ((1200, 620, "wide-1200"), (860, 620, "narrow-860")):
    opt = Options()
    opt.add_argument("--headless=new")
    opt.add_argument(f"--window-size={w},{h}")
    drv = webdriver.Chrome(options=opt)
    try:
        drv.get(tmp.as_uri())
        import time; time.sleep(1.5)
        rect = drv.execute_script(
            "const r=document.getElementById('mapWrap').getBoundingClientRect();"
            "const a=document.querySelector('.map-area');"
            "return {w:r.width,h:r.height,aw:a.clientWidth,ah:a.clientHeight,"
            "scale:window.MAP_SCALE||null};")
        # MAP_SCALE 는 let 이라 window 에 안 잡힘 -> 표시 크기로 판정
        ok = rect["w"] <= rect["aw"] and rect["h"] <= rect["ah"]
        results.append(ok)
        print(f"[2/2] {label}: map 표시 {rect['w']:.0f}x{rect['h']:.0f} / "
              f"가용 {rect['aw']}x{rect['ah']} -> {'OK(맞춤)' if ok else 'FAIL(넘침)'}")
        drv.save_screenshot(str(ROOT / "_ui_shots" / f"minivillage_fit_{label}.png"))
    finally:
        drv.quit()

assert all(results), "scale-to-fit 실패"
print("ALL PASS")
