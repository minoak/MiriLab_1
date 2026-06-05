# -*- coding: utf-8 -*-
"""Streamlit app regression tests for the board tab interaction.

Run:
    python _test_board_app.py
"""

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest


def _session_get(at: AppTest, key: str, default=None):
    return at.session_state[key] if key in at.session_state else default


def _set_demo_mode(at: AppTest) -> None:
    for checkbox in at.checkbox:
        if "데모" in (checkbox.label or ""):
            checkbox.set_value(True)


def _click_simulation(at: AppTest) -> None:
    for button in at.button:
        if "시뮬레이션 실행" in (button.label or ""):
            button.click()
            return
    raise AssertionError("시뮬레이션 실행 버튼을 찾지 못했습니다.")


def _select_main_tab(at: AppTest, label: str) -> None:
    for radio in at.radio:
        if radio.key == "main_tab":
            radio.set_value(label)
            return
    raise AssertionError("상태 저장형 메인 탭 선택 위젯을 찾지 못했습니다.")


def _question_widgets(at: AppTest):
    return [
        text_area
        for text_area in at.text_area
        if str(text_area.key).startswith("board_question_content_")
    ]


def test_board_suggestion_keeps_board_screen_after_rerun():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception, at.exception

    _set_demo_mode(at)
    _click_simulation(at)
    at.run()
    assert not at.exception, at.exception

    _select_main_tab(at, "게시판")
    at.run()
    assert not at.exception, at.exception
    assert _session_get(at, "main_tab") == "게시판"

    for button in at.button:
        if button.key == "board_suggested_question_0":
            question = button.label
            button.click()
            break
    else:
        raise AssertionError("예상 질문 버튼을 찾지 못했습니다.")

    at.run()
    assert not at.exception, at.exception
    assert _session_get(at, "main_tab") == "게시판"
    widgets = _question_widgets(at)
    assert widgets and widgets[0].value == question

    for button in at.button:
        if "질문 등록" in (button.label or ""):
            button.click()
            break
    else:
        raise AssertionError("질문 등록 버튼을 찾지 못했습니다.")

    at.run()
    assert not at.exception, at.exception
    assert _session_get(at, "main_tab") == "게시판"
    assert len(_session_get(at, "board", [])) == 1
    print("ok  board suggestion keeps board screen")


def main():
    test_board_suggestion_keeps_board_screen_after_rerun()
    print("\nboard app tests passed")


if __name__ == "__main__":
    main()
