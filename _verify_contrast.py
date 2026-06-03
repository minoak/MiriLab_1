# -*- coding: utf-8 -*-
"""정책 인생극장 end-to-end 검증 (mock 시뮬, 키 불필요).

정책 패키지 → 대조 3명 선별 → 그 3명만 인생 시뮬까지 한 흐름을 확인한다.
실행: python _verify_contrast.py   (프로젝트 루트에서)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from data.personas import load_personas
from sample_policies import PACKAGES
from contrast import run_contrast
from ui.mock import sample_village
from graph.spaces import place_label, status_label

# mock 시뮬 주입: (personas, policy_text, step_labels) 시그니처에 맞춘 래퍼.
def mock_sim(personas, policy_text, step_labels):
    return sample_village(personas, policy_text, step_labels=step_labels)


def run(pkg_name):
    personas = load_personas(n=8, seed=42)
    policies = PACKAGES[pkg_name]
    res = run_contrast(personas, policies, simulate=mock_sim, use_llm_spec=False)

    print("=" * 80)
    print("패키지:", pkg_name)
    print("정책:", " + ".join(s["name"] for s in res["specs"]))
    print("선별된 3명 id:", res["trio_ids"])
    print("-" * 80)

    # 1) 선별 결과(누가 왜 뽑혔나)
    for t in res["selection"]["trio"]:
        p = t["persona"]
        d = p.get("demographics", {})
        print(f"  ★{t['role']:<5} {p['name']}({d.get('age')}세 {d.get('occupation','')}) — {t['headline']}")
    for n in res["selection"]["notes"]:
        print("   " + n)
    print("-" * 80)

    # 2) 고른 3명만 인생 시뮬이 돌았는지(궤적 출력)
    village = res["village"]
    print(f"시뮬 결과: residents={len(village['residents'])}명, steps={village['steps']}")
    for r in village["residents"]:
        print(f"\n  ▸ {r['name']} (최종: {status_label(r['policy_status'])}, "
              f"경제 {r['economic']}, 만족 {r['wellbeing']})")
        for step in r["timeline"]:
            print(f"     {step['label']:<10} | {place_label(step['place']):<14} "
                  f"| {status_label(step['policy_status']):<8} "
                  f"| 경제{step['economic']:>3} 만족{step['wellbeing']:>3} | {step['note']}")
    print()


run("디지털 복지 3종 (소득·세대로 갈림)")
run("생애주기 3종 (서로 분리)")

# 패키지 텍스트(시뮬에 주입되는 원문)가 여러 정책을 묶는지 확인
personas = load_personas(n=8, seed=42)
res = run_contrast(personas, PACKAGES["디지털 복지 3종 (소득·세대로 갈림)"],
                   simulate=mock_sim, use_llm_spec=False)
print("=" * 80)
print("[패키지 텍스트 미리보기 — 시뮬 프롬프트에 주입되는 정책 묶음]")
print(res["package_text"][:400], "...")
