# -*- coding: utf-8 -*-
"""게시판 탭 단독 실행기.

    streamlit run _preview_board.py

전체 시뮬레이션(사이드바 → 시민 반응 생성)을 돌리지 않고 **게시판 탭만** 띄운다.
정책 원문을 직접 고르거나 붙여넣고, 답변 엔진(auto/mock/rag)을 골라 자동답변을
반복 시험할 수 있다. 게시판은 view['policy'] 하나만 읽으므로 최소 view 만 주입하면 된다.

게시판 탭은 standalone_board 풀 RAG(문서 업로드 + Chroma/OpenAI 검색 + 품질지표)를
쓴다. 답변 방식(OpenAI/근거추출)은 탭 안 라디오로 고른다. 정책을 고치거나 붙여넣고
질문을 남겨 시험하면 된다.
"""

# 한글 폰트 → 페이지 설정 → 타이틀 (app.py 와 동일한 순서 고정)
from viz import set_korean_font

set_korean_font()

import streamlit as st

st.set_page_config(page_title="게시판 단독 미리보기", layout="wide")
st.title("📋 정책 문의 게시판 — 단독 미리보기")
st.caption(
    "전체 시뮬레이션 없이 게시판 탭만 띄웁니다. 정책을 고르고 질문을 남겨 자동답변을 "
    "시험해 보세요. (app.py 와 별개로 동작하는 개발용 실행기)"
)

from sample_policies import SAMPLES, DEFAULT_POLICY
from graph.llm import has_real_key
from ui.tab_board import render_board_tab


with st.sidebar:
    st.header("미리보기 설정")

    # 1) 정책 선택 + 원문(직접 수정 가능) ----------------------------
    names = list(SAMPLES)
    default_index = names.index(DEFAULT_POLICY) if DEFAULT_POLICY in names else 0
    choice = st.selectbox("정책 선택", names, index=default_index)
    # key 에 선택값을 포함시켜, 정책을 바꾸면 원문이 새로 프리필되게 한다.
    policy = st.text_area(
        "정책 원문", value=SAMPLES.get(choice, ""), height=280,
        key=f"pv_policy::{choice}",
        help="샘플을 고치거나, 통째로 지우고 직접 붙여넣어도 됩니다.",
    )

    # 2) 키 상태 안내 — 답변 방식(OpenAI/근거추출)은 게시판 탭 안에서 고른다.
    st.caption(
        "✅ OpenAI 키 감지됨 (Chroma + OpenAI 의미검색)"
        if has_real_key() else "⚠️ OpenAI 키 없음 — 로컬 해시 검색 + 추출식 폴백"
    )
    st.caption("답변 방식(OpenAI/근거추출)은 게시판 탭 안에서 고릅니다.")

    if st.button("게시판 비우기", use_container_width=True):
        from standalone_board.app import QUESTION_KEY, THREADS_KEY
        st.session_state[THREADS_KEY] = []
        st.session_state[QUESTION_KEY] = ""
        st.rerun()


# 게시판이 읽는 최소 view 만 주입(정책 원문 하나).
view = {"policy": policy}
render_board_tab(view)
