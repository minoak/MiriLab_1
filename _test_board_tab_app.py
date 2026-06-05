# -*- coding: utf-8 -*-
"""_test_board_tab_app.py — 게시판 풀 RAG 탭(AppTest) 스모크.

_preview_board.py 를 키리스로 렌더만 해 예외 없이 그려지는지 확인한다. 질문을
등록하지 않으므로 임베딩/OpenAI 호출은 0(렌더 = 청크 분할까지만).

    python _test_board_tab_app.py
"""
import os
import sys

# 키리스 강제(실 API 0). standalone has_openai_key()=False.
os.environ["OPENAI_API_KEY"] = "sk-your-key-tabtest-keyless"

from streamlit.testing.v1 import AppTest


def main():
    at = AppTest.from_file("_preview_board.py", default_timeout=60)
    at.run()

    fails = []

    if at.exception:
        fails.append(f"예외: {[str(e.value)[:150] for e in at.exception]}")
    print(f"[{'PASS' if not at.exception else 'FAIL'}] 게시판 탭 렌더 예외 0")

    subs = [s.value for s in at.subheader]
    has_board = any("정책 문의 게시판" in s for s in subs)
    if not has_board:
        fails.append(f"게시판 subheader 없음: {subs}")
    print(f"[{'PASS' if has_board else 'FAIL'}] 게시판 subheader 렌더")

    # 라디오(답변 생성 모드)가 그려졌는지 — 질문 영역이 살아 있음을 의미
    radios = [r.label for r in at.radio]
    has_mode = any("답변 생성" in (lbl or "") for lbl in radios)
    print(f"[{'PASS' if has_mode else 'FAIL'}] 답변 생성 모드 라디오 렌더 (radios={radios})")
    if not has_mode:
        fails.append("답변 생성 라디오 없음")

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
