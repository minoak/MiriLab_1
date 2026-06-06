# -*- coding: utf-8 -*-
"""_run_gap_eval.py — 과거 정책 갭 측정: 같은 정책, 같은 단위, 시뮬 − 현실 = 몇 %p인가.

질문은 그것 하나다. 등급제/방향일치율/순위/검증쌍 없음 (2026-06-06 백지화 교훈:
"사용자 질문을 다른 프레임으로 바꿔치기하지 말 것 / 결과가 나쁘면 성적표가 아니라
시스템을 고칠 것"). 이 측정은 프롬프트 전면 재설계(판단 지시 0줄 + 페르소나 상세
서사 주입) 직후의 베이스라인이다.

정직 프레이밍: LLM 은 이 정책들의 실제 여론을 학습으로 알고 있을 수 있다 —
재현 검증(sanity check)이지 예측력 증명이 아니다.

비교 단위 (같은 것끼리만):
  - 찬성률/반대율(%): 시뮬 stance 비율 vs 당시 여론조사 직접 찬반 문항.
    mixed ≈ 여론조사의 '모름/무응답' (단위 메모: 강제선택 보정도 병기).
  - 강제선택 보정: stance 가 support/oppose 면 그대로, mixed 만 lean 으로 재배분
    (lean=none 잔여 = 모름) — 준강제선택인 전화조사와 단위를 맞춘 두 번째 줄.
  - 분열도(0~1): 2·min(찬,반)/(찬+반) — 시뮬·현실 양쪽에 같은 공식.
  - 신청 의향(재난지원금만): 시뮬 intent>=50 비율 vs 사전 수령 의향 75.3% (단위 근사).
  - 청년월세: 전국 찬반 조사 부재 → 갭 측정 불가가 그 자체로 결론(정직 보고).

사전 등록(결과 보기 전에 박아두는 예측 — 사후 합리화 방지):
  - 자격분기형(재난지원금·청년월세·만나이): 페르소나의 나이·소득·처지가 가르므로
    분산 회복 예상. 재난지원금 찬성 과대(+10~20%p) 가능(RLHF 친화 prior).
  - 가치분기형(종부세): 현실 분열의 본체는 이념(진보 찬 74.6 vs 보수 반 65.7)인데
    페르소나 데이터에 이념·자산 축이 없음 → 반대 소실/무관심 쏠림 위험,
    분열도 0.1~0.35 예상(현실 0.87). 갭이 크면 처방 = 데이터 강화(상세 서사로
    부족하면 이념·주거 점유 축), 프롬프트 재수정 아님.

용법:
    python _run_gap_eval.py --dry        # 합성 반응 플러밍 (LLM 0콜)
    python _run_gap_eval.py              # 본판: 4정책 × 24명 × 3회 = 288콜 (~$0.15)
    python _run_gap_eval.py --runs 1     # 스모크 96콜
    python _run_gap_eval.py --reuse      # 저장 JSON 으로 보고서만 재생성

산출: eval/gap_results.json · eval/gap_report.md
"""
import sys
import io
import json
import argparse
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 읽기만(절대 수정 안 함)

OUT_DIR = ROOT / "eval"
JSON_PATH = OUT_DIR / "gap_results.json"
REPORT_PATH = OUT_DIR / "gap_report.md"
PNG_PATH = OUT_DIR / "gap_viz.png"

N_PERSONAS = 24
SEED = 42

# ---------------------------------------------------------------------------
# 정책 4건 — 원문은 실제 발표 내용에 충실하게(편집자 프레임 추가 금지).
# 구버전 종부세 원문의 "1주택자도 대상 확대 가능" 문구는 내가 덧붙인 위협
# 프레임이었음(백지화 진단) → 제거하고 발표 내용만.
# ---------------------------------------------------------------------------
def _load_policies():
    from sample_policies import SAMPLES
    return {
        "disaster_relief": {
            "name": "긴급재난지원금 1차 (2020)",
            "applies": True,
            "text": (
                "[긴급재난지원금 (전 국민 지급)]\n"
                "감염병 확산으로 어려움을 겪는 국민의 생계 안정과 소비 진작을 위해 "
                "모든 국민에게 긴급재난지원금을 지급합니다.\n"
                "지원 대상: 소득·재산과 관계없이 전 국민 (가구 단위 지급).\n"
                "지원 내용: 1인 가구 40만 원, 2인 가구 60만 원, 3인 가구 80만 원, "
                "4인 이상 가구 100만 원. 신용·체크카드 충전금, 지역사랑상품권, "
                "선불카드 중 선택.\n"
                "신청 방법: 카드사 홈페이지·앱, 읍면동 주민센터, 시중은행 창구에서 신청.\n"
                "유의 사항: 거주 지역 내 가맹점에서만 사용 가능하며, 사용 기한 내 쓰지 "
                "않으면 소멸합니다. 원하는 경우 전액 또는 일부를 기부할 수 있습니다."
            ),
        },
        "youth_rent": {
            "name": "청년월세 특별지원 (2022)",
            "applies": True,
            "text": SAMPLES["청년 월세 한시 특별지원"],
        },
        "age_unification": {
            "name": "만 나이 통일 (2023)",
            "applies": False,
            "text": (
                "[만 나이 통일]\n"
                "법적·사회적 나이 계산법을 '만 나이'로 통일합니다.\n"
                "내용: 출생일 기준 0세부터 시작해 생일마다 1살씩 늘어나는 만 나이를 "
                "행정·민사상 기본 나이로 적용합니다. 기존 '세는 나이'(태어나면 1살, "
                "새해마다 한 살 추가)는 공식적으로 사용하지 않습니다.\n"
                "기대 효과: 국제 기준과 일치, 나이 계산을 둘러싼 행정·계약상 혼선 해소.\n"
                "예외: 병역 판정, 청소년 보호법상 연 나이 등 일부 법령은 기존 기준을 "
                "유지합니다.\n"
                "시행: 법 공포 후 6개월 뒤부터 적용되며, 국민이 따로 신청할 것은 없습니다."
            ),
        },
        "property_tax": {
            "name": "종합부동산세 강화 (2020)",
            "applies": False,
            "text": (
                "[종합부동산세 강화]\n"
                "부동산 시장 안정과 과세 형평을 위해 종합부동산세를 강화합니다.\n"
                "내용: 다주택자(조정대상지역 2주택 이상 보유)에 대한 세율을 기존 최고 "
                "3.2%에서 최고 6.0%까지 인상합니다. 법인 보유 주택에는 최고세율을 "
                "일괄 적용합니다.\n"
                "대상: 고가 주택 보유자 및 다주택자.\n"
                "시행: 다음 연도 납부분부터 적용되며, 별도 신청 없이 고지서가 발송됩니다."
            ),
        },
    }


POLICY_ORDER = ["disaster_relief", "youth_rent", "age_unification", "property_tax"]

# ---------------------------------------------------------------------------
# 실측 앵커 — 2026-06-05 웹 재조사 + 적대적 교차검증 통과분 (mirilab 메모리 보존).
# 같은 단위(직접 찬반 문항 %)만. 분열도는 같은 공식을 현실 수치에 적용.
# ---------------------------------------------------------------------------
REFERENCE = {
    "disaster_relief": {
        "support": 65.5, "oppose": 30.1,
        "label": "리얼미터/YTN 2020-04-24 (지급 직전, ARS n=500 ±4.4%p)",
        "intent_real": 75.3,
        "intent_label": "사전 수령 의향 75.3% (같은 조사 — 시뮬 의향과 같은 단계의 유일한 실측)",
        "note": "조사방식 민감: 갤럽 면접 65 / 한국리서치 웹 54.",
    },
    "youth_rent": {
        "support": None, "oppose": None,
        "label": "전국 단위 찬반 직접 여론조사 부재 (재확인됨)",
        "note": "갭 측정 불가가 이 정책의 정직한 결론. 행정기록: 신청 49.5만(목표 3.3배), 심사 탈락 2/3.",
    },
    "age_unification": {
        "support": 71.0, "oppose": 15.0,
        "label": "한국리서치 '여론 속의 여론' 2021-12 (확률표집 웹 n=1,000 ±3.1%p)",
        "note": "모름 14% — mixed 와 대응 비교 가능.",
    },
    "property_tax": {
        "support": 53.5, "oppose": 41.4,
        "label": "리얼미터/TBS 2020-07-08 (발표기 직접 찬반, ARS n=500)",
        "note": "입법 직후(2020-08-12) 47.5:47.5 정확한 양분(분열도 1.00) 병기. "
                "현실 분열의 본체 = 이념(진보 찬 74.6 vs 보수 반 65.7).",
    },
}


def real_conflict(ref):
    s, o = ref.get("support"), ref.get("oppose")
    if s is None or o is None or (s + o) <= 0:
        return None
    return round(2.0 * min(s, o) / (s + o), 2)


# ---------------------------------------------------------------------------
# 반응 수집 — 앱과 동일 경로(build_react_messages + ReactionOut + temperature 1.0)
# ---------------------------------------------------------------------------
def collect(policies, personas, n_runs):
    from prompts import build_react_messages
    from graph.llm import structured_call, run_threaded, MODEL
    from graph.nodes import ReactionOut, survey_to_scores

    tasks = [(pk, p, run)
             for pk in POLICY_ORDER
             for run in range(n_runs)
             for p in personas]

    def _one(task):
        pk, p, run = task
        try:
            msgs = build_react_messages(p, policies[pk]["text"], grounded=True)
            out = structured_call(msgs, ReactionOut, temperature=1.0)
            return {"policy": pk, "persona_id": p["id"], "run": run,
                    "stance": out.stance, "lean": out.lean, "text": out.text,
                    "scores": survey_to_scores(out.survey),
                    "survey": out.survey.model_dump(), "ok": True}
        except Exception:
            return {"policy": pk, "persona_id": p["id"], "run": run,
                    "stance": "mixed", "lean": "none", "text": "(실패)",
                    "scores": {}, "survey": {}, "ok": False}

    print(f"  {len(POLICY_ORDER)}정책 × {len(personas)}명 × {n_runs}회 "
          f"= {len(tasks)}콜 (model={MODEL}, temp=1.0) ...")
    return run_threaded(tasks, _one, max_workers=8)


def synth(personas, n_runs, seed=7):
    """--dry: 보고서 배관 검증용 합성 반응."""
    rng = random.Random(seed)
    profile = {"disaster_relief": (0.8, 0.1), "youth_rent": (0.4, 0.2),
               "age_unification": (0.6, 0.15), "property_tax": (0.3, 0.3)}
    rows = []
    for pk in POLICY_ORDER:
        ps_, po_ = profile[pk]
        for run in range(n_runs):
            for p in personas:
                r = rng.random()
                stance = ("support" if r < ps_
                          else "oppose" if r < ps_ + po_ else "mixed")
                lean = stance if stance != "mixed" else rng.choice(
                    ["support", "oppose", "none"])
                rows.append({"policy": pk, "persona_id": p["id"], "run": run,
                             "stance": stance, "lean": lean, "text": "(합성)",
                             "scores": {"intent": rng.randint(0, 100)},
                             "survey": {}, "ok": True})
    return rows


# ---------------------------------------------------------------------------
# 집계 — run 별 → 정책별 평균(min/max 범위 동봉)
# ---------------------------------------------------------------------------
def per_run(rows, pk, run):
    rs = [r for r in rows if r["policy"] == pk and r["run"] == run and r["ok"]]
    n = len(rs)
    if n == 0:
        return None
    n_s = sum(1 for r in rs if r["stance"] == "support")
    n_o = sum(1 for r in rs if r["stance"] == "oppose")
    n_m = n - n_s - n_o

    # 강제선택 보정: stance 우선, mixed 만 lean 으로 재배분 (lean=none = 모름 잔여).
    f_s = n_s + sum(1 for r in rs if r["stance"] == "mixed" and r["lean"] == "support")
    f_o = n_o + sum(1 for r in rs if r["stance"] == "mixed" and r["lean"] == "oppose")
    f_n = n - f_s - f_o

    def pct(x):
        return round(100.0 * x / n, 1)

    def conflict(s, o):
        return round(2.0 * min(s, o) / (s + o), 2) if (s + o) > 0 else None

    # 의향 있음 비율 — 설문 매핑에서 unsure(잘 모르겠다)=50 이므로 '> 50'
    # (= probably 이상)만 센다. 실측 '반드시+아마' 의향과 같은 단위.
    # (구 연속점수 JSON 을 --reuse 로 재분석할 때도 50 정확값만 제외돼 거의 동일.)
    intents = [r["scores"].get("intent") for r in rs
               if isinstance(r["scores"].get("intent"), (int, float))]
    intent_hi = (round(100.0 * sum(1 for v in intents if v > 50) / len(intents), 1)
                 if intents else None)

    return {"n": n,
            "support": pct(n_s), "oppose": pct(n_o), "mixed": pct(n_m),
            "f_support": pct(f_s), "f_oppose": pct(f_o), "f_none": pct(f_n),
            "conflict": conflict(n_s, n_o), "conflict_forced": conflict(f_s, f_o),
            "intent_pos": intent_hi}


def aggregate(rows, n_runs):
    agg = {}
    keys = ("support", "oppose", "mixed", "f_support", "f_oppose", "f_none",
            "conflict", "conflict_forced", "intent_pos")
    for pk in POLICY_ORDER:
        runs = [m for m in (per_run(rows, pk, r) for r in range(n_runs)) if m]
        if not runs:
            agg[pk] = None
            continue
        entry = {"n_runs": len(runs), "n": runs[0]["n"]}
        for k in keys:
            vals = [m[k] for m in runs if m[k] is not None]
            if vals:
                entry[k] = round(sum(vals) / len(vals), 1 if k != "conflict" else 2)
                entry[k + "_rng"] = [min(vals), max(vals)]
            else:
                entry[k] = None
        agg[pk] = entry
    return agg


# ---------------------------------------------------------------------------
# 보고서 — 표 하나, 갭 정직 보고. 프레임 추가 금지.
# ---------------------------------------------------------------------------
def make_report(agg, policies, cfg):
    L = []
    L.append("# 과거 정책 갭 측정 — 시뮬 − 현실 (같은 정책, 같은 단위)\n")
    L.append(f"- 설정: {cfg['n']}명 × {cfg['runs']}회 · {cfg['model']} · temp 1.0 · "
             f"프롬프트 재설계(판단 지시 0줄 + 상세 서사 카드) 직후 베이스라인")
    L.append("- 정직 프레이밍: LLM이 이 정책들의 실제 여론을 학습으로 알 수 있음 — "
             "**재현 검증이지 예측력 증명 아님**.")
    L.append("- 강제선택(f_) = stance 우선, mixed만 lean 재배분 — 준강제선택 전화조사와 "
             "단위를 맞춘 보조 줄. 잔여(f_none) ≈ 여론조사 '모름'.\n")

    L.append("## 사전 등록 예측 (결과 보기 전 기록)\n")
    L.append("- 자격분기형(재난·월세·만나이): 분산 회복 예상. 재난 찬성 +10~20%p 과대 가능.")
    L.append("- 가치분기형(종부세): 이념·자산 축 부재 → 반대 소실 위험, 분열도 0.1~0.35 예상"
             "(현실 0.87). 갭 크면 처방=데이터 강화, 프롬프트 재수정 아님.\n")

    L.append("## 결과: 정책별 갭\n")
    header = ("| 정책 | 시뮬 찬/반/혼합 (%) | 강제선택 찬/반/모름 (%) | 실측 찬/반 (%) | "
              "찬성 갭(raw/강제) | 분열도 시뮬(raw/강제) | 분열도 실측 | 분열도 갭 |")
    L.append(header)
    L.append("|---|---|---|---|---|---|---|---|")
    gaps_raw, gaps_forced, gaps_conf = [], [], []
    for pk in POLICY_ORDER:
        a = agg.get(pk)
        ref = REFERENCE[pk]
        name = policies[pk]["name"]
        if a is None:
            L.append(f"| {name} | (수집 실패) | | | | | | |")
            continue
        sim_cell = f"{a['support']} / {a['oppose']} / {a['mixed']}"
        f_cell = f"{a['f_support']} / {a['f_oppose']} / {a['f_none']}"
        rc = real_conflict(ref)
        if ref["support"] is None:
            L.append(f"| {name} | {sim_cell} | {f_cell} | **조사 부재** | 측정 불가 | "
                     f"{a['conflict']} / {a['conflict_forced']} | — | 측정 불가 |")
            continue
        g_raw = round(a["support"] - ref["support"], 1)
        g_f = round(a["f_support"] - ref["support"], 1)
        g_c = (round(a["conflict"] - rc, 2) if (a["conflict"] is not None and rc is not None)
               else None)
        gaps_raw.append(abs(g_raw)); gaps_forced.append(abs(g_f))
        if g_c is not None:
            gaps_conf.append(abs(g_c))
        L.append(f"| {name} | {sim_cell} | {f_cell} | {ref['support']} / {ref['oppose']} | "
                 f"{g_raw:+} / {g_f:+} | {a['conflict']} / {a['conflict_forced']} | "
                 f"{rc} | {g_c:+} |")
    L.append("")
    if gaps_raw:
        L.append(f"**찬성률 절대 갭 평균(MAE)**: raw {round(sum(gaps_raw)/len(gaps_raw),1)}%p · "
                 f"강제선택 {round(sum(gaps_forced)/len(gaps_forced),1)}%p "
                 f"(측정 가능 {len(gaps_raw)}정책)")
    if gaps_conf:
        L.append(f"**분열도 절대 갭 평균**: {round(sum(gaps_conf)/len(gaps_conf),2)} (0~1)")
    L.append("")

    # 보조 비교: 재난지원금 의향 (단위 근사 명시)
    a = agg.get("disaster_relief")
    if a and a.get("intent_pos") is not None:
        L.append(f"**보조**: 재난지원금 시뮬 '신청 의향 있음'(아마+반드시, unsure 제외) 비율 "
                 f"{a['intent_pos']}% vs 사전 수령 의향 실측 75.3% (같은 단계·같은 단위 — "
                 f"설문 전환으로 문항 단위 비교 가능해짐)\n")

    L.append("## 출처 (실측 앵커)\n")
    for pk in POLICY_ORDER:
        ref = REFERENCE[pk]
        L.append(f"- {policies[pk]['name']}: {ref['label']}. {ref.get('note','')}")
    L.append("")
    L.append("## 한계 (정직 노트)\n")
    L.append("- 표본 24명 — 비율의 최소 단위가 ~4.2%p. 분열도는 더 거칠다.")
    L.append("- 자극 차이: 시뮬은 발표문 전문 제공, 실측 응답자는 헤드라인 수준 정보 + "
             "조사원 1~2문장 — 이해도·관여 방향의 체계적 차이.")
    L.append("- mixed ↔ '모름/무응답' 매핑은 근사(양가/모름/무관심이 한 버킷).")
    L.append("- 페르소나에 이념·자산(주거 점유) 축 없음 — 가치분기형 정책의 알려진 공백.")
    L.append("- LLM 비결정성: run 간 범위는 JSON 의 *_rng 참조.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 시각화 — 패널 1개 = 비교 1개 (백지화 세션 사용자 피드백), 한글 폰트, ASCII 마커.
# ---------------------------------------------------------------------------
SHORT = {"disaster_relief": "재난지원금", "youth_rent": "청년월세",
         "age_unification": "만나이 통일", "property_tax": "종부세 강화"}
C_SUP, C_OPP, C_MIX, C_REAL = "#2a6fdb", "#d9534f", "#b8b8b8", "#f0ad4e"


def make_viz(agg, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False

    names = [SHORT[k] for k in POLICY_ORDER]
    x = list(range(len(POLICY_ORDER)))

    # 헤드라인 수치 재계산(보고서와 동일 정의)
    g_sup, g_conf = [], []
    for pk in POLICY_ORDER:
        a, ref = agg.get(pk), REFERENCE[pk]
        if a and ref["support"] is not None:
            g_sup.append(abs(a["support"] - ref["support"]))
            rc = real_conflict(ref)
            if a["conflict"] is not None and rc is not None:
                g_conf.append(abs(a["conflict"] - rc))
    mae = round(sum(g_sup) / len(g_sup), 1) if g_sup else None
    mae_c = round(sum(g_conf) / len(g_conf), 2) if g_conf else None

    fig, axes = plt.subplots(1, 3, figsize=(17, 6.2))
    fig.suptitle(
        f"과거 정책 갭 측정 (프롬프트 재설계 베이스라인) — 찬성률 MAE {mae}%p · "
        f"분열도 평균 갭 {mae_c}\n"
        "만장일치는 해소(혼합층 등장, 종부세 분열 0 -> 0.52) · 남은 갭 = 반대 진영과 "
        "'비대상자의 규범적 찬성'의 운반체(이념 축) 부재 — 데이터 강화가 다음 수\n"
        f"({cfg['n']}명 x {cfg['runs']}회 · {cfg['model']} · 재현 검증이지 예측력 증명 아님)",
        fontsize=11.5, fontweight="bold")

    # (1) 찬성률: 시뮬 vs 실측 ------------------------------------------------
    ax = axes[0]
    w = 0.36
    for i, pk in enumerate(POLICY_ORDER):
        a, ref = agg.get(pk), REFERENCE[pk]
        sv = a["support"] if a else 0
        ax.bar(i - w / 2, sv, w, color=C_SUP)
        ax.text(i - w / 2, sv + 1.5, f"{sv:.0f}", ha="center", fontsize=9, color=C_SUP)
        if ref["support"] is not None:
            ax.bar(i + w / 2, ref["support"], w, color=C_REAL)
            ax.text(i + w / 2, ref["support"] + 1.5, f"{ref['support']:.0f}",
                    ha="center", fontsize=9, color="#c98a1b")
            gap = a["support"] - ref["support"]
            ax.text(i, max(sv, ref["support"]) + 9, f"갭 {gap:+.0f}p",
                    ha="center", fontsize=10, fontweight="bold",
                    color="#d9534f" if abs(gap) >= 15 else "#444")
        else:
            ax.text(i + w / 2, 3, "조사\n없음", ha="center", fontsize=8, color="#888")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9.5)
    ax.set_ylim(0, 112); ax.set_ylabel("찬성 (%)")
    ax.set_title("(1) 찬성률 — 시뮬(파랑) vs 당시 여론조사(주황)", fontsize=11)
    ax.set_xlabel("막대 위 '갭' = 시뮬 - 실측 (%p). 같은 정책끼리의 직접 비교",
                  fontsize=8.5, color="#666")

    # (2) 입장 구성: 시뮬(찬/반/혼합) vs 실측(찬/반/모름) ---------------------
    ax = axes[1]
    for i, pk in enumerate(POLICY_ORDER):
        a, ref = agg.get(pk), REFERENCE[pk]
        if a:
            segs = [(a["support"], C_SUP), (a["oppose"], C_OPP), (a["mixed"], C_MIX)]
            base = 0
            for v, c in segs:
                ax.bar(i - w / 2, v, w, bottom=base, color=c)
                if v >= 9:
                    ax.text(i - w / 2, base + v / 2, f"{v:.0f}", ha="center",
                            va="center", fontsize=8, color="white")
                base += v
        if ref["support"] is not None:
            s, o = ref["support"], ref["oppose"]
            unk = max(0.0, 100.0 - s - o)
            base = 0
            for v, c in [(s, C_SUP), (o, C_OPP), (unk, C_MIX)]:
                ax.bar(i + w / 2, v, w, bottom=base, color=c, alpha=0.55)
                if v >= 9:
                    ax.text(i + w / 2, base + v / 2, f"{v:.0f}", ha="center",
                            va="center", fontsize=8, color="#333")
                base += v
        else:
            ax.text(i + w / 2, 3, "조사\n없음", ha="center", fontsize=8, color="#888")
        ax.text(i - w / 2, -7, "시뮬", ha="center", fontsize=8, color="#555")
        if ref["support"] is not None:
            ax.text(i + w / 2, -7, "실측", ha="center", fontsize=8, color="#555")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9.5)
    ax.set_ylim(-10, 108); ax.set_ylabel("구성 (%)")
    ax.set_title("(2) 입장 구성 — 파랑=찬성 / 빨강=반대 / 회색=혼합·모름", fontsize=11)
    ax.set_xlabel("핵심 결함이 보이는 패널: 시뮬에서 빨강(반대)이 사라지고, "
                  "종부세는 회색(무관심)으로 쏠림", fontsize=8.5, color="#666")

    # (3) 분열도: 시뮬 vs 실측 -----------------------------------------------
    ax = axes[2]
    for i, pk in enumerate(POLICY_ORDER):
        a, ref = agg.get(pk), REFERENCE[pk]
        sv = a["conflict"] if (a and a["conflict"] is not None) else 0
        ax.bar(i - w / 2, sv, w, color=C_SUP)
        ax.text(i - w / 2, sv + 0.02, f"{sv:.2f}", ha="center", fontsize=9, color=C_SUP)
        rc = real_conflict(ref)
        if rc is not None:
            ax.bar(i + w / 2, rc, w, color=C_REAL)
            ax.text(i + w / 2, rc + 0.02, f"{rc:.2f}", ha="center",
                    fontsize=9, color="#c98a1b")
        else:
            ax.text(i + w / 2, 0.03, "조사\n없음", ha="center", fontsize=8, color="#888")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9.5)
    ax.set_ylim(0, 1.12); ax.set_ylabel("분열도 (0~1)")
    ax.set_title("(3) 찬반 분열도 — 시뮬(파랑) vs 실측(주황)", fontsize=11)
    ax.set_xlabel("분열도 = 2 x min(찬,반) / (찬+반). 0=한쪽 쏠림, 1=정확히 5:5. "
                  "구버전 시뮬은 전부 0이었음", fontsize=8.5, color="#666")

    fig.tight_layout(rect=[0, 0, 1, 0.86])
    fig.savefig(PNG_PATH, dpi=110)
    plt.close(fig)
    return PNG_PATH


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    policies = _load_policies()

    if args.reuse:
        blob = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        rows, cfg = blob["rows"], blob["config"]
    else:
        from data.personas import load_personas
        print(f"[1] 페르소나 {N_PERSONAS}명 로드 (seed={SEED}) ...")
        personas = load_personas(n=N_PERSONAS, seed=SEED)
        print(f"    -> {len(personas)}명")
        # score_scale: 점수 출처 표식 — survey_v1 = 설문 띠 점수(2026-06-06 전환).
        # 그 이전 JSON(표식 없음)은 연속 자유점수라 분포 비교 시 섞지 말 것.
        if args.dry:
            rows = synth(personas, args.runs)
            cfg = {"n": len(personas), "runs": args.runs, "model": "(dry)",
                   "score_scale": "survey_v1"}
        else:
            from graph.llm import has_real_key, MODEL
            assert has_real_key(), "실키 없음"
            print("[2] 반응 수집 ...")
            rows = collect(policies, personas, args.runs)
            ok = sum(1 for r in rows if r["ok"])
            print(f"    -> {ok}/{len(rows)} 성공")
            cfg = {"n": len(personas), "runs": args.runs, "model": MODEL,
                   "score_scale": "survey_v1"}
        JSON_PATH.write_text(
            json.dumps({"config": cfg, "rows": rows}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    print("[3] 집계 + 보고서 + 그림 ...")
    agg = aggregate(rows, cfg["runs"])
    report = make_report(agg, policies, cfg)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"    -> {REPORT_PATH}")
    png = make_viz(agg, cfg)
    print(f"    -> {png}")
    print()
    print(report)


if __name__ == "__main__":
    main()
