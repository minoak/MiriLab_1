# -*- coding: utf-8 -*-
"""Pure standalone board RAG logic.

No Streamlit, no network calls, no imports from the main app.  The UI layer and
OpenAI adapter sit beside this module so tests can exercise fact retrieval,
metrics, persistence, and question suggestions deterministically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterable, Protocol
from uuid import uuid4


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_SENTENCE_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
_POLICY_LABELS = (
    "신청 대상",
    "지원 대상",
    "지원 내용",
    "지원 금액",
    "금액 및 기간",
    "지원 기간",
    "신청 방법",
    "접수 방법",
    "필요 서류",
    "제출 서류",
    "신청 기간",
    "접수 기간",
    "유의 사항",
    "제외 대상",
    "대상",
    "방법",
    "서류",
)
_POLICY_LABEL_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(label) for label in _POLICY_LABELS) + r")\s*[:：]"
)
_INLINE_POLICY_LABEL_RE = re.compile(
    r"(?<![가-힣A-Za-z0-9])(?:"
    + "|".join(re.escape(label) for label in _POLICY_LABELS)
    + r")\s*[:：]"
)
_STOPWORDS = {
    "그리고", "그러나", "또는", "및", "으로", "에서", "에게", "하는", "합니다",
    "있습니다", "됩니다", "대한", "관련", "무엇", "어떻게", "언제", "어디",
    "신청", "지원", "정책",
}
_METRIC_STOPWORDS = {
    "그리고", "그러나", "또는", "및", "대한", "관련", "무엇", "어떻게",
    "언제", "어디", "결론", "주요", "참고",
}
_METRIC_SUFFIXES = (
    "입니다", "합니다", "됩니다", "였습니다", "였습니다", "입니다만",
    "이고", "이며", "하는", "되는", "에서", "으로", "에게", "까지",
    "부터", "이나", "이나마", "이고요", "은", "는", "이", "가", "을", "를",
)


@dataclass(frozen=True)
class PolicyDocument:
    """A policy source file.

    pages is optional for text files.  PDF loaders should fill it with
    (page_number, page_text) pairs so answers can cite pages.
    """

    name: str
    text: str
    pages: list[tuple[int, str]] | None = None


@dataclass(frozen=True)
class PolicyChunk:
    id: str
    text: str
    document_name: str
    chunk_index: int
    page: int | None = None

    @property
    def source_label(self) -> str:
        if self.page is None:
            return self.document_name
        return f"{self.document_name} p.{self.page}"


@dataclass(frozen=True)
class SearchHit:
    chunk: PolicyChunk
    score: float


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[dict]
    metrics: dict
    mode: str = "rag"
    retrieval_backend: str = ""
    retrieval_backend_label: str = ""


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> list[float]:
        ...


class AnswerGenerator(Protocol):
    name: str

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        ...


class SearchIndex(Protocol):
    backend: str

    def search(self, query: str, *, k: int = 5, min_score: float = 0.0) -> list[SearchHit]:
        ...


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _token_features(text: str) -> list[str]:
    """Tokenize Korean/English text with short Korean n-grams for recall."""

    features: list[str] = []
    for token in _TOKEN_RE.findall((text or "").lower()):
        if token in _STOPWORDS:
            continue
        features.append(token)
        if re.fullmatch(r"[가-힣]+", token) and len(token) >= 3:
            for size in (2, 3):
                for i in range(0, len(token) - size + 1):
                    gram = token[i:i + size]
                    if gram not in _STOPWORDS:
                        features.append(gram)
    return features


def _metric_token_features(text: str) -> set[str]:
    features: set[str] = set()
    for raw in _TOKEN_RE.findall((text or "").lower()):
        token = raw
        changed = True
        while changed:
            changed = False
            for suffix in _METRIC_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                    token = token[:-len(suffix)]
                    changed = True
                    break
        if len(token) < 2 or token in _METRIC_STOPWORDS:
            continue
        features.add(token)
    return features


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    a_norm = math.sqrt(sum(x * x for x in a))
    b_norm = math.sqrt(sum(y * y for y in b))
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return dot / (a_norm * b_norm)


class HashingEmbedder:
    """Deterministic local vectorizer used for tests and keyless retrieval."""

    name = "local-hashing"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for feature in _token_features(text):
            digest = hashlib.sha1(feature.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.dimensions
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def _split_sentences(text: str) -> list[str]:
    units = [_normalize_space(p) for p in _SENTENCE_RE.split(text or "")]
    return [u for u in units if u]


def _expanded_query_features(question: str) -> set[str]:
    features = set(_token_features(question))
    expansions = [
        (("서류", "제출", "준비물"), ("서류", "제출", "증빙", "계약서", "통장", "사본")),
        (("대상", "자격", "누가", "조건"), ("대상", "자격", "나이", "연령", "소득", "조건")),
        (("금액", "얼마", "내용"), ("금액", "한도", "개월", "지원", "임대료", "바우처")),
        (("기간", "언제", "마감"), ("기간", "마감", "접수", "모집", "예산")),
        (("제외", "불가", "주의", "유의"), ("제외", "불가", "유의", "주의", "환수")),
    ]
    for triggers, related in expansions:
        if any(trigger in question for trigger in triggers):
            features.update(related)
    return features


def _sentence_relevance(question_features: set[str], sentence: str) -> int:
    sentence_features = set(_token_features(sentence))
    overlap = question_features & sentence_features
    exact_bonus = sum(2 for feature in question_features if feature in sentence)
    return len(overlap) + exact_bonus


def _is_metric_boilerplate(sentence: str) -> bool:
    boilerplate_markers = (
        "문서 근거에 따르면",
        "다음과 같이 안내",
        "주요 내용",
        "참고",
        "정확한 최종 판단",
        "최종 확인",
        "담당 기관",
        "접수 창구",
        "근거 문서 기준",
    )
    return any(marker in sentence for marker in boilerplate_markers)


def _stable_chunk_id(document_name: str, page: int | None, index: int, text: str) -> str:
    raw = f"{document_name}|{page or ''}|{index}|{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def retrieval_backend_label(backend: str) -> str:
    labels = {
        "chroma-vector": "Chroma + OpenAI Embedding",
        "local-hashing-vector": "로컬 해시 벡터 검색",
        "in-memory-vector": "메모리 벡터 검색",
    }
    return labels.get(backend or "", backend or "-")


def retrieval_score_label(score) -> str:
    if score is None:
        return ""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return ""

    if value >= 0.75:
        grade = "높음"
    elif value >= 0.35:
        grade = "적합"
    elif value >= 0.15:
        grade = "보조"
    else:
        grade = "낮음"
    return f"근거 매칭: {grade}"


def _policy_label_sections(text: str) -> list[str]:
    lines = [_normalize_space(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    sections: list[str] = []
    current = ""
    title = ""

    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            if not title:
                title = line
            continue
        if _POLICY_LABEL_RE.match(line):
            if current:
                sections.append(current)
            current = line
            continue
        if current:
            current = _normalize_space(f"{current} {line}")
        else:
            current = line

    if current:
        sections.append(current)

    labelled = [section for section in sections if _POLICY_LABEL_RE.match(section)]
    if len(labelled) >= 2:
        if title:
            return [title] + sections
        return sections

    normalized = _normalize_space(text)
    matches = list(_INLINE_POLICY_LABEL_RE.finditer(normalized))
    if len(matches) < 2:
        return []

    inline_sections: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        section = normalized[start:end].strip(" .;·")
        if section:
            inline_sections.append(section)
    return inline_sections


def _chunk_page(
    *,
    document_name: str,
    page: int | None,
    text: str,
    start_index: int,
    max_chars: int,
    overlap_chars: int,
) -> list[PolicyChunk]:
    labelled_sections = _policy_label_sections(text)
    if labelled_sections:
        chunks: list[PolicyChunk] = []
        idx = start_index
        for section in labelled_sections:
            if len(section) <= max_chars:
                chunks.append(
                    PolicyChunk(
                        id=_stable_chunk_id(document_name, page, idx, section),
                        text=section,
                        document_name=document_name,
                        page=page,
                        chunk_index=idx,
                    )
                )
                idx += 1
                continue
            section_chunks = _chunk_page(
                document_name=document_name,
                page=page,
                text=section,
                start_index=idx,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
            chunks.extend(section_chunks)
            idx += len(section_chunks)
        return chunks

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[PolicyChunk] = []
    current = ""
    idx = start_index

    def flush() -> None:
        nonlocal current, idx
        body = _normalize_space(current)
        if not body:
            return
        chunks.append(
            PolicyChunk(
                id=_stable_chunk_id(document_name, page, idx, body),
                text=body,
                document_name=document_name,
                page=page,
                chunk_index=idx,
            )
        )
        idx += 1
        current = body[-overlap_chars:] if overlap_chars > 0 else ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            flush()
            start = 0
            while start < len(sentence):
                part = sentence[start:start + max_chars]
                current = part
                flush()
                start += max(1, max_chars - overlap_chars)
            current = ""
            continue

        candidate = _normalize_space(f"{current} {sentence}")
        if current and len(candidate) > max_chars:
            flush()
            candidate = _normalize_space(f"{current} {sentence}")
        current = candidate

    flush()
    return chunks


def chunk_document(
    document: PolicyDocument,
    *,
    max_chars: int = 900,
    overlap_chars: int = 120,
) -> list[PolicyChunk]:
    """Split a policy document into page-aware chunks."""

    pages = document.pages or [(None, document.text)]
    chunks: list[PolicyChunk] = []
    next_index = 0
    for page, text in pages:
        page_chunks = _chunk_page(
            document_name=document.name,
            page=page,
            text=text,
            start_index=next_index,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        chunks.extend(page_chunks)
        next_index += len(page_chunks)
    return chunks


class VectorIndex:
    """Small local vector index for standalone board documents."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.backend = (
            "local-hashing-vector"
            if getattr(self.embedder, "name", "") == HashingEmbedder.name
            else "in-memory-vector"
        )
        self._chunks: list[PolicyChunk] = []
        self._vectors: list[list[float]] = []

    @property
    def chunks(self) -> list[PolicyChunk]:
        return list(self._chunks)

    def clear(self) -> None:
        self._chunks.clear()
        self._vectors.clear()

    def add_chunks(self, chunks: Iterable[PolicyChunk]) -> None:
        items = list(chunks)
        if not items:
            return
        self._chunks.extend(items)
        self._vectors.extend(_embed_many(self.embedder, [chunk.text for chunk in items]))

    def search(self, query: str, *, k: int = 5, min_score: float = 0.0) -> list[SearchHit]:
        qvec = self.embedder.embed(query)
        hits = [
            SearchHit(chunk=chunk, score=_cosine(qvec, vector))
            for chunk, vector in zip(self._chunks, self._vectors)
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        filtered = [h for h in hits if h.score >= min_score]
        return filtered[: max(0, k)]


def _embed_many(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    embed_many = getattr(embedder, "embed_many", None)
    if callable(embed_many):
        return [list(vector) for vector in embed_many(texts)]
    return [embedder.embed(text) for text in texts]


class ChromaVectorIndex:
    """Ephemeral Chroma vector DB index for semantic policy retrieval."""

    backend = "chroma-vector"

    def __init__(
        self,
        *,
        embedder: Embedder,
        collection_name: str | None = None,
    ) -> None:
        try:
            import chromadb
        except Exception as exc:  # pragma: no cover - exercised when dependency is absent.
            raise RuntimeError("chromadb 패키지가 필요합니다.") from exc

        self.embedder = embedder
        self.collection_name = collection_name or f"mirilab-board-{uuid4().hex}"
        self._client = chromadb.EphemeralClient()
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunks_by_id: dict[str, PolicyChunk] = {}

    @property
    def chunks(self) -> list[PolicyChunk]:
        return list(self._chunks_by_id.values())

    def clear(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunks_by_id.clear()

    def add_chunks(self, chunks: Iterable[PolicyChunk]) -> None:
        items = list(chunks)
        if not items:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for idx, chunk in enumerate(items):
            chroma_id = f"{chunk.id}-{idx}"
            ids.append(chroma_id)
            documents.append(chunk.text)
            metadatas.append(
                {
                    "document_name": chunk.document_name,
                    "chunk_index": int(chunk.chunk_index),
                    "page": -1 if chunk.page is None else int(chunk.page),
                    "source": chunk.source_label,
                }
            )
            self._chunks_by_id[chroma_id] = chunk

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=_embed_many(self.embedder, documents),
        )

    def search(self, query: str, *, k: int = 5, min_score: float = 0.0) -> list[SearchHit]:
        if k <= 0 or not self._chunks_by_id:
            return []

        qvec = self.embedder.embed(query)
        raw = self._collection.query(
            query_embeddings=[qvec],
            n_results=min(k, len(self._chunks_by_id)),
            include=["distances"],
        )
        ids = (raw.get("ids") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        hits: list[SearchHit] = []
        for chroma_id, distance in zip(ids, distances):
            chunk = self._chunks_by_id.get(chroma_id)
            if chunk is None:
                continue
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            if score >= min_score:
                hits.append(SearchHit(chunk=chunk, score=score))
        return hits


class ExtractiveAnswerGenerator:
    """Fact-only fallback answer generator using retrieved source text."""

    name = "extractive"

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        if not hits:
            return (
                "업로드된 정책 문서에서 질문과 직접 관련된 근거를 찾지 못했습니다. "
                "문서를 추가하거나 질문을 더 구체적으로 입력해 주세요."
            )

        query_features = _expanded_query_features(question)
        selected: list[str] = []
        seen: set[str] = set()
        for hit in hits:
            sentences = _split_sentences(hit.chunk.text)
            ranked = sorted(
                sentences,
                key=lambda s: _sentence_relevance(query_features, s),
                reverse=True,
            )
            sentence = ranked[0] if ranked else hit.chunk.text
            sentence = sentence.rstrip(".")
            if sentence and sentence not in seen:
                seen.add(sentence)
                selected.append(sentence)
            if len(selected) >= 3:
                break

        bullets = "\n".join(f"- {s}." for s in selected)
        return (
            "문서 근거에 따르면 다음과 같이 안내할 수 있습니다.\n\n"
            f"{bullets}\n\n"
            "정확한 최종 판단은 담당 기관의 공고문과 접수 창구에서 다시 확인해 주세요."
        )


class QualityEvaluator:
    """Learning-oriented quality metrics for policy-board answers."""

    def reference_similarity(self, answer: str, reference_answer: str) -> float:
        answer_tokens = set(_token_features(answer))
        ref_tokens = set(_token_features(reference_answer))
        if not answer_tokens or not ref_tokens:
            return 0.0
        overlap = len(answer_tokens & ref_tokens)
        return (2 * overlap) / (len(answer_tokens) + len(ref_tokens))

    def answer_support_ratio(self, answer: str, source_texts: list[str]) -> float:
        sentences = [
            s for s in _split_sentences(answer)
            if len(_metric_token_features(s)) >= 2 and not _is_metric_boilerplate(s)
        ]
        if not sentences:
            return 0.0
        source_features = [_metric_token_features(src) for src in source_texts]
        if not source_features:
            return 0.0
        source_union = set().union(*source_features)

        supported = 0
        for sentence in sentences:
            tokens = _metric_token_features(sentence)
            if not tokens:
                continue
            best_single_source = max(
                (len(tokens & src_tokens) / len(tokens) for src_tokens in source_features),
                default=0.0,
            )
            combined_sources = len(tokens & source_union) / len(tokens)
            if max(best_single_source, combined_sources) >= 0.35:
                supported += 1
        return supported / len(sentences)

    def build_metrics(
        self,
        *,
        answer: str,
        hits: list[SearchHit],
        reference_answer: str | None = None,
    ) -> dict:
        scores = [hit.score for hit in hits]
        source_texts = [hit.chunk.text for hit in hits]
        support = self.answer_support_ratio(answer, source_texts)
        reference = (
            self.reference_similarity(answer, reference_answer)
            if reference_answer and reference_answer.strip()
            else None
        )
        top = max(scores) if scores else 0.0
        avg = sum(scores) / len(scores) if scores else 0.0
        source_count = len({hit.chunk.document_name for hit in hits})

        if not hits or support < 0.35:
            verdict = "확인 필요"
        elif support < 0.65 or top < 0.05:
            verdict = "주의"
        else:
            verdict = "통과"

        return {
            "retrieval_count": len(hits),
            "top_similarity": round(top, 4),
            "avg_similarity": round(avg, 4),
            "source_document_count": source_count,
            "answer_support_ratio": round(support, 4),
            "hallucination_risk": round(1.0 - support, 4),
            "reference_similarity": None if reference is None else round(reference, 4),
            "verdict": verdict,
        }


class BoardRagService:
    """Search policy documents, generate an answer, and score the result."""

    def __init__(
        self,
        *,
        index: SearchIndex,
        generator: AnswerGenerator | None = None,
        evaluator: QualityEvaluator | None = None,
    ) -> None:
        self.index = index
        self.generator = generator or ExtractiveAnswerGenerator()
        self.evaluator = evaluator or QualityEvaluator()

    def answer(
        self,
        question: str,
        *,
        k: int = 5,
        reference_answer: str | None = None,
    ) -> AnswerResult:
        clean_question = (question or "").strip()
        if not clean_question:
            return AnswerResult(answer="", sources=[], metrics={}, mode="rag")

        backend = getattr(self.index, "backend", "")
        hits = self.index.search(clean_question, k=k, min_score=0.01)
        answer = self.generator.generate(clean_question, hits)
        metrics = self.evaluator.build_metrics(
            answer=answer,
            hits=hits,
            reference_answer=reference_answer,
        )
        sources = [
            {
                "text": hit.chunk.text,
                "source": hit.chunk.source_label,
                "score": round(hit.score, 4),
                "document": hit.chunk.document_name,
                "page": hit.chunk.page,
            }
            for hit in hits
        ]
        return AnswerResult(
            answer=answer,
            sources=sources,
            metrics=metrics,
            mode="rag",
            retrieval_backend=backend,
            retrieval_backend_label=retrieval_backend_label(backend),
        )


class IndexStore:
    """JSON persistence for standalone board chunks."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, chunks: list[PolicyChunk]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "chunks": [asdict(chunk) for chunk in chunks],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> list[PolicyChunk]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        chunks = []
        for item in payload.get("chunks", []):
            chunks.append(
                PolicyChunk(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    document_name=str(item["document_name"]),
                    chunk_index=int(item["chunk_index"]),
                    page=item.get("page"),
                )
            )
        return chunks


def suggest_questions(documents: list[PolicyDocument], *, limit: int = 8) -> list[str]:
    """Generate deterministic FAQ-style questions from policy text."""

    text = "\n".join(doc.text for doc in documents)
    rules = [
        (r"대상|자격|나이|연령|소득|조건", "신청 대상과 자격 조건은 어떻게 되나요?"),
        (r"금액|지원 내용|한도|개월|기간", "지원 금액과 지원 기간은 어떻게 되나요?"),
        (r"신청 방법|접수|방문|온라인|누리집", "어디에서 어떤 절차로 신청하나요?"),
        (r"서류|제출|증빙|계약서|통장", "신청할 때 필요한 서류는 무엇인가요?"),
        (r"신청 기간|마감|예산 소진|모집", "신청 기간과 마감 조건은 어떻게 되나요?"),
        (r"제외|불가|유의|주의|환수", "지원 제외 대상이나 유의 사항은 무엇인가요?"),
        (r"대리|보호자|자녀|가족", "가족이나 보호자가 대신 신청할 수 있나요?"),
        (r"사용처|바우처|포인트|카드", "지원금은 어디에서 어떻게 사용할 수 있나요?"),
    ]

    questions: list[str] = []
    for pattern, question in rules:
        if re.search(pattern, text):
            questions.append(question)
        if len(questions) >= limit:
            return questions

    fallback = [
        "이 정책의 핵심 지원 내용은 무엇인가요?",
        "누가 이 정책을 신청할 수 있나요?",
        "신청 방법과 준비물은 무엇인가요?",
        "주의해야 할 제외 조건은 무엇인가요?",
    ]
    for question in fallback:
        if question not in questions:
            questions.append(question)
        if len(questions) >= limit:
            break
    return questions
