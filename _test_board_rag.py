# -*- coding: utf-8 -*-
"""_test_board_rag.py — 게시판 RAG 통합(standalone_board 위임) 회귀.

board_engine.answer_with_rag 가 standalone_board 엔진에 위임하도록 구현된 뒤의
계약·폴백·캐시·키경로를 검증한다. 전부 키리스 또는 모킹으로 강제 → 실 API 0.

    python _test_board_rag.py
"""
import logging
import os

import board_engine as be

# 테스트는 의도적으로 RAG 실패를 유발한다 → board_engine 의 예외 로그 traceback 을 끈다.
logging.getLogger("board_engine").setLevel(logging.CRITICAL)


POLICY = (
    "[청년 월세 한시 특별지원]\n"
    "만 19~34세 무주택 청년에게 월 최대 20만 원을 최대 12개월 지원합니다.\n"
    "신청 방법: 복지로 누리집 또는 거주지 행정복지센터 방문. "
    "임대차계약서, 소득 증빙 서류, 통장 사본 제출.\n"
    "유의 사항: 주택 소유자, 공공임대주택 거주자는 제외됩니다."
)

FAILS = []


def check(cond, label):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


def test_keyless_contract_and_fallbacks():
    """키리스(로컬 해시 + 추출식) 경로의 계약·폴백·디스패치."""
    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-your-key-rag-test"
    try:
        # 가드: 센티넬이 키리스를 실제로 강제하는지 단언(실 API 누출 차단).
        from standalone_board.openai_adapter import has_openai_key
        check(has_openai_key() is False, "키리스 센티넬 동작(실 API 누출 차단)")

        # 1) 빈 정책 → RuntimeError(RAG 근거 없음) → answer_question 이 mock 폴백
        raised = False
        try:
            be.answer_with_rag("   ", "질문")
        except RuntimeError:
            raised = True
        check(raised, "빈 정책 → RuntimeError (RAG 근거 없음)")
        check(
            be.answer_question("", "서류 알려주세요", mode="rag")["mode"] == "mock",
            "빈 정책 + rag 강제 → mock 폴백(앱 안 죽음)",
        )

        # 2) 키리스 RAG 답변 = 추출식. mock 전용 _DISCLAIMER 가 중복으로 안 붙어야 함.
        out = be.answer_with_rag(POLICY, "신청 서류가 무엇인가요?", k=4)
        check("복지로 누리집에서 확인해 주세요" not in out["answer"],
              "mock 전용 _DISCLAIMER 가 RAG 답변에 중복 안 됨")
        check(bool(out["answer"]) and bool(out["sources"]),
              "RAG 답변·근거 비지 않음")
        check(all({"text", "source"} <= set(s) for s in out["sources"]),
              "sources {text, source} 계약")

        # 3) auto + MIRILAB_BOARD_RAG=1 → 실제 RAG 라우팅(실 앱 경로)
        os.environ["MIRILAB_BOARD_RAG"] = "1"
        check(be.answer_question(POLICY, "신청 방법 알려주세요", mode="auto")["mode"] == "rag",
              "auto + MIRILAB_BOARD_RAG 플래그 → RAG 라우팅")
        os.environ.pop("MIRILAB_BOARD_RAG", None)

        # 4) k 반영 — 작은 k 면 sources 개수가 k 이하
        few = be.answer_with_rag(POLICY, "지원 내용", k=2)
        check(len(few["sources"]) <= 2, f"k=2 → sources <= 2 (실제 {len(few['sources'])})")

    finally:
        os.environ.pop("MIRILAB_BOARD_RAG", None)
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved


def test_keyed_path_mocked():
    """키 있는 경로(OpenAIAnswerGenerator 선택 + sources 매핑)를 실 API 없이 검증.

    비-센티넬 가짜 키로 has_openai_key()=True 를 만들고 build_retrieval_index 와
    OpenAIAnswerGenerator 를 모킹해 네트워크를 0 으로 둔다.
    """
    import standalone_board.core as core
    import standalone_board.openai_adapter as oa

    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-test-fake-not-sentinel"  # has_openai_key()=True
    orig_bri, orig_gen = oa.build_retrieval_index, oa.OpenAIAnswerGenerator
    be._RAG_INDEX_CACHE.clear()

    def fake_bri(chunks, **kw):  # 로컬 인덱스(네트워크 0)
        idx = core.VectorIndex()
        idx.add_chunks(chunks)
        return idx

    class FakeOpenAIGen:
        name = "fake-openai-grounded"

        def generate(self, question, hits):
            return "GROUNDED:: " + (hits[0].chunk.text if hits else "no-hit")

    oa.build_retrieval_index = fake_bri
    oa.OpenAIAnswerGenerator = FakeOpenAIGen
    try:
        check(oa.has_openai_key() is True, "가짜 키가 '있는 키'로 인식됨")
        res = be.answer_with_rag(POLICY, "신청 서류는 무엇인가요?", k=4)
    finally:
        oa.build_retrieval_index, oa.OpenAIAnswerGenerator = orig_bri, orig_gen
        be._RAG_INDEX_CACHE.clear()
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved

    check(res["answer"].startswith("GROUNDED::"), "키 있으면 OpenAIAnswerGenerator 선택됨")
    check(all({"text", "source"} <= set(s) for s in res["sources"]),
          "키 경로 sources {text, source} 매핑")


def test_index_cache_reuses_same_policy():
    """같은 정책에 질문 2개 → 인덱스 빌드(임베딩)는 1회만(캐시 회귀 가드)."""
    import standalone_board.core as core
    import standalone_board.openai_adapter as oa

    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-your-key-cache-test"  # 키리스
    orig_bri = oa.build_retrieval_index
    be._RAG_INDEX_CACHE.clear()
    be._RAG_INDEX_ORDER.clear()
    calls = {"n": 0}

    def counting_bri(chunks, **kw):
        calls["n"] += 1
        idx = core.VectorIndex()
        idx.add_chunks(chunks)
        return idx

    oa.build_retrieval_index = counting_bri
    try:
        be.answer_with_rag(POLICY, "신청 서류는?", k=4)
        be.answer_with_rag(POLICY, "신청 방법은?", k=4)  # 같은 정책, 다른 질문
    finally:
        oa.build_retrieval_index = orig_bri
        be._RAG_INDEX_CACHE.clear()
        be._RAG_INDEX_ORDER.clear()
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved

    check(calls["n"] == 1, f"같은 정책 2질문 → 인덱스 빌드 1회 (실제 {calls['n']})")


def test_empty_sources_falls_back_to_mock():
    """검색이 근거 0건이면 answer_with_rag 가 RuntimeError → mock 폴백(빈 인덱스로 결정론).

    실제 로컬 해시는 해시 충돌로 무관한 질문에도 미세 점수를 줄 수 있어, 빈 인덱스를
    주입해 '근거 0건' 을 결정론적으로 만든다.
    """
    import standalone_board.core as core

    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-your-key-empty-test"  # 키리스
    orig = be._rag_index
    be._rag_index = lambda policy, has_key: core.VectorIndex()  # 청크 0 → 검색 0건
    try:
        raised = False
        try:
            be.answer_with_rag(POLICY, "신청 서류는?", k=4)
        except RuntimeError:
            raised = True
        check(raised, "빈 검색결과 → answer_with_rag RuntimeError")

        res = be.answer_question(POLICY, "신청 서류는?", mode="rag")
        check(res["mode"] == "mock", "빈 검색결과 → mock 폴백(빈약한 RAG 답 회피)")
        check(bool(res["sources"]), "폴백 답변은 근거 1개 이상 제시")
    finally:
        be._rag_index = orig
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved


def main():
    test_keyless_contract_and_fallbacks()
    test_empty_sources_falls_back_to_mock()
    test_keyed_path_mocked()
    test_index_cache_reuses_same_policy()

    print()
    if FAILS:
        print(f"FAILED: {FAILS}")
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
