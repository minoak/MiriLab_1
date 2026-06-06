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

# 미리 마을 탭의 '인생극장 실행' 버튼 클릭 (key 로 직접 접근)
at.button(key="village_run_contrast").click()
at.run()
assert not at.exception, f"인생극장 실행 예외: {at.exception}"

view2 = at.session_state["view"] if "view" in at.session_state else {}
sel = view2.get("selection") or {}
trio = sel.get("trio") or []
print(f"[3] 인생극장 실행 OK — 대조 {len(trio)}명: "
      + ", ".join(f"{t['role']}={t['persona']['name']}" for t in trio))
print(f"    결과표 {len(sel.get('outcomes') or [])}명, 노트 {len(sel.get('notes') or [])}개")

# 카드뽑기: 첫 카드(수혜) '펼치기' 클릭 → 서사 렌더 무예외 확인
first_pid = trio[0]["persona"]["id"]
at.button(key=f"open_{first_pid}").click()
at.run()
assert not at.exception, f"카드 펼치기 예외: {at.exception}"
opened = (at.session_state["village_open_card"]
          if "village_open_card" in at.session_state else None)
print(f"[4] 카드 펼치기 OK — 펼친 카드 id={str(opened)[:8]}… ({trio[0]['persona']['name']})")
print("\n✅ 앱 배선 스모크 통과")
