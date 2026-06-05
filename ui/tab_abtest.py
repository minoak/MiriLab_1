# -*- coding: utf-8 -*-
"""A/B 개선 효과 검증 — '정책 개선' 탭(tab_improve)의 검증 섹션.

AI가 개선안을 반영해 만든 '수정안'을 후보로 미리 채워 두고, 버튼을 누르면 같은
시민 코호트로 다시 시뮬해 **현재 정책 vs 수정안**을 비교한다. 비교는 핵심 지표 3종을
게이지로 좌우 나란히 보여주고, 변화(Δ)와 시민 입장 분포 변화를 덧붙인다.

공개 API: render_abtest_section(view)
- view: ui.model.build_view(sim) 결과(ViewModel dict).
- 수정안 시뮬은 버튼을 눌렀을 때만 실행되며, 결과는 session_state['view_b'] 에 저장.
- '목업으로 빠르게' 토글을 켜면 외부 호출 없이 ui.mock 으로 비교 가능.

비교 계산(compute_comparison 등)은 streamlit 무의존 순수 함수라 단독 테스트 가능.
"""
import streamlit as st

from viz import STYLE, gauge
from ui.rerun_util import rerun_fragment


# 후보 정책 text_area 의 session_state 키(기존 키 유지 → 세션 호환)
_CANDIDATE_KEY = "abtest_policy_b"

# 핵심 지표 3종: (표시 라벨, metrics 키, 높을수록_좋은가)
_KEY_METRICS = [
    ("정책수용도", "정책수용도", True),
    ("신청의향지수", "신청의향지수", True),
    ("사회혼란도", "사회혼란도", False),  # 낮을수록 좋음 → delta 색 반전
]

# 5축 평균: (metrics 키, 표시 라벨) — viz.STYLE.score_labels 와 일치
_AXES = [(k, STYLE["score_labels"][k]) for k in (
    "understanding", "benefit", "intent", "dissatisfaction", "shareability"
)]

# 입장(stance) 표시 순서/라벨
_STANCES = [("support", "찬성"), ("mixed", "혼합"), ("oppose", "반대")]


# =====================================================================
# 순수 계산(streamlit 무의존) — 단독 테스트 가능
# =====================================================================
def _num(x, default=0.0) -> float:
    """안전 float 변환."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _metrics(view) -> dict:
    """view 에서 metrics dict 를 꺼낸다(없으면 빈 dict)."""
    if not isinstance(view, dict):
        return {}
    m = view.get("metrics")
    return m if isinstance(m, dict) else {}


def stance_counts(view) -> dict:
    """view['reactions'] 의 입장 분포를 센다 → {'support':n,'mixed':n,'oppose':n}."""
    counts = {key: 0 for key, _ in _STANCES}
    reactions = view.get("reactions") if isinstance(view, dict) else None
    for r in reactions or []:
        s = str((r or {}).get("stance", "")).strip().lower()
        if s in counts:
            counts[s] += 1
        else:
            # 알 수 없는 입장은 혼합으로 본다(방어).
            counts["mixed"] += 1
    return counts


def compute_comparison(view_a, view_b) -> dict:
    """원문(view_a) vs 개선안(view_b) 비교 구조를 만든다(순수).

    반환 {
      'key_metrics': [(label, a, b, delta, higher_better), ...],
      'axes':        [(key, label, a, b, delta), ...],
      'stance':      {'a': {...}, 'b': {...}},
      'verdict':     str,
      'verdict_kind':'good'|'bad'|'mixed',
    }
    """
    ma, mb = _metrics(view_a), _metrics(view_b)

    key_metrics = []
    for label, key, higher in _KEY_METRICS:
        a, b = _num(ma.get(key)), _num(mb.get(key))
        key_metrics.append((label, a, b, round(b - a, 1), higher))

    axes = []
    for key, label in _AXES:
        a, b = _num(ma.get(key)), _num(mb.get(key))
        axes.append((key, label, a, b, round(b - a, 1)))

    stance = {"a": stance_counts(view_a), "b": stance_counts(view_b)}

    verdict, kind = _make_verdict(ma, mb)
    return {
        "key_metrics": key_metrics,
        "axes": axes,
        "stance": stance,
        "verdict": verdict,
        "verdict_kind": kind,
    }


def _make_verdict(ma: dict, mb: dict, thresh: float = 2.0) -> tuple:
    """핵심 지표 변화로 한 줄 총평 + 종류를 만든다.

    수용도↑·혼란도↓ 면 개선, 수용도↓·혼란도↑ 면 악화, 그 외 혼조.
    thresh 미만의 변화는 '거의 변화 없음'으로 본다(노이즈 무시).
    """
    d_acc = _num(mb.get("정책수용도")) - _num(ma.get("정책수용도"))
    d_unrest = _num(mb.get("사회혼란도")) - _num(ma.get("사회혼란도"))
    d_intent = _num(mb.get("신청의향지수")) - _num(ma.get("신청의향지수"))

    def _fmt(x):
        return f"{'+' if x >= 0 else ''}{round(x, 1)}"

    head = (f"수정안 적용 시 정책수용도 {_fmt(d_acc)}, "
            f"신청의향 {_fmt(d_intent)}, 사회혼란도 {_fmt(d_unrest)}")

    acc_up = d_acc >= thresh
    acc_down = d_acc <= -thresh
    unrest_up = d_unrest >= thresh
    unrest_down = d_unrest <= -thresh

    if (acc_up or unrest_down) and not (acc_down or unrest_up):
        return head + " — 전반적으로 개선되었습니다.", "good"
    if (acc_down or unrest_up) and not (acc_up or unrest_down):
        return head + " — 오히려 악화되었습니다. 문구를 다시 살펴보세요.", "bad"
    if not (acc_up or acc_down or unrest_up or unrest_down):
        return head + " — 의미 있는 변화가 거의 없습니다.", "mixed"
    return head + " — 좋아진 지표와 나빠진 지표가 섞여 있습니다.", "mixed"


# =====================================================================
# 렌더 — '정책 개선' 탭 ② 섹션
# =====================================================================
def render_abtest_section(view) -> None:
    """②: 개선안을 후보로 미리 채워 원문 vs 개선안을 비교한다."""
    base_policy = view.get("policy") or "" if isinstance(view, dict) else ""
    improvements = view.get("improvements") or {} if isinstance(view, dict) else {}
    easy_text = improvements.get("easy_text") or ""

    st.caption(
        "AI가 개선안을 반영해 만든 '수정안'을 미리 채웠습니다. 그대로 또는 고쳐서 "
        "'수정안으로 비교'를 누르면, 같은 시민들이 현재 정책과 수정안에 어떻게 다르게 "
        "반응하는지 비교합니다."
    )

    # 후보 미리 채움(최초 1회). 이후엔 사용자가 편집한 값을 유지한다.
    if _CANDIDATE_KEY not in st.session_state:
        st.session_state[_CANDIDATE_KEY] = easy_text or base_policy

    # '개선안으로 다시 채우기' — 편집한 걸 버리고 쉬운 글로 리셋(위젯 생성 전에 처리).
    cols_top = st.columns([1, 1])
    with cols_top[0]:
        if st.button("↺ AI 수정안으로 다시 채우기", use_container_width=True,
                     disabled=not easy_text,
                     help="AI가 만든 수정안으로 수정안 칸을 초기화합니다."):
            st.session_state[_CANDIDATE_KEY] = easy_text or base_policy
            rerun_fragment()
    with cols_top[1]:
        if st.button("원문으로 채우기", use_container_width=True,
                     disabled=not base_policy,
                     help="원문 정책으로 수정안 칸을 되돌립니다."):
            st.session_state[_CANDIDATE_KEY] = base_policy
            rerun_fragment()

    policy_b = st.text_area(
        "수정안(개선안) 정책",
        height=220,
        key=_CANDIDATE_KEY,
        help="AI 수정안을 미리 채워 두었습니다. 문구를 다듬거나 조건을 바꿔 비교해 보세요.",
    )

    col_run, col_mock = st.columns([3, 2])
    with col_mock:
        use_mock = st.checkbox(
            "목업으로 빠르게(외부 호출 없음)", value=False, key="abtest_use_mock"
        )
    with col_run:
        run_clicked = st.button(
            "수정안으로 비교", type="primary",
            use_container_width=True, key="abtest_run_btn",
        )

    if run_clicked:
        if not (policy_b or "").strip():
            st.warning("수정안 정책 내용을 입력하세요.")
        else:
            from ui.state_helpers import run_simulation
            from ui.model import build_view

            # 같은 시민 코호트로 비교(원문 시뮬과 같은 n → seed 고정이라 동일 페르소나).
            n = len(view.get("personas") or []) if isinstance(view, dict) else 0
            n = n or 24
            with st.spinner("개선안으로 시뮬레이션 중..."):
                try:
                    sim_b = run_simulation(policy_b, mock=use_mock, n=int(n))
                    st.session_state["view_b"] = build_view(sim_b)
                    st.success("수정안 시뮬이 완료되었습니다. 아래에서 비교하세요.")
                except Exception as e:  # 데모 안정성: 실패해도 탭이 죽지 않게
                    st.error(f"수정안 시뮬 실행 중 오류: {e}")

    view_b = st.session_state.get("view_b")
    st.divider()
    if view_b is None:
        st.info("위 '수정안으로 비교'를 누르면 여기에 현재 정책 vs 수정안 비교가 나타납니다.")
        return

    _render_comparison(view, view_b)


def _render_comparison(view_a, view_b) -> None:
    """현재 정책 vs 수정안 비교(게이지 3종 좌우 + 변화 요약 + 입장 분포)."""
    comp = compute_comparison(view_a, view_b)

    # ── 총평 한 줄 ──
    kind = comp["verdict_kind"]
    if kind == "good":
        st.success("✅ " + comp["verdict"])
    elif kind == "bad":
        st.warning("⚠️ " + comp["verdict"])
    else:
        st.info("• " + comp["verdict"])

    # ── 핵심 지표 3종 게이지 — 현재 정책 vs 수정안 (좌우) ──
    ma, mb = _metrics(view_a), _metrics(view_b)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            "<div style='text-align:center;font-weight:700;color:#5A6B7B;'>"
            "현재 정책 (수정 전)</div>",
            unsafe_allow_html=True,
        )
        for label, key, _ in _KEY_METRICS:
            st.plotly_chart(gauge(_num(ma.get(key)), label),
                            use_container_width=True, key=f"ab_a_{key}")
    with col_b:
        st.markdown(
            "<div style='text-align:center;font-weight:700;color:#27AE60;'>"
            "수정안 (개선 후)</div>",
            unsafe_allow_html=True,
        )
        for label, key, _ in _KEY_METRICS:
            st.plotly_chart(gauge(_num(mb.get(key)), label),
                            use_container_width=True, key=f"ab_b_{key}")

    # ── 변화(Δ) 요약 ──
    st.markdown("#### 변화 요약")
    cols = st.columns(len(comp["key_metrics"]))
    for col, (label, a, b, delta, higher) in zip(cols, comp["key_metrics"]):
        with col:
            # 사회혼란도는 낮을수록 좋음 → delta 색 반전
            st.metric(
                label=label,
                value=round(b, 1),
                delta=delta,
                delta_color=("normal" if higher else "inverse"),
                help=f"현재 {round(a, 1)} → 수정안 {round(b, 1)}",
            )
    st.caption("화살표 색: 초록 = 개선 방향, 빨강 = 악화 방향 (사회혼란도는 낮을수록 좋음).")

    # ── 시민 입장 분포 변화(한 줄) ──
    sa, sb = comp["stance"]["a"], comp["stance"]["b"]
    d_support = sb["support"] - sa["support"]
    d_oppose = sb["oppose"] - sa["oppose"]
    st.caption(
        f"입장 변화 — 찬성 {sa['support']}→{sb['support']}명 "
        f"({'+' if d_support >= 0 else ''}{d_support}), "
        f"반대 {sa['oppose']}→{sb['oppose']}명 "
        f"({'+' if d_oppose >= 0 else ''}{d_oppose})"
    )
