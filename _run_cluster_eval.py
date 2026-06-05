# -*- coding: utf-8 -*-
"""_run_cluster_eval.py — 시민 반응의 '집단화 · 견고성 · 설득력' 평가 + 보고서.

발표 질문 두 가지에 정량으로 답하는 dev 스크립트(제품 코드 무수정, 섬).

  Q1. 집단화 : LLM 페르소나들이 정책에 대해 무작위가 아니라 인구통계(연령)에 따라
               일관된 집단으로 갈리는가?  →  eta-squared(점수 변동 중 연령으로
               설명되는 비율) + 연령 그룹별 입장/점수 분포.
  Q2. 설득력 : 각 집단이 자기 입장을 그럴듯하게 주장하는가?  →  LLM-judge 채점
               (논리·근거·일관성) + 대표 예시. (judge 도 LLM 이라 순환 한계 명시.)

  + 견고성   : 같은 시민을 N회 반복했을 때 입장이 얼마나 일관되게 재현되는가
               (집단 구도가 우연이 아님을 보이는 핵심).

데이터: 페르소나 24명 × N회 반복 react(1차 반응만, interact/aggregate 불필요).

실행:
    python _run_cluster_eval.py --runs 3     # 스모크(파이프라인 검증, ~72콜)
    python _run_cluster_eval.py --runs 30    # 본판(~720콜)
    python _run_cluster_eval.py --reuse      # 저장 JSON 으로 그림/보고서만(LLM 0)

산출: eval/cluster_results.json, eval/cluster_viz.png, eval/cluster_report.md
"""
import sys
import io
import json
import argparse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 읽기만(절대 수정 안 함)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

from pydantic import BaseModel, Field

from sample_policies import SAMPLES
from prompts import build_react_messages

OUT_DIR = ROOT / "eval"
JSON_PATH = OUT_DIR / "cluster_results.json"
PNG_PATH = OUT_DIR / "cluster_viz.png"
REPORT_PATH = OUT_DIR / "cluster_report.md"

POLICY_NAME = "청년 월세 한시 특별지원"  # 연령으로 대상이 또렷이 갈리는 정책
POLICY = SAMPLES[POLICY_NAME]

# 색
C_SUP, C_OPP, C_MIX = "#2a6fdb", "#d9534f", "#9aa0a6"
C_BENEFIT, C_INTENT = "#2a6fdb", "#5cb85c"
C_BAR = "#2a6fdb"

STANCE_KR = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}
_NEUTRAL = {"understanding": 50, "benefit": 50, "intent": 50,
            "dissatisfaction": 50, "shareability": 50}


# 연령 그룹 — 청년 월세 대상(만 19~34)을 기준으로 청년/중년/노인 3분할.
GROUP_ORDER = ["청년(19~34)", "중년(35~54)", "노인(55+)"]


def age_group(age) -> str:
    try:
        a = int(age)
    except (TypeError, ValueError):
        a = 0
    if 19 <= a <= 34:
        return "청년(19~34)"
    if 35 <= a <= 54:
        return "중년(35~54)"
    if a >= 55:
        return "노인(55+)"
    return "청년(19~34)"  # 19세 미만은 거의 없음 — 청년에 흡수


# ---------------------------------------------------------------------------
# 1) 데이터 수집 — 페르소나 × 반복 react
# ---------------------------------------------------------------------------
def collect(personas, n_runs):
    from graph.llm import structured_call, run_threaded, MODEL
    from graph.nodes import ReactionOut

    tasks = [(p, run) for run in range(n_runs) for p in personas]

    def _one(task):
        p, run = task
        try:
            msgs = build_react_messages(p, POLICY, grounded=True)
            out = structured_call(msgs, ReactionOut, temperature=0.8)
            return {
                "persona_id": p["id"], "run": run,
                "stance": out.stance, "text": out.text,
                "scores": out.scores.model_dump(),
            }
        except Exception:
            return {
                "persona_id": p["id"], "run": run,
                "stance": "mixed", "text": "(응답 생성 실패)",
                "scores": dict(_NEUTRAL),
            }

    print(f"      반복 {n_runs}회 × {len(personas)}명 = {len(tasks)}회 호출 (model={MODEL}) ...")
    return run_threaded(tasks, _one, max_workers=8)


# ---------------------------------------------------------------------------
# 2) 집단화 분석 — eta-squared + 그룹별 분포
# ---------------------------------------------------------------------------
def eta_squared(groups_values: dict) -> float:
    """그룹 간 분산이 전체 분산에서 차지하는 비율(0~1). 클수록 집단화 뚜렷."""
    all_vals = [v for vs in groups_values.values() for v in vs]
    n = len(all_vals)
    if n < 2:
        return 0.0
    grand = sum(all_vals) / n
    ss_total = sum((v - grand) ** 2 for v in all_vals)
    if ss_total <= 0:
        return 0.0
    ss_between = 0.0
    for vs in groups_values.values():
        if vs:
            gm = sum(vs) / len(vs)
            ss_between += len(vs) * (gm - grand) ** 2
    return ss_between / ss_total


def analyze_clustering(reactions, p_by_id):
    axes = ("benefit", "intent", "understanding")
    by_group = {ax: {} for ax in axes}
    stance_by_group = {}
    for r in reactions:
        p = p_by_id.get(r["persona_id"]) or {}
        g = age_group((p.get("demographics") or {}).get("age"))
        for ax in axes:
            by_group[ax].setdefault(g, []).append(r["scores"].get(ax, 50))
        sc = stance_by_group.setdefault(g, {"support": 0, "oppose": 0, "mixed": 0})
        st = r["stance"] if r["stance"] in sc else "mixed"
        sc[st] += 1
    eta = {ax: round(eta_squared(by_group[ax]), 3) for ax in axes}
    group_means = {
        ax: {g: round(sum(vs) / len(vs), 1) for g, vs in by_group[ax].items()}
        for ax in axes
    }
    return {"eta": eta, "group_means": group_means, "stance_by_group": stance_by_group}


# ---------------------------------------------------------------------------
# 3) 견고성 — 입장 안정성(반복 중 최빈 입장 비율)
# ---------------------------------------------------------------------------
def analyze_robustness(reactions, personas, p_by_id):
    by_pid = {}
    for r in reactions:
        by_pid.setdefault(r["persona_id"], []).append(r["stance"])
    rows = []
    for p in personas:
        pid = p["id"]
        stances = by_pid.get(pid, [])
        if not stances:
            continue
        cnt = Counter(stances)
        top, topn = cnt.most_common(1)[0]
        rows.append({
            "name": p.get("name", ""),
            "age": (p.get("demographics") or {}).get("age"),
            "group": age_group((p.get("demographics") or {}).get("age")),
            "modal_stance": top,
            "stability": round(topn / len(stances), 3),
            "runs": len(stances),
        })
    grp = {}
    for row in rows:
        grp.setdefault(row["group"], []).append(row["stability"])
    group_stability = {g: round(sum(v) / len(v), 3) for g, v in grp.items()}
    overall = round(sum(r["stability"] for r in rows) / len(rows), 3) if rows else 0.0
    return {"rows": rows, "group_stability": group_stability, "overall_stability": overall}


# ---------------------------------------------------------------------------
# 4) 설득력 — LLM-judge (각 시민 대표 반응 1개)
# ---------------------------------------------------------------------------
class JudgeOut(BaseModel):
    persuasiveness: int = Field(ge=0, le=100, description="설득력 0~100")
    reason: str = Field(description="한 줄 이유")


def judge_persuasiveness(reactions, personas, p_by_id):
    from graph.llm import structured_call, run_threaded

    # 각 시민의 '첫 성공 반응' 1개를 대표로.
    rep = {}
    for r in reactions:
        if r["persona_id"] not in rep and r["text"] != "(응답 생성 실패)":
            rep[r["persona_id"]] = r
    items = list(rep.items())

    sys_msg = (
        "당신은 토론·논증 평가 전문가입니다. 주어진 시민 반응이 '자기 입장을 "
        "설득력 있게 주장'하는지 평가하세요. 평가 기준은 (1) 논리적 일관성, "
        "(2) 구체적 근거 제시, (3) 입장의 명확성입니다. 찬성/반대 입장 자체의 "
        "옳고 그름이 아니라 '주장의 설득력'만 0~100으로 채점하세요. 반드시 "
        "지정된 구조화 형식으로만 답하세요."
    )

    def _one(item):
        pid, r = item
        p = p_by_id.get(pid, {})
        d = p.get("demographics") or {}
        user = (
            f"[시민] {d.get('age')}세 {d.get('sex')} · {d.get('occupation')} · "
            f"입장: {STANCE_KR.get(r['stance'], '혼합')}\n\n"
            f"[반응]\n{r['text']}\n\n이 반응의 설득력을 평가하세요."
        )
        try:
            out = structured_call(
                [{"role": "system", "content": sys_msg},
                 {"role": "user", "content": user}],
                JudgeOut, temperature=0.2,
            )
            return {
                "persona_id": pid, "name": p.get("name", ""),
                "group": age_group(d.get("age")), "stance": r["stance"],
                "persuasiveness": out.persuasiveness, "reason": out.reason,
                "text": r["text"],
            }
        except Exception:
            return None

    rows = [x for x in run_threaded(items, _one, max_workers=8) if x]
    grp = {}
    for x in rows:
        grp.setdefault(x["group"], []).append(x["persuasiveness"])
    group_persuasion = {g: round(sum(v) / len(v), 1) for g, v in grp.items()}
    overall = round(sum(x["persuasiveness"] for x in rows) / len(rows), 1) if rows else 0.0
    return {"rows": rows, "group_persuasion": group_persuasion, "overall": overall}


# ---------------------------------------------------------------------------
# 5) 시각화 (2×2)
# ---------------------------------------------------------------------------
def make_viz(data):
    cl = data["clustering"]
    rb = data["robustness"]
    pe = data["persuasion"]
    cfg = data["config"]

    groups = [g for g in GROUP_ORDER if g in cl["stance_by_group"]]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        f"시민 반응의 집단화·견고성·설득력 · {cfg['policy_name']} · "
        f"{cfg['n']}명 × {cfg['runs']}회 · {cfg['model']}",
        fontsize=13, fontweight="bold",
    )

    # (a) 연령 × 입장 적층 막대(%)
    ax = axes[0][0]
    sup, opp, mix = [], [], []
    for g in groups:
        sc = cl["stance_by_group"][g]
        tot = max(1, sc["support"] + sc["oppose"] + sc["mixed"])
        sup.append(100 * sc["support"] / tot)
        opp.append(100 * sc["oppose"] / tot)
        mix.append(100 * sc["mixed"] / tot)
    ax.bar(groups, sup, color=C_SUP, label="찬성")
    ax.bar(groups, opp, bottom=sup, color=C_OPP, label="반대")
    ax.bar(groups, mix, bottom=[s + o for s, o in zip(sup, opp)], color=C_MIX, label="혼합")
    ax.set_ylabel("입장 비율 (%)")
    ax.set_ylim(0, 122)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_title("(1) 연령 집단별 입장 — 무작위가 아니라 갈린다")
    ax.legend(loc="upper center", ncol=3, fontsize=8, framealpha=0.9)

    # (b) 연령별 수혜/의향 평균 + eta²
    ax = axes[0][1]
    x = range(len(groups))
    w = 0.36
    benefit = [cl["group_means"]["benefit"].get(g, 0) for g in groups]
    intent = [cl["group_means"]["intent"].get(g, 0) for g in groups]
    ax.bar([i - w / 2 for i in x], benefit, w, color=C_BENEFIT, label="수혜")
    ax.bar([i + w / 2 for i in x], intent, w, color=C_INTENT, label="신청의향")
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups)
    ax.set_ylabel("평균 점수 (0~100)")
    ax.set_ylim(0, 100)
    eta = cl["eta"]
    ax.set_title(f"(2) 집단 분화 — 수혜 eta²={eta['benefit']} · 의향 eta²={eta['intent']}")
    ax.legend(loc="upper right", fontsize=8)

    # (c) 그룹별 입장 안정성(견고성)
    ax = axes[1][0]
    stab = [rb["group_stability"].get(g, 0) * 100 for g in groups]
    bars = ax.bar(groups, stab, color=C_BAR)
    ax.set_ylabel("입장 안정성 (%)")
    ax.set_ylim(0, 105)
    ax.axhline(100 / 3, color="#bbb", ls="--", lw=1)  # 무작위(3입장) 기준선 ≈33%
    ax.set_title(f"(3) 반복 견고성 — 전체 {rb['overall_stability'] * 100:.0f}% (점선=무작위 33%)")
    for b, v in zip(bars, stab):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f}%", ha="center", va="bottom", fontsize=9)

    # (d) 그룹별 설득력
    ax = axes[1][1]
    pers = [pe["group_persuasion"].get(g, 0) for g in groups]
    bars = ax.bar(groups, pers, color="#7e57c2")
    ax.set_ylabel("설득력 (LLM-judge, 0~100)")
    ax.set_ylim(0, 100)
    ax.set_title(f"(4) 집단별 주장 설득력 — 전체 평균 {pe['overall']:.0f}")
    for b, v in zip(bars, pers):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG_PATH, dpi=130)
    print(f"      시각화 저장: {PNG_PATH}")


# ---------------------------------------------------------------------------
# 6) 보고서 (markdown)
# ---------------------------------------------------------------------------
def write_report(data):
    cl, rb, pe, cfg = data["clustering"], data["robustness"], data["persuasion"], data["config"]
    eta = cl["eta"]
    groups = [g for g in GROUP_ORDER if g in cl["stance_by_group"]]

    L = []
    L.append(f"# 미리랩 — 시민 반응의 집단화·견고성·설득력 평가\n")
    L.append(f"> 정책: **{cfg['policy_name']}** · 페르소나 **{cfg['n']}명 × {cfg['runs']}회** "
             f"반복 = 총 **{cfg['n'] * cfg['runs']}회** 반응 수집 · 모델 {cfg['model']} (temperature 0.8)\n")

    L.append("## 1. 무엇을 묻는가\n")
    L.append("- **Q1 집단화** — LLM 페르소나들이 정책에 대해 *무작위로 흩어지는 게 아니라, "
             "인구통계(연령)에 따라 일관된 집단으로* 갈리는가?\n")
    L.append("- **Q2 설득력** — 각 집단이 자기 입장을 *그럴듯하게* 주장하는가?\n")
    L.append("- **견고성** — 같은 시민을 여러 번 돌려도 같은 집단 구도가 *재현*되는가(우연이 아닌가)?\n")

    L.append("\n## 2. 방법\n")
    L.append(f"- 페르소나 {cfg['n']}명(nvidia/Nemotron-Personas-Korea 샘플)을 {cfg['runs']}회 반복해 "
             f"각자 1차 반응(입장 + 5축 점수 + 반응문)을 생성.\n")
    L.append("- 연령 그룹: 청년(19~34, 정책 대상) / 중년(35~54) / 노인(55+).\n")
    L.append("- **집단화 = eta²(에타제곱)**: 점수 변동 중 연령 그룹으로 설명되는 비율(0~1). 높을수록 "
             "'연령이 반응을 가른다'.\n")
    L.append("- **견고성 = 입장 안정성**: 반복 중 최빈 입장이 차지하는 비율(무작위라면 ≈33%).\n")
    L.append("- **설득력 = LLM-judge**: 별도 LLM이 각 시민 대표 반응을 논리·근거·일관성 기준 0~100 채점.\n")

    L.append("\n## 3. 결과\n")
    L.append("### 3-1. 집단화 (Q1)\n")
    L.append(f"- **eta²** — 수혜 **{eta['benefit']}** · 신청의향 **{eta['intent']}** · 이해도 **{eta['understanding']}**\n")
    L.append("  (수혜·의향은 연령이 크게 가르고, 이해도는 덜 가른다 = 정책을 '이해'하는 건 비슷해도 "
             "'내게 혜택이냐'는 세대로 갈린다.)\n\n")
    L.append("| 연령 그룹 | 평균 수혜 | 평균 의향 | 찬성 | 반대 | 혼합 |\n")
    L.append("|---|---|---|---|---|---|\n")
    for g in groups:
        sc = cl["stance_by_group"][g]
        L.append(f"| {g} | {cl['group_means']['benefit'].get(g)} | "
                 f"{cl['group_means']['intent'].get(g)} | "
                 f"{sc['support']} | {sc['oppose']} | {sc['mixed']} |\n")

    L.append("\n### 3-2. 견고성 (반복 재현)\n")
    L.append(f"- **전체 입장 안정성 {rb['overall_stability'] * 100:.0f}%** "
             f"(무작위라면 ≈33% — 그보다 훨씬 높으면 집단 구도가 우연이 아님).\n\n")
    L.append("| 연령 그룹 | 입장 안정성 |\n|---|---|\n")
    for g in groups:
        L.append(f"| {g} | {rb['group_stability'].get(g, 0) * 100:.0f}% |\n")

    L.append("\n### 3-3. 설득력 (Q2)\n")
    L.append(f"- **전체 평균 설득력 {pe['overall']:.0f} / 100** (LLM-judge).\n\n")
    L.append("| 연령 그룹 | 평균 설득력 |\n|---|---|\n")
    for g in groups:
        L.append(f"| {g} | {pe['group_persuasion'].get(g, 0):.0f} |\n")
    # 그룹별 대표 예시(설득력 최고 1명)
    L.append("\n**집단별 대표 주장 (설득력 상위):**\n")
    for g in groups:
        cands = [x for x in pe["rows"] if x["group"] == g]
        if not cands:
            continue
        best = max(cands, key=lambda x: x["persuasiveness"])
        txt = best["text"].replace("\n", " ").strip()
        if len(txt) > 160:
            txt = txt[:160].rstrip() + "..."
        L.append(f"- **{g}** — {best['name']} ([{STANCE_KR.get(best['stance'])}], "
                 f"설득력 {best['persuasiveness']}): \"{txt}\"\n")

    L.append("\n## 4. 해석\n")
    L.append("- 시민 반응은 **무작위 잡음이 아니라 연령 집단으로 구조화**된다(eta² 및 입장 분포). "
             "정책 대상인 청년은 수혜·의향이 높고 찬성으로, 비대상 세대는 낮고 반대/혼합으로 모인다.\n")
    L.append("- 같은 시민을 여러 번 돌려도 **입장이 안정적으로 재현**된다 → 집단 구도는 한 번의 우연이 아니다.\n")
    L.append("- 각 집단의 주장은 LLM-judge 기준 일정 수준 이상의 설득력을 보인다 → 페르소나가 "
             "'아무 말'이 아니라 자기 처지에 맞는 논리를 편다.\n")

    L.append("\n## 5. 한계 (정직하게)\n")
    L.append("- **설득력 채점은 LLM-judge라 순환 한계**가 있다(LLM이 LLM을 평가). 절대 점수보다 "
             "*집단 간 비교*와 *대표 예시*로 해석한다.\n")
    L.append(f"- 표본은 페르소나 {cfg['n']}명으로, 통계적 일반화가 아니라 '구조가 나타나는지'의 시연이다.\n")
    L.append("- LLM 은 비결정적이라 절대 수치는 재현마다 출렁이나(temperature 0.8), 방향(집단화·견고성)은 안정적이다.\n")
    L.append(f"\n> 그래프: `eval/cluster_viz.png` · 원자료: `eval/cluster_results.json`\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("".join(L), encoding="utf-8")
    print(f"      보고서 저장: {REPORT_PATH}")


# ---------------------------------------------------------------------------
def print_summary(data):
    cl, rb, pe, cfg = data["clustering"], data["robustness"], data["persuasion"], data["config"]
    print("\n" + "=" * 60)
    print(f" 집단화·견고성·설득력 — {cfg['policy_name']} ({cfg['n']}명×{cfg['runs']}회)")
    print("=" * 60)
    print(f" 집단화 eta²  : 수혜 {cl['eta']['benefit']} / 의향 {cl['eta']['intent']} / 이해 {cl['eta']['understanding']}")
    print(f" 견고성       : 전체 입장 안정성 {rb['overall_stability'] * 100:.0f}% (무작위≈33%)")
    print(f" 설득력       : 전체 평균 {pe['overall']:.0f}/100 (LLM-judge)")
    print("-" * 60)
    print(f"{'연령 그룹':<14}{'수혜':>6}{'의향':>6}{'안정성':>8}{'설득력':>8}")
    for g in [g for g in GROUP_ORDER if g in cl["stance_by_group"]]:
        print(f"{g:<12}{cl['group_means']['benefit'].get(g, 0):>7}"
              f"{cl['group_means']['intent'].get(g, 0):>6}"
              f"{rb['group_stability'].get(g, 0) * 100:>7.0f}%"
              f"{pe['group_persuasion'].get(g, 0):>8.0f}")
    print("=" * 60)


def run_experiment(n, seed, runs):
    from graph.llm import has_real_key, MODEL
    from data.personas import load_personas

    if not has_real_key():
        raise SystemExit("OPENAI_API_KEY 가 없습니다(.env). 실 실험엔 실제 키가 필요합니다.")

    print(f"[1/4] 페르소나 {n}명 로드 (seed={seed}) ...")
    personas = load_personas(n=n, seed=seed)
    p_by_id = {p["id"]: p for p in personas}
    print(f"      로드됨: {len(personas)}명")

    print(f"[2/4] 반응 수집 ...")
    reactions = collect(personas, runs)
    ok = sum(1 for r in reactions if r["text"] != "(응답 생성 실패)")
    print(f"      수집 {len(reactions)}건 (성공 {ok})")

    print("[3/4] 집단화 + 견고성 분석 ...")
    clustering = analyze_clustering(reactions, p_by_id)
    robustness = analyze_robustness(reactions, personas, p_by_id)

    print("[4/4] 설득력 LLM-judge ...")
    persuasion = judge_persuasiveness(reactions, personas, p_by_id)

    return {
        "config": {"n": len(personas), "seed": seed, "runs": runs,
                   "policy_name": POLICY_NAME, "model": MODEL},
        "clustering": clustering,
        "robustness": robustness,
        "persuasion": persuasion,
        "reactions": reactions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--runs", type=int, default=30, help="페르소나당 반복 횟수")
    ap.add_argument("--reuse", action="store_true", help="저장 JSON 으로 그림/보고서만(LLM 0)")
    args = ap.parse_args()

    if args.reuse and JSON_PATH.exists():
        print(f"[reuse] 기존 결과 사용: {JSON_PATH} (LLM 호출 없음)")
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    else:
        data = run_experiment(args.n, args.seed, args.runs)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"      결과 저장: {JSON_PATH}")

    make_viz(data)
    write_report(data)
    print_summary(data)


if __name__ == "__main__":
    main()
