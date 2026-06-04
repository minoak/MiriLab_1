# -*- coding: utf-8 -*-
"""결과 기반 대조 선별 단위 테스트 (mock, 키 불필요·LLM 0).

핵심 회귀: 수혜/경계/사각이 '수치(반응 점수)'가 아니라 '실제 시뮬 결과'로 정해지는지.
특히 임수빈(p11)=부모 동거로 막힌 사각지대 가, 본인이 스스로 매긴 반응 점수(수혜
가능성 18 = 수치상 '무관'처럼 보임)와 무관하게 '사각(blocked)'으로 잡히는지 못 박는다.

실행: python _test_outcome_select.py   (프로젝트 루트에서)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ui.mock import _personas, _reactions, sample_village
from contrast import select_trio_from_outcomes

personas = _personas()
reactions = _reactions()
reactions_by_id = {r["persona_id"]: r for r in reactions}

# 전원 결정론 시뮬(LLM 0). 실모드의 simulate_village 와 같은 {steps,residents,aggregate}.
village = sample_village(personas)
residents = village["residents"]

by_status = {}
for r in residents:
    by_status.setdefault(r["policy_status"], []).append(r["name"])
print("전원 최종 상태 분포:")
for k, v in by_status.items():
    print(f"  {k}: {', '.join(v)}")

sel = select_trio_from_outcomes(residents, personas)
trio = sel["trio"]
print("\n대조 3명 (결과 기반):")
for t in trio:
    sc = t["score"]
    print(f"  {t['role']:<5} {t['persona']['name']} "
          f"(최종 {sc['final_status']}, 막힌적 {sc['ever_blocked']}) — {t['headline']}")
for n in sel["notes"]:
    print("  ·", n)

# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
by_role = {t["role_key"]: t for t in trio}

# 1) 임수빈(p11): 반응 수혜성 18(수치상 '무관')이지만 실제로는 막힘 → 사각.
p11 = next((t for t in trio if t["persona"]["id"] == "p11"), None)
assert p11 is not None, "임수빈(p11)이 대조 3명에 없음 — 막힌 사각을 놓침"
assert p11["role_key"] == "blindspot", f"임수빈 역할이 {p11['role_key']} (사각이어야 함)"
assert p11["score"]["ever_blocked"], "임수빈이 막힌 적 없음으로 잡힘"
r11 = reactions_by_id["p11"]["scores"]
print(f"\n[검증 1] 임수빈 반응 수혜성={r11['benefit']}·의향={r11['intent']} "
      f"(수치상 '무관') → 결과는 사각(막힘)으로 정확히 잡힘 ✅")

# 2) 수혜 카드는 실제로 '받은' 사람(이준호 p02 / 강도현 p10 중 하나).
benef = by_role.get("beneficiary")
assert benef is not None, "수혜 대표 없음"
assert benef["score"]["ever_received"], "수혜 카드가 실제로 받지 않은 사람"
assert benef["persona"]["id"] in ("p02", "p10"), f"예상 밖 수혜자 {benef['persona']['id']}"
print(f"[검증 2] 수혜 = {benef['persona']['name']} (실제 수령) ✅")

# 3) 세 사람 distinct + 수혜/사각 대비 존재.
ids = [t["persona"]["id"] for t in trio]
assert len(set(ids)) == len(ids), "중복 인물"
assert "blindspot" in by_role and "beneficiary" in by_role, "수혜/사각 대비 누락"
print("[검증 3] 3명 distinct + 수혜/사각 대비 존재 ✅")

# 4) outcomes(전원 결과표)가 전원을 담고, 카드 라벨이 결과와 일치한다.
assert len(sel["outcomes"]) == len(residents), "결과표가 전원을 안 담음"
for t in trio:
    rid = t["persona"]["id"]
    res = next(r for r in residents if r["id"] == rid)
    final = res["timeline"][-1]["policy_status"]
    ever_blocked = any(s["policy_status"] == "blocked" for s in res["timeline"])
    ever_received = any(s["policy_status"] == "received" for s in res["timeline"])
    rk = t["role_key"]
    if ever_received:
        assert rk == "beneficiary", f"{t['persona']['name']}: 받았는데 역할 {rk}"
    elif ever_blocked or final == "unaware":
        assert rk == "blindspot", f"{t['persona']['name']}: 막힘/못닿음인데 역할 {rk}"
    else:
        assert rk == "borderline", f"{t['persona']['name']}: 진행중인데 역할 {rk}"
print(f"[검증 4] 전체 결과표 {len(sel['outcomes'])}명(=전원) + 모든 카드 라벨=실제 결과 ✅")

# 5) 태그 대상 게이트 — 청년월세(나이 19~34)에 35세·76세는 '대상 아님'으로 제외.
from policy_spec import resolve_specs
from data.personas import is_target

specs = resolve_specs(["청년 월세 한시 특별지원"], use_llm=False)
sel2 = select_trio_from_outcomes(residents, personas, specs)
trio2_ids = {t["persona"]["id"] for t in sel2["trio"]}
out_ids = {r["id"] for r in sel2["outcomes"] if r["role_key"] == "out"}

assert trio2_ids, "대상자 트리오가 비었음 — 게이트가 청년 대상까지 전부 제외(정규화 실패?)"
assert "p02" in trio2_ids or "p10" in trio2_ids, "청년 수령자(이준호/강도현)가 대상에서 빠짐"
for pid, who in (("p03", "박상철 35세"), ("p01", "김복순 76세")):
    assert pid in out_ids, f"{who} 가 청년정책 비대상으로 안 걸러짐"
    assert pid not in trio2_ids, f"{who}(비대상)가 카드에 뽑힘"
# 카드는 전원 대상자(role_key != out & is_target True)
for t in sel2["trio"]:
    assert t["role_key"] != "out", f"{t['persona']['name']} 카드가 '대상 아님'"
    p = next(pp for pp in personas if pp["id"] == t["persona"]["id"])
    assert is_target(p, specs), f"{t['persona']['name']} 가 비대상인데 카드에 있음"
print(f"[검증 5] 태그 게이트: 35세·76세 비대상 제외, 카드 전원 대상자 ✅ "
      f"(대상 아님 {len(out_ids)}명)")

print("\n✅ 결과 기반 선별 + 태그 대상 게이트 테스트 통과 "
      "— 비대상은 '무관', 라벨은 실제 결과에서 나온다")
