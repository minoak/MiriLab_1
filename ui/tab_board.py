# -*- coding: utf-8 -*-
"""정책 문의 게시판 탭.

미리랩 설정에서 넘어온 `view["policy"]`를 기본 근거 문서로 쓰고, 사용자가
추가로 올린 PDF/TXT/MD 문서까지 합쳐 RAG 답변을 만든다.
"""

import hashlib
import json
import os

import streamlit as st

import board_engine
from standalone_board.app import prepare_index_update
from standalone_board.core import (
    BoardRagService,
    ExtractiveAnswerGenerator,
    PolicyDocument,
    PolicyChunk,
    QualityEvaluator,
    SearchHit,
    retrieval_backend_label,
    retrieval_score_label,
    suggest_questions,
)
from standalone_board.openai_adapter import (
    OpenAIAnswerGenerator,
    build_retrieval_index,
    has_openai_key,
)


# 답변 엔진 표시 배지 — view['board_mode'] 또는 실제 답한 엔진(mode)에 따라.
_MODE_BADGE = {
    "mock": "🧩 규칙 기반 자동응답 (RAG 미연결)",
    "rag": "🔎 RAG 기반 자동응답",
    "extractive": "🔎 근거 추출 자동응답",
    "openai-grounded": "🤖 OpenAI 근거 기반 자동응답",
    "extractive-fallback": "🔎 근거 추출 자동응답 (OpenAI 폴백)",
}
BOARD_QUESTION_KEY = "board_question_content"
_BOARD_INDEX_CACHE = {}
BOARD_QUESTION_DRAFT_KEY = "board_question_content_draft"
BOARD_QUESTION_REV_KEY = "board_question_content_rev"


def clear_board_index_cache() -> None:
    _BOARD_INDEX_CACHE.clear()


def _index_cache_key(chunks: list, *, prefer_openai: bool) -> str:
    payload = {
        "prefer_openai": prefer_openai,
        "openai_key": has_openai_key(),
        "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", ""),
        "chunks": [
            {
                "id": chunk.id,
                "text": chunk.text,
                "document": chunk.document_name,
                "page": chunk.page,
                "index": chunk.chunk_index,
            }
            for chunk in chunks
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _build_index(chunks: list, *, prefer_openai: bool = True):
    key = _index_cache_key(chunks, prefer_openai=prefer_openai)
    cached = _BOARD_INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    index = build_retrieval_index(chunks, prefer_openai=prefer_openai)
    if not (prefer_openai and has_openai_key() and getattr(index, "backend", "") != "chroma-vector"):
        _BOARD_INDEX_CACHE[key] = index
    return index


def metric_display_items(metrics: dict) -> list[dict]:
    labels = {
        "answer_support_ratio": "근거 일치도",
        "hallucination_risk": "근거 밖 가능성",
        "retrieval_count": "검색 근거",
        "verdict": "검수 상태",
    }
    return [
        {
            "label": label,
            "value": metrics.get(key, "-"),
        }
        for key, label in labels.items()
        if key in metrics
    ]


def _generator_from_mode(mode: str):
    if mode == "OpenAI" and has_openai_key():
        return OpenAIAnswerGenerator()
    return ExtractiveAnswerGenerator()


def suggested_questions_for_policy(policy: str, *, limit: int = 5) -> list[str]:
    """Return likely board questions from the current MiriLab policy text."""

    if not (policy or "").strip():
        return []
    return suggest_questions(
        [PolicyDocument(name="미리랩 설정 정책", text=policy)],
        limit=limit,
    )


def prepare_question_input_state(state, selected_question: str | None = None) -> tuple[str, str]:
    """Return the current question widget key and draft value.

    The text area uses a revisioned widget key so the same suggested question can
    be inserted again after a previous form submit cleared the browser field.
    """

    state.setdefault(BOARD_QUESTION_REV_KEY, 0)
    state.setdefault(BOARD_QUESTION_DRAFT_KEY, "")
    if selected_question is not None:
        state[BOARD_QUESTION_DRAFT_KEY] = selected_question
        state[BOARD_QUESTION_REV_KEY] += 1
    widget_key = f"{BOARD_QUESTION_KEY}_{state[BOARD_QUESTION_REV_KEY]}"
    return widget_key, state[BOARD_QUESTION_DRAFT_KEY]


def clear_question_input_after_submit(state) -> None:
    state.setdefault(BOARD_QUESTION_REV_KEY, 0)
    state[BOARD_QUESTION_DRAFT_KEY] = ""
    state[BOARD_QUESTION_REV_KEY] += 1


def answer_with_board_rag(
    policy: str,
    uploaded_files,
    question: str,
    *,
    mode: str = "OpenAI",
    reference_answer: str | None = None,
) -> dict:
    """Build an in-tab RAG answer from the MiriLab policy plus uploaded docs."""

    update = prepare_index_update(uploaded_files, base_policy_text=policy)
    if not update.can_save:
        return {
            "answer": "",
            "sources": [],
            "metrics": {},
            "mode": "error",
            "retrieval_backend": "",
            "retrieval_backend_label": "-",
            "document_count": 0,
            "errors": update.errors,
        }
    if not update.chunks:
        return {
            "answer": "정책 원문이나 추가 문서를 먼저 준비해 주세요.",
            "sources": [],
            "metrics": {},
            "mode": "extractive",
            "retrieval_backend": "",
            "retrieval_backend_label": "-",
            "document_count": len(update.documents),
            "errors": [],
        }

    generator = _generator_from_mode(mode)
    index = _build_index(update.chunks)
    backend = getattr(index, "backend", "")
    service = BoardRagService(index=index, generator=generator)
    mode_label = generator.name
    try:
        result = service.answer(question, k=5, reference_answer=reference_answer)
    except Exception as exc:
        if mode != "OpenAI" and backend == "local-hashing-vector":
            return {
                "answer": "",
                "sources": [],
                "metrics": {},
                "mode": "error",
                "retrieval_backend": backend,
                "retrieval_backend_label": retrieval_backend_label(backend),
                "document_count": len(update.documents),
                "errors": [str(exc)],
            }
        generator = ExtractiveAnswerGenerator()
        if backend != "local-hashing-vector":
            index = _build_index(update.chunks, prefer_openai=False)
            backend = getattr(index, "backend", "")
        service = BoardRagService(index=index, generator=generator)
        result = service.answer(question, k=5, reference_answer=reference_answer)
        mode_label = "extractive-fallback"

    return {
        "answer": result.answer,
        "sources": result.sources,
        "metrics": result.metrics,
        "mode": mode_label,
        "retrieval_backend": result.retrieval_backend,
        "retrieval_backend_label": result.retrieval_backend_label,
        "document_count": len(update.documents),
        "errors": [],
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
    st.caption("미리랩 설정의 정책 원문을 기본 근거로 사용합니다. 필요한 경우 추가 문서도 함께 올릴 수 있습니다.")

    policy = view.get("policy", "") or ""

    if "board" not in st.session_state:
        st.session_state["board"] = []

    with st.expander("추가 근거 문서", expanded=False):
        uploaded_files = st.file_uploader(
            "PDF/TXT/MD 업로드",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            key="board_extra_documents",
            help="미리랩 설정 정책 원문에 더해 검색할 공고문이나 FAQ를 추가할 수 있습니다.",
        )
        base_state = "불러옴" if policy.strip() else "없음"
        st.caption(f"기본 근거: 미리랩 설정 정책 원문 {base_state}")

    mode = st.radio(
        "답변 생성",
        ["OpenAI", "근거 추출"],
        horizontal=True,
        index=0 if has_openai_key() else 1,
        help="OpenAI 키가 없으면 근거 추출 방식으로 답변합니다.",
    )

    questions = suggested_questions_for_policy(policy)
    if questions:
        st.markdown("**예상 질문**")
        for idx, suggested in enumerate(questions):
            if st.button(suggested, key=f"board_suggested_question_{idx}", width="stretch"):
                prepare_question_input_state(st.session_state, selected_question=suggested)

    question_key, question_value = prepare_question_input_state(st.session_state)

    # ── 질문 입력 폼 ────────────────────────────────────────────
    with st.form("board_form"):
        nickname = st.text_input("닉네임", value="시민", max_chars=20)
        if question_key not in st.session_state:
            st.session_state[question_key] = question_value
        question = st.text_area(
            "질문 내용",
            key=question_key,
            placeholder="예) 만 35세도 신청할 수 있나요? 서류는 뭘 준비해야 하죠?",
            height=100,
        )
        submitted = st.form_submit_button("질문 등록")

    if submitted:
        q = (question or "").strip()
        if not q:
            st.warning("질문 내용을 입력해 주세요.")
        else:
            result = answer_with_board_rag(policy, uploaded_files, q, mode=mode)
            if result.get("errors"):
                for error in result["errors"]:
                    st.error(error)
                return
            comments = board_engine.make_comments(q)
            st.session_state["board"].append(
                {
                    "nickname": (nickname or "시민").strip() or "시민",
                    "question": q,
                    "answer": result.get("answer", ""),
                    "sources": result.get("sources", []),
                    "metrics": result.get("metrics", {}),
                    "mode": result.get("mode", "extractive"),
                    "retrieval_backend": result.get("retrieval_backend", ""),
                    "retrieval_backend_label": result.get("retrieval_backend_label", "-"),
                    "document_count": result.get("document_count", 0),
                    "comments": comments,
                }
            )
            clear_question_input_after_submit(st.session_state)
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
        caption_parts = []
        if thread.get("document_count"):
            caption_parts.append(f"근거 문서 {thread['document_count']}건 기준")
        if thread.get("retrieval_backend_label"):
            caption_parts.append(f"검색 방식: {thread['retrieval_backend_label']}")
        if caption_parts:
            st.caption(" · ".join(caption_parts))
        st.write(thread.get("answer", ""))
        _render_metrics(refresh_thread_metrics_for_display(thread))
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
            score = (s or {}).get("score")
            if not text:
                continue
            suffix = source_reference_caption(src, score)
            st.markdown(f"- {text}{suffix}")


def source_reference_caption(source: str, score) -> str:
    parts = []
    if source:
        parts.append(source)
    match_label = retrieval_score_label(score)
    if match_label:
        parts.append(match_label)
    if not parts:
        return ""
    return f"  \n  *— {' · '.join(parts)}*"


def refresh_thread_metrics_for_display(thread: dict) -> dict:
    answer = (thread or {}).get("answer", "")
    sources = (thread or {}).get("sources", [])
    if not answer or not sources:
        return (thread or {}).get("metrics", {})

    hits: list[SearchHit] = []
    for idx, source in enumerate(sources):
        text = (source or {}).get("text", "")
        if not text:
            continue
        try:
            score = float((source or {}).get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        hits.append(
            SearchHit(
                chunk=PolicyChunk(
                    id=f"display-source-{idx}",
                    text=text,
                    document_name=(source or {}).get("document")
                    or (source or {}).get("source")
                    or "근거 문서",
                    chunk_index=idx,
                ),
                score=score,
            )
        )

    if not hits:
        return (thread or {}).get("metrics", {})
    return QualityEvaluator().build_metrics(answer=answer, hits=hits)


def _render_metrics(metrics: dict) -> None:
    if not metrics:
        return
    items = metric_display_items(metrics)
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        col.metric(item["label"], item["value"])
