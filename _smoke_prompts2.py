# -*- coding: utf-8 -*-
"""_smoke_prompts2.py — interact/village/aggregate 재설계 키리스 스모크."""
import sys
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

import py_compile
for f in ("prompts.py", "graph/nodes.py"):
    py_compile.compile(str(ROOT / f), doraise=True)
print("compile OK")

from data.personas import load_personas
from prompts import (
    build_interact_messages, build_village_messages,
    build_aggregate_messages, _persona_card_brief,
)

ps = load_personas(8, 42)
p = ps[0]

# --- interact ---
m = build_interact_messages(
    p, "[정책]\n" + "내용 " * 100, "- 홍길동(찬성): 좋네요",
    own={"stance": "mixed", "text": "글쎄요 잘 모르겠는데"},
)
u = m[1]["content"]
assert "[당신이 먼저 단 댓글]" in u and "글쎄요" in u, "자기반응 블록 누락"
policy_part = u.split("[정책 글]")[1].split("[당신이")[0]
assert policy_part.count("내용") == 100, "정책 절단 잔존"
assert "[이 사람]" in u
# own 없이도 동작(하위호환)
m0 = build_interact_messages(p, "정책", "")
assert "[당신이 먼저 단 댓글]" not in m0[1]["content"]
print("interact OK — 자기반응/정책전문/축약카드/하위호환")
print("--- 축약카드 ---")
print(_persona_card_brief(p))

# --- village ---
mv = build_village_messages(
    p, "정책", "", "시행 1개월 후", grounded=True, space_menu="- home: 집",
    reaction={"stance": "support", "text": "오 좋다",
              "scores": {"benefit": 80}, "actions": ["신청"]},
)
sv, uv = mv[0]["content"], mv[1]["content"]
assert "정부 신뢰" not in sv and "정부 신뢰" not in uv, "죽은 참조 잔존"
assert "반신반의" not in uv, "government_trust 문장 잔존"
assert "관찰 기록자" in sv and "■ 살아온 배경" in uv
assert "★" not in uv, "패치 마커 잔존"
mv2 = build_village_messages(p, "정책", "", "1개월", grounded=False)
assert "살아온 배경" not in mv2[1]["content"], "ablation에 카드 샘"
print("village OK — 풀카드/죽은참조·패치 제거/ablation 분기")

# --- aggregate ---
ma = build_aggregate_messages("정책", {"a": 1}, "요약")
ua = ma[1]["content"]
assert "대상 기준 혼란" not in ua and "균형 있게" not in ua
print("aggregate OK — 선지정/균형 제거")

print("\nALL PASS")
