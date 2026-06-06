# -*- coding: utf-8 -*-
"""UI 진단용 스크린샷 캡처 (읽기 전용 — 앱 코드 무수정).

localhost:8502 의 미리랩 앱에서 데모 모드 체크 -> 실행(녹화 재생, LLM 0콜)
-> 7개 탭 각각 스크린샷을 _ui_shots/ 에 저장한다.
"""
import base64
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

OUT = r"C:\Users\akals\Downloads\미리랩\_ui_shots"

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1600,1000")
opts.add_argument("--hide-scrollbars")
opts.add_argument("--force-device-scale-factor=1")
driver = webdriver.Chrome(options=opts)
driver.set_page_load_timeout(60)


def shot_fullpage(path):
    """CDP 로 본문 전체 높이 캡처 (inner scroll 포함 안 되면 viewport 만)."""
    try:
        metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        content = metrics.get("cssContentSize") or metrics["contentSize"]
        width = min(int(content["width"]), 1600)
        height = min(int(content["height"]), 8000)
        res = driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {"x": 0, "y": 0, "width": width, "height": height,
                     "scale": 1},
        })
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"]))
    except Exception as e:
        print("fullpage fail, fallback viewport:", e)
        driver.save_screenshot(path)


def find_button(text):
    for b in driver.find_elements(By.TAG_NAME, "button"):
        if text in (b.text or ""):
            return b
    return None


print("open app...")
driver.get("http://localhost:8502")
time.sleep(8)

# 1) 데모 모드 체크 (키가 있으면 기본 해제 상태)
clicked = False
for lab in driver.find_elements(By.TAG_NAME, "label"):
    if "데모 모드" in (lab.text or ""):
        inp = lab.find_elements(By.TAG_NAME, "input")
        checked = inp and inp[0].is_selected()
        if not checked:
            lab.click()
            clicked = True
        break
print("demo checkbox clicked:", clicked)
time.sleep(3)

# 2) 시뮬레이션 실행 (녹화 스냅샷 재생 경로)
btn = find_button("시뮬레이션 실행")
if btn is None:
    print("run button not found"); driver.quit(); sys.exit(1)
btn.click()
print("run clicked, waiting...")

# success alert 대기 (최대 60s)
ok = False
for _ in range(30):
    time.sleep(2)
    body = driver.find_element(By.TAG_NAME, "body").text
    if "재생했습니다" in body or "완료했습니다" in body:
        ok = True
        break
print("pipeline done:", ok)
time.sleep(2)

# 3) 탭별 스크린샷
tabs = driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")
print("tabs found:", len(tabs))
names = []
for i in range(len(tabs)):
    tabs = driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")
    name = (tabs[i].text or f"tab{i}").strip().replace(" ", "_")
    names.append(name)
    driver.execute_script("arguments[0].click();", tabs[i])
    time.sleep(4)
    # iframe(components.html) 렌더 대기 여유
    shot_fullpage(rf"{OUT}\tab{i}_{name}.png")
    print("saved tab", i, name)

driver.quit()
print("ALL DONE:", ", ".join(names))
