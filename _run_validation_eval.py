# -*- coding: utf-8 -*-
"""_run_validation_eval.py — 검증 ②타당성(ablation)·③견고성(극단 정책) 실행.

기준은 eval/prereg_validation.md 에 사전등록됨(2026-06-07, 실행 전 고정).
판정이 나쁘면 기준을 다듬지 않는다 — 시스템을 고치고 전체 재실행한다.

② 그라운딩 ON/OFF ablation (청년월세, 24명 × 2조건 × 3회 = 144콜)
   V1 대상 분리: is_target 별 benefit 평균 차 — ON ≥ 30 그리고 OFF < 15
   V2 수렴타당도: policy_fit ↔ benefit Spearman r — ON ≥ 0.5 그리고 ON−OFF ≥ 0.3
   V3 분산비: 페르소나 간 std(ON)/std(OFF) ≥ 1.5 (benefit)
   V4 노이즈 바닥: 페르소나 간 std / 회차 간 std (ON) ≥ 2.0

③ 극단 정책 (10억/1원 쌍둥이 원문, 24명 × 2정책 × 3회 = 144콜)
   R1 천장 대상 자가인식 ≥ 80% / R2 천장 benefit≥75 ≥ 50%
   R3 천장 혼란도 > 바닥 그리고 ≥ 20 / R4 바닥 benefit≤50 ≥ 70%
   R5 바닥 intent>50 ≤ 20% / R6 천장 intent_pos > 바닥 intent_pos
   → 6항 중 5항 이상 = 통과

용법:
    python _run_validation_eval.py --dry      # 합성 반응 플러밍 (LLM 0콜)
    python _run_validation_eval.py            # 본판 288콜 (Gemini, ~$1.6)
    python _run_validation_eval.py --reuse    # 저장 JSON 으로 보고서만 재생성

산출: eval/ablation_results.json·ablation_report.md·ablation_viz.png
      eval/robustness_results.json·robustness_report.md·robustness_viz.png
"""
import sys
import io
import json
import argparse
import random
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 읽기만

OUT_DIR = ROOT / "eval"
AB_JSON = OUT_DIR / "ablation_results.json"
AB_MD = OUT_DIR / "ablation_report.md"
AB_PNG = OUT_DIR / "ablation_viz.png"
RB_JSON = OUT_DIR / "robustness_results.json"
RB_MD = OUT_DIR / "robustness_report.md"
RB_PNG = OUT_DIR / "robustness_viz.png"

N_PERSONAS, SEED = 24, 42
POLICY_NAME = "청년 월세 한시 특별지원"

# 사전등록 원문(쌍둥이 — 금액만 다름). _calibrate_cost.py 와 동일 문자열.
CEILING_TEXT = ("[전 국민 일시금 지급]\n"
                "정부는 전 국민에게 1인당 10억 원을 일시금으로 지급한다.\n"
                "신청 절차 없이 전 국민의 계좌로 자동 입금되며, "
                "소득·연령·재산 조건은 없다.")
FLOOR_TEXT = ("[전 국민 일시금 지급]\n"
              "정부는 전 국민에게 1인당 1원을 일시금으로 지급한다.\n"
              "신청 절차 없이 전 국민의 계좌로 자동 입금되며, "
              "소득·연령·재산 조건은 없다.")

# 사전등록 임계값 (prereg_validation.md — 변경 금지)
TH = {"V1_on": 30.0, "V1_off": 15.0, "V2_on": 0.5, "V2_diff": 0.3,
      "V3": 1.5, "V4": 2.0,
      "R1": 80.0, "R2": 50.0, "R3_floor": 20.0, "R4": 70.0, "R5": 20.0,
      "pass_min": 5}


# ---------------------------------------------------------------------------
# 수집 — 앱과 동일 경로. 셀: (part, cond, grounded, text)
# ---------------------------------------------------------------------------
def collect(personas, n_runs):
    from prompts import build_react_messages
    from sample_policies import SAMPLES
    import graph.llm as llm
    from graph.nodes import ReactionOut, survey_to_scores

    youth = SAMPLES[POLICY_NAME]
    cells = [
        ("ablation", "on", True, youth),
        ("ablation", "off", False, youth),
        ("robustness", "ceiling", True, CEILING_TEXT),
        ("robustness", "floor", True, FLOOR_TEXT),
    ]
    tasks = [(part, cond, grounded, text, p, run)
             for part, cond, grounded, text in cells
             for run in range(n_runs)
             for p in personas]

    def _one(task):
        part, cond, grounded, text, p, run = task
        base = {"part": part, "cond": cond, "persona_id": p["id"], "run": run}
        try:
            msgs = build_react_messages(p, text, grounded=grounded)
            out = llm.structured_call(msgs, ReactionOut, temperature=1.0)
            return {**base, "stance": out.stance, "lean": out.lean,
                    "text": out.text, "scores": survey_to_scores(out.survey),
                    "survey": out.survey.model_dump(), "ok": True}
        except Exception as e:
            return {**base, "stance": "mixed", "lean": "none",
                    "text": f"(실패: {type(e).__name__})",
                    "scores": {}, "survey": {}, "ok": False}

    print(f"  4셀 × {len(personas)}명 × {n_runs}회 = {len(tasks)}콜 "
          f"(model={llm.MODEL}, temp=1.0) ...")
    rows = llm.run_threaded(tasks, _one, max_workers=8)
    usage = dict(llm.LLM_USAGE)  # 캐시 적중 실측(§8-6) 스냅샷
    return rows, usage


def synth(personas, n_runs, seed=7):
    """--dry: 배관 검증용 합성 반응 (사전등록 통과 방향으로 그럴듯하게)."""
    from data.personas import policy_fit
    from sample_policies import SPECS
    spec = SPECS[POLICY_NAME]
    rng = random.Random(seed)
    rows = []

    def _survey_row(part, cond, p, run, benefit, intent, dissat, elig):
        return {"part": part, "cond": cond, "persona_id": p["id"], "run": run,
                "stance": "mixed", "lean": "none", "text": "(합성)",
                "scores": {"understanding": 65, "benefit": benefit,
                           "intent": intent, "dissatisfaction": dissat,
                           "shareability": 35},
                "survey": {"eligibility": elig}, "ok": True}

    for run in range(n_runs):
        for p in personas:
            fit = policy_fit(p, spec)
            noise = rng.gauss(0, 8)
            rows.append(_survey_row("ablation", "on", p, run,
                                    max(0, min(100, 15 + 75 * fit + noise)),
                                    max(0, min(100, 10 + 70 * fit + noise)),
                                    30, "target" if fit > 0.6 else "not_target"))
            rows.append(_survey_row("ablation", "off", p, run,
                                    max(0, min(100, 55 + rng.gauss(0, 5))),
                                    50, 30, "unsure"))
            rows.append(_survey_row("robustness", "ceiling", p, run,
                                    rng.choice([75, 100, 100, 75, 50]),
                                    rng.choice([75, 100, 100]),
                                    rng.choice([0, 30, 30, 70]), "target"))
            rows.append(_survey_row("robustness", "floor", p, run,
                                    rng.choice([50, 50, 50, 25]),
                                    rng.choice([0, 0, 25, 50]),
                                    rng.choice([0, 0, 30]), "target"))
    return rows


# ---------------------------------------------------------------------------
# 통계 헬퍼 (scipy 없이)
# ---------------------------------------------------------------------------
def _ranks(xs):
    """동순위 평균 랭크."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def _benefit_rows(rows, cond):
    """cond 의 ok 행에서 persona_id -> [benefit ...] (run 순서 무관)."""
    per = {}
    for r in rows:
        if r["cond"] != cond or not r["ok"]:
            continue
        b = r["scores"].get("benefit")
        if isinstance(b, (int, float)):
            per.setdefault(r["persona_id"], []).append(float(b))
    return per


# ---------------------------------------------------------------------------
# ② ablation 집계 + 판정
# ---------------------------------------------------------------------------
def ablation_metrics(rows, personas):
    from data.personas import policy_fit, is_target
    from sample_policies import SPECS
    spec = SPECS[POLICY_NAME]
    fit = {p["id"]: policy_fit(p, spec) for p in personas}
    target = {p["id"]: is_target(p, [spec]) for p in personas}

    cond_stats = {}
    for cond in ("on", "off"):
        per = _benefit_rows(rows, cond)
        means = {pid: mean(v) for pid, v in per.items() if v}
        tg = [m for pid, m in means.items() if target.get(pid)]
        ntg = [m for pid, m in means.items() if not target.get(pid)]
        pids = sorted(means)
        within = [stdev(v) for v in per.values() if len(v) >= 2]
        cond_stats[cond] = {
            "n_persona": len(means),
            "mean_target": round(mean(tg), 1) if tg else None,
            "mean_nontarget": round(mean(ntg), 1) if ntg else None,
            "diff": round(mean(tg) - mean(ntg), 1) if (tg and ntg) else None,
            "spearman_fit": round(spearman([fit[p] for p in pids],
                                           [means[p] for p in pids]), 3)
            if len(pids) >= 3 else None,
            "between_std": round(stdev(list(means.values())), 2)
            if len(means) >= 2 else None,
            "within_std": round((mean([s * s for s in within])) ** 0.5, 2)
            if within else None,
            "persona_means": {pid: round(m, 1) for pid, m in means.items()},
        }

    on, off = cond_stats["on"], cond_stats["off"]
    v3_ratio = (round(on["between_std"] / off["between_std"], 2)
                if (on["between_std"] and off["between_std"]) else None)
    v4_ratio = (round(on["between_std"] / on["within_std"], 2)
                if (on["between_std"] and on["within_std"]) else None)
    checks = [
        {"id": "V1", "name": "대상 분리 (benefit 평균 차)",
         "measured": f"ON {on['diff']} / OFF {off['diff']}",
         "criterion": f"ON ≥ {TH['V1_on']:.0f} 그리고 OFF < {TH['V1_off']:.0f}",
         "pass": (on["diff"] is not None and off["diff"] is not None
                  and on["diff"] >= TH["V1_on"] and off["diff"] < TH["V1_off"])},
        {"id": "V2", "name": "수렴타당도 (fit↔benefit Spearman r)",
         "measured": f"ON {on['spearman_fit']} / OFF {off['spearman_fit']}",
         "criterion": f"ON ≥ {TH['V2_on']} 그리고 차 ≥ {TH['V2_diff']}",
         "pass": (on["spearman_fit"] is not None and off["spearman_fit"] is not None
                  and on["spearman_fit"] >= TH["V2_on"]
                  and on["spearman_fit"] - off["spearman_fit"] >= TH["V2_diff"])},
        {"id": "V3", "name": "분산비 (페르소나 간 std ON/OFF)",
         "measured": f"{on['between_std']} / {off['between_std']} = {v3_ratio}",
         "criterion": f"≥ {TH['V3']}",
         "pass": v3_ratio is not None and v3_ratio >= TH["V3"]},
        {"id": "V4", "name": "노이즈 바닥 (간 std / 회차 std, ON)",
         "measured": f"{on['between_std']} / {on['within_std']} = {v4_ratio}",
         "criterion": f"≥ {TH['V4']}",
         "pass": v4_ratio is not None and v4_ratio >= TH["V4"]},
    ]
    return {"cond": cond_stats, "fit": {k: round(v, 3) for k, v in fit.items()},
            "target": target, "checks": checks,
            "n_pass": sum(c["pass"] for c in checks)}


# ---------------------------------------------------------------------------
# ③ robustness 집계 + 판정
# ---------------------------------------------------------------------------
def robustness_metrics(rows, n_runs):
    from metrics_common import social_unrest

    def _run_stats(cond, run):
        rs = [r for r in rows if r["cond"] == cond and r["run"] == run and r["ok"]]
        n = len(rs)
        if n == 0:
            return None
        def pct(pred):
            return round(100.0 * sum(1 for r in rs if pred(r)) / n, 1)
        return {
            "n": n,
            "elig_target": pct(lambda r: (r["survey"] or {}).get("eligibility") == "target"),
            "benefit_ge75": pct(lambda r: (r["scores"].get("benefit") or 0) >= 75),
            "benefit_le50": pct(lambda r: isinstance(r["scores"].get("benefit"), (int, float))
                                and r["scores"]["benefit"] <= 50),
            "intent_pos": pct(lambda r: (r["scores"].get("intent") or 0) > 50),
            "unrest": social_unrest(rs),
        }

    cond_stats = {}
    for cond in ("ceiling", "floor"):
        runs = [s for s in (_run_stats(cond, r) for r in range(n_runs)) if s]
        agg = {}
        for k in ("elig_target", "benefit_ge75", "benefit_le50", "intent_pos", "unrest"):
            vals = [s[k] for s in runs]
            agg[k] = round(mean(vals), 1)
            agg[k + "_rng"] = [min(vals), max(vals)]
        agg["per_run"] = runs
        cond_stats[cond] = agg

    c, f = cond_stats["ceiling"], cond_stats["floor"]
    checks = [
        {"id": "R1", "name": "천장: 대상 자가인식(eligibility=target)",
         "measured": f"{c['elig_target']}%", "criterion": f"≥ {TH['R1']:.0f}%",
         "pass": c["elig_target"] >= TH["R1"]},
        {"id": "R2", "name": "천장: 수혜 인식(benefit ≥ 75)",
         "measured": f"{c['benefit_ge75']}%", "criterion": f"≥ {TH['R2']:.0f}%",
         "pass": c["benefit_ge75"] >= TH["R2"]},
        {"id": "R3", "name": "천장: 혼란도 동반 상승",
         "measured": f"천장 {c['unrest']} vs 바닥 {f['unrest']}",
         "criterion": f"천장 > 바닥 그리고 천장 ≥ {TH['R3_floor']:.0f}",
         "pass": c["unrest"] > f["unrest"] and c["unrest"] >= TH["R3_floor"]},
        {"id": "R4", "name": "바닥: 무관·무효용(benefit ≤ 50)",
         "measured": f"{f['benefit_le50']}%", "criterion": f"≥ {TH['R4']:.0f}%",
         "pass": f["benefit_le50"] >= TH["R4"]},
        {"id": "R5", "name": "바닥: 적극 의향(intent > 50)",
         "measured": f"{f['intent_pos']}%", "criterion": f"≤ {TH['R5']:.0f}%",
         "pass": f["intent_pos"] <= TH["R5"]},
        {"id": "R6", "name": "순서: 천장 의향 > 바닥 의향",
         "measured": f"{c['intent_pos']}% vs {f['intent_pos']}%",
         "criterion": "부등호 성립",
         "pass": c["intent_pos"] > f["intent_pos"]},
    ]
    n_pass = sum(ck["pass"] for ck in checks)
    return {"cond": cond_stats, "checks": checks, "n_pass": n_pass,
            "overall_pass": n_pass >= TH["pass_min"]}


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def _checks_table(checks):
    L = ["| # | 항목 | 측정값 | 사전등록 기준 | 판정 |", "|---|---|---|---|---|"]
    for c in checks:
        L.append(f"| {c['id']} | {c['name']} | {c['measured']} | {c['criterion']} | "
                 f"{'통과' if c['pass'] else '**미달**'} |")
    return L


def make_ablation_report(m, cfg):
    on, off = m["cond"]["on"], m["cond"]["off"]
    head = (f"그라운딩 ON 에서만 점수가 실제 자격조건을 따라간다 — "
            f"{m['n_pass']}/4 통과" if m["n_pass"] == 4 else
            f"판정 {m['n_pass']}/4 — 미달 항목 있음(기준 다듬기 금지, 시스템 점검)")
    L = [
        "# 검증 ② 타당성 — 그라운딩 ON/OFF ablation", "",
        f"> **{head}**", "",
        f"- 설정: {POLICY_NAME} · {cfg['n']}명 × ON/OFF × {cfg['runs']}회 = "
        f"{cfg['n']*2*cfg['runs']}콜 · {cfg['model']} · temp 1.0 · "
        f"score_scale={cfg['score_scale']}",
        "- 기준: eval/prereg_validation.md (실행 전 고정). "
        "비교 기준(is_target/policy_fit)은 결정론 — LLM 과 독립.",
        "- OFF 조건은 전원 같은 프롬프트(인물 카드만 제거) — '페르소나 간 차이'는 "
        "순수 호출 노이즈여야 정상.", "",
        "## 판정", "",
        *_checks_table(m["checks"]), "",
        "## 숫자", "",
        f"- ON : 대상 {on['mean_target']} vs 비대상 {on['mean_nontarget']} "
        f"(차 {on['diff']}) · r={on['spearman_fit']} · 간std {on['between_std']} · "
        f"회차std {on['within_std']}",
        f"- OFF: 대상 {off['mean_target']} vs 비대상 {off['mean_nontarget']} "
        f"(차 {off['diff']}) · r={off['spearman_fit']} · 간std {off['between_std']} · "
        f"회차std {off['within_std']}",
        "  (OFF 의 '대상/비대상'은 카드를 안 넣었을 뿐 같은 사람 기준의 라벨 — "
        "차이가 남으면 그게 누수)", "",
        "## 의미", "",
        "- V1·V2 통과 = \"결과 차이를 만드는 건 페르소나\" — 점수가 LLM 의 기분이 아니라 "
        "인물의 실제 조건(나이·소득)을 따라간다는 직접 증거.",
        "- V3·V4 통과 = ON 의 다양성이 호출 노이즈(LLM 변덕)보다 충분히 크다 — "
        "\"그냥 랜덤이 갈린 것\" 공격 방어.", "",
        "## 한계 (정직)", "",
        "- 정책 1건(청년월세)·페르소나 24명 — 정책 일반화는 갭 실험(4정책)이 보완.",
        "- policy_fit 의 소득은 직업 기반 휴리스틱(근사) — V2 의 r 상한을 낮추는 방향.",
        f"- 캐시 적중 실측: {cfg.get('llm_usage')}", "",
    ]
    return "\n".join(L)


def make_robustness_report(m, cfg):
    c, f = m["cond"]["ceiling"], m["cond"]["floor"]
    head = (f"극단 정책 {m['n_pass']}/6 통과 — "
            + ("견고성 통과 (기준: 5항 이상)" if m["overall_pass"]
               else "**미달** (기준: 5항 이상) — 시스템 점검"))
    L = [
        "# 검증 ③ 견고성 — 극단 정책 테스트 (10억 / 1원)", "",
        f"> **{head}**", "",
        f"- 설정: 쌍둥이 원문(금액만 상이) · {cfg['n']}명 × 2정책 × {cfg['runs']}회 = "
        f"{cfg['n']*2*cfg['runs']}콜 · {cfg['model']} · temp 1.0 · "
        f"score_scale={cfg['score_scale']}",
        "- 기준: eval/prereg_validation.md (실행 전 고정).", "",
        "## 판정", "",
        *_checks_table(m["checks"]), "",
        "## 숫자 (3회 평균, [min,max])", "",
        f"- 천장(10억): 자가인식 target {c['elig_target']}% {c['elig_target_rng']} · "
        f"benefit≥75 {c['benefit_ge75']}% {c['benefit_ge75_rng']} · "
        f"의향+ {c['intent_pos']}% {c['intent_pos_rng']} · "
        f"혼란도 {c['unrest']} {c['unrest_rng']}",
        f"- 바닥(1원): benefit≤50 {f['benefit_le50']}% {f['benefit_le50_rng']} · "
        f"의향+ {f['intent_pos']}% {f['intent_pos_rng']} · "
        f"혼란도 {f['unrest']} {f['unrest_rng']}", "",
        "## 의미", "",
        "- 위아래 양 극단에서 상식 방향으로 반응하면, 그 사이의 정상 정책 구간에서도 "
        "시스템이 무너지지 않는다는 근거가 된다(검증구조 문서 ③층).", "",
        "## 한계 (정직)", "",
        "- '실현 기대' 측정축 부재(프로브1 진단) — \"안 믿지만 받으면 좋지\"가 "
        "benefit/intent 에 섞임. R2·R3 임계는 이를 감안해 보수적으로 사전등록함.",
        "- 극단 2점만 검사 — 중간 구간의 단조성(금액↑=의향↑)은 미검증.",
        f"- 캐시 적중 실측: {cfg.get('llm_usage')}", "",
    ]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 시각화 — 패널 1개 = 비교 1개, 판정 색 제목, 회색 설명줄, ASCII 마커.
# ---------------------------------------------------------------------------
C_ON, C_OFF, C_TG, C_NT = "#3b78c3", "#9aa7b5", "#2a9d4e", "#c46a6a"
G, R = "#1a7a3a", "#b03030"


def _vc(ok):
    return G if ok else R


def make_ablation_viz(m, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False

    on, off = m["cond"]["on"], m["cond"]["off"]
    ck = {c["id"]: c for c in m["checks"]}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))

    # (1) V1 대상 분리
    ax = axes[0]
    vals = [on["mean_target"], on["mean_nontarget"],
            off["mean_target"], off["mean_nontarget"]]
    cols = [C_TG, C_NT, C_TG, C_NT]
    xs = [0, 1, 2.6, 3.6]
    ax.bar(xs, vals, 0.8, color=cols)
    for x, v in zip(xs, vals):
        ax.text(x, (v or 0) + 1.5, f"{v:.0f}", ha="center", fontsize=10)
    ax.set_xticks([0.5, 3.1])
    ax.set_xticklabels([f"그라운딩 ON\n차 {on['diff']}점",
                        f"그라운딩 OFF\n차 {off['diff']}점"], fontsize=10)
    ax.set_ylim(0, 105)
    ax.set_ylabel("살림 영향(benefit) 평균")
    ax.set_title(f"V1 대상 분리 — {'통과' if ck['V1']['pass'] else '미달'} "
                 f"(기준 ON≥30, OFF<15)", color=_vc(ck["V1"]["pass"]),
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("초록=정책 대상자(is_target) / 적갈=비대상자 — 결정론 라벨",
                  fontsize=8.5, color="#666")

    # (2) V2 수렴타당도 산점
    ax = axes[1]
    fit, tgt = m["fit"], m["target"]
    for cond, col, lab in (("on", C_ON, "ON"), ("off", C_OFF, "OFF")):
        pm = m["cond"][cond]["persona_means"]
        xs_ = [fit[pid] for pid in pm]
        ys_ = [pm[pid] for pid in pm]
        ax.scatter(xs_, ys_, c=col, s=42, alpha=0.85,
                   label=f"{lab} (r={m['cond'][cond]['spearman_fit']})")
    ax.set_xlabel("policy_fit (결정론 적합도, LLM 무관)")
    ax.set_ylabel("benefit 평균 (3회)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)
    ax.set_title(f"V2 수렴타당도 — {'통과' if ck['V2']['pass'] else '미달'} "
                 f"(기준 ON r≥0.5, 차≥0.3)", color=_vc(ck["V2"]["pass"]),
                 fontsize=11, fontweight="bold")

    # (3) V3·V4 분산
    ax = axes[2]
    bars = [on["between_std"], off["between_std"], on["within_std"]]
    labs = ["페르소나 간\nstd (ON)", "페르소나 간\nstd (OFF)", "회차 간\nstd (ON)"]
    cols = [C_ON, C_OFF, "#d8b35a"]
    ax.bar(range(3), bars, 0.62, color=cols)
    for i, v in enumerate(bars):
        ax.text(i, (v or 0) + 0.4, f"{v}", ha="center", fontsize=10)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labs, fontsize=9)
    ax.set_ylabel("표준편차 (benefit)")
    v3ok, v4ok = ck["V3"]["pass"], ck["V4"]["pass"]
    ax.set_title(f"V3 분산비 {'통과' if v3ok else '미달'} · "
                 f"V4 노이즈 바닥 {'통과' if v4ok else '미달'}",
                 color=_vc(v3ok and v4ok), fontsize=11, fontweight="bold")
    ax.set_xlabel("ON 의 사람 간 차이가 OFF(노이즈)와 회차 출렁임보다 커야 함",
                  fontsize=8.5, color="#666")

    fig.suptitle(
        f"검증 ② 타당성 — 결과 차이를 만드는 건 페르소나인가: {m['n_pass']}/4 통과 "
        f"({POLICY_NAME} · {cfg['n']}명 × {cfg['runs']}회 · {cfg['model']})",
        fontsize=13, fontweight="bold")
    fig.text(0.5, 0.9,
             "비교 기준(대상 여부·적합도)은 LLM 과 무관한 결정론 코드 — "
             "점수가 인물의 실제 조건을 따라갈 때만 통과한다. 기준은 실행 전 사전등록.",
             ha="center", fontsize=9, color="#555")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(AB_PNG, dpi=130)
    plt.close(fig)


def make_robustness_viz(m, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False

    c, f = m["cond"]["ceiling"], m["cond"]["floor"]
    ck = {x["id"]: x for x in m["checks"]}
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.6))

    def _pair(ax, vc, vf, title, ok, ylab, note, th_line=None, th_label=""):
        ax.bar([0, 1], [vc, vf], 0.55, color=["#c4622d", "#3b78c3"])
        for i, v in enumerate([vc, vf]):
            ax.text(i, v + 1.5, f"{v:.0f}", ha="center", fontsize=11)
        if th_line is not None:
            ax.axhline(th_line, color="#888", ls="--", lw=1)
            ax.text(1.42, th_line, th_label, fontsize=8, color="#666", va="center")
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["천장\n(10억)", "바닥\n(1원)"], fontsize=10)
        ax.set_ylim(0, 112)
        ax.set_ylabel(ylab)
        ax.set_title(title, color=_vc(ok), fontsize=11, fontweight="bold")
        ax.set_xlabel(note, fontsize=8.5, color="#666")

    _pair(axes[0][0], c["elig_target"], f["elig_target"],
          f"R1 대상 자가인식 — {'통과' if ck['R1']['pass'] else '미달'}",
          ck["R1"]["pass"], "\"내가 대상\" 응답 (%)",
          "전 국민 지급 — 양쪽 다 높아야 정상 (판정은 천장 ≥80%)",
          TH["R1"], "기준 80")
    _pair(axes[0][1], c["benefit_ge75"], f["benefit_le50"],
          f"R2·R4 수혜 인식 — {'통과' if (ck['R2']['pass'] and ck['R4']['pass']) else '미달'}",
          ck["R2"]["pass"] and ck["R4"]["pass"], "비율 (%)",
          "천장 막대=benefit≥75(혜택 크다) / 바닥 막대=benefit≤50(의미 없다)")
    _pair(axes[1][0], c["intent_pos"], f["intent_pos"],
          f"R5·R6 적극 신청 의향 — {'통과' if (ck['R5']['pass'] and ck['R6']['pass']) else '미달'}",
          ck["R5"]["pass"] and ck["R6"]["pass"], "intent > 50 비율 (%)",
          "10억엔 움직이고 1원엔 안 움직여야 정상 (바닥 ≤20% · 천장>바닥)",
          TH["R5"], "기준 20")
    _pair(axes[1][1], c["unrest"], f["unrest"],
          f"R3 사회혼란도 — {'통과' if ck['R3']['pass'] else '미달'}",
          ck["R3"]["pass"], "혼란도 (불만 평균, 0~100)",
          "공짜 10억이 평온하면 비정상 — 불안·의심이 동반돼야 함 (천장>바닥, ≥20)",
          TH["R3_floor"], "기준 20")

    fig.suptitle(
        f"검증 ③ 견고성 — 극단 정책에서 상식을 지키는가: {m['n_pass']}/6 통과 "
        f"({'견고성 통과' if m['overall_pass'] else '미달'} · 기준 5항 이상)",
        fontsize=13, fontweight="bold")
    fig.text(0.5, 0.925,
             f"쌍둥이 원문(금액만 10억/1원) · {cfg['n']}명 × {cfg['runs']}회 · "
             f"{cfg['model']} · 기준은 실행 전 사전등록 (eval/prereg_validation.md)",
             ha="center", fontsize=9, color="#555")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(RB_PNG, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    from data.personas import load_personas
    personas = load_personas(N_PERSONAS, SEED)
    print(f"[1] 페르소나 {len(personas)}명 (seed={SEED})")

    if args.reuse:
        ab = json.loads(AB_JSON.read_text(encoding="utf-8"))
        rb = json.loads(RB_JSON.read_text(encoding="utf-8"))
        rows = ab["rows"] + rb["rows"]
        cfg = ab["config"]
    else:
        if args.dry:
            rows = synth(personas, args.runs)
            cfg = {"n": len(personas), "runs": args.runs, "model": "(dry)",
                   "provider": "(dry)", "score_scale": "survey_v1",
                   "prereg": "eval/prereg_validation.md", "llm_usage": None}
        else:
            import graph.llm as llm
            llm.set_provider("gemini")   # 사전등록: Gemini 고정
            assert llm.has_real_key(), "GEMINI_API_KEY 없음"
            print("[2] 반응 수집 ...")
            rows, usage = collect(personas, args.runs)
            ok = sum(1 for r in rows if r["ok"])
            print(f"    -> {ok}/{len(rows)} 성공 · usage={usage}")
            cfg = {"n": len(personas), "runs": args.runs, "model": llm.MODEL,
                   "provider": llm.PROVIDER, "score_scale": "survey_v1",
                   "prereg": "eval/prereg_validation.md", "llm_usage": usage}
        ab_rows = [r for r in rows if r["part"] == "ablation"]
        rb_rows = [r for r in rows if r["part"] == "robustness"]
        AB_JSON.write_text(json.dumps({"config": cfg, "rows": ab_rows},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
        RB_JSON.write_text(json.dumps({"config": cfg, "rows": rb_rows},
                                      ensure_ascii=False, indent=1), encoding="utf-8")

    print("[3] 집계 + 판정 ...")
    ab_m = ablation_metrics([r for r in rows if r["part"] == "ablation"], personas)
    rb_m = robustness_metrics([r for r in rows if r["part"] == "robustness"],
                              cfg["runs"])

    AB_MD.write_text(make_ablation_report(ab_m, cfg), encoding="utf-8")
    RB_MD.write_text(make_robustness_report(rb_m, cfg), encoding="utf-8")
    make_ablation_viz(ab_m, cfg)
    make_robustness_viz(rb_m, cfg)

    print()
    print("=" * 64)
    for c in ab_m["checks"] + rb_m["checks"]:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['id']} {c['name']} | "
              f"{c['measured']} | 기준 {c['criterion']}")
    print("-" * 64)
    print(f"(2) ablation  : {ab_m['n_pass']}/4")
    print(f"(3) robustness: {rb_m['n_pass']}/6 -> "
          f"{'PASS' if rb_m['overall_pass'] else 'FAIL'} (>=5)")
    print("out:", AB_JSON, AB_MD, AB_PNG, sep="\n     ")
    print("out:", RB_JSON, RB_MD, RB_PNG, sep="\n     ")


if __name__ == "__main__":
    main()
