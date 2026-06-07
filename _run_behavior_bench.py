# -*- coding: utf-8 -*-
"""_run_behavior_bench.py — 행동 벤치마크 v1 채점 (LLM 0콜).

데모 녹화본(data/demo_snapshots/<정책명>.json)의 reactions 를 읽어
eval/behavior_bench_v1.md 에 사전등록된 체크(B1~B5, 7개)를 판정하고
특징 발언을 추출한다. 녹화가 곧 측정 — 같은 자극·같은 풀(24명 seed42).

산출: eval/behavior_bench_results.json · eval/behavior_bench_report.md
사용: python _run_behavior_bench.py
"""
import json
import sys
import io
from pathlib import Path
from collections import Counter
from statistics import mean

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

SNAP_DIR = ROOT / "data" / "demo_snapshots"
OUT_JSON = ROOT / "eval" / "behavior_bench_results.json"
OUT_MD = ROOT / "eval" / "behavior_bench_report.md"

BENCH = ["주 3.5일 근무제", "전 국민 반려묘 보급", "경로 무임승차 폐지",
         "성별 균형 기여금", "고소득자 의무 나눔제"]

# 집단행동 신호 키워드 (사전등록: actions·behavior_text 에서 탐지)
ACTION_KW = ("민원", "항의", "서명", "시위", "국민신문고", "청원", "집회", "불매")
# B2 관찰: 찬성자 서사의 동물 친화 단서
CAT_KW = ("고양이", "반려", "동물", "강아지", "펫", "냥")
# B5 관찰: '기부의 의무화 = 모순' 류 지적
PARADOX_KW = ("모순", "강제", "기부가 아니", "세금이나 마찬가지", "준조세", "이름만 기부")


def load_snap(name: str):
    p = SNAP_DIR / f"{name}.json"
    if not p.exists():
        return None
    snap = json.loads(p.read_text(encoding="utf-8"))
    rows = [r for r in (snap.get("sim") or {}).get("reactions") or []
            if r.get("text") and "생성 실패" not in r.get("text", "")]
    return {"snap": snap, "rows": rows, "llm_model": snap.get("llm_model", "?")}


# ---------------------------------------------------------------------------
# 공통 측정
# ---------------------------------------------------------------------------
def stance_pct(rows, pred=None):
    """(찬, 반, 혼합) % — pred 로 집단 필터."""
    rs = [r for r in rows if pred is None or pred(r)]
    n = len(rs)
    if n == 0:
        return {"n": 0, "support": None, "oppose": None, "mixed": None}
    c = Counter(r.get("stance") for r in rs)
    return {"n": n,
            "support": round(100 * c.get("support", 0) / n, 1),
            "oppose": round(100 * c.get("oppose", 0) / n, 1),
            "mixed": round(100 * c.get("mixed", 0) / n, 1)}


def unrest(rows, pred=None):
    rs = [r for r in rows if pred is None or pred(r)]
    vals = [(r.get("scores") or {}).get("dissatisfaction") for r in rs]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(mean(vals), 1) if vals else None


def strong_dissat_pct(rows, pred=None):
    """불만 강함(very/somewhat) 비율 %."""
    rs = [r for r in rows if pred is None or pred(r)]
    if not rs:
        return None
    hit = sum(1 for r in rs
              if (r.get("survey") or {}).get("dissatisfaction") in ("very", "somewhat"))
    return round(100 * hit / len(rs), 1)


def action_signal(rows):
    """집단행동 신호 시민 비율 % + 해당 시민 목록."""
    hits = []
    for r in rows:
        blob = " ".join(list(r.get("actions") or []) + [r.get("behavior_text") or ""])
        if any(kw in blob for kw in ACTION_KW):
            hits.append(r)
    return round(100 * len(hits) / len(rows), 1) if rows else 0.0, hits


def behavior_counts(rows):
    c = Counter((r.get("behavior_class") or "").strip() for r in rows)
    c.pop("", None)
    return dict(c.most_common())


def _q(r, by_id, why):
    """인용 항목 포장."""
    p = by_id.get(r.get("persona_id")) or {}
    d = p.get("demographics") or {}
    return {"name": p.get("name", "?"), "age": d.get("age"),
            "occupation": d.get("occupation", ""), "stance": r.get("stance"),
            "why": why, "text": (r.get("text") or "").strip()[:220],
            "behavior_text": (r.get("behavior_text") or "").strip()[:160],
            "behavior_class": r.get("behavior_class") or ""}


# ---------------------------------------------------------------------------
# 시나리오별 채점
# ---------------------------------------------------------------------------
def score_all(personas):
    by_id = {p["id"]: p for p in personas}
    demo = {p["id"]: p["demographics"] for p in personas}

    def occ_group(pid):
        o = demo[pid]["occupation"]
        if "군" in o:
            return "군인"
        return "무직·은퇴" if ("무직" in o or "은퇴" in o) else "취업자"

    scen = {}
    checks = []
    missing = []

    # ── B1 주 3.5일 근무제 ────────────────────────────────────────────
    d = load_snap("주 3.5일 근무제")
    if d is None:
        missing.append("주 3.5일 근무제")
    else:
        rows = d["rows"]
        emp = stance_pct(rows, lambda r: occ_group(r["persona_id"]) == "취업자")
        job = stance_pct(rows, lambda r: occ_group(r["persona_id"]) == "무직·은퇴")
        sig, sig_rows = action_signal(rows)
        ok = (emp["support"] is not None and job["support"] is not None
              and emp["support"] > job["support"])
        checks.append({"id": "B1", "scenario": "주 3.5일 근무제",
                       "name": "취업자 찬성률 > 무직·은퇴 찬성률",
                       "measured": f"취업자 {emp['support']}% vs 무직·은퇴 {job['support']}%",
                       "pass": bool(ok)})
        # 인용: 취업자 찬성 1 + 의심/우려 1
        quotes = []
        for r in rows:
            if occ_group(r["persona_id"]) == "취업자" and r["stance"] == "support":
                quotes.append(_q(r, by_id, "취업자 환영")); break
        for r in rows:
            t = r.get("text") or ""
            if any(k in t for k in ("임금", "월급", "급여", "사장", "회사", "가능")) \
                    and r["stance"] != "support":
                quotes.append(_q(r, by_id, "임금·실현 의심")); break
        scen["주 3.5일 근무제"] = {
            "overall": stance_pct(rows), "by_group": {"취업자": emp, "무직·은퇴": job},
            "unrest": unrest(rows), "action_signal_pct": sig,
            "behavior": behavior_counts(rows), "quotes": quotes}

    # ── B2 전 국민 반려묘 보급 ────────────────────────────────────────
    d = load_snap("전 국민 반려묘 보급")
    if d is None:
        missing.append("전 국민 반려묘 보급")
    else:
        rows = d["rows"]
        ov = stance_pct(rows)
        ok = ov["support"] is not None and ov["support"] <= 50.0
        checks.append({"id": "B2", "scenario": "전 국민 반려묘 보급",
                       "name": "찬성률 <= 50% (무지성 찬성 아님)",
                       "measured": f"찬성 {ov['support']}%",
                       "pass": bool(ok)})
        # 관찰: 찬성자 서사 동물 친화 / 일탈 / 부담 언급
        supporters = [r for r in rows if r["stance"] == "support"]
        cat_align = []
        for r in supporters:
            p = by_id.get(r["persona_id"]) or {}
            blob = (p.get("persona_text") or "") + " ".join((p.get("meta") or {}).values())
            cat_align.append({"name": p.get("name"),
                              "animal_hint": any(k in blob for k in CAT_KW)})
        deviant = [r for r in rows if (r.get("behavior_class") or "") in
                   ("workaround", "exploit")]
        sig, _ = action_signal(rows)
        quotes = []
        if supporters:
            quotes.append(_q(supporters[0], by_id, "찬성자"))
        for r in rows:
            t = r.get("text") or ""
            if any(k in t for k in ("사료", "책임", "알레르기", "털", "병원", "부담")):
                quotes.append(_q(r, by_id, "부담·책임 인식")); break
        for r in deviant[:2]:
            quotes.append(_q(r, by_id, f"일탈({r.get('behavior_class')})"))
        scen["전 국민 반려묘 보급"] = {
            "overall": ov, "unrest": unrest(rows), "action_signal_pct": sig,
            "behavior": behavior_counts(rows),
            "supporter_animal_alignment": cat_align, "quotes": quotes}

    # ── B3 경로 무임승차 폐지 ─────────────────────────────────────────
    d = load_snap("경로 무임승차 폐지")
    if d is None:
        missing.append("경로 무임승차 폐지")
    else:
        rows = d["rows"]
        old = stance_pct(rows, lambda r: demo[r["persona_id"]]["age"] >= 60)
        yng = stance_pct(rows, lambda r: demo[r["persona_id"]]["age"] < 60)
        old_sd = strong_dissat_pct(rows, lambda r: demo[r["persona_id"]]["age"] >= 60)
        yng_sd = strong_dissat_pct(rows, lambda r: demo[r["persona_id"]]["age"] < 60)
        ok_a = (old["oppose"] is not None and yng["oppose"] is not None
                and old["oppose"] > yng["oppose"])
        ok_b = old_sd is not None and yng_sd is not None and old_sd > yng_sd
        checks.append({"id": "B3-a", "scenario": "경로 무임승차 폐지",
                       "name": "60세+ 반대율 > 60세 미만 반대율",
                       "measured": f"60+ {old['oppose']}% vs 미만 {yng['oppose']}%",
                       "pass": bool(ok_a)})
        checks.append({"id": "B3-b", "scenario": "경로 무임승차 폐지",
                       "name": "60세+ 강한 불만 비율 > 60세 미만",
                       "measured": f"60+ {old_sd}% vs 미만 {yng_sd}%",
                       "pass": bool(ok_b)})
        sig, sig_rows = action_signal(rows)
        quotes = []
        for r in rows:  # 고령 반대 1 + 집단행동 1 + 젊은층 1
            if demo[r["persona_id"]]["age"] >= 60 and r["stance"] == "oppose":
                quotes.append(_q(r, by_id, "고령 반발")); break
        for r in sig_rows:
            quotes.append(_q(r, by_id, "집단행동 신호")); break
        for r in rows:
            if demo[r["persona_id"]]["age"] < 50:
                quotes.append(_q(r, by_id, "젊은층 시선")); break
        scen["경로 무임승차 폐지"] = {
            "overall": stance_pct(rows),
            "by_group": {"60세 이상": old, "60세 미만": yng},
            "strong_dissat": {"60세 이상": old_sd, "60세 미만": yng_sd},
            "unrest": unrest(rows), "action_signal_pct": sig,
            "behavior": behavior_counts(rows), "quotes": quotes}

    # ── B4 성별 균형 기여금 ──────────────────────────────────────────
    d = load_snap("성별 균형 기여금")
    if d is None:
        missing.append("성별 균형 기여금")
    else:
        rows = d["rows"]
        fem = stance_pct(rows, lambda r: demo[r["persona_id"]]["sex"] == "여자")
        mal = stance_pct(rows, lambda r: demo[r["persona_id"]]["sex"] == "남자")
        ok_a = fem["oppose"] is not None and fem["oppose"] >= 70.0
        ok_b = (fem["oppose"] is not None and mal["oppose"] is not None
                and fem["oppose"] > mal["oppose"])
        checks.append({"id": "B4-a", "scenario": "성별 균형 기여금",
                       "name": "여성 반대율 >= 70% (거의 전원)",
                       "measured": f"여성 반대 {fem['oppose']}%",
                       "pass": bool(ok_a)})
        checks.append({"id": "B4-b", "scenario": "성별 균형 기여금",
                       "name": "여성 반대율 > 남성 반대율",
                       "measured": f"여 {fem['oppose']}% vs 남 {mal['oppose']}%",
                       "pass": bool(ok_b)})
        sig, _ = action_signal(rows)
        quotes = []
        for r in rows:
            if demo[r["persona_id"]]["sex"] == "여자" and r["stance"] == "oppose":
                quotes.append(_q(r, by_id, "여성 반발")); break
        # 관찰의 핵심: 남성 반응 — 찬성 1 + 반대 1 (있으면)
        for st, why in (("oppose", "남성의 규범적 반대"), ("support", "남성의 이득 수용")):
            for r in rows:
                if demo[r["persona_id"]]["sex"] == "남자" and r["stance"] == st:
                    quotes.append(_q(r, by_id, why)); break
        scen["성별 균형 기여금"] = {
            "overall": stance_pct(rows),
            "by_group": {"여성": fem, "남성": mal},
            "unrest": unrest(rows),
            "unrest_by_group": {"여성": unrest(rows, lambda r: demo[r["persona_id"]]["sex"] == "여자"),
                                 "남성": unrest(rows, lambda r: demo[r["persona_id"]]["sex"] == "남자")},
            "action_signal_pct": sig, "behavior": behavior_counts(rows),
            "quotes": quotes}

    # ── B5 고소득자 의무 나눔제 ──────────────────────────────────────
    d = load_snap("고소득자 의무 나눔제")
    if d is None:
        missing.append("고소득자 의무 나눔제")
    else:
        rows = d["rows"]
        is_tgt = lambda r: (r.get("survey") or {}).get("eligibility") == "target"
        tgt = [r for r in rows if is_tgt(r)]
        non = [r for r in rows if not is_tgt(r)]
        u_t, u_n = unrest(tgt), unrest(non)
        ok = u_t is not None and u_n is not None and u_t > u_n
        checks.append({"id": "B5", "scenario": "고소득자 의무 나눔제",
                       "name": "자가판정 대상자 불만 평균 > 비대상자",
                       "measured": f"대상({len(tgt)}명) {u_t} vs 비대상({len(non)}명) {u_n}",
                       "pass": bool(ok)})
        paradox = [r for r in rows
                   if any(k in (r.get("text") or "") for k in PARADOX_KW)]
        sig, _ = action_signal(rows)
        quotes = []
        if tgt:
            quotes.append(_q(tgt[0], by_id, "자가판정 대상자"))
        for r in paradox:
            quotes.append(_q(r, by_id, "'강제 기부 모순' 지적")); break
        for r in non:
            if r["stance"] == "support":
                quotes.append(_q(r, by_id, "비대상의 시선")); break
        scen["고소득자 의무 나눔제"] = {
            "overall": stance_pct(rows),
            "by_group": {"자가판정 대상": stance_pct(rows, is_tgt),
                          "비대상": stance_pct(rows, lambda r: not is_tgt(r))},
            "unrest_target": u_t, "unrest_nontarget": u_n,
            "n_self_target": len(tgt), "paradox_mentions": len(paradox),
            "unrest": unrest(rows), "action_signal_pct": sig,
            "behavior": behavior_counts(rows), "quotes": quotes}

    return scen, checks, missing


# ---------------------------------------------------------------------------
def main():
    from data.personas import load_personas
    personas = load_personas(24, 42)

    scen, checks, missing = score_all(personas)
    if missing:
        print("녹화본 없음(미채점):", missing)

    n_pass = sum(c["pass"] for c in checks)
    overall = n_pass >= 6  # 사전등록: 7개 중 6개 이상
    model = "?"
    for name in BENCH:
        d = load_snap(name)
        if d:
            model = d["llm_model"]
            break

    OUT_JSON.parent.mkdir(exist_ok=True)
    json.dump({"bench": "behavior_bench_v1", "model": model,
               "prereg": "eval/behavior_bench_v1.md",
               "n_pass": n_pass, "n_checks": len(checks),
               "overall_pass": overall, "missing": missing,
               "checks": checks, "scenarios": scen},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    L = ["# 행동 벤치마크 v1 — 스코어카드", "",
         f"- 모델: {model} · 풀: 24명(seed 42) · 채점: 녹화본에서 0콜",
         f"- 기준: eval/behavior_bench_v1.md (녹화 전 사전등록)", "",
         f"## 판정: **{n_pass}/{len(checks)}** -> "
         f"{'통과' if overall else '미달'} (기준 6+)", "",
         "| # | 시나리오 | 체크 | 측정값 | 판정 |", "|---|---|---|---|---|"]
    for c in checks:
        L.append(f"| {c['id']} | {c['scenario']} | {c['name']} | {c['measured']} | "
                 f"{'통과' if c['pass'] else '**미달**'} |")
    L.append("")
    L.append("상세·인용·시각화: notebooks/행동벤치_v1.ipynb")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")

    print("=" * 64)
    for c in checks:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['id']:<5} {c['name']} | {c['measured']}")
    print("-" * 64)
    print(f"{n_pass}/{len(checks)} -> {'PASS' if overall else 'FAIL'} (>=6)")
    print("out:", OUT_JSON)
    print("out:", OUT_MD)


if __name__ == "__main__":
    main()
