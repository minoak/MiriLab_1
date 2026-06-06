# -*- coding: utf-8 -*-
"""정책 개선 탭(AS + 종합 리포트) + 시민반응 신청여정 패널 스모크 — headless, 외부호출 0.

데모(mock) 사이드바 시뮬 → 시민 반응 탭의 신청 여정 분석(퍼널/연령접근성/병목)과
정책 개선 탭의 AS 구조(요약카드/문구수정/도움창구 제안/집계요약)가 뜨고,
종합 리포트를 '기본 문구(폴백)' 모드로 생성해 고정 양식이 렌더되는지 확인한다.
**마을 인생극장 버튼은 누르지 않고, 리포트도 폴백 모드로만**(실 LLM 과금 경로 회피).
실행: python _smoke_improve.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest

# 데모 녹화 스냅샷 우회 — 이 스모크는 합성 mock 파이프라인+폴백 리포트를 검증한다.
import ui.state_helpers as _sh
_sh.DEMO_SNAPSHOT_DIR = _sh.DEMO_SNAPSHOT_DIR / "_disabled_for_tests"


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

# 구조 검증: AS 프레이밍(요약카드+문구수정+도움창구제안+집계요약) + 리포트 섹션
#           + A/B 제거 + 시민 반응 탭의 신청 여정 분석 패널
text = all_text(at)
assert "주요 병목" in text, "요약 카드(주요 병목)가 없음"
assert "정책 사각지대" in text, "요약 카드(정책 사각지대)가 없음"
assert "정책 문구·절차 수정" in text, "정책 문구·절차 수정 섹션이 없음"
assert "도움창구 운영 제안" in text, "도움창구 운영 제안 섹션이 없음"
assert "집계 요약" in text, "집계 요약 섹션이 없음"
assert "종합 리포트" in text, "종합 리포트 섹션이 없음"
assert "개선 효과 확인" not in text, "A/B 섹션이 아직 렌더됨(제거 실패)"
assert "수정안으로 비교" not in text, "A/B 비교 버튼이 아직 렌더됨(제거 실패)"
assert "쉬운 글 변환" not in text, "쉬운 글 변환 패널이 아직 렌더됨(삭제 실패)"
assert "전파 네트워크" not in text, "전파 네트워크가 아직 렌더됨(삭제 실패)"
# v1.2: 신청 여정 분석은 '사전 추정(t0 점수 기반)' expander 로 강등(설계방향서 §8-14).
# expander 라벨은 all_text 에 안 잡혀, 내부 캡션('사전 가설')과 패널 본문으로 확인한다.
assert "사전 가설" in text, "신청 여정 분석(사전 추정 expander) 내용이 없음"
assert "신청 단계별 병목 퍼널" in text, "퍼널 패널이 없음"
assert "연령대별 정책 접근성" in text, "연령대별 접근성 패널이 없음"
assert "병목 요인 TOP 3" in text, "병목 요인 TOP3 패널이 없음"
print("[3] 구조 OK — AS(요약카드/문구수정/도움창구/집계요약) + 리포트 섹션, A/B·쉬운글·전파 제거")

# 종합 리포트: 폴백 모드로만 생성(실 LLM 회피) — 키로 직접 접근
at.checkbox(key="improve_report_fallback").set_value(True)
at.button(key="improve_report_btn").click()
at.run()
assert not at.exception, f"리포트 생성 예외: {at.exception}"
rep = at.session_state["improve_report"] if "improve_report" in at.session_state else None
assert isinstance(rep, dict) and rep.get("markdown"), "improve_report 미생성"
assert rep.get("mode") == "fallback", f"폴백 모드가 아님: {rep.get('mode')}"
md = rep["markdown"]
for h in ("# 📋 정책 개선 리포트", "## 1. 요약", "## 2. 시민 반응 진단",
          "## 3. 접근 여정 사례", "## 4. 개선 제안", "## 5. 수정안 전문",
          "## 6. 한계 노트"):
    assert h in md, f"리포트 양식 절 누락: {h}"
# §8 한 버튼: 사이드바 실행이 축2(인생극장)까지 완주하므로 리포트 3절에 실제 사례가
# 실린다. ('인생극장 미실행' 안내는 축1만 돌던 구버전의 기대 — §8 이후 뒤집힘.)
assert "인생극장 미실행" not in md, "한 버튼 완주인데 3절이 '인생극장 미실행'을 표시"
text2 = all_text(at)
assert "정책 개선 리포트" in text2, "리포트가 화면에 렌더되지 않음"
print(f"[4] 리포트 생성 OK — 폴백 모드, 양식 6절, {len(md)}자")

# [5] 새 시뮬 시 이전 리포트 무효화(다른 정책 간 착시 방지) 확인
for b in at.button:
    if "시뮬레이션 실행" in (b.label or ""):
        b.click()
at.run()
assert not at.exception, f"재시뮬 예외: {at.exception}"
assert "improve_report" not in at.session_state, \
    "재시뮬 후 improve_report 가 무효화되지 않음(착시 방지 실패)"
assert "view_b" not in at.session_state, "view_b 잔존(있을 수 없는 키)"
print("[5] 재시뮬 시 리포트 무효화 OK (정책 바뀌면 옛 리포트 자동 숨김)")

print("\n앱 스모크 통과 (A/B → 종합 리포트 교체 + 착시 방지)")
