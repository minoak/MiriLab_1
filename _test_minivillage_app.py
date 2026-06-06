# -*- coding: utf-8 -*-
"""_test_minivillage_app.py — 미리마을 탭 통합(AppTest) 스모크.

app.py 를 초기 렌더(버튼 클릭 0)만 돌려 7탭 구성과 미리마을 탭 임베드가
예외 없이 그려지는지 확인한다. 버튼을 누르지 않으므로 OpenAI 호출은 일어나지
않는다(인생극장 #7 비용 회피). 실행: python _test_minivillage_app.py
"""
import sys

from streamlit.testing.v1 import AppTest


def main():
    at = AppTest.from_file("app.py", default_timeout=90)
    at.run()

    fails = []

    # 1) 초기 렌더에서 예외 0 (각 탭은 app.py 가 try/except 로 st.exception 표시)
    if at.exception:
        fails.append(f"예외 발생: {[str(e.value)[:120] for e in at.exception]}")
    print(f"[{'PASS' if not at.exception else 'FAIL'}] 초기 렌더 예외 0")

    # 2) '미리마을' 메인 화면 선택지 존재 (7개 결과 화면 구성)
    labels = []
    for radio in at.radio:
        if radio.key == "main_tab":
            labels = list(radio.options)
            break
    has_tab = "미리마을" in labels
    if not has_tab:
        fails.append(f"미리마을 화면 선택지 없음. labels={labels}")
    print(f"[{'PASS' if has_tab else 'FAIL'}] 미리마을 화면 선택지 존재 (labels={labels})")

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
