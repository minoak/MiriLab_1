# -*- coding: utf-8 -*-
"""종합 리포트 실키 스모크 — 실제 OpenAI 1콜로 LLM 4칸 경로를 end-to-end 확인.

    python _smoke_report_real.py

mock 시뮬 데이터(12명 + 인생극장 결과)를 재료로 generate_report(use_llm=True)를
1회 호출한다. .env 의 실키 사용(~1센트 미만). 키가 없으면 폴백으로 통과만 확인.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from report import generate_report
from ui.mock import sample_simstate, sample_village
from ui.model import build_view
from contrast import select_trio_from_outcomes
from graph.llm import has_real_key

view = build_view(sample_simstate())
village = sample_village(view["personas"], view["policy"])
view["selection"] = select_trio_from_outcomes(village["residents"], view["personas"], specs=[])
view["village"] = village

print(f"실키 존재: {has_real_key()}")
out = generate_report(view, use_llm=True)
print(f"mode = {out['mode']}")

md = out["markdown"]
for h in ("## 1. 요약", "## 2. 시민 반응 진단", "## 3. 접근 여정 사례",
          "## 4. 개선 제안", "## 5. 수정안 전문", "## 6. 한계 노트"):
    assert h in md, f"양식 절 누락: {h}"
if has_real_key():
    assert out["mode"] == "llm", "키가 있는데 LLM 모드가 아님"

print(f"\n--- 리포트 ({len(md)}자) ---\n")
print(md)
