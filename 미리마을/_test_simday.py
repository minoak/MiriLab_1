# -*- coding: utf-8 -*-
"""_test_simday.py — 정책 전파 시뮬(run_day) 키리스 회귀.

검증(외부 호출 0, force_fallback):
  1) 만남 완화 — 같은 장소면 만남 → 만남 수가 늘었나(>= 8)
  2) 1일차 전파 — 시드(grandma·oldman)에서 폴백 전달로 인지 확산 + 전파 엣지 기록
  3) 일기 carry-forward — new_states 에 일기/인지가 담겨 다음 날 시드가 되나
  4) 다일차 단조 — 2일차 인지자 수 >= 1일차(전파는 줄지 않음)
실제 meetings.js 는 건드리지 않는다(write_meetings=False).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_dialogues as G  # noqa: E402

POLICY = "청년 월세 지원: 만 19~34세 무주택 청년에게 월 20만원 임대료를 지원한다."
# 엔진(전파 메커니즘) 검증용 시드 = 카페 허브 박사장(여러 사람을 만남).
# (프로토타입 시나리오 시드 grandma·oldman 은 현 스케줄상 서로만 만나 전파 0 —
#  엔진 버그가 아니라 '어르신 고립'이라는 구조적 결과. 아래 [6]에서 관측만.)
HUB_SEED = ("owner",)
SCENARIO_SEED = ("grandma", "oldman")


def _aware_count(states):
    return sum(1 for s in states.values() if s["awareness"] in G.AWARE_SET)


def main():
    villagers = G._load("villagers.json")["villagers"]
    locations = G._load("locations.json")["locations"]
    schedules = G._load("schedules.json")
    anchors = G._load_anchors()

    fails = []

    # 1) 만남 완화 + 집(가족) 만남
    meetings = G.extract_meetings(schedules, villagers, locations, anchors)
    home = [m for m in meetings if m["place"] == "houses"]
    print(f"[1] 만남 수 = {len(meetings)} (완화 전 ~6) | 집(가족) 만남 = {len(home)}")
    if len(meetings) < 12:
        fails.append(f"만남 수 부족: {len(meetings)} (>=12 기대)")
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

    # 6) 시나리오 시드(어르신) — 관측만(연결 여부는 스케줄 의존, 단언 안 함)
    se0 = G.initial_states(villagers, aware_ids=SCENARIO_SEED)
    se1, _ = G.run_day(POLICY, se0, 1, force_fallback=True, write_meetings=False)
    cross = [m for m in meetings
             if (m["a"] in SCENARIO_SEED) != (m["b"] in SCENARIO_SEED)]
    print(f"[6] (관측) 어르신 시드 - 이웃과의 다리 {len(cross)}개, 1일차 인지 {_aware_count(se1)}/10")

    print()
    if fails:
        print("[FAIL] " + " | ".join(fails))
        sys.exit(1)
    print("ALL PASS - 만남 완화+집만남 / 엔진 전파 / 일기 carry / 다일차 단조 / 빈정책 0")


if __name__ == "__main__":
    main()
