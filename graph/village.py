# -*- coding: utf-8 -*-
"""graph/village.py — 미리 마을: 정책 영향 시뮬레이션 (시간 축).

전파 그래프를 대체하는 핵심 축. Park et al.(Generative Agents) 스타일로,
가상 마을 주민들이 정책 시행 후 시간이 흐르며 '각자의 모습으로' 어떻게
살아가는지를 시뮬레이션한다.

핵심 가치 = 차등적 영향(differential impact):
  같은 정책이 누구에겐 도움, 누구에겐 무의미, 누구에겐 그림의 떡(사각지대)이
  되는지를, 페르소나 특징에 grounding 된 LLM 서사로 보여준다.

흐름:
  스텝(시간 경과)마다 각 주민에 대해 LLM 이 '이 시점의 삶'을 생성한다.
  직전까지의 삶 요약(history)을 입력으로 넘겨, 궤적이 연속되게 한다.
  누적 결과가 각 주민의 timeline 이 된다.

import 시점에는 어떤 LLM 호출도 하지 않는다(함수 실행 시에만).

공개 API:
    simulate_village(personas, policy, step_labels=None, grounded=True,
                     max_workers=8) -> dict
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from graph.llm import structured_call, run_threaded
from graph.spaces import PLACE_KEYS, space_menu_text
from prompts import build_village_messages


# ---------------------------------------------------------------------------
# LLM 구조화 출력 스키마
# ---------------------------------------------------------------------------
class VillageStepOut(BaseModel):
    """한 주민의 한 시점 삶(구조화 출력)."""
    # place 의 후보값은 graph.spaces.PLACE_KEYS 와 반드시 일치해야 한다.
    place: Literal[
        "online_portal", "community_center", "welfare_center", "work_market", "home"
    ] = Field(description="이 시점 주민이 닿은 장소(정책 채널) 키")
    reached_via: str = Field(
        description="이 정책을 어떻게/누구를 통해 알게 되거나 신청에 닿았는지 한 줄로"
        "(예: 딸이 대신 알려줌, 동료 입소문, 복지사 안내, 공지문, 직접 검색). "
        "어느 경로로도 닿지 못했으면 그 사실을 쓰세요."
    )
    action: str = Field(description="이 기간의 행동·사건, 2~4문장")
    policy_status: Literal["unaware", "aware", "applied", "received", "blocked"]
    barrier: str = Field(
        description="신청·접근이 막힌 경우(blocked) 정확히 어디서 막혔는지 한 줄로"
        "(예: 온라인 본인인증, 소득 요건 초과, 서류 미비). 막히지 않았으면 빈 문자열."
    )
    economic: int = Field(ge=0, le=100, description="경제적 여유")
    wellbeing: int = Field(ge=0, le=100, description="심리적 안정·만족")
    note: str = Field(description="이번 시점 한 줄 요약")


# 기본 스텝(시간 경과) 라벨. 대화 스텝 = 시간 경과.
DEFAULT_STEPS = ["시행 1개월 후", "시행 3개월 후", "시행 6개월 후"]

# 정책 관여 단계의 진행 순서(폴백/정렬용)
_STATUS_ORDER = ["unaware", "aware", "applied", "received", "blocked"]


def _guard_status(prev: str, cur: str, barrier: str):
    """상태 비퇴행 가드. LLM 이 '알게 된 뒤 다시 unaware' 로 떨어뜨리는 실수를 교정한다.

    - prev 가 applied(실제 신청까지 감) 인데 cur==unaware → blocked(시도했다 막힘)로
      교정하고, barrier 가 비어 있으면 기본 사유를 채운다. (예: 신청하려다 서류에 막혀 포기)
    - prev 가 aware(알기만 함)/received 인데 cur==unaware → 직전 상태 유지(되돌리지 않음).
      ★ aware→unaware 를 'blocked'로 단정하지 않는 게 핵심: 비대상이 그냥 관심을 끊은 걸
      '서류에 막힌 사각'으로 오기하던 문제(46세가 청년정책에 '자격 막힘'으로 잡히던)를 막는다.
      (신청까지 갔다 포기한 진짜 막힘은 prev==applied 로 잡힌다.)
    그 외에는 그대로 둔다.

    Returns: (교정된_status, 교정된_barrier)
    """
    if cur == "unaware" and prev == "applied":
        return "blocked", ((barrier or "").strip() or "신청·서류 절차에서 막혀 포기")
    if cur == "unaware" and prev in ("aware", "received"):
        return prev, barrier
    return cur, barrier


def _bridge_violation(status: str, reached_via: str, barrier: str) -> str:
    """다리 가드(설계방향서 v1.1 §3 축2). 위반 사유를 돌려주고, 정상이면 ''.

    사다리 위 칸(applied/received/blocked)엔 닿은 경로(reached_via)가,
    blocked 엔 막힌 지점(barrier)이 반드시 있어야 한다 — "받았다면 닿은 경로가
    기록되어야 한다"가 '모르는데 받음'을 구조적으로 막는 다리다.
    """
    if status in ("applied", "received", "blocked") and not (reached_via or "").strip():
        return f"policy_status={status} 인데 reached_via(닿은 경로)가 비어 있음"
    if status == "blocked" and not (barrier or "").strip():
        return "policy_status=blocked 인데 barrier(막힌 지점)가 비어 있음"
    return ""


# 다리 가드 위반 시 1회 재생성에 덧붙이는 피드백(같은 시점을 다시 기록).
_BRIDGE_RETRY_MSG = (
    "방금 기록에 누락이 있습니다: {reason}.\n"
    "신청(applied)·수령(received)·막힘(blocked)이려면 이 정책에 어떻게 닿았는지 "
    "reached_via 를, blocked 이면 어디서 막혔는지 barrier 를 반드시 채워 "
    "같은 시점을 다시 기록하세요. 닿은 경로를 쓸 수 없다면 이 주민은 아직 정책에 "
    "닿지 않은 것입니다(unaware 또는 aware 로 두세요)."
)


# ---------------------------------------------------------------------------
# 메인 시뮬레이션
# ---------------------------------------------------------------------------
def simulate_village(
    personas: list,
    policy: str,
    step_labels: list | None = None,
    grounded: bool = True,
    max_workers: int = 8,
    reactions_by_id: dict | None = None,
) -> dict:
    """마을 주민들의 정책 영향 궤적을 시뮬레이션한다.

    Args:
        personas: list[Persona dict].
        policy: 시뮬레이션 대상 정책 원문.
        step_labels: 시점 라벨 리스트(기본 1·3·6개월 후).
        grounded: True=특징 grounding, False=익명(ablation 대조군).
        max_workers: 주민 동시 처리 스레드 수.

    Returns:
        {"steps": [...], "residents": [Resident...], "aggregate": {...}}
    """
    personas = personas or []
    step_labels = step_labels or DEFAULT_STEPS
    reactions_by_id = reactions_by_id or {}  # 주민별 1차 반응(A-2 grounding), 없으면 {}
    space_menu = space_menu_text()  # 프롬프트 주입용 장소 메뉴(1회 계산, 순수)

    # 주민별 누적 컨테이너
    residents = {
        p["id"]: {"id": p["id"], "name": p.get("name", p["id"]), "timeline": []}
        for p in personas
    }
    histories = {p["id"]: "" for p in personas}  # 시점 요약 누적
    bridge_retries = 0      # 다리 가드: 재생성으로 교정한 횟수
    bridge_residuals = 0    # 다리 가드: 재생성 후에도 남아 코드로 교정 표기한 횟수

    for si, label in enumerate(step_labels, start=1):

        def _one(persona: dict) -> dict:
            pid = persona["id"]
            try:
                msgs = build_village_messages(
                    persona, policy, histories[pid], label,
                    grounded=grounded, space_menu=space_menu,
                    reaction=reactions_by_id.get(pid),
                )
                out: VillageStepOut = structured_call(
                    msgs, VillageStepOut, temperature=0.8
                )
                # 다리 가드: 위반이면 그 주민 그 스텝만 1회 재생성(사유를 피드백).
                violation = _bridge_violation(
                    out.policy_status, out.reached_via, out.barrier
                )
                retried = False
                if violation:
                    retry_msgs = msgs + [{
                        "role": "user",
                        "content": _BRIDGE_RETRY_MSG.format(reason=violation),
                    }]
                    out = structured_call(retry_msgs, VillageStepOut, temperature=0.8)
                    retried = True
                return {
                    "id": pid, "step": si, "label": label, "place": out.place,
                    "reached_via": out.reached_via,
                    "action": out.action, "policy_status": out.policy_status,
                    "barrier": out.barrier,
                    "economic": int(out.economic), "wellbeing": int(out.wellbeing),
                    "note": out.note,
                    "_bridge_retried": retried,
                }
            except Exception:
                # 실패 시 직전 상태를 이어받아 시뮬레이션을 멈추지 않는다.
                prev = residents[pid]["timeline"][-1] if residents[pid]["timeline"] else None
                return {
                    "id": pid, "step": si, "label": label,
                    "place": prev["place"] if prev else "home",
                    "reached_via": prev.get("reached_via", "") if prev else "",
                    "action": "(이 시점 기록 생성 실패)",
                    "policy_status": prev["policy_status"] if prev else "unaware",
                    "barrier": prev.get("barrier", "") if prev else "",
                    "economic": prev["economic"] if prev else 50,
                    "wellbeing": prev["wellbeing"] if prev else 50,
                    "note": "(기록 없음)",
                }

        results = run_threaded(personas, _one, max_workers=max_workers)

        for res in results:
            pid = res["id"]
            tl = residents[pid]["timeline"]
            prev_step = tl[-1] if tl else None
            # 상태 비퇴행 가드: 알게 된 뒤 unaware 로 떨어지는 LLM 실수를 교정.
            prev_status = prev_step["policy_status"] if prev_step else "unaware"
            res["policy_status"], res["barrier"] = _guard_status(
                prev_status, res["policy_status"], res.get("barrier", "")
            )
            # 다리 가드 마무리: 재생성 횟수 집계 + (비퇴행 교정 이후 기준) 잔존 위반은
            # 코드로 교정 표기한다. 라벨은 뒤집지 않는다(서사-라벨 일치, §1.5) —
            # 한 번 닿은 다리는 기록에 남으므로 직전 스텝 경로를 상속하고,
            # 그것도 없으면 누락을 숨기지 않는 표기를 남긴다(정직 노트로 노출).
            if res.pop("_bridge_retried", False):
                bridge_retries += 1
            residual = _bridge_violation(
                res["policy_status"], res.get("reached_via", ""),
                res.get("barrier", ""),
            )
            if residual:
                bridge_residuals += 1
                if not (res.get("reached_via") or "").strip():
                    inherited = (prev_step.get("reached_via") or "").strip() \
                        if prev_step else ""
                    res["reached_via"] = inherited or "(경로 기록 누락)"
                if res["policy_status"] == "blocked" \
                        and not (res.get("barrier") or "").strip():
                    res["barrier"] = "(막힌 지점 기록 누락)"
            tl.append(
                {k: res[k] for k in
                 ("step", "label", "place", "reached_via", "action",
                  "policy_status", "barrier", "economic", "wellbeing", "note")}
            )
            # 다음 스텝이 볼 history 갱신(한 줄 요약 누적).
            histories[pid] = (
                histories[pid] + f"\n- {label}: {res['note']}"
            ).strip()

    # 최종 상태 정리 + Resident 리스트화(personas 순서 유지)
    resident_list = []
    for p in personas:
        r = residents[p["id"]]
        last = r["timeline"][-1] if r["timeline"] else {}
        r["policy_status"] = last.get("policy_status", "unaware")
        r["economic"] = last.get("economic", 50)
        r["wellbeing"] = last.get("wellbeing", 50)
        resident_list.append(r)

    aggregate = _aggregate_village(resident_list, step_labels)
    # 다리 가드 통계(정직 노트의 원천 — contrast 가 selection.notes 로 노출).
    aggregate["bridge_guard"] = {
        "retries": bridge_retries, "residuals": bridge_residuals,
    }
    return {"steps": step_labels, "residents": resident_list, "aggregate": aggregate}


# ---------------------------------------------------------------------------
# 집계: 수령률 추이 / 사각지대 / 차등영향
# ---------------------------------------------------------------------------
def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _aggregate_village(residents: list, step_labels: list) -> dict:
    """마을 전체의 시점별 추이, 사각지대, 최대 수혜/소외자를 집계한다."""
    nsteps = len(step_labels)

    # 시점별 평균 지표 + 수령률
    per_step = []
    for i in range(nsteps):
        ec, wb, recv, n = [], [], 0, 0
        for r in residents:
            if i < len(r["timeline"]):
                t = r["timeline"][i]
                ec.append(t["economic"])
                wb.append(t["wellbeing"])
                if t["policy_status"] == "received":
                    recv += 1
                n += 1
        per_step.append({
            "label": step_labels[i],
            "avg_economic": round(_mean(ec), 1),
            "avg_wellbeing": round(_mean(wb), 1),
            "received_rate": round(recv / n, 3) if n else 0.0,
        })

    # 사각지대 = 최종적으로 정책을 못 받은(모름/막힘) 주민
    blindspot = [
        {"id": r["id"], "name": r["name"], "status": r["policy_status"]}
        for r in residents if r["policy_status"] in ("unaware", "blocked")
    ]

    # 차등영향 = (최종 economic+wellbeing) - (최초 economic+wellbeing)
    deltas = []
    for r in residents:
        if r["timeline"]:
            first, last = r["timeline"][0], r["timeline"][-1]
            d = (last["economic"] + last["wellbeing"]) - (
                first["economic"] + first["wellbeing"]
            )
            deltas.append({"id": r["id"], "name": r["name"], "delta": d,
                           "final_status": r["policy_status"]})
    deltas.sort(key=lambda x: x["delta"], reverse=True)

    # 장소별 사건 뷰 + 채널 도달 (공간 트리 MVP의 핵심 산출)
    per_place, place_reach, home_bound = _place_views(residents, step_labels)

    return {
        "per_step": per_step,
        "blindspot": blindspot,
        "blindspot_rate": round(len(blindspot) / len(residents), 3) if residents else 0.0,
        "winners": deltas[:3],          # 최대 수혜자
        "losers": deltas[-3:][::-1],    # 최대 소외/악화자
        "n": len(residents),
        # --- 장소(채널) 기반 집계 ---
        "per_place": per_place,         # [{label, places:{place_key:[{id,name,status,note}...]}}]
        "place_reach": place_reach,     # {place_key: 한 번이라도 닿은 주민 수}
        "home_bound": home_bound,       # 모든 시점을 집에서만 보낸 주민(깊은 사각지대)
    }


def _place_views(residents: list, step_labels: list):
    """장소별 사건 뷰, 채널 도달 수, 집에만 머문 주민을 집계한다.

    Returns:
        per_place  : 시점별 [{label, places:{place_key:[{id,name,status,note}...]}}]
        place_reach: {place_key: 한 번이라도 그 장소에 닿은 주민 수}
        home_bound : 모든 시점을 home 에서만 보낸 주민(깊은 사각지대) [{id,name}]
    """
    per_place = []
    for i, label in enumerate(step_labels):
        bucket = {k: [] for k in PLACE_KEYS}
        for r in residents:
            if i < len(r["timeline"]):
                t = r["timeline"][i]
                pk = t.get("place") or "home"
                bucket.setdefault(pk, [])
                bucket[pk].append({
                    "id": r["id"], "name": r["name"],
                    "status": t.get("policy_status", "unaware"),
                    "note": t.get("note", ""),
                })
        per_place.append({"label": label, "places": bucket})

    place_reach = {k: 0 for k in PLACE_KEYS}
    home_bound = []
    for r in residents:
        if not r["timeline"]:
            continue
        visited = [t.get("place") or "home" for t in r["timeline"]]
        for pk in set(visited):
            place_reach[pk] = place_reach.get(pk, 0) + 1
        if all(pk == "home" for pk in visited):
            home_bound.append({"id": r["id"], "name": r["name"]})

    return per_place, place_reach, home_bound
