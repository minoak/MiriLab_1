# -*- coding: utf-8 -*-
"""Standalone board RAG tests.

Run:
    python _test_standalone_board.py

These tests keep the board-only RAG stack independent from app.py,
ui/tab_board.py, and board_engine.py so teammates can keep editing those files.
"""

from pathlib import Path
import os
from tempfile import TemporaryDirectory

from standalone_board.app import _metric_rows, format_source_markdown, index_path_for_session, prepare_index_update
from standalone_board.core import (
    BoardRagService,
    ChromaVectorIndex,
    ExtractiveAnswerGenerator,
    IndexStore,
    PolicyDocument,
    PolicyChunk,
    QualityEvaluator,
    SearchHit,
    VectorIndex,
    chunk_document,
    retrieval_backend_label,
    suggest_questions,
)
from standalone_board.openai_adapter import (
    OpenAIEmbeddingEmbedder,
    build_answer_response_kwargs,
    build_retrieval_index,
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


def test_chunk_document_splits_policy_labels_into_focused_chunks():
    chunks = chunk_document(PolicyDocument(name="rent.txt", text=POLICY_TEXT))
    chunk_texts = [chunk.text for chunk in chunks]

    assert any(text.startswith("지원 내용:") for text in chunk_texts)
    assert any(text.startswith("신청 기간:") for text in chunk_texts)
    assert all(not ("지원 내용:" in text and "신청 기간:" in text) for text in chunk_texts)
    print("ok  policy label chunk boundaries")


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


def test_quality_evaluator_accepts_structured_grounded_openai_answers():
    evaluator = QualityEvaluator()
    sources = [
        "신청 대상: 본인 소득이 기준 중위소득 60% 이하이고, 원가구 소득이 기준 중위소득 100% 이하인 무주택 청년.",
        "신청 기간: 상시 접수(예산 소진 시 조기 마감될 수 있음).",
        "신청 방법: 복지로 누리집 또는 거주지 행정복지센터 방문 신청. 임대차계약서, 소득 증빙 서류, 통장 사본 제출 필요.",
        "지원 내용: 실제 납부하는 임대료 범위 내에서 월 20만 원 한도 지원합니다.",
    ]
    answer = (
        "1. 결론: 청년 월세 한시 특별지원은 만 19~34세 무주택 청년에게 "
        "월 최대 20만 원을 최대 12개월간 지원합니다.\n\n"
        "2. 주요 내용\n\n"
        "- 대상: 본인 소득이 기준 중위소득 60% 이하이고 원가구 소득이 "
        "기준 중위소득 100% 이하인 무주택 청년입니다.\n"
        "- 방법: 복지로 누리집 또는 거주지 행정복지센터 방문 신청입니다.\n"
        "- 서류: 임대차계약서, 소득 증빙 서류, 통장 사본이 필요합니다.\n"
        "- 신청 기간: 상시 접수이나 예산 소진 시 조기 마감될 수 있습니다.\n\n"
        "3. 참고\n\n"
        "- 근거 문서 기준이며, 최종 확인은 담당 기관에 문의하세요."
    )

    support = evaluator.answer_support_ratio(answer, sources)

    assert support >= 0.65
    print("ok  structured grounded answer metric")


def test_quality_evaluator_supports_facts_combined_across_retrieved_chunks():
    evaluator = QualityEvaluator()
    sources = [
        "지원 내용: 실제 납부하는 임대료 범위 내에서 월 20만 원 한도 지원합니다.",
        "신청 기간: 상시 접수(예산 소진 시 조기 마감될 수 있음).",
    ]
    answer = "지원 금액은 월 최대 20만 원이고, 신청 기간은 상시 접수입니다."

    support = evaluator.answer_support_ratio(answer, sources)

    assert support >= 0.65
    print("ok  cross-chunk grounded answer metric")


def test_quality_evaluator_uses_review_needed_instead_of_failure_verdict():
    evaluator = QualityEvaluator()

    metrics = evaluator.build_metrics(answer="문서에 없는 답변입니다.", hits=[])

    assert metrics["verdict"] == "확인 필요"
    print("ok  review-needed verdict wording")


def test_metric_rows_use_evidence_scoped_labels():
    rows = _metric_rows(
        {
            "answer_support_ratio": 1.0,
            "hallucination_risk": 0.0,
            "retrieval_count": 2,
        }
    )
    labels = [row["지표"] for row in rows]
    descriptions = "\n".join(row["의미"] for row in rows)

    assert "근거 일치도" in labels
    assert "근거 밖 가능성" in labels
    assert "근거 충실도" not in labels
    assert "환각 위험도" not in labels
    assert "실제 진실" not in descriptions
    print("ok  standalone metric wording")


def test_source_markdown_uses_match_grade_instead_of_raw_score():
    markdown = format_source_markdown(
        {
            "source": "미리랩 설정 정책",
            "score": 0.4337,
            "text": "신청 대상: 본인 소득이 기준 중위소득 60% 이하입니다.",
        }
    )

    assert "근거 매칭: 적합" in markdown
    assert "score=" not in markdown
    assert "0.4337" not in markdown
    print("ok  standalone source score grade")


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


def test_board_guide_describes_current_embedding_and_metric_wording():
    guide = Path("BOARD.md").read_text(encoding="utf-8")

    assert "Chroma + OpenAI Embedding" in guide
    assert "근거 일치도" in guide
    assert "근거 밖 가능성" in guide
    assert "근거 충실도" not in guide
    assert "환각 위험도" not in guide
    print("ok  BOARD guide matches current RAG behavior")


def test_standalone_requirements_include_chroma_vector_database():
    board_requirements = Path("standalone_board/requirements.txt").read_text(encoding="utf-8").lower()

    assert "chromadb" in board_requirements
    print("ok  standalone requirements include Chroma vector DB")


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


def test_index_update_uses_mirilab_policy_without_uploads():
    update = prepare_index_update([], base_policy_text=POLICY_TEXT)

    assert update.can_save is True
    assert [doc.name for doc in update.documents] == ["미리랩 설정 정책"]
    assert update.chunks
    assert all(chunk.document_name == "미리랩 설정 정책" for chunk in update.chunks)
    print("ok  default MiriLab policy document")


def test_index_update_merges_mirilab_policy_and_uploaded_documents():
    def loader(name: str, data: bytes) -> PolicyDocument:
        return PolicyDocument(name=name, text=data.decode("utf-8"))

    update = prepare_index_update(
        [_Upload("extra.txt", "추가 공고: 방문 신청은 주민센터에서 가능합니다.".encode("utf-8"))],
        base_policy_text=POLICY_TEXT,
        loader=loader,
    )

    names = [doc.name for doc in update.documents]
    assert names == ["미리랩 설정 정책", "extra.txt"]
    assert "월세" in " ".join(chunk.text for chunk in update.chunks)
    assert "주민센터" in " ".join(chunk.text for chunk in update.chunks)
    print("ok  MiriLab policy plus uploaded documents")


class _FakeEmbeddingDatum:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.data = [_FakeEmbeddingDatum(embedding) for embedding in embeddings]


class _FakeEmbeddingsEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _FakeEmbeddingResponse:
        self.calls.append(kwargs)
        return _FakeEmbeddingResponse(
            [[float(i), float(i + 1)] for i, _ in enumerate(kwargs["input"])]
        )


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddingsEndpoint()


def test_openai_embedding_embedder_batches_inputs_with_model():
    client = _FakeOpenAIClient()
    embedder = OpenAIEmbeddingEmbedder(model="text-embedding-3-small", client=client)

    vectors = embedder.embed_many(["자격 조건", "필요 서류"])

    assert vectors == [[0.0, 1.0], [1.0, 2.0]]
    assert client.embeddings.calls == [
        {
            "model": "text-embedding-3-small",
            "input": ["자격 조건", "필요 서류"],
            "encoding_format": "float",
        }
    ]
    print("ok  OpenAI embedding embedder request")


class _KeywordEmbedder:
    name = "keyword-test"

    def embed(self, text: str) -> list[float]:
        if "주민센터" in text or "방문" in text:
            return [1.0, 0.0, 0.0]
        if "서류" in text or "임대차계약서" in text or "통장" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def test_chroma_vector_index_ranks_by_embedding_similarity():
    chunks = [
        PolicyChunk(
            id="doc-documents",
            text="필요 서류는 임대차계약서, 소득 증빙 서류, 통장 사본입니다.",
            document_name="policy.txt",
            chunk_index=0,
        ),
        PolicyChunk(
            id="doc-visit",
            text="방문 신청은 거주지 주민센터에서 가능합니다.",
            document_name="extra.txt",
            chunk_index=1,
        ),
    ]
    index = ChromaVectorIndex(embedder=_KeywordEmbedder())
    index.add_chunks(chunks)

    hits = index.search("주민센터 방문 신청", k=1)

    assert index.backend == "chroma-vector"
    assert hits[0].chunk.id == "doc-visit"
    assert hits[0].score >= 0.99
    print("ok  Chroma vector index ranking")


def test_retrieval_index_prefers_chroma_when_embedding_factory_is_available():
    chunks = chunk_document(PolicyDocument(name="rent.txt", text=POLICY_TEXT))

    index = build_retrieval_index(
        chunks,
        embedding_factory=lambda: _KeywordEmbedder(),
    )

    assert index.backend == "chroma-vector"
    print("ok  retrieval index prefers Chroma semantic vector backend")


def test_retrieval_index_falls_back_to_local_hashing_without_openai_key():
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        chunks = chunk_document(PolicyDocument(name="rent.txt", text=POLICY_TEXT))
        index = build_retrieval_index(chunks)
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved

    assert index.backend == "local-hashing-vector"
    print("ok  retrieval index local fallback without OpenAI key")


def test_retrieval_backend_label_is_user_visible_and_specific():
    assert retrieval_backend_label("chroma-vector") == "Chroma + OpenAI Embedding"
    assert retrieval_backend_label("local-hashing-vector") == "로컬 해시 벡터 검색"
    assert retrieval_backend_label("unknown") == "unknown"
    print("ok  retrieval backend label")


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
    assert "지원 기간" in kwargs["input"]
    assert "신청 기간" in kwargs["input"]
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
    test_chunk_document_splits_policy_labels_into_focused_chunks()
    test_vector_index_ranks_relevant_policy_chunk()
    test_board_rag_service_returns_fact_based_answer_sources_and_metrics()
    test_quality_evaluator_reports_reference_similarity_when_reference_exists()
    test_quality_evaluator_accepts_structured_grounded_openai_answers()
    test_quality_evaluator_supports_facts_combined_across_retrieved_chunks()
    test_quality_evaluator_uses_review_needed_instead_of_failure_verdict()
    test_metric_rows_use_evidence_scoped_labels()
    test_source_markdown_uses_match_grade_instead_of_raw_score()
    test_index_store_round_trips_chunks_without_touching_shared_sources()
    test_suggest_questions_covers_common_policy_faq_topics()
    test_default_requirements_install_pdf_loader_dependency()
    test_requirements_pin_responses_capable_openai_sdk()
    test_board_guide_describes_current_embedding_and_metric_wording()
    test_standalone_requirements_include_chroma_vector_database()
    test_index_path_is_scoped_by_session_id()
    test_index_update_with_any_upload_error_is_not_saveable()
    test_index_update_uses_mirilab_policy_without_uploads()
    test_index_update_merges_mirilab_policy_and_uploaded_documents()
    test_openai_embedding_embedder_batches_inputs_with_model()
    test_chroma_vector_index_ranks_by_embedding_similarity()
    test_retrieval_index_prefers_chroma_when_embedding_factory_is_available()
    test_retrieval_index_falls_back_to_local_hashing_without_openai_key()
    test_retrieval_backend_label_is_user_visible_and_specific()
    test_openai_adapter_builds_gpt5_responses_request_without_temperature()
    test_openai_adapter_omits_reasoning_for_non_reasoning_models()
    test_openai_adapter_rejects_empty_response_text()
    print("\nstandalone board tests passed")


if __name__ == "__main__":
    main()
