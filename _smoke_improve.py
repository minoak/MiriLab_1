# -*- coding: utf-8 -*-
"""정책 개선 탭(AS 프레이밍) + 시민반응 신청여정 패널 스모크 — headless, 외부호출 0.

데모(mock) 사이드바 시뮬 → 시민 반응 탭의 신청 여정 분석(퍼널/연령접근성/병목)과
정책 개선 탭의 AS 구조(요약카드/문구수정/도움창구 제안/집계요약)가 뜨고, A/B 비교를
목업으로 돌려 현재 정책 vs 수정안 게이지 비교가 렌더되는지 확인한다.
**마을 인생극장 버튼은 누르지 않는다**(실 LLM 과금 경로 회피).
실행: python _smoke_improve.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest


def all_text(at) -> str:
    """렌더된 텍스트성 요소를 한데 모은다(탭 라벨/헤더/본문 검사용)."""
    out = []
    for attr in ("markdown", "header", "subheader", "title", "caption",
                 "info", "warning", "success", "error", "text"):
        try:
            for el in getattr(at, attr):
                v = getattr(el, "value", None)
                if v:
                    out.append(str(v))
        except Exception:
            pass
    return "\n".join(out)


at = AppTest.from_file("app.py", default_timeout=60)
at.run()
assert not at.exception, f"초기 로드 예외: {at.exception}"
print("[1] 초기 로드 OK")

# 데모 모드 + 사이드바 시뮬 실행(mock → 외부호출 0)
for cb in at.checkbox:
    if "데모" in (cb.label or ""):
        cb.set_value(True)
for b in at.button:
    if "시뮬레이션 실행" in (b.label or ""):
        b.click()
at.run()
assert not at.exception, f"데모 시뮬 예외: {at.exception}"
view = at.session_state["view"] if "view" in at.session_state else {}
print(f"[2] 데모 시뮬 OK — personas={len(view.get('personas') or [])}명")

# 구조 검증: AS 프레이밍(요약카드+문구수정+도움창구제안+집계요약) + 쉬운글/전파 제거
#           + 시민 반응 탭의 신청 여정 분석 패널
text = all_text(at)
assert "주요 병목" in text, "요약 카드(주요 병목)가 없음"
assert "정책 문구·절차 수정" in text, "정책 문구·절차 수정 섹션이 없음"
assert "도움창구 운영 제안" in text, "도움창구 운영 제안 섹션이 없음"
assert "집계 요약" in text, "집계 요약 섹션이 없음"
assert "쉬운 글 변환" not in text, "쉬운 글 변환 패널이 아직 렌더됨(삭제 실패)"
assert "전파 네트워크" not in text, "전파 네트워크가 아직 렌더됨(삭제 실패)"
assert "신청 여정 분석" in text, "신청 여정 분석 섹션이 없음"
assert "신청 단계별 병목 퍼널" in text, "퍼널 패널이 없음"
assert "연령대별 정책 접근성" in text, "연령대별 접근성 패널이 없음"
assert "병목 요인 TOP 3" in text, "병목 요인 TOP3 패널이 없음"
print("[3] 구조 OK — AS(요약카드/문구수정/도움창구/집계요약) + 신청여정 분석, 쉬운글·전파 제거")

# A/B 비교: 목업으로만 실행(실 LLM 회피) — 키로 직접 접근
at.checkbox(key="abtest_use_mock").set_value(True)
at.button(key="abtest_run_btn").click()
at.run()
assert not at.exception, f"A/B 목업 실행 예외: {at.exception}"
assert "view_b" in at.session_state and at.session_state["view_b"], "view_b 미생성"
text2 = all_text(at)
assert "현재 정책 (수정 전)" in text2, "현재 정책 게이지 라벨 없음"
assert "수정안 (개선 후)" in text2, "수정안 게이지 라벨 없음"
assert "변화 요약" in text2, "변화 요약 렌더 안 됨"
assert "입장 변화" in text2, "입장 분포 변화 렌더 안 됨"
print("[4] A/B 목업 비교 OK — 게이지 좌우(현재/수정안)·변화요약·입장변화 렌더 확인")

# 미리채움 검증: 후보 text_area 가 개선안(쉬운 글) 기반인지
cand = at.session_state["abtest_policy_b"] if "abtest_policy_b" in at.session_state else ""
assert cand, "수정안 후보가 비어 있음(미리채움 실패)"
print(f"[5] 수정안 미리채움 OK — {len(cand)}자 (AI 수정안 프리필)")

# [6] 새 시뮬 시 이전 A/B 비교 무효화(다른 정책 간 착시 방지) 확인
for b in at.button:
    if "시뮬레이션 실행" in (b.label or ""):
        b.click()
at.run()
assert not at.exception, f"재시뮬 예외: {at.exception}"
assert "view_b" not in at.session_state, "재시뮬 후 view_b 가 무효화되지 않음(착시 방지 실패)"
print("[6] 재시뮬 시 view_b 무효화 OK (정책 바뀌면 옛 비교 자동 숨김)")

print("\n앱 스모크 통과 (정책 개선 병합 + 전파 그래프 제거 + 착시 방지)")
