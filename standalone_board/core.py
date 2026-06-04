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


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_SENTENCE_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
_STOPWORDS = {
    "그리고", "그러나", "또는", "및", "으로", "에서", "에게", "하는", "합니다",
    "있습니다", "됩니다", "대한", "관련", "무엇", "어떻게", "언제", "어디",
    "신청", "지원", "정책",
}


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


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> list[float]:
        ...


class AnswerGenerator(Protocol):
    name: str

    def generate(self, question: str, hits: list[SearchHit]) -> str:
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


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


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


def _chunk_page(
    *,
    document_name: str,
    page: int | None,
    text: str,
    start_index: int,
    max_chars: int,
    overlap_chars: int,
) -> list[PolicyChunk]:
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
        self._chunks: list[PolicyChunk] = []
        self._vectors: list[list[float]] = []

    @property
    def chunks(self) -> list[PolicyChunk]:
        return list(self._chunks)

    def clear(self) -> None:
        self._chunks.clear()
        self._vectors.clear()

    def add_chunks(self, chunks: Iterable[PolicyChunk]) -> None:
        for chunk in chunks:
            self._chunks.append(chunk)
            self._vectors.append(self.embedder.embed(chunk.text))

    def search(self, query: str, *, k: int = 5, min_score: float = 0.0) -> list[SearchHit]:
        qvec = self.embedder.embed(query)
        hits = [
            SearchHit(chunk=chunk, score=_cosine(qvec, vector))
            for chunk, vector in zip(self._chunks, self._vectors)
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        filtered = [h for h in hits if h.score >= min_score]
        return filtered[: max(0, k)]


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
            if len(set(_token_features(s))) >= 2 and not _is_metric_boilerplate(s)
        ]
        if not sentences:
            return 0.0
        source_features = [set(_token_features(src)) for src in source_texts]
        if not source_features:
            return 0.0

        supported = 0
        for sentence in sentences:
            tokens = set(_token_features(sentence))
            if not tokens:
                continue
            best = max(
                (len(tokens & src_tokens) / len(tokens) for src_tokens in source_features),
                default=0.0,
            )
            if best >= 0.35:
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
            verdict = "실패"
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
        index: VectorIndex,
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
