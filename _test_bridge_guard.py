# -*- coding: utf-8 -*-
"""_test_bridge_guard.py — §8-3 축2 다리 가드 스모크 (LLM 호출 0, structured_call 패치).

검증:
1) _bridge_violation 순수 규칙 — applied 이상 reached_via 필수, blocked barrier 필수.
2) 위반 시 그 주민·그 스텝만 1회 재생성(재시도 피드백 메시지 포함).
3) 재생성 후에도 위반(잔존) → 직전 스텝 경로 상속/'(기록 누락)' 표기 + 카운트.
4) run_contrast 정직 노트 — bridge_guard 통계가 selection.notes 로 노출.
5) mock(sample_village) 전 주민: 사다리 위 칸인데 reached_via 빈 케이스 0.
실행: python _test_bridge_guard.py
"""
import sys

import graph.village as gv
from graph.village import VillageStepOut, _bridge_violation


def _out(**kw):
    base = dict(place="welfare_center", reached_via="", action="이번 달의 일.",
                policy_status="received", barrier="", economic=60, wellbeing=60,
                note="요약")
    base.update(kw)
    return VillageStepOut(**base)


def main():
    fails = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    # ── 1) 순수 규칙 ──
    check("received+경로없음 위반", bool(_bridge_violation("received", "", "")))
    check("applied+경로없음 위반", bool(_bridge_violation("applied", " ", "")))
    check("blocked+barrier없음 위반", bool(_bridge_violation("blocked", "공지문", "")))
    check("received+경로있음 정상", _bridge_violation("received", "복지사 안내", "") == "")
    check("aware 는 다리 비필수", _bridge_violation("aware", "", "") == "")
    check("unaware 정상", _bridge_violation("unaware", "", "") == "")

    # ── 2·3) 재생성 + 잔존 교정 (structured_call 패치) ──
    # 시나리오(단일 주민 × 2스텝, 호출 순서 결정론):
    #   스텝1 원본=위반(received, 경로 "") → 재시도=정상("복지사 안내") → 채택
    #   스텝2 원본=위반 → 재시도도 위반 → 잔존: 직전 스텝 경로 상속
    script = [
        _out(),                                  # 스텝1 원본 — 위반
        _out(reached_via="복지사 안내"),          # 스텝1 재시도 — 정상
        _out(economic=62),                       # 스텝2 원본 — 위반
        _out(economic=62),                       # 스텝2 재시도 — 여전히 위반
    ]
    calls = {"n": 0, "retry_msgs": []}
    orig_call = gv.structured_call

    def fake_call(msgs, schema, temperature=0.8):
        i = calls["n"]
        calls["n"] += 1
        if msgs and "누락이 있습니다" in (msgs[-1].get("content") or ""):
            calls["retry_msgs"].append(msgs[-1]["content"])
        return script[i]

    gv.structured_call = fake_call
    try:
        persona = {"id": "p1", "name": "김복지"}
        village = gv.simulate_village([persona], "정책", step_labels=["1개월", "3개월"])
    finally:
        gv.structured_call = orig_call

    tl = village["residents"][0]["timeline"]
    bg = village["aggregate"]["bridge_guard"]
    check("호출 수 = 4(스텝당 원본+재시도)", calls["n"] == 4, f"calls={calls['n']}")
    check("재시도에 위반 사유 피드백 포함",
          len(calls["retry_msgs"]) == 2 and "reached_via" in calls["retry_msgs"][0])
    check("스텝1 = 재생성본 채택", tl[0]["reached_via"] == "복지사 안내")
    check("스텝2 잔존 → 직전 경로 상속", tl[1]["reached_via"] == "복지사 안내",
          f"got={tl[1]['reached_via']!r}")
    check("재생성 카운트 = 2", bg["retries"] == 2, f"got={bg}")
    check("잔존 카운트 = 1", bg["residuals"] == 1, f"got={bg}")
    check("라벨은 안 뒤집음(received 유지)",
          all(s["policy_status"] == "received" for s in tl))

    # 잔존 + 직전 경로도 없음 → '(기록 누락)' 표기 (1스텝, 둘 다 위반)
    script2 = [_out(), _out()]
    calls2 = {"n": 0}

    def fake_call2(msgs, schema, temperature=0.8):
        out = script2[calls2["n"]]
        calls2["n"] += 1
        return out

    gv.structured_call = fake_call2
    try:
        v2 = gv.simulate_village([persona], "정책", step_labels=["1개월"])
    finally:
        gv.structured_call = orig_call
    check("직전 경로 없으면 '(경로 기록 누락)' 표기",
          v2["residents"][0]["timeline"][0]["reached_via"] == "(경로 기록 누락)")

    # blocked + barrier 누락 잔존 → barrier 교정 표기
    script3 = [_out(policy_status="blocked", reached_via="주민센터 방문", barrier=""),
               _out(policy_status="blocked", reached_via="주민센터 방문", barrier="")]
    calls3 = {"n": 0}

    def fake_call3(msgs, schema, temperature=0.8):
        out = script3[calls3["n"]]
        calls3["n"] += 1
        return out

    gv.structured_call = fake_call3
    try:
        v3 = gv.simulate_village([persona], "정책", step_labels=["1개월"])
    finally:
        gv.structured_call = orig_call
    check("blocked 잔존 → barrier '(막힌 지점 기록 누락)' 표기",
          v3["residents"][0]["timeline"][0]["barrier"] == "(막힌 지점 기록 누락)")

    # ── 4) 정직 노트 — run_contrast 가 bridge_guard 를 notes 로 노출 ──
    from contrast import run_contrast

    def fake_sim(ps, pol, sl):
        return {
            "steps": ["1개월"],
            "residents": [{"id": "p1", "name": "김복지", "timeline": [{
                "step": 1, "label": "1개월", "place": "welfare_center",
                "reached_via": "(경로 기록 누락)", "action": "...",
                "policy_status": "received", "barrier": "",
                "economic": 60, "wellbeing": 60, "note": "",
            }], "policy_status": "received", "economic": 60, "wellbeing": 60}],
            "aggregate": {"bridge_guard": {"retries": 3, "residuals": 1}},
        }

    res = run_contrast([persona], ["정책"], simulate=fake_sim, use_llm_spec=False)
    notes = res["selection"].get("notes") or []
    check("정직 노트: 재생성 노출", any("재생성" in n for n in notes),
          f"notes={notes}")
    check("정직 노트: 모순 감지 노출", any("모순 감지 1건" in n for n in notes))

    # ── 5) mock 경로 위반 0 (수용 기준: received 인데 reached_via 빈 케이스 0) ──
    from ui.mock import sample_simstate, sample_village
    sim = sample_simstate("청년 월세 지원")
    mock_village = sample_village(sim["personas"], "청년 월세 지원")
    viol = [
        (r["id"], s["policy_status"])
        for r in mock_village["residents"] for s in r["timeline"]
        if _bridge_violation(s.get("policy_status", ""), s.get("reached_via", ""),
                             s.get("barrier", ""))
    ]
    check("mock 전 주민·전 스텝 다리 위반 0", not viol, f"viol={viol[:5]}")

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
