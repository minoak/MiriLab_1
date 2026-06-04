# -*- coding: utf-8 -*-
"""OpenAI adapters for standalone board RAG.

Imports are lazy so the pure board package can run without an API key.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .core import SearchHit


load_dotenv()

CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
            "2. 필요한 경우 bullet로 대상/금액/방법/서류/제외 조건을 정리한다.\n"
            "3. 마지막에 '근거 문서 기준이며, 최종 확인은 담당 기관에 문의하세요.'를 붙인다."
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
