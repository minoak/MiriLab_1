# -*- coding: utf-8 -*-
"""_test_board_tab_app.py — 게시판 풀 RAG 탭(AppTest) 스모크.

_preview_board.py 를 키리스로 (1) 렌더 (2) 질문 등록까지 굴려, 검색→추출식 답변→
스레드(품질지표·근거) 렌더가 예외 없이 도는지 확인한다. 키리스라 임베딩/OpenAI
호출은 0(로컬 해시 + 추출식). python _test_board_tab_app.py
"""
import os
import sys

# 키리스 강제(실 API 0). standalone has_openai_key()=False.
os.environ["OPENAI_API_KEY"] = "sk-your-key-tabtest-keyless"

from streamlit.testing.v1 import AppTest

from standalone_board.app import QUESTION_KEY, THREADS_KEY

FAILS = []


def check(cond, label):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


def main():
    at = AppTest.from_file("_preview_board.py", default_timeout=120)
    at.run()

    # 1) 초기 렌더 ------------------------------------------------------
    check(not at.exception, f"게시판 탭 렌더 예외 0 ({[str(e.value)[:120] for e in at.exception]})")
    subs = [s.value for s in at.subheader]
    check(any("정책 문의 게시판" in s for s in subs), "게시판 subheader 렌더")
    check(any("답변 생성" in (r.label or "") for r in at.radio), "답변 생성 모드 라디오 렌더")

    # 2) 질문 등록 → 검색·추출식 답변·스레드 렌더 ----------------------
    at.text_area(key=QUESTION_KEY).set_value("신청할 때 필요한 서류는 무엇인가요?")
    clicked = False
    for b in at.button:
        if b.label == "질문 등록":
            b.click()
            clicked = True
            break
    check(clicked, "'질문 등록' 버튼 존재(정책 인덱싱돼 활성)")
    at.run()

    check(not at.exception, f"질문 등록 후 예외 0 ({[str(e.value)[:120] for e in at.exception]})")
    threads = list(at.session_state[THREADS_KEY]) if THREADS_KEY in at.session_state else []
    check(len(threads) == 1, f"스레드 1건 누적 (실제 {len(threads)})")
    if threads:
        t = threads[0]
        check(bool(t.get("answer")), "답변 본문 생성됨")
        check(bool(t.get("sources")), "근거 1건 이상")
        check("verdict" in (t.get("metrics") or {}), "품질지표 계산됨(verdict)")
    check(any("게시글 답변" in s for s in [x.value for x in at.subheader]),
          "스레드 영역('게시글 답변') 렌더")

    # 3) 정책 변경 → 옛 정책 기준 스레드 자동 정리(스테일 답변 방지) -------
    sels = [s for s in at.selectbox if (s.label or "") == "정책 선택"]
    if sels and len(list(sels[0].options)) > 1:
        sb = sels[0]
        other = next(o for o in sb.options if o != sb.value)
        sb.set_value(other)
        at.run()
        after = list(at.session_state[THREADS_KEY]) if THREADS_KEY in at.session_state else []
        check(len(after) == 0, f"정책 변경 → 스레드 자동 정리 (실제 {len(after)})")
        check(not at.exception, "정책 변경 후 예외 0")
    else:
        check(True, "정책 후보 1개 — 변경 테스트 생략")

    print()
    if FAILS:
        print(f"FAILED: {FAILS}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
