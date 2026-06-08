# -*- coding: utf-8 -*-
"""전파 적극성 진단(일회용 dev): 오늘 런 vs git 커밋본(구 시드) 비교.

지표:
  - 혼합 만남(한쪽만 아는 만남) 대비 전파 성사율 — '꺼낼지는 그 사람에게 달렸다'가
    실제로 갈리는지, 아니면 사실상 항상 꺼내는지.
  - 만남 대화에서 정책 토큰 언급 비율(오늘 런 meetings.json 만 — 구 런은 대사 미보존).
"""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\akals\Downloads\미리랩"


def spread_stats(state, label):
    """sim_state(history)에서 일자별 혼합만남 전파율을 propagation 타임라인으로 근사."""
    print(f"=== {label} ===")
    pol = (state.get("policy") or "").replace("\n", " ")
    print(f"정책: {pol[:70]}")
    for rec in state.get("history", []):
        day = rec.get("day")
        edges = rec.get("propagation") or []
        diaries = rec.get("diaries") or {}
        n_aware_end = sum(1 for d in diaries.values()
                          if d.get("awareness") in ("aware", "interested", "acting"))
        print(f"  {day}일차: 전파 {len(edges)}건, 일과 후 인지 {n_aware_end}/10")
        for e in edges:
            t = e.get("time", 0)
            print(f"    {e['from']:8s} -> {e['to']:8s} {t//60:02d}:{t%60:02d} @ {e.get('place','')}")
    print()


# 1) 오늘 런
cur = json.load(open(rf"{ROOT}\미리마을\data\sim_state.json", encoding="utf-8"))
spread_stats(cur, "오늘 런 (시드=staff, 주3.5일제)")

# 2) 커밋본(HEAD) 구 런
try:
    out = subprocess.run(
        ["git", "-C", ROOT, "show", "HEAD:미리마을/data/sim_state.json"],
        capture_output=True, check=True)
    old = json.loads(out.stdout.decode("utf-8"))
    spread_stats(old, "커밋본 구 런 (HEAD)")
except Exception as ex:
    print(f"커밋본 로드 실패: {ex}")

# 3) 오늘 런 만남 대화 — 혼합 만남에서 정책이 언급된 비율
meetings = json.load(open(rf"{ROOT}\미리마을\data\meetings.json", encoding="utf-8"))
toks = ("3.5", "근무", "근로", "정책", "주말")
aware = {"staff"}  # 시드
edges_by_time = {(e["from"], e["to"], e["time"]) for e in cur["history"][0]["propagation"]}
mixed = both = none = mixed_mention = mixed_spread = 0
for m in sorted(meetings, key=lambda x: x["start"]):
    a, b = m["a"], m["b"]
    a_aw, b_aw = a in aware, b in aware
    text = " ".join(t.get("t", "") for t in m.get("turns", []))
    mention = any(t in text for t in toks)
    if a_aw != b_aw:
        mixed += 1
        if mention:
            mixed_mention += 1
        # 이 만남에서 전파됐나(타임라인 갱신)
        spread = any((x, y, m["start"]) in edges_by_time
                     for x, y in ((a, b), (b, a)))
        if spread:
            mixed_spread += 1
            aware.add(b if a_aw else a)
    elif a_aw and b_aw:
        both += 1
    else:
        none += 1
print("=== 오늘 런 만남 분해 ===")
print(f"총 {len(meetings)}개: 혼합(한쪽만 앎) {mixed} / 둘다앎 {both} / 둘다모름 {none}")
print(f"혼합 만남 중 정책 언급 {mixed_mention}/{mixed}, 전파 성사 {mixed_spread}/{mixed}")
