# -*- coding: utf-8 -*-
"""check.py regression tests that avoid real OpenAI calls."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_check_module_has_main_guard():
    source = Path("check.py").read_text(encoding="utf-8")

    assert 'if __name__ == "__main__"' in source
    print("ok  check.py import guard")


def test_check_uses_responses_api_for_reasoning_models():
    source = Path("check.py").read_text(encoding="utf-8")

    assert "client.responses.create" in source
    print("ok  check.py responses API")


def test_check_request_uses_current_output_token_parameter():
    check = importlib.import_module("check")
    kwargs = check.build_response_kwargs("gpt-5-nano")

    assert kwargs["max_output_tokens"] >= 128
    assert "max_completion_tokens" not in kwargs
    assert "max_tokens" not in kwargs
    print("ok  check.py output token parameter")


def test_check_request_uses_minimal_reasoning_for_gpt5():
    check = importlib.import_module("check")
    kwargs = check.build_response_kwargs("gpt-5-nano")

    assert kwargs["reasoning"] == {"effort": "minimal"}
    print("ok  check.py GPT-5 reasoning effort")


def test_check_request_omits_reasoning_for_non_reasoning_models():
    check = importlib.import_module("check")
    kwargs = check.build_response_kwargs("gpt-4o-mini")

    assert "reasoning" not in kwargs
    print("ok  check.py non-reasoning model request")


def test_validate_reply_rejects_empty_model_response():
    check = importlib.import_module("check")

    try:
        check.validate_reply("")
    except ValueError:
        pass
    else:
        raise AssertionError("empty model replies must fail the environment check")
    print("ok  check.py empty reply validation")


def main():
    test_check_module_has_main_guard()
    test_check_uses_responses_api_for_reasoning_models()
    test_check_request_uses_current_output_token_parameter()
    test_check_request_uses_minimal_reasoning_for_gpt5()
    test_check_request_omits_reasoning_for_non_reasoning_models()
    test_validate_reply_rejects_empty_model_response()
    print("\ncheck.py tests passed")


if __name__ == "__main__":
    main()
