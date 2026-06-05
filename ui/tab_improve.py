# -*- coding: utf-8 -*-
"""정책 개선 탭 — 'AS 작업'(정책 요약에서 드러난 문제를 해소).

한 화면이 진단 → 개선 → 검증으로 이어진다.
  진단 : 요약 카드 3개(주요 병목 / 도움창구 개선폭 / 우선 지원 시민) + 집계 요약(서사)
  개선 : ① 정책 문구·절차 수정(LLM 개선안)  ② 도움창구 운영 제안(접근성 분석 기반)
  검증 : A/B — 현재 정책 vs 수정안(개선안을 반영해 다시 쓴 정책)을 같은 시민으로 비교

쉬운글 변환 기능은 폐지됐다. 'easy_text' 는 의미가 '수정안'으로 바뀌어 A/B 후보로만
내부적으로 쓰인다(별도 패널 없음). view 는 ui/model.py build_view 결과.
"""

import streamlit as st

import access_analysis as access
from ui.tab_abtest import render_abtest_section


@st.fragment   # 탭 안 A/B 체크박스·버튼의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
def render_improve_tab(view):
    """정책 개선 탭을 렌더링한다.

    매개변수
    --------
    view : dict | None
        ViewModel. 시뮬레이션 전이면 None.
        사용 키: 'summary', 'metrics', 'improvements'{'policy_fixes'},
                 'personas', 'reactions_by_id', 'policy_spec', 'policy'.
    """
    if view is None:
        st.info("먼저 정책을 입력하고 시뮬레이션을 실행해 주세요. 결과가 나오면 개선안이 여기에 표시됩니다.")
        return

    # 접근성 분석(병목/우선시민/도움창구 제안) — 시민 반응 기반, 결정론.
    analysis = access.analyze(view)

    # ── 진단: 요약 카드 3개 ──────────────────────────────────────
    _render_summary_cards(view, analysis)

    st.divider()

    # ── 개선(AS): 정책 문구 수정 + 도움창구 운영 제안 ────────────
    _render_fixes(view)
    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    _render_helpdesk(analysis)

    st.divider()

    # ── 진단 서사: 집계 요약 ──────────────────────────────────────
    st.subheader("집계 요약")
    summary = view.get("summary") or "요약 정보가 아직 없습니다."
    st.markdown(summary)

    st.divider()

    # ── 검증: A/B (현재 정책 vs 수정안) ──────────────────────────
    st.subheader("개선 효과 확인 — 현재 정책 vs 수정안")
    render_abtest_section(view)


# ─────────────────────────────────────────────────────────────────────────
# 요약 카드 3개
# ─────────────────────────────────────────────────────────────────────────
def _improvement_delta(view) -> float | None:
    """A/B 가 실행됐으면 수정안의 신청의향지수 개선폭(b − a), 아니면 None.

    (해석1: 도움창구 개선폭 = A/B 결과의 신청의향 변화를 미러링.)
    """
    view_b = st.session_state.get("view_b")
    if not isinstance(view_b, dict):
        return None
    a = (view.get("metrics") or {}).get("신청의향지수")
    b = (view_b.get("metrics") or {}).get("신청의향지수")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(float(b) - float(a), 1)
    return None


def _card_html(title: str, value: str, color: str, sub: str = "") -> str:
    """라이트 테마 요약 카드 1개 HTML."""
    sub_html = (f"<div style='font-size:0.72rem;color:#9AA7B2;margin-top:4px;'>{sub}</div>"
                if sub else "")
    # min-height + flex 세로 중앙정렬 → sub(하단 설명줄) 유무와 상관없이 3개 카드가
    # 똑같은 높이로 보이게 한다('주요 병목'만 sub 가 없어 더 짧던 문제 해결).
    return (
        "<div style='border:1px solid #E8ECEF;border-radius:10px;padding:14px 16px;"
        "text-align:center;background:#FAFBFC;min-height:118px;display:flex;"
        "flex-direction:column;justify-content:center;align-items:center;'>"
        f"<div style='font-size:0.8rem;color:#7A8794;margin-bottom:6px;'>{title}</div>"
        f"<div style='font-size:1.5rem;font-weight:800;color:{color};line-height:1.2;'>{value}</div>"
        f"{sub_html}</div>"
    )


def _render_summary_cards(view, analysis: dict) -> None:
    """주요 병목 / 도움창구 개선폭 / 우선 지원 시민 카드 3개."""
    bottleneck = analysis.get("main_bottleneck") or "없음"
    priority = analysis.get("priority") or {}
    pri_count = int(priority.get("count", 0))
    pri_pct = int(priority.get("threshold_pct", 40))

    delta = _improvement_delta(view)
    if delta is None:
        delta_val, delta_color, delta_sub = "—", "#9AA7B2", "A/B 실행 시 표시"
    else:
        sign = "+" if delta >= 0 else ""
        delta_val = f"{sign}{delta}%p"
        delta_color = "#27AE60" if delta > 0 else ("#C0392B" if delta < 0 else "#7A8794")
        delta_sub = "수정안 신청의향 변화"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            _card_html("주요 병목", bottleneck, "#C0392B" if bottleneck != "없음" else "#7A8794"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _card_html("도움창구 개선폭", delta_val, delta_color, delta_sub),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _card_html("우선 지원 시민", f"{pri_count}명", "#2D7DD2",
                       f"접근 가능성 {pri_pct}% 미만"),
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────
# 개선(AS): 정책 문구 수정 + 도움창구 운영 제안
# ─────────────────────────────────────────────────────────────────────────
def _render_fixes(view) -> None:
    """정책 문구·절차 수정 (LLM 개선안 = improvements.policy_fixes)."""
    st.subheader("정책 문구·절차 수정")
    fixes = (view.get("improvements") or {}).get("policy_fixes") or []
    lines = [f"- {str(f).strip()}" for f in fixes if str(f).strip()]
    if lines:
        st.markdown("\n".join(lines))
    else:
        st.caption("제안된 수정 사항이 아직 없습니다.")


def _render_helpdesk(analysis: dict) -> None:
    """도움창구 운영 제안 (접근성 분석 기반 결정론 제안)."""
    st.subheader("도움창구 운영 제안")
    recs = analysis.get("helpdesk") or []
    lines = [f"- {str(r).strip()}" for r in recs if str(r).strip()]
    if lines:
        st.markdown("\n".join(lines))
    else:
        st.caption("운영 제안이 없습니다.")
