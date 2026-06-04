# -*- coding: utf-8 -*-
"""정책 문의 게시판 탭(stretch) — 화면(폼·말풍선)만 담당.

답변을 만드는 로직은 전부 `board_engine` 으로 분리돼 있다. 이 파일은
  · 질문 입력 폼을 그리고,
  · 제출 시 `board_engine.answer_question()` / `make_comments()` 를 호출해
    스레드를 만들어 `session_state['board']` 에 누적하고,
  · 누적된 Q/A 스레드를 말풍선으로 표시한다.
만 한다. mock↔RAG 교체나 답변 품질 작업은 `board_engine.py` 에서 하면 된다.

게시판이 바깥에서 받는 것은 `view['policy']`(정책 원문) 하나뿐이고, 자기 상태는
`session_state['board']` 에만 쌓는다. 그래서 전체 시뮬레이션 없이도 동작하며,
`_preview_board.py` 로 이 탭만 단독 실행할 수 있다.
"""

import streamlit as st

import board_engine


# 답변 엔진 표시 배지 — view['board_mode'] 또는 실제 답한 엔진(mode)에 따라.
_MODE_BADGE = {
    "mock": "🧩 규칙 기반 자동응답 (RAG 미연결)",
    "rag": "🔎 RAG 기반 자동응답",
}


def render_board_tab(view):
    """정책 문의 게시판을 그린다.

    상단 폼으로 질문을 받아 제출하면, 정책 텍스트 기반 답변과 가상 시민 댓글을
    만들어 session_state['board'] 에 누적하고, 누적된 스레드를 최신순으로 표시한다.
    view 가 None 이면 안내 후 종료한다.

    엔진 선택: view['board_mode']('auto'|'mock'|'rag', 기본 'auto')를 그대로
    board_engine.answer_question 에 넘긴다. 일반 앱에서는 키가 없으면 'auto' 가
    mock 으로 동작하고, _preview_board.py 는 이 값을 바꿔 RAG 를 단독 시험한다.
    """
    if view is None:
        st.info("아직 시뮬레이션 결과가 없습니다. 정책을 입력하고 시뮬레이션을 실행해 주세요.")
        return

    st.subheader("정책 문의 게시판")
    st.caption(
        "정책에 대해 궁금한 점을 남겨 보세요. 정책 원문을 바탕으로 한 자동 안내와 "
        "가상 시민들의 댓글이 달립니다."
    )

    policy = view.get("policy", "") or ""
    mode = view.get("board_mode", "auto")

    if "board" not in st.session_state:
        st.session_state["board"] = []

    # ── 질문 입력 폼 ────────────────────────────────────────────
    with st.form("board_form", clear_on_submit=True):
        nickname = st.text_input("닉네임", value="시민", max_chars=20)
        question = st.text_area(
            "질문 내용",
            placeholder="예) 만 35세도 신청할 수 있나요? 서류는 뭘 준비해야 하죠?",
            height=100,
        )
        submitted = st.form_submit_button("질문 등록")

    if submitted:
        q = (question or "").strip()
        if not q:
            st.warning("질문 내용을 입력해 주세요.")
        else:
            # 답변/댓글 생성은 전부 엔진에 위임 — 이 탭은 결과를 누적·표시만 한다.
            result = board_engine.answer_question(policy, q, mode=mode)
            comments = board_engine.make_comments(q)
            st.session_state["board"].append(
                {
                    "nickname": (nickname or "시민").strip() or "시민",
                    "question": q,
                    "answer": result.get("answer", ""),
                    "sources": result.get("sources", []),
                    "mode": result.get("mode", "mock"),
                    "comments": comments,
                }
            )
            st.success("질문이 등록되었습니다. 아래에서 답변을 확인하세요.")

    st.divider()

    # ── 누적된 Q/A 스레드 표시(최신순) ──────────────────────────
    board = st.session_state.get("board", [])
    if not board:
        st.info("아직 등록된 문의가 없습니다. 첫 질문을 남겨 보세요!")
        return

    for idx, thread in enumerate(reversed(board)):
        _render_thread(thread)
        # 스레드 사이 구분선(마지막 스레드 제외)
        if idx < len(board) - 1:
            st.divider()


def _render_thread(thread: dict) -> None:
    """질문 1건 + 자동답변 + 시민 댓글 묶음(스레드 1개)을 말풍선으로 그린다."""
    # 질문(시민) 말풍선
    with st.chat_message("user"):
        st.markdown(f"**{thread.get('nickname', '시민')}** 님의 질문")
        st.write(thread.get("question", ""))

    # 자동 안내 답변 말풍선
    with st.chat_message("assistant"):
        badge = _MODE_BADGE.get(thread.get("mode", "mock"), _MODE_BADGE["mock"])
        st.markdown(f"**정책 안내 도우미** · {badge}")
        st.write(thread.get("answer", ""))
        _render_sources(thread.get("sources", []))

    # 가상 시민 댓글들
    for comment in thread.get("comments", []):
        with st.chat_message("user"):
            st.caption("다른 시민의 댓글")
            st.write(comment)


def _render_sources(sources) -> None:
    """답변 근거(정책 문장/RAG 청크)를 접이식으로 표시한다. 없으면 아무것도 안 그림.

    mock 과 RAG 둘 다 [{"text":.., "source":..}] 모양으로 sources 를 주므로
    렌더는 한 곳에서 공통으로 처리된다.
    """
    if not sources:
        return
    with st.expander(f"📎 답변 근거 {len(sources)}건 보기"):
        for s in sources:
            text = (s or {}).get("text", "")
            src = (s or {}).get("source", "")
            if not text:
                continue
            st.markdown(f"- {text}" + (f"  \n  *— {src}*" if src else ""))
