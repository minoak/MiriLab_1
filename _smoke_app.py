# -*- coding: utf-8 -*-
"""앱 스모크 — 정책 인생극장 배선이 Streamlit 에서 안 깨지는지 headless 검증.

데모 모드로 사이드바 시뮬 실행 → 미리 마을 탭의 '인생극장 실행' 버튼 클릭까지.
실행: python _smoke_app.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest

# 데모 녹화 스냅샷 우회 — 이 스모크는 합성 mock 경로의 인생극장 배선을 검증한다.
import ui.state_helpers as _sh
_sh.DEMO_SNAPSHOT_DIR = _sh.DEMO_SNAPSHOT_DIR / "_disabled_for_tests"

at = AppTest.from_file("app.py", default_timeout=60)
at.run()
assert not at.exception, f"초기 로드 예외: {at.exception}"
print("[1] 초기 로드 OK (예외 없음)")

# 데모 모드 체크 + 사이드바 시뮬 실행
for cb in at.checkbox:
    if "데모" in (cb.label or ""):
        cb.set_value(True)
for b in at.button:
    if "시뮬레이션 실행" in (b.label or ""):
        b.click()
at.run()
assert not at.exception, f"사이드바 시뮬 예외: {at.exception}"
sim = at.session_state["sim"] if "sim" in at.session_state else {}
view = at.session_state["view"] if "view" in at.session_state else {}
print(f"[2] 데모 시뮬 OK — sim keys={len(sim)}개, personas={len(view.get('personas') or [])}명")

# 상태 저장형 메인 화면 내비게이션은 선택한 화면만 렌더한다.
for radio in at.radio:
    if radio.key == "main_tab":
        radio.set_value("정책 인생극장")
        break
else:
    raise AssertionError("main_tab 선택 위젯을 찾지 못했습니다.")
at.run()
assert not at.exception, f"정책 인생극장 전환 예외: {at.exception}"

# 선택 화면만 렌더되는 구조에서 인생극장 실행 버튼이 배선되는지 확인한다.
assert at.button(key="village_run_contrast"), "인생극장 실행 버튼을 찾지 못했습니다."
assert at.button(key="village_run_pkg_demo"), "패키지 데모 실행 버튼을 찾지 못했습니다."
print("[3] 정책 인생극장 화면 전환/버튼 배선 OK")
print("\n✅ 앱 배선 스모크 통과")
