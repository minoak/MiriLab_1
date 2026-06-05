# -*- coding: utf-8 -*-
"""_run_ablation_eval.py — 페르소나 grounding ablation 실험 + 수렴 타당도 + 시각화.

발표용 '정량 평가' 근거를 한 번에 뽑는 dev 스크립트(제품 코드 무수정, 섬).

무엇을 만드나:
  1) grounding ON/OFF 를 각각 시뮬(eval/ablation.py 재사용) → 다양성 지표 + collapse_score.
     - collapse_score > 0  : "grounding 을 끄면 시민이 고정관념으로 붕괴(동질화)" 가설 성립.
  2) 수렴 타당도(convergent validity): 코드가 결정론으로 유도한 신호(digital_literacy,
     government_trust)와 LLM 이 낸 점수(이해도/신청의향/불만도)의 Pearson 상관.
     - grounded 에서만 상관이 살아나고 ungrounded(인물 정보 제거)에선 ~0 이면,
       "서로 모르는 두 측정이 같은 현실을 가리킨다 + grounding 이 그 연결을 만든다" 이중 증명.
  3) 시각화 PNG 3장 + 결과 JSON 저장.

실행:
    python _run_ablation_eval.py            # 실 LLM 호출(OpenAI), 8명
    python _run_ablation_eval.py --n 24     # 표본 키우기(페르소나 재다운로드 가능)
    python _run_ablation_eval.py --reuse    # 저장된 JSON 으로 그림만 다시(LLM 호출 0)

산출물: eval/ablation_results.json, eval/ablation_viz.png
"""
import sys
import io
import json
import math
import argparse
from pathlib import Path

# --- 경로/환경: 어디서 실행해도 미리랩 루트 기준으로 동작 ---
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # .env 는 읽기만(절대 수정 안 함)

import matplotlib
matplotlib.use("Agg")  # GUI 없이 PNG 저장
import matplotlib.pyplot as plt

# 한글 라벨용 폰트(Windows 기본 '맑은 고딕'). 음수 부호(-) 깨짐 방지.
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

from sample_policies import SAMPLES

OUT_DIR = ROOT / "eval"
JSON_PATH = OUT_DIR / "ablation_results.json"
PNG_PATH = OUT_DIR / "ablation_viz.png"

# 인물 특성이 수혜에 강하게 작용해 ablation 효과가 또렷한 정책(메모리 대표 정책).
POLICY_NAME = "청년 월세 한시 특별지원"
POLICY = SAMPLES[POLICY_NAME]

BLUE = "#2a6fdb"
GRAY = "#9aa0a6"
RED = "#d33"


# ---------------------------------------------------------------------------
# 순수 계산 헬퍼
# ---------------------------------------------------------------------------
def pearson(xs, ys):
    """두 리스트의 Pearson 상관계수. 표본<2 또는 분산 0 이면 None."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _pairs(reactions, sig_by_id, sig_key, score_key):
    """reactions 를 persona signals 와 조인해 (신호값, 점수값) 짝 리스트로."""
    xs, ys = [], []
    for r in reactions:
        pid = r.get("persona_id")
        sc = r.get("scores") or {}
        s = sig_by_id.get(pid, {})
        x = s.get(sig_key)
        y = sc.get(score_key)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            xs.append(float(x))
            ys.append(float(y))
    return xs, ys


def _axis_list(reactions, axis):
    """특정 점수 축만 뽑아 리스트로(분포 시각화용)."""
    out = []
    for r in reactions:
        v = (r.get("scores") or {}).get(axis)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


# 수렴 타당도로 볼 (신호 ↔ 점수) 가설 페어
_CONV_PAIRS = [
    ("digital_vs_understanding", "digital_literacy", "understanding"),
    ("digital_vs_intent",        "digital_literacy", "intent"),
    ("trust_vs_intent",          "government_trust", "intent"),
    ("trust_vs_dissatisfaction", "government_trust", "dissatisfaction"),
]


# ---------------------------------------------------------------------------
# 실험
# ---------------------------------------------------------------------------
def run_experiment(n, seed):
    from graph.build import build_graph
    from graph.llm import has_real_key, MODEL
    from data.personas import load_personas
    from eval.ablation import _run_once, _analyze

    if not has_real_key():
        raise SystemExit(
            "OPENAI_API_KEY 가 없습니다(.env). ablation 실 실험엔 실제 키가 필요합니다."
        )

    print(f"[1/4] 페르소나 {n}명 로드 (seed={seed}) ...")
    personas = load_personas(n=n, seed=seed)
    print(f"      로드됨: {len(personas)}명")
    sig_by_id = {p["id"]: (p.get("signals") or {}) for p in personas}

    app = build_graph()
    print(f"[2/4] grounding ON 시뮬 (model={MODEL}) ...")
    g_react = _run_once(app, POLICY, personas, True)
    print(f"      반응 {len(g_react)}건")
    print("[3/4] grounding OFF 시뮬 ...")
    u_react = _run_once(app, POLICY, personas, False)
    print(f"      반응 {len(u_react)}건")

    print("[4/4] 다양성 지표 + 수렴 타당도 계산 ...")
    g = _analyze(g_react)
    u = _analyze(u_react)

    g_rng = g["understanding_spread"]["max"] - g["understanding_spread"]["min"]
    u_rng = u["understanding_spread"]["max"] - u["understanding_spread"]["min"]
    delta = {
        "stance_entropy": round(g["stance_entropy"] - u["stance_entropy"], 4),
        "score_std": round(g["score_std"] - u["score_std"], 4),
        "understanding_spread_range": round(g_rng - u_rng, 4),
        # 양수 = ungrounded 가 더 동질화(붕괴)
        "collapse_score": round(u["homogeneity"] - g["homogeneity"], 4),
    }

    def conv_for(reactions):
        out = {}
        for label, sk, ak in _CONV_PAIRS:
            xs, ys = _pairs(reactions, sig_by_id, sk, ak)
            r = pearson(xs, ys)
            out[label] = round(r, 4) if r is not None else None
        return out

    convergent = {"grounded": conv_for(g_react), "ungrounded": conv_for(u_react)}

    dl_xs, und_ys = _pairs(g_react, sig_by_id, "digital_literacy", "understanding")
    contrasts = build_contrasts(g_react, u_react, personas, top=3)

    return {
        "config": {"n": n, "seed": seed, "policy_name": POLICY_NAME, "model": MODEL},
        "grounded": g,
        "ungrounded": u,
        "delta": delta,
        "convergent": convergent,
        "points": {
            "grounded_understanding": _axis_list(g_react, "understanding"),
            "ungrounded_understanding": _axis_list(u_react, "understanding"),
            "grounded_intent": _axis_list(g_react, "intent"),
            "ungrounded_intent": _axis_list(u_react, "intent"),
            "scatter_digital": dl_xs,
            "scatter_understanding": und_ys,
        },
        "contrasts": contrasts,
    }


# ---------------------------------------------------------------------------
# 시각화 (영어 라벨 — 한글 폰트 의존 없이 어디서나 안 깨짐)
# ---------------------------------------------------------------------------
def make_viz(data):
    g, u = data["grounded"], data["ungrounded"]
    delta, pts = data["delta"], data["points"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7))
    fig.suptitle(
        f"페르소나 정보 영향 실험 (Ablation) · 청년 월세 지원 · "
        f"n={data['config']['n']} · {data['config']['model']}",
        fontsize=13, fontweight="bold",
    )

    # (1) 다양성 붕괴 — 5축 점수 표준편차
    ax = axes[0]
    vals = [g["score_std"], u["score_std"]]
    bars = ax.bar(["정보 주입\n(ON)", "정보 제거\n(OFF)"], vals, color=[BLUE, GRAY])
    ax.set_ylabel("5축 점수 표준편차 (다양성)")
    ax.set_title(f"다양성 붕괴\ncollapse_score = {delta['collapse_score']:+.3f}")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}",
                ha="center", va="bottom", fontsize=10)

    # (2) 신청의향 분포 — grounding 에 가장 민감한 축(ON 넓게, OFF 뭉침)
    ax = axes[1]

    def strip(vals, xc, color):
        for i, v in enumerate(vals):
            jit = ((i * 37) % 21 - 10) / 50.0  # 결정론 jitter
            ax.scatter(xc + jit, v, color=color, s=42, alpha=0.75,
                       edgecolor="white", linewidth=0.5)

    # intent(신청의향)가 grounding 에 가장 민감. 구버전 JSON(understanding만) 호환 폴백.
    g_mid = pts.get("grounded_intent") or pts["grounded_understanding"]
    u_mid = pts.get("ungrounded_intent") or pts["ungrounded_understanding"]
    strip(g_mid, 0, BLUE)
    strip(u_mid, 1, GRAY)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["정보 주입\n(ON)", "정보 제거\n(OFF)"])
    ax.set_ylabel("신청의향 점수 (0~100)")
    ax.set_ylim(-5, 105)
    ax.set_title("신청의향 분포\n(정보 ON=퍼짐 · OFF=뭉침)")

    # (3) 수렴 타당도 — digital_literacy(코드) vs 이해도(LLM)
    ax = axes[2]
    xs, ys = pts["scatter_digital"], pts["scatter_understanding"]
    ax.scatter(xs, ys, color=BLUE, s=50, alpha=0.8, edgecolor="white", linewidth=0.5)
    r = data["convergent"]["grounded"].get("digital_vs_understanding")
    if len(xs) >= 2:
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx > 0:
            b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
            a = my - b * mx
            x0, x1 = min(xs), max(xs)
            ax.plot([x0, x1], [a + b * x0, a + b * x1], color=RED, lw=1.8)
    ax.set_xlabel("디지털 능력 (코드 유도, 0~1)")
    ax.set_ylabel("이해도 (LLM 평가, 0~100)")
    rtxt = f"r = {r:+.2f}" if r is not None else "r = n/a"
    ax.set_title(f"수렴 타당도\n{rtxt}")

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG_PATH, dpi=130)
    print(f"      시각화 저장: {PNG_PATH}")


# ---------------------------------------------------------------------------
# 콘솔 표
# ---------------------------------------------------------------------------
def print_table(data):
    g, u, d, c = data["grounded"], data["ungrounded"], data["delta"], data["convergent"]
    cfg = data["config"]
    print("\n" + "=" * 58)
    print(f" Ablation — {cfg['policy_name']}  (n={cfg['n']}, seed={cfg['seed']})")
    print("=" * 58)
    print(f"{'지표':<22}{'grounded':>12}{'ungrounded':>14}")
    print("-" * 58)
    print(f"{'입장 다양성(엔트로피)':<18}{g['stance_entropy']:>12.3f}{u['stance_entropy']:>14.3f}")
    print(f"{'5축 점수 표준편차':<19}{g['score_std']:>12.3f}{u['score_std']:>14.3f}")
    grng = g['understanding_spread']['max'] - g['understanding_spread']['min']
    urng = u['understanding_spread']['max'] - u['understanding_spread']['min']
    print(f"{'이해도 분포폭(max-min)':<16}{grng:>12.1f}{urng:>14.1f}")
    print(f"{'동질성(homogeneity)':<18}{g['homogeneity']:>12.3f}{u['homogeneity']:>14.3f}")
    print("-" * 58)
    print(f"  collapse_score = {d['collapse_score']:+.3f}   (>0 이면 'grounding 끄면 붕괴' 성립)")

    print("\n 수렴 타당도 (코드 신호 <-> LLM 점수, Pearson r):")
    print(f"{'페어':<24}{'grounded':>11}{'ungrounded':>13}")
    print("-" * 58)
    labels = {
        "digital_vs_understanding": "디지털능력 <-> 이해도",
        "digital_vs_intent":        "디지털능력 <-> 신청의향",
        "trust_vs_intent":          "정부신뢰 <-> 신청의향",
        "trust_vs_dissatisfaction": "정부신뢰 <-> 불만도",
    }
    for k, lab in labels.items():
        gv, uv = c['grounded'].get(k), c['ungrounded'].get(k)
        gs = f"{gv:+.2f}" if gv is not None else "n/a"
        us = f"{uv:+.2f}" if uv is not None else "n/a"
        print(f"{lab:<20}{gs:>11}{us:>13}")
    print("=" * 58)


# ---------------------------------------------------------------------------
# 정성 대비 — grounding 켜고 끌 때 가장 극적으로 갈린 시민 (before/after 카드)
# ---------------------------------------------------------------------------
_STANCE_KR = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}


def _clip(text, n):
    t = (text or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[:n].rstrip() + "..."


def _persona_brief(p):
    d = p.get("demographics") or {}
    s = p.get("signals") or {}
    return {
        "id": p["id"], "name": p.get("name", ""),
        "age": d.get("age", 0), "sex": d.get("sex", ""),
        "occupation": d.get("occupation", ""),
        "digital_literacy": s.get("digital_literacy"),
        "income_level": s.get("income_level"),
        "description": p.get("description", ""),
    }


def _reaction_brief(r):
    sc = r.get("scores") or {}
    return {
        "stance": r.get("stance", ""),
        "text": (r.get("text") or "").strip(),
        "understanding": sc.get("understanding"),
        "benefit": sc.get("benefit"),
        "intent": sc.get("intent"),
        "dissatisfaction": sc.get("dissatisfaction"),
    }


def build_contrasts(g_react, u_react, personas, top=3):
    """같은 시민의 grounded/ungrounded 반응을 짝지어 대비가 큰 순으로 top 명.

    대비 = |수혜 차| + |신청의향 차| (+ 입장이 뒤집혔으면 가중 30).
    """
    g_by_id = {r.get("persona_id"): r for r in g_react}
    u_by_id = {r.get("persona_id"): r for r in u_react}
    rows = []
    for p in personas:
        pid = p["id"]
        gr, ur = g_by_id.get(pid), u_by_id.get(pid)
        if not gr or not ur:
            continue
        gsc, usc = gr.get("scores") or {}, ur.get("scores") or {}

        def diff(k):
            a, b = gsc.get(k), usc.get(k)
            return abs(a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else 0

        gap = diff("intent") + diff("benefit")
        if (gr.get("stance") or "") != (ur.get("stance") or ""):
            gap += 30  # 입장이 뒤집힌 사례에 가중
        rows.append({
            "gap": round(gap, 1),
            "persona": _persona_brief(p),
            "grounded": _reaction_brief(gr),
            "ungrounded": _reaction_brief(ur),
        })
    rows.sort(key=lambda x: -x["gap"])
    return rows[:top]


def print_contrasts(contrasts):
    print("\n" + "=" * 58)
    print(" 정성 대비 — grounding 켜고 끌 때 가장 극적으로 갈린 시민")
    print("=" * 58)
    for i, c in enumerate(contrasts, 1):
        p, g, u = c["persona"], c["grounded"], c["ungrounded"]
        dl = p.get("digital_literacy")
        dls = f"{dl:.2f}" if isinstance(dl, (int, float)) else "?"
        print(f"\n[{i}] {p['name']} · {p['age']}세 {p['sex']} · {p['occupation']}"
              f" · 디지털 {dls} · 소득 {p.get('income_level')}   (대비 {c['gap']})")
        print(f"  -- 정보 주입(ON)  [{_STANCE_KR.get(g['stance'], g['stance'])}]"
              f" 수혜 {g['benefit']} / 의향 {g['intent']}")
        print(f"     \"{_clip(g['text'], 130)}\"")
        print(f"  -- 정보 제거(OFF) [{_STANCE_KR.get(u['stance'], u['stance'])}]"
              f" 수혜 {u['benefit']} / 의향 {u['intent']}")
        print(f"     \"{_clip(u['text'], 130)}\"")
    print("=" * 58)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8, help="페르소나 수 (기본 8 = 캐시)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reuse", action="store_true",
                    help="저장된 JSON 으로 그림/표만 다시(LLM 호출 0)")
    args = ap.parse_args()

    if args.reuse and JSON_PATH.exists():
        print(f"[reuse] 기존 결과 사용: {JSON_PATH} (LLM 호출 없음)")
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    else:
        data = run_experiment(args.n, args.seed)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"      결과 저장: {JSON_PATH}")

    make_viz(data)
    print_table(data)
    if data.get("contrasts"):
        print_contrasts(data["contrasts"])


if __name__ == "__main__":
    main()
