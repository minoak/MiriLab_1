# -*- coding: utf-8 -*-
"""Standalone board RAG tests.

Run:
    python _test_standalone_board.py

These tests keep the board-only RAG stack independent from app.py,
ui/tab_board.py, and board_engine.py so teammates can keep editing those files.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from standalone_board.app import index_path_for_session, prepare_index_update
from standalone_board.core import (
    BoardRagService,
    ExtractiveAnswerGenerator,
    IndexStore,
    PolicyDocument,
    PolicyChunk,
    QualityEvaluator,
    SearchHit,
    VectorIndex,
    chunk_document,
    suggest_questions,
)
from standalone_board.openai_adapter import (
    build_answer_response_kwargs,
    validate_answer_text,
)


POLICY_TEXT = """
[청년 월세 한시 특별지원]
신청 대상: 만 19~34세 무주택 청년 중 부모와 별도 거주하는 사람입니다.
지원 내용: 실제 납부하는 임대료 범위 안에서 월 최대 20만 원을 최대 12개월 지원합니다.
신청 방법: 복지로 누리집 또는 거주지 행정복지센터에서 신청합니다.
필요 서류: 임대차계약서, 소득 증빙 서류, 통장 사본을 제출해야 합니다.
신청 기간: 예산 소진 시 조기 마감될 수 있습니다.
유의 사항: 주택 소유자와 공공임대주택 거주자는 제외됩니다.
"""


def test_chunk_document_keeps_source_and_page_metadata():
    doc = PolicyDocument(
        name="youth-rent.pdf",
        text=POLICY_TEXT,
        pages=[(3, POLICY_TEXT)],
    )

    chunks = chunk_document(doc, max_chars=80, overlap_chars=20)

    assert len(chunks) >= 3
    assert all(c.document_name == "youth-rent.pdf" for c in chunks)
    assert all(c.page == 3 for c in chunks)
    assert all(c.source_label == "youth-rent.pdf p.3" for c in chunks)
    print("ok  chunk_document metadata")


def test_vector_index_ranks_relevant_policy_chunk():
    rent = PolicyDocument(name="rent.txt", text=POLICY_TEXT)
    education = PolicyDocument(
        name="education.txt",
        text="어르신 디지털 금융 교육은 키오스크와 은행 앱 사용법을 8주 동안 교육합니다.",
    )
    index = VectorIndex()
    index.add_chunks(chunk_document(rent) + chunk_document(education))

    hits = index.search("신청할 때 어떤 서류를 제출해야 하나요?", k=3)

    assert hits
    assert "서류" in hits[0].chunk.text or "임대차계약서" in hits[0].chunk.text
    assert hits[0].score > 0
    print("ok  vector search ranking")


def test_board_rag_service_returns_fact_based_answer_sources_and_metrics():
    index = VectorIndex()
    index.add_chunks(chunk_document(PolicyDocument(name="rent.txt", text=POLICY_TEXT)))
    service = BoardRagService(index=index, generator=ExtractiveAnswerGenerator())

    result = service.answer("월세 지원 신청 서류가 무엇인가요?", k=4)

    assert result.answer
    assert "임대차계약서" in result.answer
    assert result.sources
    assert result.metrics["retrieval_count"] > 0
    assert result.metrics["answer_support_ratio"] >= 0.5
    assert result.metrics["verdict"] in {"통과", "주의"}
    print("ok  service answer contract")


def test_quality_evaluator_reports_reference_similarity_when_reference_exists():
    evaluator = QualityEvaluator()
    answer = "필요 서류는 임대차계약서, 소득 증빙 서류, 통장 사본입니다."
    reference = "신청 시 임대차계약서와 소득 증빙 서류, 통장 사본을 제출해야 합니다."
    unrelated = "교육은 주민센터와 복지관에서 8주 동안 진행됩니다."

    similar = evaluator.reference_similarity(answer, reference)
    different = evaluator.reference_similarity(answer, unrelated)

    assert 0 <= different < similar <= 1
    assert similar >= 0.5
    print("ok  reference similarity metric")


def test_index_store_round_trips_chunks_without_touching_shared_sources():
    chunks = chunk_document(PolicyDocument(name="rent.txt", text=POLICY_TEXT))
    with TemporaryDirectory() as tmp:
        store = IndexStore(Path(tmp) / "index.json")
        store.save(chunks)
        loaded = store.load()

    assert [c.id for c in loaded] == [c.id for c in chunks]
    assert loaded[0].document_name == "rent.txt"
    assert "월세" in " ".join(c.text for c in loaded)
    print("ok  index store round trip")


def test_suggest_questions_covers_common_policy_faq_topics():
    questions = suggest_questions([PolicyDocument(name="rent.txt", text=POLICY_TEXT)], limit=6)
    joined = "\n".join(questions)

    assert len(questions) >= 5
    assert "신청 대상" in joined or "자격" in joined
    assert "서류" in joined
    assert "제외" in joined or "유의" in joined
    print("ok  suggested questions")


def test_default_requirements_install_pdf_loader_dependency():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()

    assert "pypdf" in requirements
    print("ok  default requirements include pypdf")


def test_requirements_pin_responses_capable_openai_sdk():
    root_requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()
    board_requirements = Path("standalone_board/requirements.txt").read_text(encoding="utf-8").lower()

    assert "openai>=2" in root_requirements
    assert "openai>=2" in board_requirements
    print("ok  requirements pin Responses-capable OpenAI SDK")


def test_index_path_is_scoped_by_session_id():
    one = index_path_for_session("session-one")
    two = index_path_for_session("session-two")

    assert one != two
    assert one.name == "session-one.json"
    assert two.name == "session-two.json"
    print("ok  index persistence session scope")


class _Upload:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def test_index_update_with_any_upload_error_is_not_saveable():
    def loader(name: str, data: bytes) -> PolicyDocument:
        if name == "bad.pdf":
            raise RuntimeError("broken pdf")
        return PolicyDocument(name=name, text=data.decode("utf-8"))

    update = prepare_index_update(
        [_Upload("good.txt", b"good policy"), _Upload("bad.pdf", b"not a pdf")],
        loader=loader,
    )

    assert update.errors == ["bad.pdf: broken pdf"]
    assert update.can_save is False
    assert update.chunks == []
    print("ok  upload errors preserve previous index")


def test_openai_adapter_builds_gpt5_responses_request_without_temperature():
    hit = SearchHit(
        chunk=PolicyChunk(
            id="rent-doc-1",
            text="필요 서류는 임대차계약서, 소득 증빙 서류, 통장 사본입니다.",
            document_name="rent.txt",
            chunk_index=0,
        ),
        score=0.9,
    )

    kwargs = build_answer_response_kwargs(
        "gpt-5-nano",
        "신청 서류가 무엇인가요?",
        [hit],
    )

    assert kwargs["model"] == "gpt-5-nano"
    assert kwargs["reasoning"] == {"effort": "minimal"}
    assert kwargs["max_output_tokens"] >= 800
    assert "temperature" not in kwargs
    assert "임대차계약서" in kwargs["input"]
    print("ok  OpenAI adapter GPT-5 response request")


def test_openai_adapter_omits_reasoning_for_non_reasoning_models():
    kwargs = build_answer_response_kwargs("gpt-4o-mini", "질문", [])

    assert "reasoning" not in kwargs
    assert "temperature" not in kwargs
    print("ok  OpenAI adapter non-reasoning request")


def test_openai_adapter_rejects_empty_response_text():
    try:
        validate_answer_text("")
    except RuntimeError:
        pass
    else:
        raise AssertionError("empty OpenAI answers must trigger extractive fallback")
    print("ok  OpenAI adapter empty response validation")


def main():
    test_chunk_document_keeps_source_and_page_metadata()
    test_vector_index_ranks_relevant_policy_chunk()
    test_board_rag_service_returns_fact_based_answer_sources_and_metrics()
    test_quality_evaluator_reports_reference_similarity_when_reference_exists()
    test_index_store_round_trips_chunks_without_touching_shared_sources()
    test_suggest_questions_covers_common_policy_faq_topics()
    test_default_requirements_install_pdf_loader_dependency()
    test_requirements_pin_responses_capable_openai_sdk()
    test_index_path_is_scoped_by_session_id()
    test_index_update_with_any_upload_error_is_not_saveable()
    test_openai_adapter_builds_gpt5_responses_request_without_temperature()
    test_openai_adapter_omits_reasoning_for_non_reasoning_models()
    test_openai_adapter_rejects_empty_response_text()
    print("\nstandalone board tests passed")


if __name__ == "__main__":
    main()
