# -*- coding: utf-8 -*-
"""'시민 반응' 대시보드 히트맵(커스텀 HTML 컴포넌트) — AppTest 렌더/필터 검증.

AppTest 는 components.html 의 JS(행 토글·정렬)는 실행하지 않는다(village_map 와 동일).
그래서 여기선 '예외 없이 컴포넌트 너머 푸터까지 렌더됐는가 + 필터가 동작하는가'를 본다.
JS 토글/정렬/색감은 브라우저로 확인.

실행: python _test_dashboard_app.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest

# 데모 녹화 스냅샷 우회 — 이 테스트는 합성 mock 데이터로 히트맵 렌더를 검증한다.
import ui.state_helpers as _sh
_sh.DEMO_SNAPSHOT_DIR = _sh.DEMO_SNAPSHOT_DIR / "_disabled_for_tests"


def all_text(at):
    out = []
    for attr in ("markdown", "caption"):
        try:
            for el in getattr(at, attr):
                out.append(el.value or "")
        except Exception:
            pass
    return "\n".join(out)


def select_main_tab(at, label):
    for radio in at.radio:
        if radio.key == "main_tab":
            radio.set_value(label)
            return
    raise AssertionError("상태 저장형 메인 탭 선택 위젯을 찾지 못함")


FOOTER = "불만도는 높을수록 부정 신호"

at = AppTest.from_file("app.py", default_timeout=60)
at.run()
assert not at.exception, f"초기 로드 예외: {at.exception}"

# 데모 모드 + 시뮬 실행 → 반응 생성
for cb in at.checkbox:
    if "데모" in (cb.label or ""):
        cb.set_value(True)
for b in at.button:
    if "시뮬레이션 실행" in (b.label or ""):
        b.click()
at.run()
assert not at.exception, f"데모 시뮬 예외: {at.exception}"

select_main_tab(at, "시민 반응")
at.run()
assert not at.exception, f"시민 반응 탭 선택 예외: {at.exception}"

# 1) 컴포넌트 너머 푸터까지 렌더됐나(= 표 컴포넌트가 예외 없이 그려졌다는 증거)
assert FOOTER in all_text(at), "대시보드 렌더가 표 컴포넌트 이후 푸터까지 도달 못함"
print("[1] 히트맵 컴포넌트 렌더 OK — 푸터까지 도달, 예외 없음")

# 2) 입장 필터(radio) 존재 + 옵션 확인
filt = None
for r in at.radio:
    opts = list(r.options or [])
    if any(str(o).startswith("전체") for o in opts):
        filt = r
        break
assert filt is not None, "입장 필터 radio 를 못 찾음"
print(f"[2] 입장 필터 OK — 옵션: {list(filt.options)}")

# 3) '찬성' 필터 적용해도 안 깨지고 다시 렌더되나
target = next((o for o in filt.options if "찬성" in str(o)), None)
assert target, "찬성 옵션 없음"
filt.set_value(target)
at.run()
assert not at.exception, f"찬성 필터 적용 예외: {at.exception}"
assert FOOTER in all_text(at), "필터 후 렌더가 푸터까지 도달 못함"
print("[3] '찬성' 필터 적용 OK — 예외 없음, 재렌더 정상")

print("\n✅ 대시보드 히트맵(컴포넌트) AppTest 통과")
