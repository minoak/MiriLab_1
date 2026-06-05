# -*- coding: utf-8 -*-
"""정책 문의 게시판 탭 — 풀 RAG (standalone_board 문서 기반 답변 경험을 탭에 통합).

(ii) 풀 채택: 동료의 standalone_board(PDF/다중문서 업로드 → Chroma/OpenAI 임베딩
검색 → grounded 답변 → 품질지표)를 메인 앱 게시판 탭으로 들였다. 현재 정책
(view['policy'])이 항상 기본 근거 문서로 포함되고, 사용자가 PDF/TXT/MD 를 추가로
올리면 함께 인덱싱된다. 키가 없으면 로컬 해시 검색 + 추출식 답변으로 폴백한다.

로직(청크·인덱스·검색·생성·지표)은 standalone_board 에 위임하고, 이 파일은 그 흐름을
메인 앱 사이드바가 아닌 '탭 안'에서 렌더한다(사이드바는 시뮬레이션용). 실 OpenAI 호출은
'질문 등록'/'문서 인덱싱' 시점에만 일어난다.

경계: 바깥에서 받는 것은 view['policy'] 하나. 상태는 standalone_board 세션 키에만 쌓는다.
참고: 단일정책 간단 API 는 board_engine.answer_question 으로 그대로 남아 있다(이 탭은
다중 문서/품질지표를 위해 standalone_board.BoardRagService 를 직접 쓴다).
"""
import hashlib
import re

import streamlit as st

from ui.rerun_util import rerun_fragment
from standalone_board.app import (
    CHUNKS_KEY,
    CLEAR_QUESTION_KEY,
    DOCS_KEY,
    QUESTION_KEY,
    THREADS_KEY,
    _build_index,
    _generator_from_mode,
    _metric_rows,
    _session_index_path,
    clear_index_cache,
    format_source_markdown,
    prepare_index_update,
)

# 근거 본문에 든 마크다운 제어문자(*, #, `, _ 등)가 표시를 깨뜨리지 않도록 이스케이프.
_MD_SPECIAL = re.compile(r"([\\`*_#~>\[\]|])")


def _escape_md(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text or "")
from standalone_board.core import (
    BoardRagService,
    ExtractiveAnswerGenerator,
    IndexStore,
    PolicyDocument,
    retrieval_backend_label,
    suggest_questions,
)
from standalone_board.openai_adapter import has_openai_key

# 현재 정책이 인덱스에 반영됐는지 추적(정책이 바뀌면 기본 인덱스를 재생성).
_POLICY_SIG_KEY = "board_policy_sig"


@st.fragment   # 질문 등록·문서 업로드·라디오의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
def render_board_tab(view):
    """정책 문의 게시판(풀 RAG)을 그린다. view 가 None 이면 안내 후 종료."""
    if view is None:
        st.info("아직 시뮬레이션 결과가 없습니다. 정책을 입력하고 시뮬레이션을 실행해 주세요.")
        return

    # 이전 제출이 등록됐으면 다음 런에서 질문 입력칸을 비운다(위젯 생성 전에 처리).
    if st.session_state.pop(CLEAR_QUESTION_KEY, False):
        st.session_state[QUESTION_KEY] = ""

    policy = (view.get("policy") or "").strip()

    st.subheader("정책 문의 게시판")
    st.caption(
        "정책 원문(그리고 추가로 올린 문서)을 근거로, 시민 질문에 사실 기반 답변을 "
        "남깁니다. 답변은 검색된 근거 안에서만 생성되며 품질 지표가 함께 표시됩니다."
    )

    _ensure_base_index(policy)
    chunks = st.session_state.get(CHUNKS_KEY, [])
    documents = st.session_state.get(DOCS_KEY, [])

    _render_documents(policy)

    left, right = st.columns([0.9, 1.1])
    with left:
        _render_suggestions(documents, chunks)
    with right:
        _render_question(chunks)

    _render_threads()


def _policy_sig(policy: str):
    return hashlib.sha1((policy or "").encode("utf-8")).hexdigest()


def _ensure_base_index(policy: str) -> None:
    """현재 정책을 기본 근거 문서로 항상 인덱싱한다(정책이 바뀌면 재생성).

    인덱스가 비었거나 정책 원문이 직전과 달라졌으면 정책만으로 기본 인덱스를 만든다.
    업로드 문서는 '문서 인덱싱' 버튼으로 정책 위에 더해진다. (여기선 청크 분할만 —
    임베딩/검색은 질문 등록 시점에 _build_index 가 캐시와 함께 수행.)
    """
    if not policy:
        return
    sig = _policy_sig(policy)
    if st.session_state.get(_POLICY_SIG_KEY) == sig and st.session_state.get(CHUNKS_KEY):
        return

    # 정책이 바뀐 경우인지(이전 sig 존재) + 그때 업로드 문서가 있었는지 기록.
    is_policy_change = st.session_state.get(_POLICY_SIG_KEY) is not None
    had_uploads = len(st.session_state.get(DOCS_KEY) or []) > 1  # base 정책 1개 외

    update = prepare_index_update([], base_policy_text=policy)
    st.session_state[CHUNKS_KEY] = update.chunks
    st.session_state[DOCS_KEY] = update.documents
    st.session_state[_POLICY_SIG_KEY] = sig
    _persist(update.chunks)

    if is_policy_change:
        # 정책이 바뀌면 옛 정책 기준 답변·인덱스는 무효 → 스레드와 전역 인덱스 캐시를
        # 비워 스테일 답변 노출과 캐시 누적을 막는다(app.py 의 view_b 무효화와 동형).
        st.session_state[THREADS_KEY] = []
        clear_index_cache()
        if had_uploads:
            st.info(
                "정책이 바뀌어 기본 인덱스를 새로 만들었습니다. 이전에 올린 문서는 "
                "'문서 인덱싱'으로 다시 추가해 주세요."
            )


def _persist(chunks) -> None:
    """세션 인덱스를 디스크에 저장한다(실패해도 세션 상태로 동작하므로 무해)."""
    try:
        IndexStore(_session_index_path()).save(chunks)
    except Exception:
        pass


def _render_documents(policy: str) -> None:
    """정책 + 업로드 문서 패널(탭 안). 업로드 후 '문서 인덱싱'으로 근거에 추가."""
    chunks = st.session_state.get(CHUNKS_KEY, [])
    with st.expander(f"📄 근거 문서 (현재 {len(chunks)}개 조각 인덱싱됨)", expanded=False):
        st.caption(
            "현재 정책 원문은 항상 근거로 포함됩니다. PDF/TXT/MD 를 추가로 올린 뒤 "
            "'문서 인덱싱'을 누르면 함께 검색됩니다."
        )
        uploaded = st.file_uploader(
            "정책 문서 추가 (PDF/TXT/MD)",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            key="board_uploader",
        )
        col_a, col_b = st.columns(2)
        build = col_a.button("문서 인덱싱", use_container_width=True)
        clear = col_b.button("업로드 초기화", use_container_width=True)

        st.caption(
            "OpenAI 키: " + ("감지됨 (Chroma + OpenAI 임베딩 의미검색)"
                              if has_openai_key() else "없음 (로컬 해시 검색 폴백)")
        )

        if clear:
            # 정책 기본 인덱스로 되돌린다(업로드 문서 제거). 전역 인덱스 캐시도 비운다.
            st.session_state.pop(_POLICY_SIG_KEY, None)
            st.session_state[CHUNKS_KEY] = []
            st.session_state[DOCS_KEY] = []
            clear_index_cache()
            rerun_fragment()

        if build:
            update = prepare_index_update(uploaded, base_policy_text=policy)
            if update.errors:
                for err in update.errors:
                    st.error(err)
                st.warning("오류가 있어 기존 인덱스를 유지했습니다.")
            else:
                st.session_state[CHUNKS_KEY] = update.chunks
                st.session_state[DOCS_KEY] = update.documents
                st.session_state[_POLICY_SIG_KEY] = _policy_sig(policy)
                _persist(update.chunks)
                st.success(
                    f"문서 {len(update.documents)}개, 근거 조각 {len(update.chunks)}개 인덱싱"
                )
                rerun_fragment()


def _render_suggestions(documents, chunks) -> None:
    """정책/문서에서 뽑은 예시 질문 버튼."""
    questions = suggest_questions(documents, limit=6) if documents else []
    if not questions and chunks:
        pseudo = PolicyDocument(
            name="indexed", text="\n".join(c.text for c in chunks[:20])
        )
        questions = suggest_questions([pseudo], limit=6)
    if not questions:
        st.info("정책이 인덱싱되면 예시 질문이 표시됩니다.")
        return

    st.markdown("**예시 질문**")
    for i, q in enumerate(questions):
        if st.button(q, key=f"board_suggest_{i}", use_container_width=True):
            st.session_state[QUESTION_KEY] = q
            rerun_fragment()


def _render_question(chunks) -> None:
    """질문 입력 + 모드/기준정답 → 답변 생성."""
    st.markdown("**정책 문의**")
    mode = st.radio(
        "답변 생성", ["OpenAI", "근거 추출"], horizontal=True,
        index=0 if has_openai_key() else 1,
        help="OpenAI 키가 없으면 근거 추출 방식으로 사실 기반 답변을 만듭니다.",
    )
    reference = st.text_area(
        "기준 정답(선택)", height=80, key="board_reference",
        placeholder="공식 FAQ/담당자 답변이 있으면 붙여넣으세요. 유사도 지표가 함께 계산됩니다.",
    )
    question = st.text_area(
        "질문 내용", key=QUESTION_KEY, height=110,
        placeholder="예) 신청할 때 필요한 서류는 무엇인가요?",
    )
    disabled = not chunks
    if st.button("질문 등록", type="primary", disabled=disabled):
        q = (question or "").strip()
        if not q:
            st.warning("질문 내용을 입력해 주세요.")
            return
        _submit_question(q, mode, reference, chunks)
    if disabled:
        st.caption("정책이 비어 있어 인덱스가 없습니다. 정책을 입력하고 시뮬레이션을 실행하세요.")


def _submit_question(question: str, mode: str, reference: str, chunks) -> None:
    """검색→생성→평가 후 스레드에 누적한다. OpenAI 실패 시 추출식으로 폴백."""
    index = _build_index(chunks)
    backend = getattr(index, "backend", "")
    generator = _generator_from_mode(mode)
    mode_label = generator.name
    try:
        result = BoardRagService(index=index, generator=generator).answer(
            question, k=5, reference_answer=reference
        )
    except Exception as exc:  # OpenAI 답변 실패 → 추출식으로 한 번 더(앱이 안 죽음).
        st.warning(f"OpenAI 답변 생성 실패로 근거 추출 답변으로 대체합니다: {exc}")
        result = BoardRagService(
            index=index, generator=ExtractiveAnswerGenerator()
        ).answer(question, k=5, reference_answer=reference)
        mode_label = "extractive-fallback"

    st.session_state.setdefault(THREADS_KEY, []).append(
        {
            "question": question,
            "answer": result.answer,
            "sources": result.sources,
            "metrics": result.metrics,
            "mode": mode_label,
            "backend_label": retrieval_backend_label(backend),
        }
    )
    st.session_state[CLEAR_QUESTION_KEY] = True
    rerun_fragment()


def _render_threads() -> None:
    """누적된 Q/A 스레드(최신순) — 답변 + 품질지표 + 근거."""
    threads = st.session_state.get(THREADS_KEY, [])
    if not threads:
        st.info("아직 등록된 문의가 없습니다. 첫 질문을 남겨 보세요!")
        return

    st.divider()
    st.subheader("게시글 답변")
    for thread in reversed(threads):
        with st.chat_message("user"):
            st.markdown("**시민 질문**")
            st.write(thread.get("question", ""))

        with st.chat_message("assistant"):
            st.markdown(f"**정책 안내 답변** · {thread.get('mode', '')}")
            if thread.get("backend_label"):
                st.caption(f"검색 방식: {thread['backend_label']}")
            st.write(thread.get("answer", ""))
            if thread.get("metrics"):
                with st.expander("품질 지표"):
                    # '값' 열에 숫자와 '-'(기준정답 없을 때 None)가 섞이면 st.table 의
                    # arrow 변환이 깨진다 → 열 타입을 문자열로 통일해 안전하게 렌더.
                    rows = [
                        {**r, "값": str(r["값"])}
                        for r in _metric_rows(thread["metrics"])
                    ]
                    st.table(rows)
            sources = thread.get("sources", [])
            if sources:
                with st.expander(f"근거 문서 {len(sources)}건"):
                    for s in sources:
                        # 본문의 마크다운 제어문자를 이스케이프해 표시 깨짐을 막는다.
                        safe = {**s, "text": _escape_md(s.get("text", ""))}
                        st.markdown(format_source_markdown(safe))
