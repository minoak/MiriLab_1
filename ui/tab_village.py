# -*- coding: utf-8 -*-
"""정책 인생극장 탭 — 정책 패키지에 대해 대조 3명의 인생을 '카드 이야기'로.

DESIGN v3 + 슬라이스 2(프롬프트 통일). 인구통계로 대조되는 3명(수혜/경계/사각)을
선별해 세 장의 카드로 보여준다. **한 장을 뽑으면(펼치면) 그 사람의 이야기가
서사로 펼쳐진다.** 미래·결과는 마지막에 간단한 태그로만. *같은 정책, 다른 인생.*

이 탭은 자체 정책 선택기를 두지 않는다. **사이드바에서 입력한 단일 정책 원문
(view['policy'])과 태그 명세(view['policy_spec'])를 그대로 읽어** 모델에 함께
전달한다 → SNS축과 인생극장이 같은 정책·같은 태그를 본다('프롬프트 통일').
여러 정책 동시 실험은 접힌 '확인용 데모'(run_contrast_sim, 멀티 패키지)로 남김.

이 탭은 view 의 'selection'(대조 선별)과 'village'(3인 시뮬 궤적)를 읽는다.

(구 '미리 마을' 오버월드 맵/마을 집계는 제거. 확장 비전 placeholder 만 남김.)
"""

import streamlit as st

from graph.spaces import place_label, status_label


# 정책 관여 상태별 색
_STATUS_COLOR = {
    "received": "#27AE60",   # 수령 = 초록
    "applied": "#2980B9",    # 신청 = 파랑
    "aware": "#F39C12",      # 알게 됨 = 주황
    "blocked": "#E74C3C",    # 막힘 = 빨강
    "unaware": "#9E9E9E",    # 모름 = 회색
}
# 역할(role_key) → 색
_ROLE_COLOR = {
    "beneficiary": "#27AE60",   # 수혜 = 초록
    "borderline": "#F39C12",    # 경계 = 주황
    "blindspot": "#E74C3C",     # 사각 = 빨강
}
# 커버리지 셀 상태 → 기호 (매트릭스용)
_CELL_SYM = {"received": "✓", "blocked": "⊘", "eligible": "◐", "out": "·"}

# 카드뽑기: 지금 펼친 카드의 persona id 를 담는 세션 키
_OPEN_KEY = "village_open_card"


# ---------------------------------------------------------------------------
# 작은 렌더 헬퍼
# ---------------------------------------------------------------------------
def _arrow(a: int, b: int) -> str:
    """두 값의 변화 방향 화살표."""
    if b > a:
        return "↑"
    if b < a:
        return "↓"
    return "→"


def _tag(text: str, color: str) -> str:
    """작은 색 태그(html). 결말·지표 같은 '결과'를 간단히 붙일 때."""
    return (
        f"<span style='display:inline-block;background:{color};color:#fff;"
        f"padding:2px 10px;border-radius:10px;font-size:0.78rem;"
        f"margin:2px 4px 2px 0;white-space:nowrap;'>{text}</span>"
    )


# ---------------------------------------------------------------------------
# 실행 — 사이드바 단일 정책(+태그)으로 (슬라이스 2: 프롬프트 통일)
# ---------------------------------------------------------------------------
def _render_runner(view):
    """사이드바에서 입력한 단일 정책 원문 + policy_spec(태그)으로 대조 시뮬을 돌린다.

    인생극장은 자체 정책 선택기를 두지 않는다. 사이드바 입력을 그대로 모델에 전달해
    SNS축과 같은 정책·같은 태그를 보게 한다(프롬프트 통일). spec 의 태그는
    package_text 를 거쳐 시뮬 프롬프트에 함께 실린다.
    """
    from policy_spec import tag_line
    from graph.llm import has_real_key
    from ui.state_helpers import run_contrast_sim

    personas = view.get("personas") or []
    policy = (view.get("policy") or "").strip()
    spec = dict(view.get("policy_spec") or {})

    st.markdown("#### 🎬 인생극장 실행 — 사이드바에서 입력한 정책으로")

    if not policy:
        st.warning(
            "먼저 좌측 사이드바에서 정책을 입력하고 **시뮬레이션 실행**을 누르세요. "
            "그 정책이 인생극장에도 그대로 쓰입니다."
        )
        return

    # 어떤 정책·태그가 모델에 전달되는지 그대로 보여준다(프롬프트 통일 가시화).
    name = spec.get("name") or "직접 입력 정책"
    st.caption(f"대상 정책: **{name}**")
    line = tag_line(spec)
    if line:
        st.markdown(
            f"<div style='color:#2C3E50;font-size:0.85rem;margin:-4px 0 8px;'>"
            f"🏷️ {line}</div>",
            unsafe_allow_html=True,
        )

    can_run = bool(policy and personas)
    if st.button("▶ 인생극장 실행", type="primary", disabled=not can_run,
                 key="village_run_contrast"):
        # spec 에 원문/이름을 방어적으로 보강(사이드바에서 이미 채워지지만 안전망).
        if spec:
            spec.setdefault("text", policy)
            spec.setdefault("name", name)
        mock = not has_real_key()
        result = run_contrast_sim(
            [policy], personas, grounded=True, mock=mock,
            specs=[spec] if spec else None,   # 사이드바 태그 명세 직접 주입(재추출 X)
        )
        view["selection"] = result.get("selection") or {}
        view["village"] = result.get("village") or {}
        view["policies"] = [policy]
        st.session_state["view"] = view
        st.session_state[_OPEN_KEY] = None   # 새 시뮬 → 펼친 카드 초기화
        st.rerun()

    if not personas:
        st.warning("페르소나가 없습니다. 먼저 좌측 사이드바에서 시뮬레이션을 실행하세요.")


def _render_package_demo(view):
    """(격하) 여러 정책을 한 사람 삶에 동시에 비추는 '확인용 데모'.

    사이드바 단일 정책과 별개로, 정책 간 차등(수혜·간접·사각)을 확인할 때만 쓴다.
    실작동의 진실원은 사이드바 단일 정책이며, 이건 접힌 보조 도구다.
    """
    from sample_policies import PACKAGES, SAMPLES
    from graph.llm import has_real_key
    from ui.state_helpers import run_contrast_sim

    personas = view.get("personas") or []
    with st.expander("🧪 여러 정책 함께 실험 (확인용 데모)", expanded=False):
        st.caption(
            "여러 정책을 동시에 시행했다고 가정하고 한 사람 삶에 비춰 보는 데모입니다. "
            "사이드바 단일 정책과는 별개 경로예요(정책 간 차등 확인용)."
        )
        mode = st.radio(
            "선택 방식", ["추천 패키지", "직접 고르기"],
            horizontal=True, key="village_pkg_mode",
        )
        if mode == "추천 패키지":
            pkg_name = st.selectbox("패키지", list(PACKAGES.keys()),
                                    key="village_pkg_name")
            policies = list(PACKAGES.get(pkg_name) or [])
        else:
            policies = st.multiselect(
                "정책(여러 개 선택 가능)", list(SAMPLES.keys()),
                default=list(SAMPLES.keys())[:2], key="village_pkg_multi",
            )
        if policies:
            st.caption("선택: " + "  +  ".join(policies))

        can_run = bool(policies and personas)
        if st.button("▶ 패키지 데모 실행", disabled=not can_run,
                     key="village_run_pkg_demo"):
            mock = not has_real_key()
            result = run_contrast_sim(policies, personas, grounded=True, mock=mock)
            view["selection"] = result.get("selection") or {}
            view["village"] = result.get("village") or {}
            view["policies"] = policies
            st.session_state["view"] = view
            st.session_state[_OPEN_KEY] = None   # 새 시뮬 → 펼친 카드 초기화
            st.rerun()


def _render_specs(specs: list):
    """정책별 타깃 명세(나이·소득·가구·채널)를 expander 로."""
    if not specs:
        return
    with st.expander("🎯 정책별 타깃 명세 (누구를 대상으로?)", expanded=False):
        for s in specs:
            age = s.get("age") or (0, 0)
            inc = "/".join(s.get("income") or []) or "무관"
            fam = s.get("family_kw") or "무관"
            ch = place_label(s.get("channel", ""))
            st.markdown(
                f"- **{s.get('name','')}** — 나이 {age[0]}~{age[1]} · "
                f"소득 {inc} · 가구 {fam} · 주채널 {ch}"
            )


# ---------------------------------------------------------------------------
# 세 장의 카드 — 한 장을 뽑으면 그 인물의 이야기가 서사로 펼쳐진다
# ---------------------------------------------------------------------------
def _render_stories(selection: dict, village: dict):
    """대조 3인을 '카드뽑기'로. 한 번에 한 장만 펼쳐 그 사람의 이야기를 읽는다."""
    trio = selection.get("trio") or []
    if not trio:
        return
    residents = {r.get("id"): r for r in (village.get("residents") or [])}

    st.markdown("### 🃏 세 장의 카드 — 한 장을 뽑아 이야기를 펼치세요")
    st.caption("같은 정책, 다른 인생. 카드를 골라 그 사람의 6개월을 따라가 보세요.")

    trio_ids = [(t.get("persona") or {}).get("id") for t in trio]
    open_pid = st.session_state.get(_OPEN_KEY)
    if open_pid not in trio_ids:        # 유효하지 않으면(시뮬 바뀜 등) 접힘 상태
        open_pid = None

    for t in trio:
        pid = (t.get("persona") or {}).get("id")
        _render_card(t, residents.get(pid), is_open=(pid == open_pid))


def _render_card(t: dict, resident: dict, is_open: bool):
    """카드 1장 — 앞면(역할·인물·티저)은 항상, 펼치면 서사 이야기 + 결말 태그."""
    p = t.get("persona") or {}
    d = p.get("demographics") or {}
    color = _ROLE_COLOR.get(t.get("role_key"), "#7F8C8D")
    name = p.get("name", "")
    pid = p.get("id", name)

    with st.container(border=True):
        # --- 카드 앞면(항상 보임) ---
        st.markdown(
            f"<span style='display:inline-block;background:{color};color:#fff;"
            f"padding:2px 12px;border-radius:12px;font-weight:bold;'>"
            f"{t.get('role','')}</span> &nbsp;<b>{name}</b> · "
            f"{d.get('age','')}세 {d.get('sex','')}",
            unsafe_allow_html=True,
        )
        st.caption(f"{d.get('occupation','')} · {d.get('province','')} {d.get('district','')}")
        st.markdown(f"*{t.get('headline','')}*")   # 티저(이야기 맛보기)

        # --- 펼치기 / 접기 (카드뽑기: 한 번에 한 장) ---
        if not is_open:
            if st.button(f"🃏 «{name}» 카드 펼치기", key=f"open_{pid}",
                         use_container_width=True):
                st.session_state[_OPEN_KEY] = pid
                st.rerun()
            return

        if st.button("◂ 접기", key=f"close_{pid}"):
            st.session_state[_OPEN_KEY] = None
            st.rerun()

        # --- 펼친 카드: 서사 이야기 ---
        st.markdown("---")
        _render_narrative(t, resident)


def _render_narrative(t: dict, resident: dict):
    """한 인물의 시간 경과 이야기를 서사 산문으로. 결과는 마지막 태그로만."""
    tl = (resident or {}).get("timeline") or []
    if not tl:
        st.info("아직 이 인물의 시뮬 궤적이 없습니다.")
        return

    for step in tl:
        # 시점·장소를 작은 '씬 헤더'로 (딱딱한 칩 대신 서사 톤)
        st.markdown(
            f"<div style='color:#8E44AD;font-size:0.82rem;margin:8px 0 2px;'>"
            f"— {step.get('label','')} · {place_label(step.get('place','home'))} —</div>",
            unsafe_allow_html=True,
        )
        st.markdown(step.get("action", ""))   # 서사 본문(2~4문장)

    # --- 결말: 간단한 태그로만 (미래·결과) ---
    _render_outcome_tags(t, tl)


def _render_outcome_tags(t: dict, tl: list):
    """이야기의 결말을 간단한 태그 몇 개로 (경제·만족 변화, 최종 상태, 수혜 수)."""
    e0, eN = tl[0].get("economic", 0), tl[-1].get("economic", 0)
    w0, wN = tl[0].get("wellbeing", 0), tl[-1].get("wellbeing", 0)
    final = tl[-1].get("policy_status", "unaware")
    cover = (t.get("score") or {}).get("cover", 0)

    tags = [
        _tag(f"결말 · {status_label(final)}", _STATUS_COLOR.get(final, "#9E9E9E")),
        _tag(f"경제 {_arrow(e0, eN)}", "#34495E"),
        _tag(f"만족 {_arrow(w0, wN)}", "#34495E"),
        _tag(f"{cover}개 수혜", _ROLE_COLOR.get(t.get("role_key"), "#7F8C8D")),
    ]
    st.markdown(
        "<div style='margin-top:12px'>" + "".join(tags) + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 전체 커버리지 매트릭스 (증거)
# ---------------------------------------------------------------------------
def _render_matrix(selection: dict):
    """전체 페르소나 × 정책 커버리지 매트릭스(증거 뷰)."""
    rows = selection.get("matrix") or []
    if not rows:
        return
    trio_ids = {
        (t.get("persona") or {}).get("id")
        for t in (selection.get("trio") or [])
    }
    st.caption("✓ 수혜  ·  ⊘ 자격되나 접근막힘  ·  ◐ 자격되나 미수혜  ·  · 대상아님   (★ = 대조 3인)")
    table = []
    for r in rows:
        row = {
            "": "★" if r.get("id") in trio_ids else "",
            "이름": r.get("name", ""),
            "나이": r.get("age", 0),
            "접근": round(r.get("access", 0), 2),
        }
        for c in r.get("cells") or []:
            label = (c.get("policy") or "")[:7]
            row[label] = f"{_CELL_SYM.get(c.get('state'), '·')} {c.get('benefit', 0):.2f}"
        row["커버"] = r.get("cover", 0)
        row["막힘"] = r.get("blocked", 0)
        table.append(row)
    st.dataframe(table, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# 미리 마을 placeholder (자리만 — 확장 비전)
# ---------------------------------------------------------------------------
def _render_placeholder():
    """제거된 '미리 마을'의 자리. 나중에 마을·도시 규모 확장 비전으로 부활 예정."""
    with st.container(border=True):
        st.markdown("🏘️ **미리 마을** — *준비 중 (다음 버전)*")
        st.caption(
            "3명의 대조를 LLM 신경망으로 마을·도시 규모까지 확장하는 비전. "
            "지금은 3인 인생극장에 집중합니다."
        )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def render_village_tab(view):
    """정책 인생극장 탭 본체. view 가 None 이면 안내 후 return."""
    if view is None:
        st.info("먼저 좌측에서 정책을 입력하고 시뮬레이션을 실행하세요.")
        return

    st.subheader("정책 인생극장 — 같은 정책, 다른 인생")
    st.caption(
        "사이드바에서 입력한 정책으로, 인구통계로 대조되는 3명의 인생이 시간에 따라 "
        "어떻게 갈리는지 카드 이야기로 펼쳐집니다."
    )

    # 1) 실행 — 사이드바 단일 정책(+태그)으로 (프롬프트 통일)
    _render_runner(view)
    # (격하) 여러 정책 동시 실험은 접힌 확인용 데모로만 노출
    _render_package_demo(view)

    selection = view.get("selection") or {}
    if not selection.get("trio"):
        st.info("위에서 **▶ 인생극장 실행**을 누르세요. (사이드바에서 입력한 정책이 쓰입니다.)")
        return

    st.divider()

    # 2) 헤드라인 — 명세 + 세 장의 카드(뽑아서 서사 펼치기)
    _render_specs(selection.get("specs") or [])
    _render_stories(selection, view.get("village") or {})

    # 3) 증거 — 전체 커버리지 매트릭스 + 정직한 노트
    st.divider()
    st.markdown("#### 📊 전체 커버리지 매트릭스 (증거)")
    _render_matrix(selection)
    for note in selection.get("notes") or []:
        st.caption("· " + note)

    # 4) 미리 마을 자리(확장 비전 placeholder)
    st.divider()
    _render_placeholder()
