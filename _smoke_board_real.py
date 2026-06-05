# -*- coding: utf-8 -*-
"""_smoke_board_real.py — 실 OpenAI 키로 게시판 RAG 1질문 end-to-end 스모크.

⚠️ 실제 OpenAI API 를 호출한다(임베딩 + Responses, ~$0.001). .env 실키 사용.
회귀 테스트(키리스/모킹)가 못 치는 '키 있는 경로'를 한 번 실측한다.

    python _smoke_board_real.py
"""
import board_engine as be
from standalone_board.openai_adapter import has_openai_key

POLICY = (
    "[청년 월세 한시 특별지원]\n"
    "만 19~34세 무주택 청년에게 월 최대 20만 원을 최대 12개월 지원합니다.\n"
    "신청 방법: 복지로 누리집 또는 거주지 행정복지센터 방문. "
    "임대차계약서, 소득 증빙 서류, 통장 사본 제출.\n"
    "유의 사항: 주택 소유자, 공공임대주택 거주자는 제외됩니다."
)

print("OpenAI 키 감지:", has_openai_key())
if not has_openai_key():
    raise SystemExit("실키가 없습니다(.env 확인). 스모크 생략.")

q = "신청할 때 필요한 서류가 무엇인가요?"
res = be.answer_with_rag(POLICY, q, k=4)

print("\n[질문]", q)
print("\n[답변]\n" + res["answer"])
print("\n[근거]", len(res["sources"]), "건")
for s in res["sources"]:
    print(" -", s.get("source", ""), "::", (s.get("text", "")[:70]))
print("\nSMOKE OK")
