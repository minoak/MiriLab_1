# -*- coding: utf-8 -*-
"""검증 ① 신뢰성 — 페르소나 표본 분포 검증 (LLM 0콜, 다운로드 0).

질문: "우리 시민 24명이 진짜 한국 인구(데이터셋 전체 100만)를 닮았나?"
      (검증구조 문서의 ①층 — '재료' 검증. notebooks/미리랩_검증구조_팀공유.md)

방법:
  - 전체 분포: HF datasets-server statistics API (전체 100만 행, partial=False,
    다운로드 0). eval/dataset_statistics.json 에 캐시.
  - 표본: data.personas.load_personas(24, 42) — 실험(②③·갭)과 같은 풀.
  - 변수별 TV 거리(total variation distance, 0~1)를 재고,
    "같은 전체 분포에서 무작위 24명을 1만 번 뽑았을 때의 TV 분포" 안에서
    우리 표본이 어디쯤인지(백분위·p값)를 본다 = 부트스트랩.
    p >= 0.05 면 무작위 추출과 구분 불가 = "쏠림 없음".

  ⚠ 주장 범위(정직): 통과해도 "한국을 대표한다"가 아니라
    "무작위 추출과 구분되는 쏠림이 없다"까지만. n=24 는 작은 표본이다.

산출:
  eval/persona_eval.json     원자료(분포·TV·백분위·p)
  eval/persona_eval.md       보고서(헤드라인·표·층1/층3 노트·한계)
  eval/persona_eval_viz.png  대표 4변수 — 패널 1개=비교 1개(전체 vs 표본)

사용:
  python _run_persona_eval.py            # 캐시된 statistics 재사용
  python _run_persona_eval.py --refetch  # statistics API 재호출
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

EVAL_DIR = os.path.join(ROOT, "eval")
STATS_PATH = os.path.join(EVAL_DIR, "dataset_statistics.json")
OUT_JSON = os.path.join(EVAL_DIR, "persona_eval.json")
OUT_MD = os.path.join(EVAL_DIR, "persona_eval.md")
OUT_PNG = os.path.join(EVAL_DIR, "persona_eval_viz.png")

STATS_URL = ("https://datasets-server.huggingface.co/statistics"
             "?dataset=nvidia/Nemotron-Personas-Korea&config=default&split=train")

# 실험(②③·갭)과 같은 풀 — 바꾸면 검증 대상이 달라진다.
POOL_N, POOL_SEED = 24, 42
# 부트스트랩 설정 — seed 고정(재현성).
BOOT_ITER, BOOT_SEED = 10_000, 20260607
ALPHA = 0.05

# 검사 변수: statistics API 가 빈도를 주는 범주형 + age(히스토그램 빈).
# district(라벨 수백 개)·occupation(자유 텍스트, 빈도 미제공)은 제외 — 한계에 명시.
CAT_VARS = ["sex", "province", "education_level", "marital_status",
            "family_type", "housing_type"]
VIZ_VARS = ["age", "sex", "province", "education_level"]  # 패널 1=비교 1

VAR_LABEL = {
    "age": "나이", "sex": "성별", "province": "지역(시도)",
    "education_level": "학력", "marital_status": "혼인 상태",
    "family_type": "가구 형태", "housing_type": "주거 형태",
}


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------
def load_stats(refetch: bool = False) -> dict:
    """전체 분포 statistics(캐시 우선). partial=False 가 아니면 중단(부분 통계 금지)."""
    os.makedirs(EVAL_DIR, exist_ok=True)
    if refetch or not os.path.exists(STATS_PATH):
        with urllib.request.urlopen(STATS_URL, timeout=60) as r:
            stats = json.load(r)
        json.dump(stats, open(STATS_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    else:
        stats = json.load(open(STATS_PATH, encoding="utf-8"))
    if stats.get("partial"):
        raise RuntimeError("statistics 가 partial=True — 전체 분포가 아니므로 중단")
    return stats


def pop_distribution(stats: dict, var: str) -> tuple[list[str], np.ndarray]:
    """변수의 전체(모집단) 분포 -> (라벨 리스트, 비율 배열)."""
    cols = {c["column_name"]: c["column_statistics"] for c in stats["statistics"]}
    if var == "age":
        h = cols["age"]["histogram"]
        edges = h["bin_edges"]
        labels = [_age_bin_label(edges[i], edges[i + 1], i == len(h["hist"]) - 1)
                  for i in range(len(h["hist"]))]
        counts = np.array(h["hist"], dtype=float)
    else:
        freq = cols[var]["frequencies"]
        # 빈도 내림차순(표·그림 안정 정렬)
        items = sorted(freq.items(), key=lambda kv: -kv[1])
        labels = [k for k, _ in items]
        counts = np.array([v for _, v in items], dtype=float)
    return labels, counts / counts.sum()


def _age_bin_label(lo, hi, last: bool) -> str:
    """나이 빈 라벨. datasets-server 히스토그램은 마지막 빈만 [lo, hi] 닫힘."""
    return f"{lo}-{hi}" if last else f"{lo}-{hi - 1}"


def sample_distribution(personas: list[dict], var: str,
                        labels: list[str], stats: dict) -> np.ndarray:
    """표본(24명)의 분포를 모집단 라벨 순서에 맞춰 비율 배열로."""
    idx = {lab: i for i, lab in enumerate(labels)}
    counts = np.zeros(len(labels))
    if var == "age":
        cols = {c["column_name"]: c["column_statistics"] for c in stats["statistics"]}
        edges = cols["age"]["histogram"]["bin_edges"]
        for p in personas:
            age = (p.get("demographics") or {}).get("age") or 0
            counts[_age_bin_index(age, edges)] += 1
    else:
        for p in personas:
            val = (p.get("demographics") or {}).get(var)
            if val in idx:
                counts[idx[val]] += 1
            else:  # 모집단에 없는 라벨 — 프로브에서 NONE 확인했지만 방어
                raise RuntimeError(f"{var}: 표본 라벨 {val!r} 가 모집단에 없음")
    return counts / counts.sum()


def _age_bin_index(age: int, edges: list) -> int:
    """나이 -> 히스토그램 빈 인덱스(마지막 빈만 양끝 닫힘)."""
    n_bins = len(edges) - 1
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if (lo <= age < hi) or (i == n_bins - 1 and lo <= age <= hi):
            return i
    # 범위 밖(19 미만 등)은 가장 가까운 끝 빈으로
    return 0 if age < edges[0] else n_bins - 1


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------
def tv_distance(p: np.ndarray, q: np.ndarray) -> float:
    """total variation distance = 0.5 * sum|p-q| (0=동일, 1=완전 분리)."""
    return float(0.5 * np.abs(p - q).sum())


def bootstrap_tv(pop: np.ndarray, n: int, rng: np.random.Generator,
                 iters: int = BOOT_ITER) -> np.ndarray:
    """모집단 비율 pop 에서 n명 무작위 추출을 iters회 — 각 회의 TV 거리 배열."""
    draws = rng.multinomial(n, pop, size=iters) / n          # (iters, k)
    return 0.5 * np.abs(draws - pop[None, :]).sum(axis=1)     # (iters,)


def eval_variable(var: str, personas: list[dict], stats: dict,
                  rng: np.random.Generator) -> dict:
    """변수 1개: TV + 부트스트랩 백분위/p값."""
    labels, pop = pop_distribution(stats, var)
    samp = sample_distribution(personas, var, labels, stats)
    tv = tv_distance(pop, samp)
    boots = bootstrap_tv(pop, len(personas), rng)
    # p = 무작위 표본이 우리 표본 이상으로 어긋날 확률(클수록 평범한 표본)
    p = float((boots >= tv).mean())
    return {
        "var": var, "label": VAR_LABEL[var], "n_labels": len(labels),
        "tv": round(tv, 4),
        "boot_tv_mean": round(float(boots.mean()), 4),
        "boot_tv_p95": round(float(np.quantile(boots, 0.95)), 4),
        "percentile": round(float((boots < tv).mean()) * 100, 1),
        "p_value": round(p, 4),
        "pass": p >= ALPHA,
        "labels": labels,
        "pop": [round(float(x), 5) for x in pop],
        "sample": [round(float(x), 5) for x in samp],
    }


# ---------------------------------------------------------------------------
# 층1·층3 (숫자가 아니라 출처·정직성 — 보고서 재료)
# ---------------------------------------------------------------------------
def layer1_snapshot(stats: dict) -> dict:
    """층1 — 데이터셋 자체: 제작사(NVIDIA) 데이터셋 카드 인용 + 전체 분포 스냅샷.

    카드 내용은 2026-06 HF 데이터셋 페이지에서 발췌 — 층1의 "데이터셋↔현실" 정합은
    제작사가 이미 검증·문서화했고 우리는 그걸 인용한다(우리 실측 = 층2 표본↔데이터셋).
    """
    cols = {c["column_name"]: c["column_statistics"] for c in stats["statistics"]}
    age = cols["age"]
    sex = cols["sex"]["frequencies"]
    total = sum(sex.values())
    return {
        "rows": stats.get("num_examples"),
        "partial": bool(stats.get("partial")),
        "age": {"min": age["min"], "max": age["max"],
                "mean": age["mean"], "median": age["median"]},
        "sex_ratio": {k: round(v / total, 4) for k, v in sex.items()},
        "card_url": "https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea",
        # ── 이하 데이터셋 카드 인용(우리가 측정한 것이 아님) ──
        "card_sources": [
            "통계청 KOSIS — 성별·지역·산업·직업·여가 분포",
            "대법원 — 출생연도·성별·이름",
            "국민건강보험공단 — 건강검진 기록 (2024-12-31 기준)",
            "농촌경제연구원 — 2024 식품소비행태조사",
            "NAVER Cloud — 시드 데이터·도메인 자문",
        ],
        "card_method": ("확률 그래프 모델(PGM) + NeMo Data Designer 로 실제 분포에서 "
                        "속성을 합성. 단 변수 간 독립 가정 적용 — 상호작용 효과"
                        "(예: 성별x전공 결합 효과)는 모델링하지 않음(제작사 명시 한계)."),
        "card_fidelity": [
            "연령 분포가 한국의 현재 인구 패턴을 반영 (제작사 검증)",
            "고령층(80-89세) 성비 여:남 약 1.52배 — 여성 기대수명 반영",
            "초혼 연령(31~33세) 등 혼인 패턴이 실제 경향과 정합",
            "이름 충실도: 성+이름 고유조합 209,167개, 최다 성씨 김(21.5%) — 실제 조사와 일치",
            "커버리지: 17개 시도, 약 252개 시군구, 100만 레코드(페르소나 텍스트 700만 개)",
        ],
        "card_limits": [
            "변수 간 독립 가정 — 인구통계 변수들의 상호작용 미모델링",
            "젠더(생물학적 성별과 구분되는) 통계는 한국 공공 데이터 부재로 미반영",
            "일부 직업 분포는 현실 격차를 반영하되 교차 보정 없음",
            "공공 통계의 시의성에 의존",
        ],
    }


def layer3_derived(personas: list[dict]) -> dict:
    """층3 — 유도 필드 정직성: 데이터셋에 없어 코드가 파생한 값들의 실체."""
    dl = [p["signals"]["digital_literacy"] for p in personas]
    inc = [p["signals"]["income_level"] for p in personas]
    inc_counts = {k: inc.count(k) for k in ("low", "mid", "high")}
    return {
        "digital_literacy": {
            "origin": "결정론 파생 — 나이 기본점수 x 학력 보정 x 직업 키워드 (data/personas.py)",
            "sample_min": min(dl), "sample_max": max(dl),
            "sample_mean": round(sum(dl) / len(dl), 3),
            "honesty": "실측 아님. 나이가 주축이라 연령 분포가 통과하면 함께 따라간다.",
        },
        "income_level": {
            "origin": "결정론 파생 — 직업 키워드 우선, 학력 보정 (low/mid/high)",
            "sample_counts": inc_counts,
            "honesty": "휴리스틱 근사. 실제 소득 데이터 아님 — 정책 소득요건 판정은 근사치.",
        },
        "government_trust": {
            "origin": "uuid 해시 지터 0.5±0.10 — 사실상 자리표시자(노이즈)",
            "honesty": ("실측 아님·정보 없음. react 재설계 때 프롬프트에서 제거됨. "
                        "현재 용도는 접근도(policy_access) 가중 0.25 한 곳뿐."),
        },
    }


# ---------------------------------------------------------------------------
# 산출물
# ---------------------------------------------------------------------------
def write_markdown(results: list[dict], l1: dict, l3: dict, cfg: dict) -> None:
    n_pass = sum(r["pass"] for r in results)
    n_all = len(results)
    worst = min(results, key=lambda r: r["p_value"])
    if n_pass == n_all:
        headline = (f"검사한 {n_all}개 변수 전부 무작위 추출 기대범위 안 "
                    f"(최소 p={worst['p_value']:.2f}, 기준 {ALPHA}) — 쏠림 없음")
    else:
        bad = [r["label"] for r in results if not r["pass"]]
        headline = (f"{n_all}개 변수 중 {n_all - n_pass}개({', '.join(bad)})가 "
                    f"무작위 기대범위 밖 — 쏠림 의심")

    lines = [
        "# 검증 ① 신뢰성 — 페르소나 표본 분포",
        "",
        f"> **{headline}**",
        "",
        f"- 표본: `load_personas(n={cfg['pool_n']}, seed={cfg['pool_seed']})` — "
        "②③ 검증·갭 실험과 같은 풀",
        f"- 전체: nvidia/Nemotron-Personas-Korea {l1['rows']:,}행 "
        "(datasets-server statistics API, partial=False — 부분 통계 아님)",
        f"- 방법: 변수별 TV 거리 + 부트스트랩 {cfg['boot_iter']:,}회 "
        f"(seed={cfg['boot_seed']}, LLM 0콜·다운로드 0)",
        "",
        "**쉬운 말**: \"전체 100만 명에서 아무나 24명을 뽑아도 분포는 조금씩 어긋난다. "
        "그 '무작위로 생기는 어긋남'의 범위 안에 우리 24명이 들어 있으면, "
        "우리 표본은 한쪽으로 쏠리지 않은 것\" — p값이 그 판정이다.",
        "",
        "## 변수별 결과",
        "",
        "| 변수 | 라벨 수 | TV 거리 | 무작위 평균 TV | 백분위 | p값 | 판정 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        verdict = "통과" if r["pass"] else "쏠림 의심"
        lines.append(
            f"| {r['label']} | {r['n_labels']} | {r['tv']:.3f} | "
            f"{r['boot_tv_mean']:.3f} | {r['percentile']:.0f}% | "
            f"{r['p_value']:.3f} | {verdict} |"
        )
    lines += [
        "",
        "- TV 거리: 두 분포가 다른 정도(0=동일, 1=완전 분리). "
        "라벨이 많은 변수(가구 형태 39개)는 n=24 로는 TV 가 원래 크다 — "
        "그래서 절대값이 아니라 '무작위 표본 대비 백분위'로 판정한다.",
        f"- 판정 기준: p >= {ALPHA} (무작위 추출과 구분 불가). "
        f"{n_all}개 변수를 각각 5% 기준으로 보므로 전부 정상이어도 "
        "1개쯤은 우연히 걸릴 수 있다(다중비교) — 걸린 변수가 있다면 그 점도 고려.",
        "",
        "## 층1 — 데이터셋 자체는 믿을 만한가 (제작사 데이터셋 카드 인용)",
        "",
        f"데이터셋 카드({l1['card_url']})가 출처·방법론·정합성 검증을 직접 문서화하고 있다 — "
        "층1의 \"데이터셋 ↔ 한국 현실\" 정합은 **제작사(NVIDIA)가 이미 검증해 공개**했고, "
        "우리는 그것을 인용한다. 우리의 실측 검증(층2)은 \"표본 ↔ 데이터셋\"을 맡는다.",
        "",
        "**공식 통계 출처 (카드 명시)**:",
        "",
        *[f"- {s}" for s in l1["card_sources"]],
        "",
        f"**합성 방법**: {l1['card_method']}",
        "",
        "**제작사 자체 정합성 검증 (카드 발췌)**:",
        "",
        *[f"- {s}" for s in l1["card_fidelity"]],
        "",
        "**제작사가 밝힌 한계 (카드 발췌)**:",
        "",
        *[f"- {s}" for s in l1["card_limits"]],
        "",
        "**statistics API 로 본 전체 분포 스냅샷 (우리 확인)**:",
        "",
        f"- 전체 {l1['rows']:,}행: 나이 {l1['age']['min']}~{l1['age']['max']}세 "
        f"(평균 {l1['age']['mean']:.1f} / 중앙값 {l1['age']['median']:.0f}) — "
        "성인 전용 데이터셋(만 19세 미만 없음, 카드 명시와 일치)",
        f"- 성비: {' / '.join(f'{k} {v:.1%}' for k, v in l1['sex_ratio'].items())}",
        "",
        "## 층3 — 유도 필드 정직성 (데이터셋에 없어 코드가 만든 값)",
        "",
    ]
    for key, info in l3.items():
        lines.append(f"- **{key}**: {info['origin']}")
        lines.append(f"  - {info['honesty']}")
    lines += [
        "",
        "## 한계 (정직)",
        "",
        f"- n={cfg['pool_n']} 작은 표본 — 통과의 의미는 \"무작위 추출과 구분되는 쏠림 없음\"까지. "
        "\"한국 인구를 대표한다\"는 주장이 아니다.",
        "- 변수별(주변) 분포만 검증 — 결합분포(예: '고령 x 저학력' 조합 비율)는 미검증. "
        "단 데이터셋 자체도 변수 간 독립 가정으로 합성됐다(층1 카드 한계) — "
        "결합분포 정합은 원천 데이터 수준에서도 보장되지 않는 영역.",
        "- district(시군구, 라벨 수백 개)·occupation(자유 텍스트, 빈도 미제공)은 검사 제외.",
        "- 부트스트랩은 '같은 데이터셋에서의 무작위 추출' 대비다 — 층1 한계와 같은 이유로 "
        "한국 현실 자체와의 비교가 아니다.",
        "",
        f"재실험: `python _run_persona_eval.py` (statistics 캐시 재사용, "
        "`--refetch` 로 API 재호출. LLM 0콜)",
        "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_viz(results: list[dict], cfg: dict) -> None:
    """대표 4변수 — 패널 1개=비교 1개(전체 vs 표본 쌍막대 + 판정 색 제목)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False

    by_var = {r["var"]: r for r in results}
    n_pass = sum(r["pass"] for r in results)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    for ax, var in zip(axes.flat, VIZ_VARS):
        r = by_var[var]
        labels, pop, samp = r["labels"], r["pop"], r["sample"]
        x = np.arange(len(labels))
        w = 0.38
        ax.bar(x - w / 2, pop, w, label="전체 100만", color="#9aa7b5")
        ax.bar(x + w / 2, samp, w, label=f"표본 {cfg['pool_n']}명", color="#3b78c3")
        ok = r["pass"]
        ax.set_title(
            f"{r['label']} — {'통과' if ok else '쏠림 의심'} "
            f"(TV {r['tv']:.2f}, p={r['p_value']:.2f})",
            color=("#1a7a3a" if ok else "#b03030"), fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        rot = 45 if len(labels) > 6 else 0
        ax.set_xticklabels(labels, rotation=rot, ha="right" if rot else "center",
                           fontsize=8)
        ax.set_ylabel("비율", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.25)

    fig.suptitle(
        f"검증 ① 신뢰성 — 표본이 전체 분포를 닮았나: {n_pass}/{len(results)}개 변수 통과",
        fontsize=14, fontweight="bold")
    fig.text(0.5, 0.935,
             "각 패널 = 비교 1개(회색=전체 분포, 파랑=우리 표본). p값 = 무작위 24명을 "
             f"{cfg['boot_iter']:,}번 뽑았을 때 우리보다 더 어긋날 확률(클수록 평범한 표본).",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true", help="statistics API 재호출")
    args = ap.parse_args()

    stats = load_stats(refetch=args.refetch)
    from data.personas import load_personas
    personas = load_personas(POOL_N, POOL_SEED)
    if len(personas) != POOL_N:
        raise RuntimeError(f"페르소나 {len(personas)}명 != {POOL_N}명")

    rng = np.random.default_rng(BOOT_SEED)
    cfg = {"pool_n": POOL_N, "pool_seed": POOL_SEED,
           "boot_iter": BOOT_ITER, "boot_seed": BOOT_SEED, "alpha": ALPHA,
           "stats_source": STATS_URL, "llm_calls": 0}

    results = [eval_variable(v, personas, stats, rng)
               for v in ["age"] + CAT_VARS]
    l1 = layer1_snapshot(stats)
    l3 = layer3_derived(personas)

    os.makedirs(EVAL_DIR, exist_ok=True)
    json.dump({"config": cfg, "results": results, "layer1": l1, "layer3": l3},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_markdown(results, l1, l3, cfg)
    write_viz(results, cfg)

    # 콘솔 요약(ASCII 위주 — cp949 안전)
    print("=" * 60)
    for r in results:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"[{mark}] {r['var']:<16} TV={r['tv']:.3f} "
              f"pct={r['percentile']:5.1f}% p={r['p_value']:.3f}")
    n_pass = sum(r["pass"] for r in results)
    print("-" * 60)
    print(f"{n_pass}/{len(results)} variables pass (alpha={ALPHA})")
    print("out:", OUT_JSON)
    print("out:", OUT_MD)
    print("out:", OUT_PNG)


if __name__ == "__main__":
    main()
