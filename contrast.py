# -*- coding: utf-8 -*-
"""contrast.py — 정책 인생극장 오케스트레이션 (DESIGN v3, 결과 기반 선별).

정책 패키지(여러 정책)를 받아 한 흐름으로 묶는다:

    정책 패키지(list)
      → policy_spec.resolve_specs    : 각 정책의 타깃 명세(프롬프트 힌트/표시용)
      → graph.village.simulate_village: **전원**의 시간 경과 인생 시뮬(정책 패키지 주입,
                                        각자의 1차 반응으로 grounding)
      → select_trio_from_outcomes    : 실제 시뮬 *결과*에서 대조 3명(수혜/경계/사각) 선별

핵심 설계(2026-06): 수혜/경계/사각은 '시뮬 전 점수'(직업→소득 매트릭스도, 반응
benefit/intent 점수도)로 예측하지 않는다. 그런 예측은 틀릴 수 있다(예: 임수빈은
스스로 수혜 가능성을 낮게 매기지만 실제로는 자격이 되는데 부모 동거 요건에 막힌
사각지대다). 전원을 먼저 '살게' 한 뒤, **실제 결과(받음/막힘/못 닿음)** 에서 대조
3명을 고른다 → 카드의 라벨과 이야기가 같은 데서 나오므로 어긋날 수 없다.

Streamlit 의존이 없어 헤드리스로 검증 가능하다(_verify_contrast.py / _test_outcome_select.py).
import 시점에는 어떤 네트워크/LLM 호출도 하지 않는다.

공개 API:
    run_contrast(personas, policies, simulate=None, ..., reactions_by_id=None) -> dict
    select_trio_from_outcomes(residents, personas, specs=None) -> dict
"""
from __future__ import annotations

from policy_spec import resolve_specs, package_text
from data.personas import is_target


# 역할 키(role_key) → 표시명. 대상 여부=태그(사실), 결과(수혜/막힘)=시뮬 궤적.
_ROLE_LABEL = {
    "beneficiary": "수혜",
    "borderline": "경계",
    "blindspot": "사각지대",
    "out": "대상 아님",
}
# 표시/정렬 순서: 수혜 → 경계 → 사각
_ROLE_ORDER = {"beneficiary": 0, "borderline": 1, "blindspot": 2}


def run_contrast(
    personas: list,
    policies,
    simulate=None,
    grounded: bool = True,
    step_labels: list | None = None,
    max_workers: int = 8,
    use_llm_spec: bool = True,
    specs: list | None = None,
    reactions_by_id: dict | None = None,
) -> dict:
    """정책 패키지 → 전원 인생 시뮬 → 결과에서 대조 3명 선별, 한 번에 실행한다.

    Args:
        personas: list[Persona dict] (load_personas 결과, 시뮬 대상 전원).
        policies: 정책 패키지. 정책명(SAMPLES 키)/원문/{name,text} 의 list(또는 단일).
        simulate: (personas, policy_text, step_labels) -> village dict 콜러블.
                  None 이면 graph.village.simulate_village 를 실제 실행한다.
                  (mock 검증 시 ui.mock.sample_village 래퍼를 주입.)
        grounded: 페르소나 grounding 토글(ablation 시 False).
        step_labels: 시점 라벨(기본 simulate_village 의 1·3·6개월).
        use_llm_spec: 임의 정책의 명세를 LLM 으로 추출할지(False=키워드 폴백).
        specs: 이미 만들어진 타깃 명세(list). 주어지면 resolve_specs 를 건너뛴다.
        reactions_by_id: {persona_id: Reaction}. 주어지면 마을 시뮬을 각자의 1차 반응으로
                  grounding 한다(인생극장이 '시민 반응'과 같은 출발점을 갖게 함). 멀티정책
                  데모 등 반응이 정책과 대응하지 않을 땐 None. (선별은 시뮬 결과만 보므로
                  이 인자를 쓰지 않는다 — 시딩 전용.)

    Returns:
        {
          "specs":        list[spec dict],            # 정책별 타깃 명세(표시/힌트용)
          "selection":    select_trio_from_outcomes 결과 {specs, trio, outcomes, notes},
          "package_text": str,                        # 시뮬에 주입한 패키지 원문
          "village":      {steps, residents, aggregate},  # **전원** 인생 궤적
          "trio_ids":     [선별된 3명 id],
        }
    """
    personas = personas or []
    # 1) 정책 → 타깃 명세(패키지). specs 가 주어지면(사이드바 policy_spec) 재추출 생략.
    if specs is None:
        specs = resolve_specs(policies, use_llm=use_llm_spec)
    bundle = package_text(specs)

    # 2) **전원**의 시간 경과 인생 시뮬(정책 패키지 텍스트 주입 + 각자 1차 반응 grounding).
    #    3명만 미리 고르지 않는다 — 결과를 봐야 누가 수혜/경계/사각인지 정확히 안다.
    if not personas:
        village = {"steps": step_labels or [], "residents": [], "aggregate": {}}
    elif simulate is not None:
        # mock 검증: sample_village 래퍼((personas, policy_text, step_labels) 시그니처).
        village = simulate(personas, bundle, step_labels)
    else:
        from graph.village import simulate_village
        village = simulate_village(
            personas, bundle, step_labels=step_labels,
            grounded=grounded, max_workers=max_workers,
            reactions_by_id=reactions_by_id,
        )

    # 3) 실제 결과에서 대조 3명 선별(순수, LLM 0). 선별은 시뮬 결과만 본다(반응 미사용).
    selection = select_trio_from_outcomes(
        village.get("residents") or [], personas, specs
    )
    trio_ids = [(t.get("persona") or {}).get("id") for t in selection.get("trio", [])]

    # 다리 가드 정직 노트(설계방향서 §2 불변규칙 3): 가드가 일한 것도, 잔존 위반을
    # 코드로 교정 표기한 것도 숨기지 않고 노출한다.
    bg = (village.get("aggregate") or {}).get("bridge_guard") or {}
    if bg.get("retries"):
        selection.setdefault("notes", []).append(
            f"ⓘ 다리 가드: 경로(reached_via)·막힌 지점(barrier) 누락 "
            f"{bg['retries']}건을 그 주민·그 시점만 재생성했습니다."
        )
    if bg.get("residuals"):
        selection.setdefault("notes", []).append(
            f"⚠ 다리 가드: 모순 감지 {bg['residuals']}건 — 재생성 후에도 경로가 비어 "
            f"직전 경로 상속/'(기록 누락)' 표기로 교정했습니다(라벨은 뒤집지 않음)."
        )

    return {
        "specs": specs,
        "selection": selection,
        "package_text": bundle,
        "village": village,
        "trio_ids": trio_ids,
    }


# ===========================================================================
# 결과 기반 선별 — 시뮬 궤적의 실제 결과에서 대조 3명을 고른다 (순수, LLM 0)
# ===========================================================================
def _resident_outcome(resident: dict, persona: dict | None, specs=None) -> dict:
    """주민 1명의 궤적에서 결과 요약을 뽑는다(순수).

    먼저 태그(나이·소득·가구)로 '이 정책 대상인가'를 사실 판정하고(is_target),
    대상자에 한해 시뮬 *결과*로 역할을 정한다. 비대상은 결과와 무관하게 '대상 아님(무관)'.

    dist_key (사람 단위 범주 — 분포 막대·결과표·역할 공용):
      out       : 정책 대상이 아님(나이·소득·가구 조건 밖)         → role out(대상 아님)
      received  : (대상) 한 번이라도 수령(혜택 받음)               → beneficiary(수혜)
      blocked   : (대상) 막힌 적 있음 — 막힌 사유(요건/절차/…)는 barrier
                  인용이 말한다. 코드는 자격 여부를 단정하지 않는다.   → blindspot(사각)
      unaware   : (대상) 끝내 정책을 알지도 못함(못 닿음)           → blindspot(사각)
      inprogress: (대상) 그 외(알게 됨/신청 대기 — 진행 중)         → borderline(경계)
    """
    tl = resident.get("timeline") or []
    raw_final = tl[-1].get("policy_status", "unaware") if tl else "unaware"
    ever_blocked = any((s.get("policy_status") == "blocked") for s in tl)
    ever_received = any((s.get("policy_status") == "received") for s in tl)

    target = is_target(persona or {}, specs)
    if not target:
        dist_key, role_key = "out", "out"
    elif ever_received:
        dist_key, role_key = "received", "beneficiary"
    elif ever_blocked:
        dist_key, role_key = "blocked", "blindspot"
    elif raw_final == "unaware":
        dist_key, role_key = "unaware", "blindspot"
    else:
        dist_key, role_key = "inprogress", "borderline"

    e0 = tl[0].get("economic", 0) if tl else 0
    eN = tl[-1].get("economic", 0) if tl else 0
    w0 = tl[0].get("wellbeing", 0) if tl else 0
    wN = tl[-1].get("wellbeing", 0) if tl else 0

    # 막힌 지점(barrier)과 마지막으로 정책에 닿은 경로(reached_via)를 끌어온다.
    barrier = ""
    for s in tl:
        if s.get("policy_status") == "blocked" and (s.get("barrier") or "").strip():
            barrier = s["barrier"].strip()
            break
    reached_via = ""
    for s in reversed(tl):
        rv = (s.get("reached_via") or "").strip()
        if rv:
            reached_via = rv
            break

    # 수령자(중간에 막혔어도) / 비대상(무관)은 '막힌 지점'을 결과에 노출하지 않는다
    # (최종 결과·역할과 모순되지 않게 — 라벨이 이야기와 어긋나지 않게).
    if ever_received or not target:
        barrier = ""

    demo = (persona or {}).get("demographics") or {}
    return {
        "id": resident.get("id"),
        "name": resident.get("name", resident.get("id")),
        "age": demo.get("age", 0),
        "raw_final": raw_final,
        "dist_key": dist_key,
        "role_key": role_key,
        "ever_blocked": ever_blocked,
        "ever_received": ever_received,
        "econ_delta": eN - e0,
        "wb_delta": wN - w0,
        "delta": (eN - e0) + (wN - w0),
        "barrier": barrier,
        "reached_via": reached_via,
        "is_target": target,
    }


def _outcome_headline(row: dict) -> str:
    """결과 한 줄 = 상태 라벨 + LLM 인용(barrier/reached_via)뿐.

    코드는 문장을 짓지 않는다 — 스키마 토큰의 사전적 의미와 인용까지가 코드의 몫,
    '왜·어떻게'는 시뮬 서사(action/barrier)가 말한다. (2026-06-06 천명준 사건:
    구 템플릿이 '자격은 됐지만'·'신청을 시도했지만'을 지어내 서사와 모순 —
    실제로는 신청 없이 요건 확인만 하고 막힌 사람이었다.)
    """
    k = row["dist_key"]
    if k == "out":
        # 유일하게 코드가 말하는 판정 — is_target 태그 게이트의 결정론 결과라서.
        return "대상 아님 — 나이·소득·가구 태그 조건 밖"
    if k == "received":
        via = (row.get("reached_via") or "").strip()
        return f"수령 — {via}" if via else "수령"
    if k == "blocked":
        b = (row.get("barrier") or "").strip()
        return f"막힘 — {b}" if b else "막힘"
    if k == "unaware":
        return "끝내 모름"
    # inprogress
    if row["raw_final"] == "applied":
        return "신청 — 결과 대기"
    return "알게 됨 — 신청까지는 안 감"


def _trio_entry(row: dict, by_id: dict) -> dict:
    """선별된 1명을 trio 항목 dict 로 포장.

    role_key 는 그 사람의 *실제 결과*(row["role_key"])를 그대로 쓴다 — 슬롯을 강제로
    채우지 않는다. (예: 받은 사람이 없으면 '수혜' 카드를 억지로 만들지 않는다.)
    """
    persona = by_id.get(row["id"], {"id": row["id"], "name": row["name"]})
    role_key = row["role_key"]
    return {
        "role_key": role_key,
        "role": _ROLE_LABEL.get(role_key, role_key),
        "kind": None,
        "persona": persona,
        "score": {
            "final_status": row["raw_final"],
            "dist_key": row["dist_key"],
            "ever_blocked": row["ever_blocked"],
            "ever_received": row["ever_received"],
            "econ_delta": row["econ_delta"],
            "wb_delta": row["wb_delta"],
            "barrier": row["barrier"],
            "reached_via": row["reached_via"],
        },
        "headline": _outcome_headline(row),
    }


# 그룹(카테고리) 안에서 '대표'가 맨 앞에 오도록 하는 정렬 키.
def _group_sort_key(role_key: str):
    if role_key == "beneficiary":      # 수혜: 삶이 가장 좋아진 순
        return lambda r: -r["delta"]
    if role_key == "blindspot":        # 사각: 막힘(강) 먼저, 그다음 삶이 가장 나빠진 순
        return lambda r: (0 if r["dist_key"] == "blocked" else 1, r["delta"])
    # borderline(경계): 신청까지 간 사람 먼저, 그다음 결과가 중간(델타 0에 가까운)
    return lambda r: (0 if r["raw_final"] == "applied" else 1, abs(r["delta"]))


def select_trio_from_outcomes(
    residents: list, personas: list, specs: list | None = None,
) -> dict:
    """전원 시뮬 결과를 대상자에 한해 역할별로 묶고, 각 그룹의 대표를 뽑는다(순수, LLM 0).

    역할은 '시뮬 전 점수'가 아니라 **실제 결과 × 태그 대상여부**에서 나온다:
      비대상=무관(out) / (대상) 수혜=받음 / 사각=막힘(강)·못 닿음 / 경계=진행 중.
    비대상(out)은 카드 그룹에서 제외(분포·결과표에만). 각 그룹의 첫 사람이 '대표'(trio),
    나머지는 같은 그룹의 하위 항목으로 펼친다.

    Returns:
        {specs, trio:[대표 entry...], groups:{role_key:[entry...]}, outcomes:[row...], notes}
        groups: 카테고리별 전원 엔트리(대표 먼저 정렬). outcomes: 전원 결과 행(분포·표 공용).
    """
    by_id = {p.get("id"): p for p in (personas or [])}
    rows = [_resident_outcome(r, by_id.get(r.get("id")), specs) for r in (residents or [])]
    if not rows:
        return {"specs": specs or [], "trio": [], "groups": {}, "outcomes": [],
                "notes": ["시뮬 결과가 없어 대조를 만들 수 없습니다."]}

    # 대상자만 카드로(비대상=무관은 분포·표에만). 역할별로 묶고 그룹 안에서 대표가 앞에.
    targets = [r for r in rows if r["role_key"] != "out"]
    n_out = len(rows) - len(targets)

    buckets = {"beneficiary": [], "borderline": [], "blindspot": []}
    for r in targets:
        buckets[r["role_key"]].append(r)
    for rk, members in buckets.items():
        members.sort(key=_group_sort_key(rk))

    order = ("beneficiary", "borderline", "blindspot")  # 표시 순서: 수혜 → 경계 → 사각
    groups = {rk: [_trio_entry(r, by_id) for r in buckets[rk]] for rk in order}
    rep_rows = [buckets[rk][0] for rk in order if buckets[rk]]   # 각 그룹 대표(첫 사람)
    trio = [_trio_entry(r, by_id) for r in rep_rows]

    notes = _selection_notes(targets, rep_rows, n_out)
    return {"specs": specs or [], "trio": trio, "groups": groups,
            "outcomes": rows, "notes": notes}


def _selection_notes(targets: list, picks: list, n_out: int) -> list:
    """선별 결과의 정직한 경고/메모(대상자 기준). 검증 공격을 정면으로 받는 산출물."""
    notes: list = []
    if not targets:
        notes.append("⚠ 이 정책의 대상(나이·소득·가구 조건)에 드는 사람이 풀에 없습니다.")
    n_recv = sum(1 for r in targets if r["dist_key"] == "received")
    n_block = sum(1 for r in targets if r["dist_key"] == "blocked")
    n_unaware = sum(1 for r in targets if r["dist_key"] == "unaware")

    if targets and n_recv == 0:
        notes.append("⚠ 대상자 중 실제로 혜택을 받은 사람이 없습니다 — 정책이 대상에게도 닿지 못했습니다.")
    if picks and len({r["role_key"] for r in picks}) <= 1:
        notes.append("⚠ 대조가 약합니다 — 세 사람의 결과가 크게 다르지 않습니다.")

    blind = next((r for r in picks if r["role_key"] == "blindspot"), None)
    if blind:
        if blind["dist_key"] == "blocked":
            notes.append(f"사각지대 = 자격은 되는데 절차에 막힌 사람({blind['name']}).")
        elif blind["dist_key"] == "unaware":
            notes.append(f"사각지대 = 자격은 되는데 정책에 끝내 닿지 못한 사람({blind['name']}).")
    elif targets and n_block == 0 and n_unaware == 0:
        notes.append("ⓘ 대상자 중 막히거나 못 닿은 사람이 없어 뚜렷한 사각지대는 나타나지 않았습니다.")
    if n_out:
        notes.append(f"ⓘ 풀의 {n_out}명은 이 정책 대상이 아니어서(무관) 대조에서 제외했습니다.")
    return notes
