# -*- coding: utf-8 -*-
"""정책 인생극장 실모드 검증 (실제 OpenAI LLM). 3명×3턴 = 9콜.

정책 패키지를 주입했을 때 LLM 이 세 인물의 삶을 실제로 다르게 그리는지 본다.
실행: python _verify_real.py   (.env 에 OPENAI_API_KEY 필요)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from data.personas import load_personas
from sample_policies import PACKAGES
from contrast import run_contrast
from graph.spaces import place_label, status_label

PKG = "디지털 복지 3종 (소득·세대로 갈림)"

personas = load_personas(n=8, seed=42)
print(f"실모드 시뮬 시작 — 패키지: {PKG} (3명 × 3턴 = 9콜)\n")

res = run_contrast(personas, PACKAGES[PKG], simulate=None,  # None → 실제 simulate_village
                   grounded=True, use_llm_spec=False)

# 선별 요약
print("정책:", " + ".join(s["name"] for s in res["specs"]))
print("-" * 80)
for t in res["selection"]["trio"]:
    p = t["persona"]; d = p.get("demographics", {})
    print(f"  ★{t['role']:<5} {p['name']}({d.get('age')}세 {d.get('occupation','')}) — {t['headline']}")
print("=" * 80)

# 실제 LLM 이 그린 3인 인생 궤적(서사 포함)
for r in res["village"]["residents"]:
    print(f"\n▣ {r['name']}  (최종: {status_label(r['policy_status'])} · "
          f"경제 {r['economic']} · 만족 {r['wellbeing']})")
    for s in r["timeline"]:
        print(f"  [{s['label']}] {place_label(s['place'])} · {status_label(s['policy_status'])} "
              f"(경제{s['economic']} 만족{s['wellbeing']})")
        print(f"    {s['action']}")
