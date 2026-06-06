# -*- coding: utf-8 -*-
"""정책 개선 탭 — 'AS 작업'(정책 요약에서 드러난 문제를 해소).

한 화면이 진단 → 개선 → 리포트로 이어진다.
  진단   : 요약 카드 4개(주요 병목 / 정책 사각지대 / 우선 지원 시민 / 악용 위험)
           + 관측된 허점·일탈 행동 목록(DESIGN §9) + 집계 요약(서사)
  개선   : ① 정책 문구·절차 수정(LLM 개선안)  ② 도움창구 운영 제안(접근성 분석 기반)
  리포트 : 📋 종합 리포트 — 시민반응축 + 인생극장축 + 개선안을 고정 양식으로 종합
           (report.generate_report). 다운로드(.md) 가능.

A/B 검증(현재 정책 vs 수정안 재시뮬)은 폐지됐다 — LLM 비결정성 때문에 절대값
델타가 노이즈와 구분되지 않아서다. ui/tab_abtest.py 는 dormant(호출 안 함)로 남긴다.
수정안 재실험은 리포트의 수정안을 '정책 입력'에 다시 넣는 수동 루프로 안내한다.

쉬운글 변환 기능은 폐지됐다. 'easy_text' 는 의미가 '수정안'으로 바뀌어 리포트
5절(수정안 전문)의 재료로 쓰인다. view 는 ui/model.py build_view 결과.
"""

from html import escape

import streamlit as st

import access_analysis as access
from report import generate_report, theater_data


# 생성된 리포트를 담는 session_state 키(새 시뮬 시 app.py 가 무효화한다).
_REPORT_KEY = "improve_report"

# 일탈 행동(behavior_class) → (라벨, 색) — 대시보드 배지와 동일 의미(DESIGN §9).
_BEHAVIOR_LABELS = {
    "exploit": ("부정수급 시도", "#C0392B"),
    "workaround": ("틈새·편법", "#E67E22"),
    "complain": ("민원·행동화", "#8E44AD"),
}


@st.fragment   # 탭 안 버튼의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
def render_improve_tab(view):
    """정책 개선 탭을 렌더링한다.

    매개변수
    --------
    view : dict | None
        ViewModel. 시뮬레이션 전이면 None.
        사용 키: 'summary', 'metrics', 'improvements'{'policy_fixes','easy_text'},
                 'personas', 'reactions', 'reactions_by_id', 'policy_spec',
                 'policy', 'selection', 'policies'(인생극장 출처 판정).
    """
    if view is None:
        st.info("먼저 정책을 입력하고 시뮬레이션을 실행해 주세요. 결과가 나오면 개선안이 여기에 표시됩니다.")
        return

    # 접근성 분석(병목/우선시민/도움창구 제안) — 시민 반응 기반, 결정론.
    analysis = access.analyze(view)

    # ── 진단: 요약 카드 4개 ──────────────────────────────────────
    _render_summary_cards(view, analysis)

    # ── 진단: 관측된 허점·일탈 행동(DESIGN §9) — 있을 때만 ────────
    _render_deviance(view)

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

    # ── 리포트: 두 축 + 개선안 종합 (A/B 검증 대체) ───────────────
    st.subheader("📋 종합 리포트")
    _render_report_section(view)


# ─────────────────────────────────────────────────────────────────────────
# 요약 카드 3개
# ─────────────────────────────────────────────────────────────────────────
def _theater_missed(view) -> int | None:
    """인생극장 결과에서 '막힘 + 못 닿음' 인원. 미실행/출처 불일치면 None.

    report.theater_data 를 그대로 써 리포트 3절과 같은 출처 게이트를 공유한다
    (패키지 데모의 다정책 결과가 단일 정책 카드에 섞이지 않게).
    (구 '도움창구 개선폭' 카드 대체 — A/B 델타 미러링은 A/B 폐지로 함께 폐지.)
    """
    th = theater_data(view)
    if not th:
        return None
    dist = th.get("dist") or {}
    return int(dist.get("blocked", 0)) + int(dist.get("unaware", 0))


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


def _deviant_rows(view) -> list:
    """일탈 속내가 관측된 시민 목록 — 순수(streamlit 무의존).

    반환: [(behavior_class, persona_id, 이름, 태그, 속내)] — 심각도순
    (부정수급 시도 → 틈새·편법 → 민원·행동화). 속내(text)가 빈 항목은 제외.
    """
    personas = {p.get("id"): p for p in (view.get("personas") or [])}
    rows = []
    for r in view.get("reactions") or []:
        bc = str(r.get("behavior_class") or "")
        text = str(r.get("behavior_text") or "").strip()
        if bc not in _BEHAVIOR_LABELS or not text:
            continue
        pid = r.get("persona_id")
        p = personas.get(pid) or {}
        name = p.get("name") or pid or "익명"
        rows.append((bc, pid, name, str(r.get("behavior_tag") or "").strip(), text))
    order = {"exploit": 0, "workaround": 1, "complain": 2}
    rows.sort(key=lambda t: order.get(t[0], 9))
    return rows


def _render_summary_cards(view, analysis: dict) -> None:
    """주요 병목 / 정책 사각지대(인생극장) / 우선 지원 시민 / 악용 위험 카드 4개."""
    bottleneck = analysis.get("main_bottleneck") or "없음"
    priority = analysis.get("priority") or {}
    pri_count = int(priority.get("count", 0))
    pri_pct = int(priority.get("threshold_pct", 40))

    missed = _theater_missed(view)
    if missed is None:
        miss_val, miss_color, miss_sub = "—", "#9AA7B2", "인생극장 실행 시 표시"
    else:
        miss_val = f"{missed}명"
        miss_color = "#C0392B" if missed > 0 else "#27AE60"
        miss_sub = "막힘·못 닿음 (인생극장 결과)"

    # 악용 위험(DESIGN §9): 편법+부정수급 시도 인원(시뮬 관측).
    deviants = _deviant_rows(view)
    n_dev = sum(1 for bc, *_ in deviants if bc in ("exploit", "workaround"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            _card_html("주요 병목", bottleneck, "#C0392B" if bottleneck != "없음" else "#7A8794"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _card_html("정책 사각지대", miss_val, miss_color, miss_sub),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _card_html("우선 지원 시민", f"{pri_count}명", "#2D7DD2",
                       f"접근 가능성 {pri_pct}% 미만"),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            _card_html("정책 악용 위험", f"{n_dev}명",
                       "#C0392B" if n_dev > 0 else "#27AE60",
                       "편법·부정수급 시도 (시뮬 관측)"),
            unsafe_allow_html=True,
        )


def _render_deviance(view) -> None:
    """관측된 허점·일탈 행동 목록(DESIGN §9). 관측이 없으면 아무것도 안 그린다.

    '다른 페르소나와 동일 취급' 원칙대로 별도 탭 없이, 정책 개선 진단의 한 절로만
    모아 보여준다 — 정책입안자가 반응 카드 24장을 뒤지지 않아도 허점이 보이게.
    """
    rows = _deviant_rows(view)
    if not rows:
        return

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.subheader("관측된 허점·일탈 행동")
    st.caption(
        "시뮬레이션 시민들이 드러낸 속내(편법·부정수급 시도·민원 예고)입니다 — "
        "가능성 시나리오이며 실제 행동의 예측이 아닙니다. 정책 문구·검증 절차가 "
        "막아야 할 지점을 보여줍니다."
    )

    casting = (view.get("casting") or {}).get("members") or {}
    blocks = []
    for bc, pid, name, tag, text in rows:
        label, color = _BEHAVIOR_LABELS[bc]
        head = f"<b>{escape(name)}</b>" + (f" · {escape(tag)}" if tag else "")
        # 캐스팅 근거('왜 이 사람이') — 있으면 한 줄 덧붙인다.
        rationale = str((casting.get(pid) or {}).get("rationale") or "").strip()
        rationale_html = (
            f"<div style='font-size:0.76rem;color:#9AA7B2;margin-top:4px;'>"
            f"왜 이 사람이: {escape(rationale)}</div>"
        ) if rationale else ""
        blocks.append(
            f"<div style='margin:6px 0;padding:10px 14px;border-left:4px solid {color};"
            "background:#FAFBFC;border-radius:6px;'>"
            f"<span style='color:{color};font-weight:700;font-size:0.78rem;'>{label}</span>"
            f"&nbsp; {head}<br>"
            f"<span style='color:#2C3E50;'>“{escape(text)}”</span>"
            f"{rationale_html}</div>"
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)


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


# ─────────────────────────────────────────────────────────────────────────
# 📋 종합 리포트 (A/B 검증 대체)
# ─────────────────────────────────────────────────────────────────────────
def _report_theater_stale(report: dict, view) -> bool:
    """리포트 생성 시점의 인생극장 스냅샷과 현재가 다르면 True(stale).

    report.theater_data(결정론 추출 전체: 분포+사례+notes)를 다시 계산해 저장본과
    통째로 비교한다 — 분포가 우연히 같아도 사례 인물·막힌 지점이 바뀌면 잡힌다.
    """
    had = (report.get("data") or {}).get("theater")
    return had != theater_data(view)


def _render_report_section(view) -> None:
    """리포트 생성 버튼 + 결과 렌더 + 다운로드."""
    st.caption(
        "시민 반응(지표·퍼널·목소리)과 정책 인생극장(접근 여정), 그리고 개선안을 "
        "고정 양식 한 장으로 종합합니다. 숫자는 시뮬 결과 그대로, 진단·제안 산문만 "
        "AI 가 작성합니다."
    )
    # 출처 게이트 포함(report.theater_data) — 패키지 데모 결과는 '실행됨'으로 안 친다.
    # 문구는 시점 중립으로: 다른 fragment(인생극장)가 방금 실행돼 이 조각이 아직
    # 낡은 상태여도 거짓말이 되지 않게 한다(조건부 표현).
    theater_ran = theater_data(view) is not None
    if not theater_ran:
        st.caption(
            "ⓘ 인생극장을 아직 실행하지 않았다면 리포트는 시민 반응축만으로 작성됩니다 — "
            "'정책 인생극장' 탭에서 실행하면 접근 여정 사례(누가 어디서 막혔는지)가 "
            "함께 담깁니다."
        )

    col_run, col_fb = st.columns([3, 2])
    with col_fb:
        use_fallback = st.checkbox(
            "기본 문구로 빠르게(외부 호출 없음)", value=False,
            key="improve_report_fallback",
            help="AI 산문 없이 결정론 문구로만 리포트를 만듭니다(데모·오프라인용).",
        )
    with col_run:
        run_clicked = st.button(
            "리포트 생성", type="primary",
            use_container_width=True, key="improve_report_btn",
        )

    if run_clicked:
        with st.spinner("리포트 작성 중..."):
            try:
                st.session_state[_REPORT_KEY] = generate_report(
                    view, use_llm=not use_fallback
                )
            except Exception as e:  # 데모 안정성: 실패해도 탭이 죽지 않게
                st.error(f"리포트 생성 중 오류: {e}")

    report = st.session_state.get(_REPORT_KEY)
    st.divider()
    if not isinstance(report, dict) or not report.get("markdown"):
        st.info("위 '리포트 생성'을 누르면 여기에 종합 리포트가 나타납니다.")
        return

    # 신선도: 리포트 생성 *이후* 인생극장이 (재)실행됐으면 다시 만들라고 안내.
    # 생성 시점 theater 분포와 현재 view 의 분포가 어긋나면 stale 로 본다
    # (미실행→실행 전환 + 재실행으로 결과가 바뀐 경우 둘 다 잡힘).
    if theater_ran and _report_theater_stale(report, view):
        st.warning(
            "이 리포트는 현재 인생극장 결과가 반영되기 *전*에 만들어졌습니다 — "
            "'리포트 생성'을 다시 누르면 최신 접근 여정 사례가 반영됩니다."
        )

    if report.get("mode") == "fallback":
        if report.get("llm_error"):
            # 키는 있는데 호출이 실패한 경우 — '키 없으면 보강' 오안내 대신 사실대로.
            st.caption(
                "⚠ AI 산문 생성에 실패해 기본(결정론) 문구로 작성했습니다 — "
                f"'리포트 생성'을 다시 누르면 재시도합니다. (원인: {report['llm_error']})"
            )
        else:
            st.caption(
                "기본(결정론) 문구로 작성된 리포트입니다 — OpenAI 키가 있으면 "
                "진단·제안 산문이 AI 로 보강됩니다."
            )
    st.markdown(report["markdown"])
    st.download_button(
        "⬇ 리포트 다운로드 (.md)",
        report["markdown"].encode("utf-8"),
        file_name="미리랩_정책개선리포트.md",
        mime="text/markdown",
        key="improve_report_dl",
        use_container_width=True,
    )
