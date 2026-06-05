# -*- coding: utf-8 -*-
"""OpenAI adapters for standalone board RAG.

Imports are lazy so the pure board package can run without an API key.
"""

from __future__ import annotations

<<<<<<< HEAD
import logging
=======
>>>>>>> 740a98d076fc5e9021ac80ea286f72d1de3f9d95
import os
from typing import Callable, Iterable

from dotenv import load_dotenv

from .core import ChromaVectorIndex, Embedder, PolicyChunk, SearchHit, SearchIndex, VectorIndex


<<<<<<< HEAD
# override=False 필수: 회귀 테스트가 'sk-your-key' 센티넬을 환경변수에 미리 박아
# 키리스를 강제한다. override=True 로 바꾸면 .env 의 실키가 센티넬을 덮어 키리스
# 테스트가 실 OpenAI API 를 치고 과금된다 — 절대 True 로 바꾸지 말 것.
load_dotenv(override=False)
=======
load_dotenv()
>>>>>>> 740a98d076fc5e9021ac80ea286f72d1de3f9d95

CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
SYSTEM_INSTRUCTIONS = (
    "너는 한국어 정책 문의 게시판의 사실 기반 답변 도우미다. "
    "반드시 제공된 근거 문서 안에서만 답한다. 근거에 없는 내용은 "
    "'근거 문서에서 확인되지 않습니다'라고 말한다. 숫자, 기간, 대상, "
    "제외 조건은 근거 표현을 유지한다. 추측하지 않는다."
)


def has_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "")
    return bool(key and not key.startswith("sk-your-key"))


def is_reasoning_model(model: str) -> bool:
    return (model or "").startswith(REASONING_PREFIXES)


def build_answer_response_kwargs(
    model: str,
    question: str,
    hits: list[SearchHit],
) -> dict:
    evidence = "\n\n".join(
        f"[{i}] {hit.chunk.source_label} (score={hit.score:.4f})\n{hit.chunk.text}"
        for i, hit in enumerate(hits, start=1)
    )
    kwargs = {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": (
            f"질문:\n{question}\n\n"
            f"근거 문서:\n{evidence}\n\n"
            "답변 형식:\n"
            "1. 결론을 1~2문장으로 답한다.\n"
            "2. 필요한 경우 bullet로 대상/금액/지원 기간/신청 기간/방법/서류/제외 조건을 정리한다.\n"
            "3. 지원 기간과 신청 기간은 서로 다른 항목으로 분리한다. "
            "예: 지원 기간은 돈을 받을 수 있는 기간이고, 신청 기간은 접수 가능 기간이다.\n"
            "4. 마지막에 '근거 문서 기준이며, 최종 확인은 담당 기관에 문의하세요.'를 붙인다."
        ),
        "max_output_tokens": 900,
    }
    if is_reasoning_model(model):
        kwargs["reasoning"] = {"effort": "minimal"}
    return kwargs


def validate_answer_text(answer: str | None) -> str:
    clean = (answer or "").strip()
    if not clean:
        raise RuntimeError("OpenAI returned an empty answer.")
    return clean


class OpenAIEmbeddingEmbedder:
    """OpenAI embedding adapter used by Chroma semantic retrieval."""

    name = "openai-embedding"

    def __init__(
        self,
        *,
        model: str = EMBEDDING_MODEL,
        client=None,
    ) -> None:
        self.model = model
        self._client = client

    def _openai_client(self):
        if self._client is None:
            if not has_openai_key():
                raise RuntimeError("OPENAI_API_KEY가 없어 OpenAI 임베딩을 실행할 수 없습니다.")
            from openai import OpenAI

            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client

    def embed(self, text: str) -> list[float]:
        vectors = self.embed_many([text])
        return vectors[0] if vectors else []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        inputs = [(text or "").strip() or " " for text in texts]
        resp = self._openai_client().embeddings.create(
            model=self.model,
            input=inputs,
            encoding_format="float",
        )
        return [list(item.embedding) for item in resp.data]


def build_retrieval_index(
    chunks: Iterable[PolicyChunk],
    *,
    embedding_factory: Callable[[], Embedder] | None = None,
    prefer_openai: bool = True,
) -> SearchIndex:
    """Build the best available board retrieval index.

    With an API key, policy chunks are embedded through OpenAI and stored in an
    ephemeral Chroma collection.  If embeddings or Chroma fail, the deterministic
    local hashing vector index remains the keyless fallback.
    """

    items = list(chunks)
    if prefer_openai and (embedding_factory is not None or has_openai_key()):
        try:
            embedder = embedding_factory() if embedding_factory else OpenAIEmbeddingEmbedder()
            index = ChromaVectorIndex(embedder=embedder)
            index.add_chunks(items)
            return index
<<<<<<< HEAD
        except Exception as exc:
            # 키/쿼터/Chroma 문제로 의미검색 빌드 실패 → 로컬 해시 검색으로 폴백한다.
            # 앱은 살리되, 무엇이 실패했는지 알 수 있게 경고만 남긴다(키 값은 안 찍음).
            logging.getLogger(__name__).warning(
                "OpenAI/Chroma 인덱스 빌드 실패 → 로컬 해시 검색 폴백: %s", exc
            )
=======
        except Exception:
            pass
>>>>>>> 740a98d076fc5e9021ac80ea286f72d1de3f9d95

    index = VectorIndex()
    index.add_chunks(items)
    return index


class OpenAIAnswerGenerator:
    name = "openai-grounded"

    def __init__(self, *, model: str = CHAT_MODEL) -> None:
        self.model = model

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        if not has_openai_key():
            raise RuntimeError("OPENAI_API_KEY가 없어 OpenAI 답변 생성을 실행할 수 없습니다.")
        if not hits:
            return (
                "업로드된 정책 문서에서 질문과 직접 관련된 근거를 찾지 못했습니다. "
                "근거가 확인되는 문서를 추가해 주세요."
            )

        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.responses.create(
            **build_answer_response_kwargs(self.model, question, hits)
        )
        return validate_answer_text(resp.output_text)
