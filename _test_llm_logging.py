# -*- coding: utf-8 -*-
"""_test_llm_logging.py — §8-6 cached_tokens 로깅 스모크 (네트워크 0, 가짜 client).

검증:
1) structured_call 경유 시 LLM_USAGE 누적 + 'mirilab.llm' 로거에 usage 레코드.
2) usage 가 없거나 깨져도 본 호출은 무해(_log_usage 가 삼킴).
실행: python _test_llm_logging.py
"""
import logging
import sys
from types import SimpleNamespace

import graph.llm as gl


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def _fake_resp(prompt=100, cached=64, completion=20, with_usage=True):
    usage = SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
    ) if with_usage else None
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed={"ok": True}))],
        usage=usage,
    )


class _FakeClient:
    def __init__(self, resp):
        parse = lambda **kw: resp  # noqa: E731
        self.beta = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(parse=parse)))


def main():
    fails = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    cap = _Capture()
    gl.logger.addHandler(cap)
    gl.logger.setLevel(logging.INFO)
    base = dict(gl.LLM_USAGE)

    # 1) 정상 usage — 누적 + 로그
    gl._clients[gl.PROVIDER] = _FakeClient(_fake_resp())  # get_client 캐시 주입
    out = gl.structured_call([{"role": "user", "content": "x"}], dict)
    check("parsed 반환 유지", out == {"ok": True})
    check("calls 누적 +1", gl.LLM_USAGE["calls"] == base["calls"] + 1)
    check("cached_tokens 누적 +64",
          gl.LLM_USAGE["cached_tokens"] == base["cached_tokens"] + 64)
    check("prompt_tokens 누적 +100",
          gl.LLM_USAGE["prompt_tokens"] == base["prompt_tokens"] + 100)
    check("usage 로그 찍힘(cached 포함)",
          any("cached=64" in m for m in cap.records), f"records={cap.records}")

    # 2) usage 없음 — 본 호출 무해, 누적 불변
    snap = dict(gl.LLM_USAGE)
    gl._clients[gl.PROVIDER] = _FakeClient(_fake_resp(with_usage=False))
    out2 = gl.structured_call([{"role": "user", "content": "x"}], dict)
    check("usage 없어도 parsed 반환", out2 == {"ok": True})
    check("usage 없으면 누적 불변", gl.LLM_USAGE == snap)

    gl._clients.clear()  # 캐시 원복
    gl.logger.removeHandler(cap)

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
