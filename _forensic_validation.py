# -*- coding: utf-8 -*-
"""②③ 실패 부검 — 원자료(설문 토큰·자가인식·반응문)에서 원인 찾기. LLM 0콜."""
import json
import sys
import io
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

ab = json.loads((ROOT / "eval" / "ablation_results.json").read_text(encoding="utf-8"))
rb = json.loads((ROOT / "eval" / "robustness_results.json").read_text(encoding="utf-8"))

from data.personas import load_personas, is_target, policy_fit
from sample_policies import SPECS
personas = {p["id"]: p for p in load_personas(24, 42)}
spec = SPECS["청년 월세 한시 특별지원"]

print("=" * 70)
print("[A] ablation ON — 페르소나별: 나이/is_target/fit | 자가인식 | benefit 토큰")
print("=" * 70)
rows_on = [r for r in ab["rows"] if r["cond"] == "on" and r["ok"]]
by_pid = {}
for r in rows_on:
    by_pid.setdefault(r["persona_id"], []).append(r)
for pid, rs in sorted(by_pid.items(),
                      key=lambda kv: personas[kv[0]]["demographics"]["age"]):
    p = personas[pid]
    d = p["demographics"]
    tg = is_target(p, [spec])
    ft = policy_fit(p, spec)
    eligs = [r["survey"].get("eligibility") for r in rs]
    bens = [r["survey"].get("benefit") for r in rs]
    intents = [r["survey"].get("intent") for r in rs]
    print(f"{p['name']:<5} {d['age']:>2}세 {d['occupation'][:10]:<10} "
          f"tgt={'Y' if tg else 'N'} fit={ft:.2f} | "
          f"자가인식={','.join(str(e) for e in eligs):<32} | "
          f"benefit={','.join(str(b) for b in bens):<28} | intent={','.join(str(i) for i in intents)}")

print()
print("[B] ablation ON/OFF benefit·intent 토큰 분포")
for cond in ("on", "off"):
    rs = [r for r in ab["rows"] if r["cond"] == cond and r["ok"]]
    bc = Counter(r["survey"].get("benefit") for r in rs)
    ic = Counter(r["survey"].get("intent") for r in rs)
    ec = Counter(r["survey"].get("eligibility") for r in rs)
    print(f"  {cond:>3}: benefit={dict(bc.most_common())}")
    print(f"       intent ={dict(ic.most_common())}")
    print(f"       자가인식={dict(ec.most_common())}")

print()
print("[C] ablation ON — 젊은 대상자(is_target=Y)의 반응문 (1회차)")
for pid, rs in by_pid.items():
    p = personas[pid]
    if is_target(p, [spec]):
        r0 = sorted(rs, key=lambda r: r["run"])[0]
        print(f"--- {p['name']} {p['demographics']['age']}세 "
              f"{p['demographics']['occupation'][:14]} / 가구={p['demographics']['family_type']}")
        print(f"    자가인식={r0['survey'].get('eligibility')} "
              f"benefit={r0['survey'].get('benefit')} intent={r0['survey'].get('intent')}")
        print(f"    \"{r0['text'][:150]}\"")

print()
print("=" * 70)
print("[D] robustness 바닥(1원) — 불만 토큰 분포 + 반응문 표본 4개")
print("=" * 70)
fl = [r for r in rb["rows"] if r["cond"] == "floor" and r["ok"]]
dc = Counter(r["survey"].get("dissatisfaction") for r in fl)
ic = Counter(r["survey"].get("intent") for r in fl)
print(f"  불만 토큰={dict(dc.most_common())}")
print(f"  intent  ={dict(ic.most_common())}")
for r in fl[:4]:
    p = personas[r["persona_id"]]
    print(f"--- {p['name']} {p['demographics']['age']}세 | "
          f"불만={r['survey'].get('dissatisfaction')} intent={r['survey'].get('intent')}")
    print(f"    \"{r['text'][:150]}\"")

print()
print("[E] robustness 천장(10억) — 불만/의향 분포 + 표본 2개")
ce = [r for r in rb["rows"] if r["cond"] == "ceiling" and r["ok"]]
print(f"  불만 토큰={dict(Counter(r['survey'].get('dissatisfaction') for r in ce).most_common())}")
print(f"  intent  ={dict(Counter(r['survey'].get('intent') for r in ce).most_common())}")
for r in ce[:2]:
    p = personas[r["persona_id"]]
    print(f"--- {p['name']} {p['demographics']['age']}세 | "
          f"불만={r['survey'].get('dissatisfaction')} intent={r['survey'].get('intent')}")
    print(f"    \"{r['text'][:150]}\"")
