# -*- coding: utf-8 -*-
"""board_engine 단위 테스트(순수, streamlit 무의존).

    python _test_board.py

답변 엔진의 결정론·반환 계약·RAG 폴백을 검증한다. 화면(tab_board) 없이 로직만 돈다.
"""

import os
import random

import board_engine as be
import ui.tab_board as tb
from standalone_board.core import VectorIndex
from ui.tab_board import (
    answer_with_board_rag,
    clear_board_index_cache,
    clear_question_input_after_submit,
    refresh_thread_metrics_for_display,
    source_reference_caption,
    metric_display_items,
    prepare_question_input_state,
    suggested_questions_for_policy,
)


# 청년 월세 정책 일부 — 문장 분리/매칭 검증용 고정 텍스트.
POLICY = (
    "[청년 월세 한시 특별지원]\n"
    "만 19~34세 무주택 청년 중 부모와 별도 거주하는 자에게 월 최대 20만 원을 "
    "최대 12개월간 지원합니다.\n"
    "신청 대상: 본인 소득이 기준 중위소득 60% 이하인 무주택 청년.\n"
    "신청 방법: 복지로 누리집 또는 거주지 행정복지센터 방문 신청. "
    "임대차계약서, 소득 증빙 서류, 통장 사본 제출 필요.\n"
    "유의 사항: 주택 소유자, 공공임대주택 거주자는 제외됩니다."
)


class _Upload:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self._text = text

    def getvalue(self) -> bytes:
        return self._text.encode("utf-8")


def test_match_topic():
    # 대상 키워드(누가/나이/조건)가 방법(신청)보다 많아 '대상'으로 판정.
    assert be._match_topic("누가 신청할 수 있나요? 나이 조건이 어떻게 되나요?") == "대상"
    # 서류/제출 → 방법.
    assert be._match_topic("서류는 뭘 제출해야 하나요?") == "방법"
    # 매칭 키워드 없음 → 빈 문자열.
    assert be._match_topic("음 글쎄요 그냥요") == ""
    print("ok  _match_topic")


def test_split_and_pick():
    sents = be._split_sentences(POLICY)
    assert sents, "문장이 하나는 나와야 한다"
    # 제목 줄([청년 월세 …])은 제외된다.
    assert not any(s.startswith("[") for s in sents)

    picked = be._pick_relevant_sentences(POLICY, "서류는 뭘 제출하나요?", k=2)
    assert 0 < len(picked) <= 2
    assert all(isinstance(s, str) for s in picked)
    # 서류 관련 질문이면 '제출/서류'가 든 문장이 잡혀야 한다.
    assert any(("서류" in s or "제출" in s) for s in picked)

    # 빈 정책 → 빈 리스트(방어).
    assert be._pick_relevant_sentences("", "아무거나") == []
    print("ok  _split_sentences / _pick_relevant_sentences")


def test_answer_question_mock():
    res = be.answer_question(POLICY, "신청 자격이 어떻게 되나요?", mode="mock")
    assert set(res) >= {"answer", "sources", "mode"}
    assert res["mode"] == "mock"
    assert res["answer"], "mock 답변은 비어 있으면 안 된다"
    assert isinstance(res["sources"], list) and res["sources"]
    # sources 모양은 RAG 와 동일한 {text, source} 계약.
    assert all({"text", "source"} <= set(s) for s in res["sources"])
    print("ok  answer_question(mock) 반환 계약")


def test_empty_question():
    res = be.answer_question(POLICY, "   ", mode="mock")
    assert res["answer"] == "" and res["sources"] == []
    print("ok  빈 질문 → 빈 답변")


def test_rag_seam_raises():
    raised = False
    try:
        be.answer_with_rag(POLICY, "질문")
    except NotImplementedError:
        raised = True
    assert raised, "answer_with_rag 는 미구현 상태에서 NotImplementedError 를 던져야 한다"
    print("ok  answer_with_rag 미구현 시 NotImplementedError")


def test_rag_mode_fallback():
    # rag 강제 → 미구현이므로 mock 으로 폴백하되, 사유(⚠️)를 앞에 덧붙인다.
    res = be.answer_question(POLICY, "신청 방법 알려주세요", mode="rag")
    assert res["answer"].startswith("⚠️"), "강제 rag 폴백은 안내 문구로 시작해야 한다"
    assert res["mode"] == "mock"
    assert res["answer"], "폴백 답변 본문이 있어야 한다"
    print("ok  mode='rag' 미구현 → mock 폴백 + 안내")


def test_auto_mode_default_mock():
    # 환경변수 없이 auto → mock (데모/키없음 안전).
    saved = os.environ.pop("MIRILAB_BOARD_RAG", None)
    try:
        assert be._rag_enabled() is False
        res = be.answer_question(POLICY, "자격 조건", mode="auto")
        assert res["mode"] == "mock"
        # 플래그를 켜면 _rag_enabled True (그래도 seam 미구현이라 answer_question은 폴백).
        os.environ["MIRILAB_BOARD_RAG"] = "1"
        assert be._rag_enabled() is True
    finally:
        os.environ.pop("MIRILAB_BOARD_RAG", None)
        if saved is not None:
            os.environ["MIRILAB_BOARD_RAG"] = saved
    print("ok  auto 모드 기본 mock + MIRILAB_BOARD_RAG 토글")


def test_make_comments():
    random.seed(42)
    for _ in range(20):
        cs = be.make_comments("질문")
        assert 1 <= len(cs) <= 2
        assert len(set(cs)) == len(cs), "댓글은 중복되지 않아야 한다"
        assert all(c in be._CITIZEN_COMMENTS for c in cs)
    assert be.make_comments(n=0) == []
    assert len(be.make_comments(n=3)) == 3
    print("ok  make_comments 개수/중복/풀")


def test_board_tab_rag_uses_mirilab_policy_as_default_source():
    saved_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        res = answer_with_board_rag(
            POLICY,
            [],
            "신청할 때 필요한 서류가 무엇인가요?",
            mode="근거 추출",
        )
    finally:
        if saved_key is not None:
            os.environ["OPENAI_API_KEY"] = saved_key

    assert res["answer"]
    assert "임대차계약서" in res["answer"]
    assert res["sources"]
    assert res["document_count"] == 1
    assert res["retrieval_backend"] == "local-hashing-vector"
    assert res["retrieval_backend_label"] == "로컬 해시 벡터 검색"
    assert res["errors"] == []
    print("ok  게시판 RAG 기본 정책 원문")


def test_board_tab_rag_separates_support_period_and_application_period():
    policy = (
        "[청년 월세 한시 특별지원]\n"
        "지원 내용: 실제 납부하는 임대료 범위 안에서 월 최대 20만 원을 최대 12개월 지원합니다.\n"
        "신청 기간: 상시 접수하되 예산 소진 시 조기 마감될 수 있습니다.\n"
    )
    saved_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        res = answer_with_board_rag(
            policy,
            [],
            "지원 금액과 지원 기간은 어떻게 되나요? 신청 기간도 알려주세요.",
            mode="근거 추출",
        )
    finally:
        if saved_key is not None:
            os.environ["OPENAI_API_KEY"] = saved_key

    assert "월 최대 20만 원" in res["answer"]
    assert "최대 12개월" in res["answer"]
    assert "예산 소진" in res["answer"]
    assert any("지원 내용:" in source.get("text", "") for source in res["sources"])
    assert any("신청 기간:" in source.get("text", "") for source in res["sources"])
    print("ok  게시판 RAG 지원 기간/신청 기간 분리")


def test_board_metric_labels_are_evidence_scoped_not_truth_claims():
    items = metric_display_items(
        {
            "answer_support_ratio": 1.0,
            "hallucination_risk": 0.0,
            "retrieval_count": 2,
            "verdict": "통과",
        }
    )

    labels = [item["label"] for item in items]
    assert "근거 일치도" in labels
    assert "근거 밖 가능성" in labels
    assert "근거 충실도" not in labels
    assert "환각 위험도" not in labels
    print("ok  게시판 지표 문구 완화")


def test_board_source_caption_uses_match_grade_instead_of_raw_score():
    caption = source_reference_caption("미리랩 설정 정책", 0.4337)

    assert "근거 매칭: 적합" in caption
    assert "score=" not in caption
    assert "0.4337" not in caption
    print("ok  게시판 근거 점수 등급 표시")


def test_board_question_input_state_refreshes_when_same_suggestion_is_reselected():
    state = {}

    first_key, first_value = prepare_question_input_state(state, selected_question="신청 대상은?")
    clear_question_input_after_submit(state)
    second_key, second_value = prepare_question_input_state(state, selected_question="신청 대상은?")

    assert first_value == "신청 대상은?"
    assert second_value == "신청 대상은?"
    assert second_key != first_key
    assert state["board_question_content_draft"] == "신청 대상은?"
    print("ok  게시판 같은 예상 질문 재선택 입력 갱신")


def test_board_question_input_state_clears_after_submit_without_touching_widget_key():
    state = {}
    question_key, value = prepare_question_input_state(state, selected_question="필요 서류는?")

    clear_question_input_after_submit(state)
    next_key, next_value = prepare_question_input_state(state)

    assert value == "필요 서류는?"
    assert next_value == ""
    assert next_key != question_key
    assert "board_question_content_draft" in state
    print("ok  게시판 제출 후 입력 상태 초기화")


def test_board_refreshes_stale_thread_metrics_for_display():
    thread = {
        "answer": (
            "지원 금액은 월 최대 20만 원이고, 신청 기간은 상시 접수입니다. "
            "필요 서류는 임대차계약서, 소득 증빙 서류, 통장 사본입니다."
        ),
        "sources": [
            {
                "text": "지원 내용: 실제 납부하는 임대료 범위 내에서 월 20만 원 한도 지원합니다.",
                "source": "미리랩 설정 정책",
                "score": 0.43,
            },
            {
                "text": "신청 기간: 상시 접수(예산 소진 시 조기 마감될 수 있음).",
                "source": "미리랩 설정 정책",
                "score": 0.42,
            },
            {
                "text": "신청 방법: 임대차계약서, 소득 증빙 서류, 통장 사본 제출 필요.",
                "source": "미리랩 설정 정책",
                "score": 0.35,
            },
        ],
        "metrics": {
            "answer_support_ratio": 0.2667,
            "hallucination_risk": 0.7333,
            "retrieval_count": 3,
            "verdict": "실패",
        },
    }

    metrics = refresh_thread_metrics_for_display(thread)

    assert metrics["answer_support_ratio"] >= 0.65
    assert metrics["hallucination_risk"] <= 0.35
    assert metrics["verdict"] != "실패"
    print("ok  게시판 저장된 이전 지표 재계산")


class _FailingSearchIndex:
    backend = "chroma-vector"

    def search(self, query: str, *, k: int = 5, min_score: float = 0.0):
        raise RuntimeError("query embedding failed")


def test_board_tab_rag_rebuilds_local_index_when_semantic_search_fails():
    calls = []

    def fake_build_index(chunks, *, prefer_openai: bool = True):
        calls.append(prefer_openai)
        if prefer_openai:
            return _FailingSearchIndex()
        index = VectorIndex()
        index.add_chunks(chunks)
        return index

    saved_key = os.environ.get("OPENAI_API_KEY")
    original = tb._build_index
    try:
        os.environ["OPENAI_API_KEY"] = "sk-test"
        tb._build_index = fake_build_index
        res = answer_with_board_rag(
            POLICY,
            [],
            "신청할 때 필요한 서류가 무엇인가요?",
            mode="OpenAI",
        )
    finally:
        tb._build_index = original
        if saved_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved_key

    assert calls == [True, False]
    assert res["answer"]
    assert res["mode"] == "extractive-fallback"
    assert res["retrieval_backend"] == "local-hashing-vector"
    assert res["retrieval_backend_label"] == "로컬 해시 벡터 검색"
    assert "임대차계약서" in res["answer"]
    print("ok  게시판 semantic 검색 실패시 로컬 재빌드 폴백")


class _FailingAnswerGenerator:
    name = "openai-grounded"

    def generate(self, question, hits):
        raise RuntimeError("OpenAI answer failed")


def test_board_tab_rag_falls_back_to_extractive_when_openai_answer_fails_after_local_search():
    def local_build_index(chunks, *, prefer_openai: bool = True):
        index = VectorIndex()
        index.add_chunks(chunks)
        return index

    saved_key = os.environ.get("OPENAI_API_KEY")
    original_build = tb._build_index
    original_generator = tb.OpenAIAnswerGenerator
    try:
        os.environ["OPENAI_API_KEY"] = "sk-test"
        tb._build_index = local_build_index
        tb.OpenAIAnswerGenerator = lambda: _FailingAnswerGenerator()
        res = answer_with_board_rag(
            POLICY,
            [],
            "신청할 때 필요한 서류가 무엇인가요?",
            mode="OpenAI",
        )
    finally:
        tb._build_index = original_build
        tb.OpenAIAnswerGenerator = original_generator
        if saved_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved_key

    assert res["answer"]
    assert res["errors"] == []
    assert res["mode"] == "extractive-fallback"
    assert res["retrieval_backend"] == "local-hashing-vector"
    assert "임대차계약서" in res["answer"]
    print("ok  게시판 로컬 검색 후 OpenAI 답변 실패시 추출 폴백")


def test_board_tab_reuses_cached_index_for_same_policy_documents():
    calls = []

    def fake_build_retrieval_index(chunks, *, prefer_openai: bool = True):
        calls.append((len(chunks), prefer_openai))
        index = VectorIndex()
        index.add_chunks(chunks)
        return index

    original = tb.build_retrieval_index
    saved_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        clear_board_index_cache()
        tb.build_retrieval_index = fake_build_retrieval_index
        first = answer_with_board_rag(POLICY, [], "신청 서류가 무엇인가요?", mode="근거 추출")
        second = answer_with_board_rag(POLICY, [], "신청 대상은 누구인가요?", mode="근거 추출")
    finally:
        tb.build_retrieval_index = original
        clear_board_index_cache()
        if saved_key is not None:
            os.environ["OPENAI_API_KEY"] = saved_key

    assert first["answer"]
    assert second["answer"]
    assert len(calls) == 1
    print("ok  게시판 동일 문서 인덱스 캐시 재사용")


def test_board_tab_rag_merges_uploaded_documents():
    res = answer_with_board_rag(
        POLICY,
        [_Upload("extra.txt", "추가 안내: 방문 신청은 주민센터에서 가능합니다.")],
        "방문 신청은 어디에서 하나요?",
        mode="근거 추출",
    )

    assert res["answer"]
    assert "주민센터" in res["answer"]
    assert res["document_count"] == 2
    assert any(source.get("document") == "extra.txt" for source in res["sources"])
    print("ok  게시판 RAG 추가 업로드 문서")


def test_board_tab_suggests_five_questions_from_policy():
    questions = suggested_questions_for_policy(POLICY)

    assert len(questions) == 5
    assert len(set(questions)) == 5
    joined = "\n".join(questions)
    assert "신청 대상" in joined or "자격" in joined
    assert "서류" in joined
    print("ok  게시판 예상 질문 5개")


def main():
    test_match_topic()
    test_split_and_pick()
    test_answer_question_mock()
    test_empty_question()
    test_rag_seam_raises()
    test_rag_mode_fallback()
    test_auto_mode_default_mock()
    test_make_comments()
    test_board_tab_rag_uses_mirilab_policy_as_default_source()
    test_board_tab_rag_separates_support_period_and_application_period()
    test_board_metric_labels_are_evidence_scoped_not_truth_claims()
    test_board_source_caption_uses_match_grade_instead_of_raw_score()
    test_board_question_input_state_refreshes_when_same_suggestion_is_reselected()
    test_board_question_input_state_clears_after_submit_without_touching_widget_key()
    test_board_refreshes_stale_thread_metrics_for_display()
    test_board_tab_rag_rebuilds_local_index_when_semantic_search_fails()
    test_board_tab_rag_falls_back_to_extractive_when_openai_answer_fails_after_local_search()
    test_board_tab_reuses_cached_index_for_same_policy_documents()
    test_board_tab_rag_merges_uploaded_documents()
    test_board_tab_suggests_five_questions_from_policy()
    print("\n전부 통과")


if __name__ == "__main__":
    main()
