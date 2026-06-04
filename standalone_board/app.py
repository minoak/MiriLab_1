# -*- coding: utf-8 -*-
"""Streamlit app for the standalone policy board."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

import streamlit as st

from .core import (
    BoardRagService,
    ExtractiveAnswerGenerator,
    IndexStore,
    PolicyDocument,
    VectorIndex,
    chunk_document,
    suggest_questions,
)
from .document_loaders import load_uploaded_document
from .openai_adapter import OpenAIAnswerGenerator, has_openai_key


RUNTIME_DIR = Path(__file__).resolve().parent / ".runtime"
INDEX_DIR = RUNTIME_DIR / "indexes"

QUESTION_KEY = "standalone_board_question"
THREADS_KEY = "standalone_board_threads"
DOCS_KEY = "standalone_board_documents"
CHUNKS_KEY = "standalone_board_chunks"
CLEAR_QUESTION_KEY = "standalone_board_clear_question"
SESSION_ID_KEY = "standalone_board_session_id"


@dataclass(frozen=True)
class IndexUpdate:
    documents: list[PolicyDocument]
    chunks: list
    errors: list[str]

    @property
    def can_save(self) -> bool:
        return not self.errors


def index_path_for_session(session_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
    return INDEX_DIR / f"{safe or 'default'}.json"


def _session_index_path() -> Path:
    session_id = st.session_state.setdefault(SESSION_ID_KEY, uuid4().hex)
    return index_path_for_session(session_id)


def prepare_index_update(
    uploaded_files,
    *,
    loader: Callable[[str, bytes], PolicyDocument] = load_uploaded_document,
) -> IndexUpdate:
    documents: list[PolicyDocument] = []
    errors: list[str] = []
    for file in uploaded_files or []:
        try:
            documents.append(loader(file.name, file.getvalue()))
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")

    if errors:
        return IndexUpdate(documents=documents, chunks=[], errors=errors)

    chunks = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return IndexUpdate(documents=documents, chunks=chunks, errors=[])


def _init_state() -> None:
    if st.session_state.pop(CLEAR_QUESTION_KEY, False):
        st.session_state[QUESTION_KEY] = ""
    st.session_state.setdefault(QUESTION_KEY, "")
    st.session_state.setdefault(THREADS_KEY, [])
    st.session_state.setdefault(DOCS_KEY, [])
    st.session_state.setdefault(CHUNKS_KEY, [])


def _load_saved_chunks() -> list:
    if st.session_state[CHUNKS_KEY]:
        return st.session_state[CHUNKS_KEY]
    chunks = IndexStore(_session_index_path()).load()
    st.session_state[CHUNKS_KEY] = chunks
    return chunks


def _build_index(chunks: list) -> VectorIndex:
    index = VectorIndex()
    index.add_chunks(chunks)
    return index


def _generator_from_mode(mode: str):
    if mode == "OpenAI" and has_openai_key():
        return OpenAIAnswerGenerator()
    return ExtractiveAnswerGenerator()


def _metric_rows(metrics: dict) -> list[dict]:
    labels = {
        "retrieval_count": "검색 근거 수",
        "top_similarity": "최고 검색 유사도",
        "avg_similarity": "평균 검색 유사도",
        "source_document_count": "근거 문서 수",
        "answer_support_ratio": "근거 충실도",
        "hallucination_risk": "환각 위험도",
        "reference_similarity": "기준 정답 유사도",
        "verdict": "판정",
    }
    descriptions = {
        "retrieval_count": "답변 생성에 사용한 문서 조각 개수",
        "top_similarity": "질문과 가장 가까운 근거의 로컬 벡터 점수",
        "avg_similarity": "검색된 근거들의 평균 점수",
        "source_document_count": "서로 다른 원본 문서 개수",
        "answer_support_ratio": "답변 문장이 검색 근거로 뒷받침되는 비율",
        "hallucination_risk": "근거 밖 내용이 섞였을 가능성",
        "reference_similarity": "기준 정답을 입력했을 때 답변과의 토큰 유사도",
        "verdict": "학습/검수용 종합 판정",
    }
    return [
        {
            "지표": labels[key],
            "값": "-" if value is None else value,
            "의미": descriptions[key],
        }
        for key, value in metrics.items()
        if key in labels
    ]


def _render_document_panel() -> None:
    st.sidebar.header("정책 문서")
    uploaded = st.sidebar.file_uploader(
        "PDF/TXT/MD 업로드",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        help="여러 정책 문서를 동시에 올리면 게시판 답변 검색 대상이 됩니다.",
    )

    col_a, col_b = st.sidebar.columns(2)
    build_clicked = col_a.button("인덱스 생성", use_container_width=True)
    clear_clicked = col_b.button("초기화", use_container_width=True)

    if clear_clicked:
        st.session_state[DOCS_KEY] = []
        st.session_state[CHUNKS_KEY] = []
        st.session_state[THREADS_KEY] = []
        index_path = _session_index_path()
        if index_path.exists():
            index_path.unlink()
        st.rerun()

    if build_clicked:
        update = prepare_index_update(uploaded)

        if not update.can_save:
            for error in update.errors:
                st.sidebar.error(error)
            st.sidebar.warning("오류가 있어 기존 인덱스를 유지했습니다.")
            return

        st.session_state[DOCS_KEY] = update.documents
        st.session_state[CHUNKS_KEY] = update.chunks
        IndexStore(_session_index_path()).save(update.chunks)

        st.sidebar.success(
            f"문서 {len(update.documents)}개, 근거 조각 {len(update.chunks)}개 인덱싱"
        )
        st.rerun()

    chunks = _load_saved_chunks()
    st.sidebar.caption(f"현재 인덱스: 근거 조각 {len(chunks)}개")
    st.sidebar.caption("OpenAI 키: " + ("감지됨" if has_openai_key() else "없음"))


def _render_suggestions(documents: list[PolicyDocument], chunks: list) -> None:
    if documents:
        questions = suggest_questions(documents, limit=8)
    elif chunks:
        pseudo_doc = PolicyDocument(
            name="indexed-documents",
            text="\n".join(chunk.text for chunk in chunks[:20]),
        )
        questions = suggest_questions([pseudo_doc], limit=8)
    else:
        questions = []

    if not questions:
        st.info("정책 문서를 업로드하고 인덱스를 생성하면 예시 질문이 표시됩니다.")
        return

    st.subheader("예시 질문")
    cols = st.columns(2)
    for idx, question in enumerate(questions):
        if cols[idx % 2].button(question, key=f"suggested_question_{idx}", use_container_width=True):
            st.session_state[QUESTION_KEY] = question
            st.rerun()


def _render_question_box(chunks: list) -> None:
    st.subheader("정책 문의")
    mode = st.radio(
        "답변 생성",
        ["OpenAI", "근거 추출"],
        horizontal=True,
        index=0 if has_openai_key() else 1,
        help="OpenAI 키가 없으면 근거 추출 방식으로 사실 기반 답변을 만듭니다.",
    )
    reference = st.text_area(
        "기준 정답(선택)",
        height=90,
        placeholder="공식 FAQ나 담당자 답변이 있으면 붙여넣으세요. 유사도 지표가 함께 계산됩니다.",
    )
    question = st.text_area(
        "질문 내용",
        key=QUESTION_KEY,
        height=120,
        placeholder="예) 신청할 때 필요한 서류는 무엇인가요?",
    )

    disabled = not chunks
    if st.button("질문 등록", type="primary", disabled=disabled):
        q = (question or "").strip()
        if not q:
            st.warning("질문 내용을 입력해 주세요.")
            return

        index = _build_index(chunks)
        generator = _generator_from_mode(mode)
        service = BoardRagService(index=index, generator=generator)
        mode_label = generator.name
        try:
            result = service.answer(q, k=5, reference_answer=reference)
        except Exception as exc:
            if mode != "OpenAI":
                st.error(f"답변 생성 중 오류가 발생했습니다: {exc}")
                return
            st.warning(f"OpenAI 답변 생성 실패로 근거 추출 답변으로 대체합니다: {exc}")
            generator = ExtractiveAnswerGenerator()
            service = BoardRagService(index=index, generator=generator)
            result = service.answer(q, k=5, reference_answer=reference)
            mode_label = "extractive-fallback"

        st.session_state[THREADS_KEY].append(
            {
                "question": q,
                "answer": result.answer,
                "sources": result.sources,
                "metrics": result.metrics,
                "mode": mode_label,
            }
        )
        st.session_state[CLEAR_QUESTION_KEY] = True
        st.rerun()

    if disabled:
        st.caption("먼저 사이드바에서 정책 문서를 업로드하고 인덱스를 생성하세요.")


def _render_threads() -> None:
    threads = st.session_state.get(THREADS_KEY, [])
    if not threads:
        st.info("아직 등록된 문의가 없습니다.")
        return

    st.divider()
    st.subheader("게시글 답변")
    for thread in reversed(threads):
        with st.chat_message("user"):
            st.markdown("**시민 질문**")
            st.write(thread["question"])

        with st.chat_message("assistant"):
            st.markdown(f"**정책 안내 답변** · {thread['mode']}")
            st.write(thread["answer"])
            if thread.get("metrics"):
                st.markdown("**품질 지표**")
                st.table(_metric_rows(thread["metrics"]))
            sources = thread.get("sources", [])
            if sources:
                with st.expander(f"근거 문서 {len(sources)}건"):
                    for source in sources:
                        st.markdown(
                            f"- `{source.get('source', '')}` "
                            f"(score={source.get('score', 0)})\n\n"
                            f"  {source.get('text', '')}"
                        )


def main() -> None:
    st.set_page_config(page_title="정책 문의 게시판", layout="wide")
    _init_state()
    st.title("정책 문의 게시판")
    st.caption("여러 정책 문서 PDF/TXT/MD를 근거로 게시글에 사실 기반 답변을 남깁니다.")

    _render_document_panel()
    chunks = _load_saved_chunks()
    documents = st.session_state.get(DOCS_KEY, [])

    left, right = st.columns([0.9, 1.1])
    with left:
        _render_suggestions(documents, chunks)
    with right:
        _render_question_box(chunks)

    _render_threads()


if __name__ == "__main__":
    main()
