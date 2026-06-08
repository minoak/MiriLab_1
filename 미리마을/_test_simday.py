# -*- coding: utf-8 -*-
"""_test_simday.py — 정책 전파 시뮬(run_day) 키리스 회귀.

검증(외부 호출 0, force_fallback):
  1) 그룹 만남 — 같은 장소·시간 = 한 장면. parts(참가자) 존재, 3명+ 그룹 장면 있음, a/b 하위호환
  2) 1일차 전파 — 허브 시드(owner)에서 폴백 전달로 인지 확산 + 전파 엣지 기록
  3) 일기 carry-forward — new_states 에 일기/인지가 담겨 다음 날 시드가 되나
  4) 다일차 단조 — 2일차 인지자 수 >= 1일차(전파는 줄지 않음)
  7) 과거 일기 주입 — past_diaries 가 만남·일기 프롬프트에 실리고 run_day 가 깨지지 않나
실제 meetings.js 는 건드리지 않는다(write_meetings=False).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_dialogues as G  # noqa: E402

POLICY = "청년 월세 지원: 만 19~34세 무주택 청년에게 월 20만원 임대료를 지원한다."
# 엔진(전파 메커니즘) 검증용 시드 = 카페 허브 박사장(여러 사람을 만남).
HUB_SEED = ("owner",)
# 시나리오 시드 = 정책 담당 공무원 영희(2026-06-08 교체, tab_minivillage.SEED_IDS 와 동일).
# 구 어르신 시드(grandma·oldman)는 동선이 겹쳐 서로끼리만 만나는 날이 있었음(고립).
SCENARIO_SEED = ("staff",)


def _aware_count(states):
    return sum(1 for s in states.values() if s["awareness"] in G.AWARE_SET)


def main():
    villagers = G._load("villagers.json")["villagers"]
    locations = G._load("locations.json")["locations"]
    schedules = G._load("schedules.json")
    anchors = G._load_anchors()

    fails = []

    # 1) 그룹 만남 — 장소·시간 스윕, 3명+ 그룹 장면 + 집(가족) 장면 + a/b 하위호환
    meetings = G.extract_meetings(schedules, villagers, locations, anchors)
    home = [m for m in meetings if m["place"] == "houses"]
    groups = [m for m in meetings if len(m.get("parts", [])) >= 3]
    print(f"[1] 장면 수 = {len(meetings)} | 3명+ 그룹 = {len(groups)} | 집(가족) = {len(home)}")
    if len(meetings) < 8:
        fails.append(f"장면 수 부족: {len(meetings)} (>=8 기대)")
    if not groups:
        fails.append("3명+ 그룹 장면 0 — 그룹 만남 추출 실패")
    if not all("parts" in m and len(m["parts"]) >= 2 for m in meetings):
        fails.append("parts(참가자) 누락 또는 1명 장면 존재")
    if not all(m["a"] == m["parts"][0] and m["b"] == m["parts"][1] for m in meetings):
        fails.append("a/b 하위호환(parts[0]/parts[1]) 불일치")
    if meetings != sorted(meetings, key=lambda m: m["start"]):
        fails.append("만남이 시간순이 아님")
    if not all("close" in m for m in meetings):
        fails.append("close 플래그 누락")
    if not home:
        fails.append("집(가족) 만남 0 — 같은 집 식구 만남 누락")

    # 2) 엔진 전파 — 허브 인물(박사장) 시드로 메커니즘 검증(전파 > 0)
    s0 = G.initial_states(villagers, aware_ids=HUB_SEED)
    if _aware_count(s0) != 1:
        fails.append(f"허브 시드 수 이상: {_aware_count(s0)} (1 기대)")
    s1, rec1 = G.run_day(POLICY, s0, 1, force_fallback=True, write_meetings=False)
    aware1 = _aware_count(s1)
    print(f"[2] 허브 시드 1일차 후 인지자 = {aware1}/10, 전파 엣지 = {len(rec1['propagation'])}")
    if not rec1["propagation"]:
        fails.append("엔진 전파 실패: 허브 시드인데 전파 엣지 0")
    if aware1 <= 1:
        fails.append(f"엔진 전파 실패: 허브 시드인데 인지 안 늘어남({aware1})")

    # 3) 전파 엣지 형식 + 일기 carry
    e = rec1["propagation"][0]
    if set(e) != {"from", "to", "place", "time", "day"}:
        fails.append(f"전파 엣지 키 이상: {sorted(e)}")
    if not all(set(v) == {"awareness", "stance", "diary"} for v in s1.values()):
        fails.append("new_states 필드 형식 이상")
    if not all(rec1["diaries"][v["id"]]["diary"] for v in villagers):
        fails.append("일기 비어있는 캐릭터 존재")

    # 4) 다일차 단조(2일차 >= 1일차) + 일기 carry-forward 가 시드로 작동
    s2, rec2 = G.run_day(POLICY, s1, 2, force_fallback=True, write_meetings=False)
    aware2 = _aware_count(s2)
    print(f"[4] 2일차 후 인지자 = {aware2}/10 (carry-forward)")
    if aware2 < aware1:
        fails.append(f"2일차 인지 후퇴: {aware2} < {aware1}")

    # 5) 정책/시드 없음 → 전파 0(평범한 하루)
    s_empty, rec_empty = G.run_day("", G.initial_states(villagers), 1,
                                   force_fallback=True, write_meetings=False)
    if _aware_count(s_empty) != 0 or rec_empty["propagation"]:
        fails.append("정책/시드 없음인데 인지/전파 발생")

    # 6) 시나리오 시드(공무원 staff) — 다리 수 관측 + 전파 단언(허브 직업이라 기대)
    se0 = G.initial_states(villagers, aware_ids=SCENARIO_SEED)
    se1, _ = G.run_day(POLICY, se0, 1, force_fallback=True, write_meetings=False)
    cross = [m for m in meetings
             if (m["a"] in SCENARIO_SEED) != (m["b"] in SCENARIO_SEED)]
    print(f"[6] 시나리오 시드(staff) - 이웃과의 다리 {len(cross)}개, 1일차 인지 {_aware_count(se1)}/10")

    # 7) 과거 일기 주입 — 만남 프롬프트에 '지난 일기' 블록이 실리고, run_day 가 깨지지 않는다
    past = {v["id"]: [(1, f"{v['name']}의 1일차 일기")] for v in villagers}
    by_id = {v["id"]: v for v in villagers}
    loc_label = {l["key"]: l["label"] for l in locations}
    today0 = {v["id"]: {"awareness": "aware", "stance": "support", "diary": "", "log": []}
              for v in villagers}
    grp = next((m for m in meetings if len(m["parts"]) >= 3), meetings[0])
    mu = G.build_meeting_user(grp, by_id, loc_label, schedules, today0, past_diaries=past)
    if "지난 일기:" not in mu or "1일차 일기" not in mu:
        fails.append("과거 일기 블록이 만남 프롬프트에 안 실림")
    s_past, rec_past = G.run_day(POLICY, s1, 3, force_fallback=True,
                                 write_meetings=False, past_diaries=past)
    if _aware_count(s_past) < aware1:
        fails.append(f"past_diaries 경로 3일차 인지 후퇴: {_aware_count(s_past)} < {aware1}")
    print(f"[7] 과거일기 주입 OK - 블록 실림 + 3일차 인지 {_aware_count(s_past)}/10")

    print()
    if fails:
        print("[FAIL] " + " | ".join(fails))
        sys.exit(1)
    print("ALL PASS - 그룹만남+집만남 / 엔진 전파 / 일기 carry / 다일차 단조 / 빈정책 0 / 과거일기 주입")


if __name__ == "__main__":
    main()
