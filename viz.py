# -*- coding: utf-8 -*-
"""시각화 헬퍼 모음 (presentation layer).

이 모듈은 순수 렌더링만 담당한다. 외부 네트워크/OpenAI 호출 금지.
- matplotlib: 한글 폰트 설정(set_korean_font).
- plotly: 게이지(go.Indicator).
- streamlit: 점수 막대/반응 카드/말풍선 (함수 안에서만 st 호출).

주의:
- 최상단에서 st.set_page_config 등 부수효과 실행 금지. 모든 st 호출은 함수 안에서만.
"""

import matplotlib.pyplot as plt
import plotly.graph_objects as go
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────
# 전역 스타일 사전 (팀 공용 색/라벨 약속)
# ─────────────────────────────────────────────────────────────────────────
STYLE = {
    # 입장(stance)별 색 — 찬성/반대/혼합
    "stance_colors": {
        "support": "#27AE60",   # 찬성 = 초록
        "oppose": "#E74C3C",    # 반대 = 빨강
        "mixed": "#F39C12",     # 혼합 = 주황
    },
    # 게이지 구간 색 — 낮음/중간/높음
    "gauge_bands": {
        "low": "#27AE60",       # 낮음 = 초록
        "mid": "#F1C40F",       # 중간 = 노랑
        "high": "#E74C3C",      # 높음 = 빨강
    },
    # 5축 점수 한글 라벨 (Scores 키 → 표시 이름)
    "score_labels": {
        "understanding": "이해도",
        "benefit": "수혜가능성",
        "intent": "신청의향",
        "dissatisfaction": "불만도",
        "shareability": "공유가능성",
    },
    # chip 기본 색
    "chip_bg": "#ECF0F1",
    "chip_fg": "#2C3E50",
    # 채팅 자기 말풍선 색 (카카오 노랑)
    "chat_self_bubble": "#FEE500",
}

# stance 한글 표기 (헤더용)
_STANCE_LABEL = {
    "support": "찬성",
    "oppose": "반대",
    "mixed": "혼합",
}

# 점수 표시 순서 (Scores 정의 순서와 동일하게 고정)
_SCORE_ORDER = [
    "understanding",
    "benefit",
    "intent",
    "dissatisfaction",
    "shareability",
]


# ─────────────────────────────────────────────────────────────────────────
# 한글 폰트
# ─────────────────────────────────────────────────────────────────────────
def set_korean_font():
    """matplotlib 한글 폰트를 설정한다.

    OS별로 사용 가능한 폰트를 우선순위 리스트로 넘겨 깨짐을 방지하고,
    음수 부호(−)가 □ 로 나오는 문제도 막는다.
    """
    plt.rcParams["font.family"] = [
        "Malgun Gothic",   # Windows
        "AppleGothic",     # macOS
        "NanumGothic",     # Linux(나눔)
        "DejaVu Sans",     # 최종 폴백
    ]
    plt.rcParams["axes.unicode_minus"] = False


# ─────────────────────────────────────────────────────────────────────────
# chip (둥근 HTML 배지)
# ─────────────────────────────────────────────────────────────────────────
def chip(text, bg=None, fg=None):
    """둥근 모서리의 작은 HTML 배지(span) 문자열을 반환한다.

    st.markdown(..., unsafe_allow_html=True) 로 출력하는 용도.
    bg/fg 미지정 시 STYLE 기본색 사용.
    """
    bg = bg or STYLE["chip_bg"]
    fg = fg or STYLE["chip_fg"]
    # 안전을 위해 문자열화 + 최소한의 꺾쇠 이스케이프
    safe = str(text).replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<span style=\""
        f"display:inline-block;background:{bg};color:{fg};"
        "padding:2px 10px;margin:2px 3px;border-radius:12px;"
        "font-size:0.78rem;line-height:1.4;white-space:nowrap;"
        "\">"
        f"{safe}</span>"
    )


# ─────────────────────────────────────────────────────────────────────────
# gauge (plotly Indicator)
# ─────────────────────────────────────────────────────────────────────────
def gauge(value, label, bands=None):
    """0~100 범위의 반원형 게이지 Figure 를 만든다.

    value : 표시할 값 (0~100 로 클램프).
    label : 게이지 상단 한글 라벨.
    bands : {'low','mid','high'} 색 사전 (미지정 시 STYLE 사용).
    """
    bands = bands or STYLE["gauge_bands"]

    # 값 보정 — 숫자 아님/None/범위 밖 방어
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    v = max(0.0, min(100.0, v))

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=v,
            title={"text": label, "font": {"size": 16}},
            number={"font": {"size": 28}, "suffix": ""},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickwidth": 1,
                    "tickcolor": "#7f8c8d",
                },
                "bar": {"color": "#34495E"},  # 현재 값 바늘 바
                "borderwidth": 0,
                # 3구간 색칠: 낮음(0~33)/중간(33~66)/높음(66~100)
                "steps": [
                    {"range": [0, 33], "color": bands["low"]},
                    {"range": [33, 66], "color": bands["mid"]},
                    {"range": [66, 100], "color": bands["high"]},
                ],
                "threshold": {
                    "line": {"color": "#2C3E50", "width": 3},
                    "thickness": 0.75,
                    "value": v,
                },
            },
        )
    )
    # 컴팩트한 여백
    fig.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────
# score_bars (streamlit progress 5축)
# ─────────────────────────────────────────────────────────────────────────
def score_bars(scores: dict):
    """5축 점수를 st.progress 막대 5개로 표시한다.

    scores : Scores 형태 dict (0~100 정수값).
    각 막대 텍스트 = '라벨 값'. st 호출 함수이므로 반환값 없음.
    """
    scores = scores or {}
    for key in _SCORE_ORDER:
        label = STYLE["score_labels"].get(key, key)
        # 값 보정 — None/문자/범위 밖 방어
        raw = scores.get(key, 0)
        try:
            v = int(round(float(raw)))
        except (TypeError, ValueError):
            v = 0
        v = max(0, min(100, v))
        # st.progress 는 0.0~1.0 비율을 받는다
        st.progress(v / 100.0, text=f"{label} {v}")


# ─────────────────────────────────────────────────────────────────────────
# render_reaction_card (시민 반응 카드)
# ─────────────────────────────────────────────────────────────────────────
def render_reaction_card(reaction, persona, style=None):
    """페르소나 1명의 반응을 카드 형태로 렌더링한다.

    구성:
      1) 이름 + 데모그래픽 chip 들
      2) stance(찬성/반대/혼합) 색 헤더
      3) 5축 점수 막대(score_bars)
      4) 반응 텍스트
      5) 근거(evidence) expander
    st 호출 함수이므로 반환값 없음.
    """
    style = style or STYLE
    reaction = reaction or {}
    persona = persona or {}

    stance = reaction.get("stance", "mixed")
    stance_color = style["stance_colors"].get(stance, style["stance_colors"]["mixed"])
    stance_kr = _STANCE_LABEL.get(stance, "혼합")

    with st.container(border=True):
        # ── 1) 이름 + 데모그래픽 chip ──────────────────────────
        name = persona.get("name") or "(이름 미상)"
        desc = persona.get("description") or ""
        st.markdown(f"**{name}**" + (f" · {desc}" if desc else ""))

        demo = persona.get("demographics") or {}
        # 표시할 데모그래픽 키 순서/라벨 (값이 있을 때만 chip)
        demo_fields = [
            ("sex", ""),
            ("age", "세"),
            ("marital_status", ""),
            ("housing_type", ""),
            ("occupation", ""),
            ("district", ""),
            ("province", ""),
        ]
        chips = []
        for fkey, suffix in demo_fields:
            val = demo.get(fkey)
            if val in (None, "", []):
                continue
            text = f"{val}{suffix}" if suffix else str(val)
            chips.append(chip(text))
        if chips:
            st.markdown("".join(chips), unsafe_allow_html=True)

        # ── 2) stance 색 헤더 ──────────────────────────────────
        st.markdown(
            "<div style=\""
            f"background:{stance_color};color:#ffffff;"
            "padding:4px 12px;border-radius:8px;margin:6px 0;"
            "font-weight:600;display:inline-block;\">"
            f"{stance_kr}</div>",
            unsafe_allow_html=True,
        )

        # grounded 가 False(ablation) 면 표식 — 일반 시민 응답임을 알림
        if reaction.get("grounded") is False:
            st.caption("페르소나 미적용(일반 시민) 응답")

        # ── 3) 5축 점수 막대 ───────────────────────────────────
        score_bars(reaction.get("scores", {}))

        # ── 4) 반응 텍스트 ─────────────────────────────────────
        text = reaction.get("text") or ""
        if text:
            st.markdown(text)

        # 예상 행동(actions) 이 있으면 chip 으로 한 줄 표시
        actions = reaction.get("actions") or []
        if actions:
            act_chips = "".join(
                chip(str(a), bg="#EAF2F8", fg="#21618C") for a in actions
            )
            st.markdown(act_chips, unsafe_allow_html=True)

        # ── 5) 근거 expander ───────────────────────────────────
        evidence = reaction.get("evidence") or []
        if evidence:
            with st.expander(f"근거 보기 ({len(evidence)}건)"):
                for i, ev in enumerate(evidence, 1):
                    st.markdown(f"{i}. {ev}")


# ─────────────────────────────────────────────────────────────────────────
# chat_bubble (st.chat_message 말풍선)
# ─────────────────────────────────────────────────────────────────────────
def chat_bubble(message, is_self=False):
    """채팅 말풍선 1개를 그린다.

    is_self=True 면 카카오 노란색 배경의 '나' 말풍선,
    아니면 기본 '상대' 말풍선. st 호출 함수이므로 반환값 없음.
    message 는 문자열 또는 {'name':..,'text':..} dict 모두 허용.
    """
    # message 정규화
    name = None
    if isinstance(message, dict):
        name = message.get("name") or message.get("from")
        text = message.get("text") or message.get("content") or ""
    else:
        text = str(message)

    if is_self:
        # 자신 = 노란 말풍선 (오른쪽 정렬 느낌의 배경 박스)
        with st.chat_message("user"):
            if name:
                st.caption(name)
            st.markdown(
                "<div style=\""
                f"background:{STYLE['chat_self_bubble']};color:#2C3E50;"
                "padding:8px 12px;border-radius:14px;display:inline-block;"
                "max-width:90%;\">"
                f"{str(text)}</div>",
                unsafe_allow_html=True,
            )
    else:
        # 상대 = 기본 말풍선
        with st.chat_message("assistant"):
            if name:
                st.caption(name)
            st.markdown(str(text))
