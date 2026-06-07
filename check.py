# -*- coding: utf-8 -*-
"""OpenAI environment check.

This module is safe to import from tests. The network check only runs from
``main()`` when the file is executed directly.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def has_real_key(key: str | None) -> bool:
    return bool(key and not key.startswith("sk-your-key"))


def _is_reasoning_model(model: str) -> bool:
    normalized = (model or "").lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))


def build_response_kwargs(model: str) -> dict:
    """Build a small Responses API request for an environment smoke check."""
    kwargs = {
        "model": model,
        "input": "Reply with the single word: OK",
        "max_output_tokens": 128,
    }
    if _is_reasoning_model(model):
        kwargs["reasoning"] = {"effort": "minimal"}
    return kwargs


def validate_reply(reply: str) -> str:
    clean = (reply or "").strip()
    if not clean:
        raise ValueError("OpenAI returned an empty reply")
    return clean


def main() -> int:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")

    if not has_real_key(key):
        print("[FAIL] OPENAI_API_KEY is not set.")
        print("       -> Copy .env.example to .env and paste your key into it.")
        return 1

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        response = client.responses.create(**build_response_kwargs(model))
        reply = validate_reply(getattr(response, "output_text", ""))
        print("[OK] Environment ready. model=" + model + "  reply=" + reply)
        return 0
    except Exception as exc:
        print("[FAIL] OpenAI call failed: " + repr(exc))
        print("       -> Check your key, billing, and internet connection.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
