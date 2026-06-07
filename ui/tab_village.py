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

(구 '미리 마을' 오버월드 맵/마을 집계·확장 비전 placeholder 모두 제거 — 진짜 '미리마을' 탭이 별도로 있다.)
"""

from html import escape

import streamlit as st

from graph.spaces import place_label, status_label
from ui.rerun_util import rerun_fragment


# 정책 관여 상태 → (이모지, 짧은 라벨, 색). 카드 가시성의 핵심:
# '모름 → 알게 됨 → 신청 → 막힘/수령' 의 사건을 한눈에 색·기호로 보이게 한다.
_STATUS_META = {
    "received": ("✅", "수령", "#27AE60"),    # 정책에 닿아 혜택 받음
    "applied":  ("📨", "신청", "#2980B9"),    # 신청까지 진행
    "aware":    ("👀", "알게 됨", "#F39C12"),  # 알았지만 아직 신청 전
    "blocked":  ("⛔", "막힘", "#E74C3C"),     # 막힘 — 사유(요건/절차)는 barrier 인용이 말함
    "unaware":  ("🚫", "모름", "#9E9E9E"),     # 존재조차 닿지 못함
}


def _status_meta(status: str):
    """상태 키 -> (이모지, 짧은 라벨, 색). 모르는 키도 죽지 않게."""
    return _STATUS_META.get(status, ("•", status_label(status), "#9E9E9E"))
# 역할(role_key) → 색
_ROLE_COLOR = {
    "beneficiary": "#27AE60",   # 수혜 = 초록
    "borderline": "#F39C12",    # 경계 = 주황
    "blindspot": "#E74C3C",     # 사각 = 빨강
    "out": "#BDC3C7",           # 대상 아님(무관) = 회색
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


def _final_outcome(resident: dict) -> tuple:
    """timeline → 최종 접근 결과 (emoji, 짧은 라벨, 색). 칩·버튼 라벨의 공용 진실원.

    우선순위는 콜아웃과 동일(받음 > 막힘 > 진행 > 못 닿음) — 단, 받은 적 없이
    막힌 적이 있으면 '막힘'을 앞세운다(도움 필요 신호를 놓치지 않게).
    """
    tl = (resident or {}).get("timeline") or []
    if not tl:
        return ("•", "기록 없음", "#9E9E9E")
    final = tl[-1].get("policy_status", "unaware")
    ever_received = any(s.get("policy_status") == "received" for s in tl)
    blocked = any(s.get("policy_status") == "blocked" for s in tl)
    if ever_received:
        return ("✅", "정책에 닿음", "#27AE60")
    if blocked or final == "blocked":
        return ("⛔", "막힘", "#E74C3C")
    if final == "applied":
        return ("📨", "신청함", "#2980B9")
    if final == "aware":
        return ("👀", "알게만 됨", "#F39C12")
    return ("🚫", "끝내 못 닿음", "#9E9E9E")


def _front_access_chip(resident: dict) -> str:
    """펼치지 않아도 보이는 '최종 접근 결과' 작은 신호(테두리 칩)."""
    tl = (resident or {}).get("timeline") or []
    if not tl:
        return ""
    emoji, txt, color = _final_outcome(resident)
    return (
        f"<span style='display:inline-block;border:1px solid {color};color:{color};"
        f"background:{color}10;padding:1px 9px;border-radius:10px;font-size:0.76rem;"
        f"margin-top:4px;'>{emoji} {txt}</span>"
    )


# ---------------------------------------------------------------------------
# 실행 — 사이드바 단일 정책(+태그)으로 (슬라이스 2: 프롬프트 통일)
# ---------------------------------------------------------------------------
def _render_runner(view):
    """인생극장 재실행(축2부터) — 사이드바 한 버튼의 축1 결과를 재사용한다(§8-2).

    사이드바 '시뮬레이션 실행'이 축1→축2→축3를 이미 완주하므로, 이 버튼은
    같은 t0 기록 위에서 축2(시간 전개)만 다시 굴리는 **재실행**이다.
    축1 전수 react 호출이 통째로 절약된다(층1 체크포인트 — 설계방향서 §6).
    """
    from policy_spec import tag_line
    from ui.state_helpers import rerun_from_axis2

    personas = view.get("personas") or []
    policy = (view.get("policy") or "").strip()
    spec = dict(view.get("policy_spec") or {})

    st.markdown("#### 🔁 인생극장 재실행 (축2부터)")
    st.caption(
        "사이드바 실행이 만든 시민 반응(t0 기록)은 그대로 두고, "
        "시간 전개(인생극장)만 다시 굴립니다 — 축1 호출 없음."
    )

    if not policy:
        st.warning(
            "먼저 좌측 사이드바에서 정책을 입력하고 **시뮬레이션 실행**을 누르세요. "
            "인생극장은 그 실행에 포함되어 자동으로 채워집니다."
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
    if st.button("🔁 재실행 (축2부터 — 축1 재사용)", disabled=not can_run,
                 key="village_run_contrast"):
        out = rerun_from_axis2()
        if out is None:
            st.warning(
                "재사용할 축1 체크포인트가 없습니다. "
                "좌측 사이드바에서 **시뮬레이션 실행**을 먼저 눌러 주세요."
            )
        else:
            st.session_state[_OPEN_KEY] = None   # 새 시뮬 → 펼친 카드 초기화
            rerun_fragment()

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
            rerun_fragment()


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
# 세 장의 커버 카드(인스타 카드뉴스 스타일) — 한 장을 뽑으면 이야기가 아래로 펼쳐진다
# ---------------------------------------------------------------------------
# 카테고리 그룹 헤더 메타: (role_key, 한글, 이모지, 색). 표시 순서 = 수혜 → 경계 → 사각.
_GROUP_META = [
    ("beneficiary", "수혜", "🟢", "#27AE60"),
    ("borderline", "경계", "🟠", "#F39C12"),
    ("blindspot", "사각지대", "🔴", "#E74C3C"),
]

# 역할 → 커버 그라데이션 (진한색 → 밝은색). 카드뉴스 가시성의 핵심 = 색면.
_ROLE_GRADIENT = {
    "beneficiary": ("#1E8449", "#52BE80"),
    "borderline": ("#CA8A04", "#F5B041"),
    "blindspot": ("#C0392B", "#EC7063"),
    "out": ("#7F8C8D", "#B2BABB"),
}


def _short_quote(reactions: dict, pid: str, limit: int = 64) -> str:
    """이 사람의 t0 첫 반응에서 '한 마디' 인용을 뽑는다(없으면 "")."""
    text = str(((reactions or {}).get(pid) or {}).get("text") or "").strip()
    if not text:
        return ""
    # 한 문장이면 그대로, 길면 limit 에서 자르고 말줄임.
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _region_label(d: dict) -> str:
    """province+district 표시용 결합 — district 의 '도(道) 접두' 중복을 정리한다.

    데이터셋 district 는 '경상북-예천군'처럼 도를 다시 품는 표기가 있어 그대로
    이으면 '경상북 경상북-예천군'이 된다. 접두가 겹치면 잘라 '경상북 예천군'으로.
    """
    prov = str(d.get("province", "") or "").strip()
    dist = str(d.get("district", "") or "").strip()
    if prov and dist.startswith(prov + "-"):
        dist = dist[len(prov) + 1:]
    return f"{prov} {dist}".strip()


def _cover_chip_html(resident: dict) -> str:
    """커버(그라데이션 헤더)용 최종 결과 칩 — 반투명 흰 배경에 흰 글씨."""
    tl = (resident or {}).get("timeline") or []
    if not tl:
        return ""
    emoji, txt, _color = _final_outcome(resident)
    return (
        f"<span style='background:rgba(255,255,255,.24);color:#fff;"
        f"padding:2px 10px;border-radius:12px;font-size:.74rem;font-weight:600;"
        f"white-space:nowrap;'>{emoji} {txt}</span>"
    )


def _cover_card_html(t: dict, resident: dict, quote: str = "") -> str:
    """커버 카드 1장 HTML(순수) — 인스타 카드뉴스 스타일.

    위 = 역할색 그라데이션 면(역할 배지 + 최종결과 칩 + 아바타 원 + 큰 이름),
    아래 = 흰 본문(시민의 '한 마디' 인용 + 헤드라인). 버튼은 호출측 st.button.
    """
    p = t.get("persona") or {}
    d = p.get("demographics") or {}
    c1, c2 = _ROLE_GRADIENT.get(t.get("role_key"), ("#7F8C8D", "#B2BABB"))
    name = str(p.get("name", ""))
    initial = escape(name[:1] or "?")
    age = escape(str(d.get("age", "")))
    sex = escape(str(d.get("sex", "")))
    occ = escape(str(d.get("occupation", "")))
    region = escape(_region_label(d))
    role = escape(str(t.get("role", "")))
    headline = escape(str(t.get("headline", "")))

    # 본문: 한 마디(인용)가 있으면 그것이 주인공, 없으면 헤드라인을 크게.
    if quote:
        body = (
            f"<div style='font-size:.95rem;font-weight:700;color:#2C3E50;"
            f"line-height:1.5;word-break:keep-all;'>“{escape(quote)}”</div>"
            f"<div style='color:#8A97A3;font-size:.78rem;margin-top:7px;'>"
            f"{headline}</div>"
        )
    else:
        body = (
            f"<div style='font-size:.92rem;font-weight:700;color:#2C3E50;"
            f"line-height:1.5;word-break:keep-all;'>{headline}</div>"
        )

    return (
        # 카드 틀: 둥근 모서리 + 그림자(카드뉴스 한 장)
        f"<div style='border-radius:16px;overflow:hidden;margin:2px 0 10px;"
        f"box-shadow:0 4px 14px rgba(0,0,0,.13);'>"
        # ── 색면(그라데이션 헤더) ──
        f"<div style='background:linear-gradient(135deg,{c1},{c2});"
        f"padding:13px 15px 13px;color:#fff;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"gap:6px;'>"
        f"<span style='background:rgba(255,255,255,.24);padding:2px 11px;"
        f"border-radius:12px;font-size:.78rem;font-weight:800;letter-spacing:.4px;"
        f"white-space:nowrap;'>{role}</span>"
        f"{_cover_chip_html(resident)}"
        f"</div>"
        f"<div style='display:flex;align-items:center;gap:11px;margin-top:13px;'>"
        # 아바타 원(이름 첫 글자) — 사진 없는 데이터셋의 프로필 대용
        f"<div style='width:46px;height:46px;border-radius:50%;background:#fff;"
        f"color:{c1};display:flex;align-items:center;justify-content:center;"
        f"font-size:1.3rem;font-weight:800;flex:none;'>{initial}</div>"
        f"<div style='min-width:0;'>"
        f"<div style='font-size:1.22rem;font-weight:800;line-height:1.3;'>"
        f"{escape(name)} <span style='font-weight:500;font-size:.85rem;"
        f"opacity:.95;'>{age}세 {sex}</span></div>"
        f"<div style='font-size:.78rem;opacity:.92;white-space:nowrap;"
        f"overflow:hidden;text-overflow:ellipsis;'>{occ} · {region}</div>"
        f"</div></div></div>"
        # ── 흰 본문 ──
        f"<div style='background:#fff;padding:12px 15px 13px;'>{body}</div>"
        f"</div>"
    )


def _empty_group_html(label: str) -> str:
    """비어 있는 카테고리 자리 — 점선 빈 카드(레이아웃 유지 + 정직한 공백)."""
    return (
        f"<div style='border:2px dashed #D5DBDF;border-radius:16px;"
        f"padding:26px 12px;text-align:center;color:#95A5A6;font-size:.85rem;"
        f"margin:2px 0 10px;'>이번 시뮬에선<br><b>{escape(label)}</b> 없음</div>"
    )


def _mini_header_html(t: dict) -> str:
    """펼친 이야기 패널의 미니 헤더 — 커버와 같은 그라데이션 띠(연속성)."""
    p = t.get("persona") or {}
    d = p.get("demographics") or {}
    c1, c2 = _ROLE_GRADIENT.get(t.get("role_key"), ("#7F8C8D", "#B2BABB"))
    name = str(p.get("name", ""))
    return (
        f"<div style='background:linear-gradient(135deg,{c1},{c2});color:#fff;"
        f"border-radius:12px;padding:9px 14px;display:flex;align-items:center;"
        f"gap:10px;margin-bottom:10px;'>"
        f"<div style='width:34px;height:34px;border-radius:50%;background:#fff;"
        f"color:{c1};display:flex;align-items:center;justify-content:center;"
        f"font-size:1.05rem;font-weight:800;flex:none;'>{escape(name[:1] or '?')}</div>"
        f"<div style='font-size:1.02rem;font-weight:800;'>{escape(name)}"
        f"<span style='font-weight:500;font-size:.8rem;opacity:.95;'>"
        f" · {escape(str(d.get('age', '')))}세 {escape(str(d.get('sex', '')))} · "
        f"{escape(str(d.get('occupation', '')))}</span></div>"
        f"<span style='margin-left:auto;background:rgba(255,255,255,.24);"
        f"padding:2px 11px;border-radius:12px;font-size:.78rem;font-weight:800;"
        f"white-space:nowrap;'>{escape(str(t.get('role', '')))}</span>"
        f"</div>"
    )


def _toggle_open(pid):
    """카드 펼침 토글 — 같은 카드를 다시 누르면 접힌다(한 번에 한 장)."""
    st.session_state[_OPEN_KEY] = None if st.session_state.get(_OPEN_KEY) == pid else pid
    rerun_fragment()


def _render_groups(selection: dict, village: dict, reactions: dict | None = None):
    """커버 카드 3장(수혜/경계/사각) 나란히 + 같은 처지 시민 미니 버튼.

    인스타 카드뉴스 레이아웃: 카테고리별 대표가 색면 커버 카드로 한 줄에 서고,
    누구든 펼치면 그 사람의 이야기가 카드 줄 **아래 전폭 패널**로 열린다
    (좁은 칼럼 안에서 서사가 찌그러지지 않게). 한 번에 한 명.
    """
    groups = selection.get("groups") or {}
    if not any(groups.get(rk) for rk, *_ in _GROUP_META):
        return
    residents = {r.get("id"): r for r in (village.get("residents") or [])}
    reactions = reactions or {}

    # 유효한 펼침 id(시뮬 바뀌면 접힘) + pid → (entry, resident) 색인
    entry_by_pid = {}
    for rk, *_ in _GROUP_META:
        for e in (groups.get(rk) or []):
            pid = (e.get("persona") or {}).get("id")
            if pid:
                entry_by_pid[pid] = e
    open_pid = st.session_state.get(_OPEN_KEY)
    if open_pid not in entry_by_pid:
        open_pid = None

    st.markdown("### 🃏 정책 대상자, 갈리는 인생 — 같은 정책 다른 결과")
    st.caption("카테고리별 대표 + 같은 처지의 나머지 시민. 누구든 펼쳐 그 사람의 6개월을 따라가 보세요.")

    cols = st.columns(len(_GROUP_META), gap="medium")
    for (rk, label, emoji, color), col in zip(_GROUP_META, cols):
        entries = groups.get(rk) or []
        with col:
            # 그룹 헤더: 색 라벨 + 인원 칩
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:7px;"
                f"margin:6px 0 8px;'>"
                f"<span style='font-size:1.02rem;font-weight:800;color:{color};'>"
                f"{emoji} {label}</span>"
                f"<span style='background:{color}1A;color:{color};padding:1px 10px;"
                f"border-radius:10px;font-size:.8rem;font-weight:700;'>"
                f"{len(entries)}명</span></div>",
                unsafe_allow_html=True,
            )
            if not entries:
                st.markdown(_empty_group_html(label), unsafe_allow_html=True)
                continue

            # 대표 = 커버 카드
            rep = entries[0]
            rep_p = rep.get("persona") or {}
            rep_pid = rep_p.get("id", rep_p.get("name", ""))
            quote = _short_quote(reactions, rep_pid)
            st.markdown(
                _cover_card_html(rep, residents.get(rep_pid), quote),
                unsafe_allow_html=True,
            )
            btn_label = ("▲ 접기" if rep_pid == open_pid
                         else f"🃏 «{rep_p.get('name', '')}» 이야기 펼치기")
            if st.button(btn_label, key=f"toggle_{rep_pid}", width="stretch"):
                _toggle_open(rep_pid)

            # 같은 처지의 나머지 — 미니 버튼(이모지 = 각자의 최종 결과)
            rest = entries[1:]
            if rest:
                st.caption(f"같은 {label} {len(rest)}명 더")
                for e in rest:
                    p = e.get("persona") or {}
                    pid = p.get("id", p.get("name", ""))
                    d = p.get("demographics") or {}
                    o_emoji, o_txt, _c = _final_outcome(residents.get(pid))
                    mark = "▲" if pid == open_pid else o_emoji
                    mini = (f"{mark} {p.get('name', '')} · "
                            f"{d.get('age', '')}세 — {o_txt}")
                    if st.button(mini, key=f"toggle_{pid}", width="stretch"):
                        _toggle_open(pid)

    # 펼친 사람의 이야기 — 카드 줄 아래 전폭 패널
    if open_pid:
        _render_story_panel(entry_by_pid[open_pid], residents.get(open_pid))


def _render_story_panel(t: dict, resident: dict):
    """펼친 카드의 이야기 패널(전폭) — 미니 헤더 + 서사 + 접기."""
    p = t.get("persona") or {}
    pid = p.get("id", p.get("name", ""))
    with st.container(border=True):
        st.markdown(_mini_header_html(t), unsafe_allow_html=True)
        _render_narrative(t, resident)
        if st.button("▲ 카드 접기", key=f"close_{pid}"):
            st.session_state[_OPEN_KEY] = None
            rerun_fragment()


def _events(timeline: list) -> list:
    """timeline 을 '사건' 리스트로 압축한다(시점 눈금 대신 사건 기준).

    연속된 같은 policy_status 를 하나의 사건으로 묶는다. 사각지대 인물은 사건 1개
    (`끝내 모름`), 수혜 인물은 여러 개(`알게됨 → 신청 → 수령`)가 되어 '무슨 일이
    있었나'가 자연스럽게 드러난다. 각 사건 = {"status": str, "steps": [step,...]}.
    """
    events = []
    for step in timeline:
        s = step.get("policy_status", "unaware")
        if events and events[-1]["status"] == s:
            events[-1]["steps"].append(step)
        else:
            events.append({"status": s, "steps": [step]})
    return events


def _journey_strip_html(events: list) -> str:
    """접근 여정 칩 띠 HTML(순수) — `알게됨(주민센터) → 신청 → ⛔막힘`. 한눈에 경로·막힘."""
    chips = []
    for ev in events:
        emoji, label, color = _status_meta(ev["status"])
        place = place_label((ev["steps"][0] or {}).get("place", "home"))
        chips.append(
            f"<span style='display:inline-flex;align-items:center;background:{color};"
            f"color:#fff;padding:3px 11px;border-radius:12px;font-size:0.82rem;"
            f"white-space:nowrap;'>{emoji}&nbsp;{label}"
            f"<span style='opacity:0.85;font-size:0.72rem;'>&nbsp;·&nbsp;{place}</span>"
            f"</span>"
        )
    arrow = "<span style='color:#bbb;margin:0 2px;'>→</span>"
    return (
        "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:6px;"
        "margin:4px 0 10px;'>" + arrow.join(chips) + "</div>"
    )


def _render_journey_strip(events: list):
    st.markdown(_journey_strip_html(events), unsafe_allow_html=True)


def _outcome_callout_html(events: list) -> str:
    """접근의 '결론' 콜아웃 HTML(순수) — 상태 라벨 + LLM 인용만.

    결론은 전적으로 시뮬 '결과'(events)에서 나온다 — 사전 역할 라벨에 의존하지 않는다.
    코드는 문장을 짓지 않는다: 상태 토큰의 사전적 의미(라벨)와 인용(barrier/
    reached_via)까지가 코드의 몫, '왜·어떻게'는 위 여정·산문이 말한다.
    (구 템플릿의 '신청을 시도했지만'·'자격을 갖추고도'는 데이터에 없는 주장이었다.)
    """
    final = events[-1]["status"] if events else "unaware"
    ever_received = any(e["status"] == "received" for e in events)
    blocked = any(e["status"] == "blocked" for e in events)

    def _first(status_key: str, field: str) -> str:
        """해당 상태 사건들에서 field(LLM 자유텍스트)의 첫 비어있지 않은 값."""
        for e in events:
            if e["status"] != status_key:
                continue
            val = next(
                (s[field].strip() for s in e["steps"] if (s.get(field) or "").strip()),
                "",
            )
            if val:
                return val
        return ""

    # 우선순위 = 결과(받음 > 막힘 > 진행 중 > 못 닿음). dist_key/역할과 같은 기준이라
    # 콜아웃·배지·결과표가 한 결과에서 일관되게 나온다(받았다 중간에 막힌 사람도 '수혜').
    if ever_received:
        via = _first("received", "reached_via")
        quote = f" — {escape(via)}" if via else ""
        icon, msg, color = "✅", f"<b>수령</b>{quote}", "#27AE60"
    elif blocked or final == "blocked":
        barrier = _first("blocked", "barrier")
        quote = f" — {escape(barrier)}" if barrier else ""
        icon, msg, color = "⛔", f"<b>막힘</b>{quote}", "#E74C3C"
    elif final == "applied":
        icon, msg, color = "📨", "<b>신청</b> — 결과 대기", "#2980B9"
    elif final == "aware":
        icon, msg, color = "👀", "<b>알게 됨</b> — 신청까지는 안 감", "#F39C12"
    else:  # unaware
        icon, msg, color = "🚫", "<b>끝내 모름</b>", "#9E9E9E"

    return (
        f"<div style='border-left:4px solid {color};background:{color}14;"
        f"padding:8px 12px;border-radius:4px;margin:2px 0 10px;font-size:0.9rem;'>"
        f"{icon} {msg}</div>"
    )


def _render_outcome_callout(events: list):
    st.markdown(_outcome_callout_html(events), unsafe_allow_html=True)


def _render_event_detail(events: list):
    """사건별 산문 — 상태를 앞세운 작은 헤더 + 그 사건의 행동(중복 문장은 생략)."""
    seen = None
    for ev in events:
        emoji, label, color = _status_meta(ev["status"])
        steps = ev["steps"]
        place = place_label((steps[0] or {}).get("place", "home"))
        t0 = (steps[0] or {}).get("label", "")
        t1 = (steps[-1] or {}).get("label", "")
        when = t0 if t0 == t1 else f"{t0} ~ {t1}"
        st.markdown(
            f"<div style='margin:12px 0 4px;'>"
            f"<span style='background:{color};color:#fff;padding:2px 11px;"
            f"border-radius:10px;font-size:0.82rem;font-weight:bold;'>{emoji} {label}</span>"
            f"<span style='color:#555;font-size:0.85rem;'> · {place}</span>"
            f"<span style='color:#aaa;font-size:0.74rem;'> {when}</span></div>",
            unsafe_allow_html=True,
        )
        # 방향 추적: 어떻게/누구를 통해 닿았나(경로) + 막혔다면 어디서(막힌 지점)
        via = ((steps[0] or {}).get("reached_via") or "").strip()
        if via:
            st.markdown(
                f"<div style='color:#2980B9;font-size:0.8rem;margin:1px 0 3px;'>"
                f"↳ 경로 · {escape(via)}</div>",
                unsafe_allow_html=True,
            )
        if ev["status"] == "blocked":
            barrier = next(
                (s["barrier"].strip() for s in steps if (s.get("barrier") or "").strip()),
                "",
            )
            if barrier:
                st.markdown(
                    f"<div style='color:#E74C3C;font-size:0.8rem;margin:1px 0 3px;'>"
                    f"⛔ 막힌 지점 · {escape(barrier)}</div>",
                    unsafe_allow_html=True,
                )
        for step in steps:
            act = (step.get("action") or "").strip()
            if act and act != seen:    # mock 등 동일 문장 반복은 생략
                st.markdown(act)
                seen = act


def _render_narrative(t: dict, resident: dict):
    """한 인물의 이야기를 '접근 여정(사건별)'로. 여정 띠 + 결론 콜아웃 + 사건별 산문."""
    tl = (resident or {}).get("timeline") or []
    if not tl:
        st.info("아직 이 인물의 시뮬 궤적이 없습니다.")
        return

    events = _events(tl)

    # 1) 한눈에 보는 접근 여정(사건 띠)
    st.markdown("**🧭 접근 여정**")
    _render_journey_strip(events)
    # 2) 접근의 결론(막힘·도움 필요를 명시) — 전적으로 결과 기반
    _render_outcome_callout(events)

    # 3) 사건별 자세한 이야기
    st.markdown("---")
    _render_event_detail(events)

    # 4) 삶의 변화 요약 태그(경제·만족·수혜 수)
    _render_outcome_tags(t, tl)


# 최종 결과(timeline) → (태그 라벨, 색). 카드 '삶의 변화'의 결과 칩.
_STATUS_TAG = {
    "received": ("혜택 받음", "#27AE60"),
    "blocked": ("막혀 못 받음", "#E74C3C"),
    "unaware": ("끝내 못 닿음", "#9E9E9E"),
    "applied": ("신청 대기", "#2980B9"),
    "aware": ("신청 전", "#F39C12"),
}


def _render_outcome_tags(t: dict, tl: list):
    """삶의 변화를 간단한 태그로 (경제·만족 변화 + 최종 결과). 전적으로 결과 기반."""
    e0, eN = tl[0].get("economic", 0), tl[-1].get("economic", 0)
    w0, wN = tl[0].get("wellbeing", 0), tl[-1].get("wellbeing", 0)
    final = tl[-1].get("policy_status", "unaware") if tl else "unaware"
    blocked = any(s.get("policy_status") == "blocked" for s in tl)
    eff = "blocked" if (blocked and final != "received") else final
    label, color = _STATUS_TAG.get(eff, ("진행 중", "#7F8C8D"))
    tags = [
        _tag(f"경제 {_arrow(e0, eN)}", "#34495E"),
        _tag(f"만족 {_arrow(w0, wN)}", "#34495E"),
        _tag(label, color),
    ]
    st.markdown(
        "<div style='margin-top:6px'><span style='color:#888;font-size:0.78rem;'>"
        "삶의 변화 &nbsp;</span>" + "".join(tags) + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 전체 풀 분포 (대표성 숫자) — 3명 카드는 이 분포의 대표 사례일 뿐
# ---------------------------------------------------------------------------
# 사람 단위 4범주 (우선순위: 수혜 > 막힘 > 자격되나미수혜 > 대상아님)
_DIST_META = [
    ("received", "수혜", "#27AE60"),
    ("blocked", "막힘·도움 필요", "#E74C3C"),
    ("eligible", "자격되나 미수혜", "#F39C12"),
    ("out", "대상 아님", "#BDC3C7"),
]


def pool_distribution(rows: list) -> list:
    """커버리지 매트릭스 행들을 사람 단위 4범주로 집계한다(순수, 단일·다정책 모두).

    각 사람의 '가장 좋은 도달'로 한 범주에 넣는다:
      수혜(cover>0) > 막힘(blocked>0) > 자격되나미수혜(eligible>0) > 대상아님.
    Returns: [{key, label, color, count}] (고정 순서).
    """
    buckets = {"received": 0, "blocked": 0, "eligible": 0, "out": 0}
    for r in rows or []:
        if r.get("cover", 0) > 0:
            buckets["received"] += 1
        elif r.get("blocked", 0) > 0:
            buckets["blocked"] += 1
        elif r.get("eligible", 0) > 0:
            buckets["eligible"] += 1
        else:
            buckets["out"] += 1
    return [{"key": k, "label": l, "color": c, "count": buckets[k]}
            for k, l, c in _DIST_META]


def _distribution_bar_html(dist: list, total: int) -> str:
    """4범주 비율을 한 줄 누적 막대로(순수)."""
    if total <= 0:
        return ""
    segs = []
    for d in dist:
        if d["count"] <= 0:
            continue
        pct = d["count"] / total * 100
        segs.append(
            f"<div title='{d['label']} {d['count']}명' "
            f"style='width:{pct:.1f}%;background:{d['color']};height:100%;'></div>"
        )
    return (
        "<div style='display:flex;height:18px;border-radius:5px;overflow:hidden;"
        "border:1px solid #eee;margin:6px 0;'>" + "".join(segs) + "</div>"
    )


def _distribution_legend_html(dist: list) -> str:
    """범주 색·이름·수 범례(순수)."""
    parts = []
    for d in dist:
        parts.append(
            f"<span style='display:inline-flex;align-items:center;font-size:0.82rem;"
            f"margin-right:14px;'><span style='width:10px;height:10px;border-radius:2px;"
            f"background:{d['color']};display:inline-block;margin-right:4px;'></span>"
            f"{d['label']} <b style='margin-left:3px;'>{d['count']}</b></span>"
        )
    return "<div style='margin:4px 0 2px;'>" + "".join(parts) + "</div>"


# 결과 기반 분포: 사람 단위 4범주(시뮬 실제 결과 = dist_key). 표시 순서 고정.
_DIST_META_OUT = [
    ("received", "수혜(혜택 받음)", "#27AE60"),
    ("inprogress", "진행 중(알게됨·신청)", "#F39C12"),
    ("blocked", "막힘·도움 필요", "#E74C3C"),
    ("unaware", "끝내 못 닿음", "#9E9E9E"),
    ("out", "대상 아님(무관)", "#BDC3C7"),
]


def outcome_distribution(outcomes: list) -> list:
    """결과 행(contrast.select_trio_from_outcomes 의 outcomes)을 5범주로 집계(순수).

    각 사람의 실제 결과(dist_key)를 그대로 센다 — 비대상은 'out'(대상 아님)으로 분리.
    Returns: [{key, label, color, count}] (고정 순서).
    """
    buckets = {"received": 0, "inprogress": 0, "blocked": 0, "unaware": 0, "out": 0}
    for r in outcomes or []:
        k = r.get("dist_key", "inprogress")
        buckets[k if k in buckets else "inprogress"] += 1
    return [{"key": k, "label": l, "color": c, "count": buckets[k]}
            for k, l, c in _DIST_META_OUT]


def _render_distribution(outcomes: list):
    """전체 풀의 실제 결과 분포를 숫자 헤드라인 + 누적 막대로. 3명 카드 위 '대표성' 층."""
    dist = outcome_distribution(outcomes)
    total = sum(d["count"] for d in dist)
    if total <= 0:
        return
    st.markdown(f"#### 📈 전체 {total}명에게 이 정책이 어떻게 닿았나")
    st.markdown(_distribution_bar_html(dist, total), unsafe_allow_html=True)
    st.markdown(_distribution_legend_html(dist), unsafe_allow_html=True)
    blk = next((d["count"] for d in dist if d["key"] == "blocked"), 0)
    una = next((d["count"] for d in dist if d["key"] == "unaware"), 0)
    if blk or una:
        st.caption(
            f"이 중 막힘 {blk}명·못 닿음 {una}명이 정책 사각지대입니다. "
            "아래 3명은 이 정책 대상자 중에서 고른 대표 사례예요."
        )
    else:
        st.caption("아래 3명은 이 정책 대상자 중에서 고른 대표 사례예요.")


# ---------------------------------------------------------------------------
# 전체 결과표 (증거) — 전원의 실제 시뮬 결과
# ---------------------------------------------------------------------------
# 최종 상태 → 짧은 표시(결과표 셀)
_STATUS_SHORT = {
    "received": "✅ 수령", "applied": "📨 신청", "aware": "👀 알게됨",
    "blocked": "⛔ 막힘", "unaware": "🚫 못 닿음",
}

# 결과표 '구분' 칸: role_key → 라벨(대상자 역할 / 무관). 비대상이 경계처럼 안 보이게.
_ROLE_TABLE_LABEL = {
    "beneficiary": "수혜", "borderline": "경계",
    "blindspot": "사각", "out": "— 무관",
}


def _render_outcomes_table(outcomes: list, trio_ids: set):
    """전원의 실제 시뮬 결과 표(증거 뷰). '구분'으로 대상/무관까지 한눈에. 카드와 같은 데이터."""
    if not outcomes:
        return
    st.caption("구분: 수혜·경계·사각=정책 대상자 / —무관=대상 아님   |   "
               "✅ 수령 · 📨 신청 · 👀 알게됨 · ⛔ 막힘 · 🚫 못 닿음   (★ = 카테고리 대표)")
    table = []
    for r in outcomes:
        raw = r.get("raw_final", "")
        status_txt = _STATUS_SHORT.get(raw, raw)
        # 막힌 적 있으면(최종이 달라도) 막힘으로 표기 — '도움 필요'를 놓치지 않게.
        if r.get("ever_blocked") and raw != "received":
            status_txt = "⛔ 막힘"
        table.append({
            "": "★" if r.get("id") in trio_ids else "",
            "이름": r.get("name", ""),
            "나이": r.get("age", 0),
            "구분": _ROLE_TABLE_LABEL.get(r.get("role_key"), ""),
            "최종 결과": status_txt,
            "경제": f"{int(r.get('econ_delta', 0)):+d}",
            "만족": f"{int(r.get('wb_delta', 0)):+d}",
            "경로": (r.get("reached_via") or "")[:24],
            "막힌 지점": (r.get("barrier") or "")[:24],
        })
    # use_container_width 를 쓰면 9개 열을 화면 폭에 욱여넣어 칸이 잘리고 가로 스크롤이
    # 안 생긴다. 자연 폭(+긴 텍스트 열 넓힘)으로 두어 폭을 넘치면 가로 스크롤로 볼 수 있게.
    st.dataframe(
        table,
        hide_index=True,
        column_config={
            "경로": st.column_config.TextColumn("경로", width="large"),
            "막힌 지점": st.column_config.TextColumn("막힌 지점", width="large"),
        },
    )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
@st.fragment   # 탭 안 버튼/카드 펼침의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
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
    if not selection.get("outcomes"):
        st.info(
            "좌측 사이드바에서 **시뮬레이션 실행**을 누르면 인생극장까지 자동으로 "
            "채워집니다. (위 재실행 버튼은 시간 전개만 다시 굴릴 때 쓰세요.)"
        )
        return

    st.divider()

    # 2) 헤드라인 — 명세 + 전체 결과 분포(대표성 숫자) + 커버 카드 3장(카드뉴스)
    _render_specs(selection.get("specs") or [])
    _render_distribution(selection.get("outcomes") or [])
    _render_groups(selection, view.get("village") or {},
                   reactions=view.get("reactions_by_id") or {})

    # 3) 증거 — 전원의 실제 결과표 + 정직한 노트
    st.divider()
    st.markdown("#### 📊 전체 결과표 (증거)")
    trio_ids = {
        (t.get("persona") or {}).get("id")
        for t in (selection.get("trio") or [])
    }
    _render_outcomes_table(selection.get("outcomes") or [], trio_ids)
    for note in selection.get("notes") or []:
        st.caption("· " + note)
