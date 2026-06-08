# -*- coding: utf-8 -*-
"""정책 임팩트 vs 구조 — A/B 진단(일회용 dev, 부작용 0).

오늘 런과 동일한 동선·만남(schedules.json 그대로, 시드=staff)에 정책만
'청년월세(타깃 정책)'로 바꿔 1일차를 돌린다. write_meetings=False + sim_state
미접촉 — 화면/상태에 아무 흔적 없음. 비교 지표 = 혼합 만남(한쪽만 앎)의
정책 언급률·전파 성사율 (주3.5일제 기준값: 8/8 = 100%).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\akals\Downloads\미리랩\미리마을")

import gen_dialogues as G  # noqa: E402

POLICY = ("[청년 월세 한시 특별지원]\n"
          "만 19~34세 무주택 청년 중 부모와 따로 거주하고 소득 기준(중위소득 60% 이하)을 "
          "충족하는 사람에게 월 20만 원의 임대료를 최대 12개월 지원합니다. "
          "신청은 복지로 누리집 또는 주민센터 방문.")
TOKS = ("청년", "월세", "임대", "20만")

assert G.has_real_key(), "실키 없음 — 중단"
print(f"프로바이더: {G.PROVIDER} ({G.MODEL})")

villagers = G._load("villagers.json")["villagers"]
by_id = {v["id"]: v for v in villagers}
s0 = G.initial_states(villagers, aware_ids=("staff",))
new_states, rec = G.run_day(POLICY, s0, 1, write_meetings=False)

aware_end = [v for v, s in new_states.items() if s["awareness"] in G.AWARE_SET]
print()
print(f"=== 청년월세 1일차 (같은 동선) ===")
print(f"인지 {len(aware_end)}/10: {', '.join(aware_end)}")
print(f"전파 {len(rec['propagation'])}건:")
for e in rec["propagation"]:
    t = e.get("time", 0)
    print(f"  {e['from']:8s} -> {e['to']:8s} {t//60:02d}:{t%60:02d} @ {e.get('place','')}")

# 혼합 만남 분해(전파 타임라인 재생) + 비전파 혼합 만남의 대사 확인
aware = {"staff"}
edges = {(e["from"], e["to"], e["time"]) for e in rec["propagation"]}
mixed = mention = spread = 0
quiet = []   # 정책이 안 옮은 혼합 만남
for m in rec["meetings"]:
    a, b = m["a"], m["b"]
    a_aw, b_aw = a in aware, b in aware
    if a_aw == b_aw:
        continue
    mixed += 1
    text = " ".join(t.get("t", "") for t in m.get("turns", []))
    if any(t in text for t in TOKS):
        mention += 1
    if any((x, y, m["start"]) in edges for x, y in ((a, b), (b, a))):
        spread += 1
        aware.add(b if a_aw else a)
    else:
        quiet.append(m)
print()
print(f"혼합 만남 {mixed}개 중 정책 언급 {mention}, 전파 성사 {spread}")
print(f"(기준값 주3.5일제: 8개 중 8 언급, 8 성사)")

if quiet:
    print()
    print("=== 정책이 '안' 옮은 혼합 만남 (대사 샘플) ===")
    for m in quiet[:4]:
        nm = lambda i: by_id[i]["name"]
        t0 = m["start"]
        print(f"-- {t0//60:02d}:{t0%60:02d} @ {m['place']}: {nm(m['a'])} x {nm(m['b'])}")
        for t in m.get("turns", [])[:4]:
            print(f"   {nm(t['s'])}: {t['t']}")
