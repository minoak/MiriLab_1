# -*- coding: utf-8 -*-
"""대조 3명 선별 스모크 테스트 (키 불필요, 캐시 페르소나로 결정론 검증).

실행: python _test_trio.py   (프로젝트 루트에서)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from data.personas import load_personas, select_contrast_trio
from policy_spec import resolve_specs, keyword_spec
from sample_policies import SAMPLES, PACKAGES

# 셀 상태 → 표시 기호
SYM = {"received": "✓", "blocked": "⊘", "eligible": "◐", "out": "·"}


def show(title, policy_names, use_llm=False):
    personas = load_personas(n=8, seed=42)          # 캐시에서(네트워크 X)
    specs = resolve_specs(policy_names, use_llm=use_llm)
    res = select_contrast_trio(personas, specs)

    print("=" * 84)
    print("정책 패키지:", " + ".join(s["name"] for s in specs))
    for s in specs:
        print(f"   · {s['name']}: 나이{s['age']} 소득{s['income']} 가구={s['family_kw']} 채널={s['channel']}")
    print("-" * 84)
    head = f"{'이름':<7}{'나이':>3} {'접근':>5} | " + " ".join(f"{s['name'][:4]:>6}" for s in specs) + " | 커버 막힘"
    print(head)
    print("-" * 84)
    for r in res["matrix"]:
        cells = " ".join(f"{SYM[c['state']]}{c['benefit']:.2f}" for c in r["cells"])
        print(f"{r['name']:<7}{r['age']:>3} {r['access']:>5.2f} | {cells} |  {r['cover']}    {r['blocked']}")
    print("-" * 84)
    for t in res["trio"]:
        p = t["persona"]
        print(f"  ★{t['role']:<5} {p.get('name')}({t['score']['age']}세) — {t['headline']}")
    for n in res["notes"]:
        print("   " + n)
    print("  범례:", " ".join(f"{v}{k}" for k, v in SYM.items()))
    print()


# 1) 겹치는 패키지 (소득·세대로 갈림) — 부분수혜 경계가 자연 발생
show("겹침 패키지", PACKAGES["디지털 복지 3종 (소득·세대로 갈림)"])

# 2) 생애주기 분리형 — 강한 사각 / 약한 경계(한계 인물 폴백) 확인
show("분리형 패키지", PACKAGES["생애주기 3종 (서로 분리)"])

# 3) 단일 정책 (청년월세) — 범위가 좁아 대조 약한 케이스
show("단일: 청년월세", ["청년 월세 한시 특별지원"])

# 3) 키워드 폴백 검증: 샘플에 없는 임의 정책 텍스트
print("=" * 84)
print("[키워드 폴백] 임의 정책 텍스트 → spec 추출 (use_llm=False)")
arbitrary = "[청년 구직활동 지원금] 만 18~34세 미취업 청년에게 월 50만 원을 6개월간 지원합니다. 복지로에서 온라인 신청."
ks = keyword_spec(arbitrary)
print("   추출:", {k: ks[k] for k in ("name", "age", "income", "family_kw", "channel")})
