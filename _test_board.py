# -*- coding: utf-8 -*-
"""board_engine 단위 테스트(순수, streamlit 무의존).

    python _test_board.py

답변 엔진의 결정론·반환 계약·RAG 폴백을 검증한다. 화면(tab_board) 없이 로직만 돈다.
"""

import os
import random

import board_engine as be


# 청년 월세 정책 일부 — 문장 분리/매칭 검증용 고정 텍스트.
POLICY = (
    "[청년 월세 한시 특별지원]\n"
    "만 19~34세 무주택 청년 중 부모와 별도 거주하는 자에게 월 최대 20만 원을 "
    "최대 12개월간 지원합니다.\n"
    "신청 대상: 본인 소득이 기준 중위소득 60% 이하인 무주택 청년.\n"
    "신청 방법: 복지로 누리집 또는 거주지 행정복지센터 방문 신청. "
    "임대차계약서, 소득 증빙 서류, 통장 사본 제출 필요.\n"
    "유의 사항: 주택 소유자, 공공임대주택 거주자는 제외됩니다."
)


def test_match_topic():
    # 대상 키워드(누가/나이/조건)가 방법(신청)보다 많아 '대상'으로 판정.
    assert be._match_topic("누가 신청할 수 있나요? 나이 조건이 어떻게 되나요?") == "대상"
    # 서류/제출 → 방법.
    assert be._match_topic("서류는 뭘 제출해야 하나요?") == "방법"
    # 매칭 키워드 없음 → 빈 문자열.
    assert be._match_topic("음 글쎄요 그냥요") == ""
    print("ok  _match_topic")


def test_split_and_pick():
    sents = be._split_sentences(POLICY)
    assert sents, "문장이 하나는 나와야 한다"
    # 제목 줄([청년 월세 …])은 제외된다.
    assert not any(s.startswith("[") for s in sents)

    picked = be._pick_relevant_sentences(POLICY, "서류는 뭘 제출하나요?", k=2)
    assert 0 < len(picked) <= 2
    assert all(isinstance(s, str) for s in picked)
    # 서류 관련 질문이면 '제출/서류'가 든 문장이 잡혀야 한다.
    assert any(("서류" in s or "제출" in s) for s in picked)

    # 빈 정책 → 빈 리스트(방어).
    assert be._pick_relevant_sentences("", "아무거나") == []
    print("ok  _split_sentences / _pick_relevant_sentences")


def test_answer_question_mock():
    res = be.answer_question(POLICY, "신청 자격이 어떻게 되나요?", mode="mock")
    assert set(res) >= {"answer", "sources", "mode"}
    assert res["mode"] == "mock"
    assert res["answer"], "mock 답변은 비어 있으면 안 된다"
    assert isinstance(res["sources"], list) and res["sources"]
    # sources 모양은 RAG 와 동일한 {text, source} 계약.
    assert all({"text", "source"} <= set(s) for s in res["sources"])
    print("ok  answer_question(mock) 반환 계약")


def test_empty_question():
    res = be.answer_question(POLICY, "   ", mode="mock")
    assert res["answer"] == "" and res["sources"] == []
    print("ok  빈 질문 → 빈 답변")


def _force_keyless(fn):
    """OpenAI 키 없는 경로(standalone 로컬 해시 + 추출식)를 강제로 타게 한다.

    standalone has_openai_key() 는 'sk-your-key' 로 시작하면 False 를 반환하고,
    openai_adapter 의 load_dotenv(override=False) 는 이미 설정된 환경변수를 덮지
    않으므로, 이 센티넬을 미리 박아두면 .env 의 실제 키가 무시돼 네트워크 호출이
    일어나지 않는다(단위 테스트 = 실 API 0).
    """
    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-your-key-board-test-keyless"
    try:
        # 가드: 센티넬이 실제로 키리스를 강제하는지 단언한다. 누군가 load_dotenv 를
        # override=True 로 바꿔 .env 실키가 새어들면 여기서 시끄럽게 실패한다(과금 차단).
        from standalone_board.openai_adapter import has_openai_key
        assert has_openai_key() is False, "키리스 센티넬 실패 — 테스트가 실 API 를 칠 위험"
        return fn()
    finally:
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved


def test_rag_seam_returns_contract():
    # 시임이 구현됨 → NotImplementedError 가 아니라 {answer, sources} 를 돌려준다.
    res = _force_keyless(lambda: be.answer_with_rag(POLICY, "신청 서류는 무엇인가요?", k=4))
    assert {"answer", "sources"} <= set(res)
    assert isinstance(res["answer"], str) and res["answer"], "RAG 답변 본문이 있어야 한다"
    assert isinstance(res["sources"], list) and res["sources"], "근거가 비면 안 된다"
    # sources 는 시임 계약 {text, source} 모양으로 축약돼 있어야 한다.
    assert all({"text", "source"} <= set(s) for s in res["sources"])
    # 서류 질문 → 로컬 검색이 관련 근거(서류/계약서/통장)를 끌어와야 한다.
    joined = " ".join(s.get("text", "") for s in res["sources"])
    assert ("서류" in joined or "임대차계약서" in joined or "통장" in joined)
    print("ok  answer_with_rag 구현 계약(키리스 로컬 폴백)")


def test_rag_mode_runs_engine():
    # rag 강제 → 시임이 구현됐으므로 실제 RAG 로 답한다(키리스면 로컬+추출식).
    res = _force_keyless(
        lambda: be.answer_question(POLICY, "신청 방법 알려주세요", mode="rag")
    )
    assert res["mode"] == "rag", "구현된 시임이므로 mode 는 'rag' 여야 한다"
    assert res["answer"] and not res["answer"].startswith("⚠️"), \
        "이제 미연결 안내(⚠️) 없이 실제 답변이 나와야 한다"
    assert all({"text", "source"} <= set(s) for s in res["sources"])
    print("ok  mode='rag' 실제 엔진 동작(키리스 로컬)")


def test_auto_mode_default_mock():
    # 환경변수 없이 auto → mock (데모/키없음 안전).
    saved = os.environ.pop("MIRILAB_BOARD_RAG", None)
    try:
        assert be._rag_enabled() is False
        res = be.answer_question(POLICY, "자격 조건", mode="auto")
        assert res["mode"] == "mock"
        # 플래그를 켜면 _rag_enabled True (그래도 seam 미구현이라 answer_question은 폴백).
        os.environ["MIRILAB_BOARD_RAG"] = "1"
        assert be._rag_enabled() is True
    finally:
        os.environ.pop("MIRILAB_BOARD_RAG", None)
        if saved is not None:
            os.environ["MIRILAB_BOARD_RAG"] = saved
    print("ok  auto 모드 기본 mock + MIRILAB_BOARD_RAG 토글")


def test_make_comments():
    random.seed(42)
    for _ in range(20):
        cs = be.make_comments("질문")
        assert 1 <= len(cs) <= 2
        assert len(set(cs)) == len(cs), "댓글은 중복되지 않아야 한다"
        assert all(c in be._CITIZEN_COMMENTS for c in cs)
    assert be.make_comments(n=0) == []
    assert len(be.make_comments(n=3)) == 3
    print("ok  make_comments 개수/중복/풀")


def main():
    test_match_topic()
    test_split_and_pick()
    test_answer_question_mock()
    test_empty_question()
    test_rag_seam_returns_contract()
    test_rag_mode_runs_engine()
    test_auto_mode_default_mock()
    test_make_comments()
    print("\n전부 통과")


if __name__ == "__main__":
    main()
