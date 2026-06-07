# -*- coding: utf-8 -*-
"""PPT용 검증·벤치 차트 2장 생성 (eval JSON에서, LLM 0콜).

- eval/ablation_shift_viz.png : 검증 ② 부검 핵심 — ON/OFF 응답 분포 이동
- eval/behavior_bench_viz.png : 행동 벤치마크 v1 대표 3장면

_make_pptx.py 가 이 두 PNG 를 임베드한다. 검증·벤치를 재실행했으면
이 스크립트도 재실행해 그림을 갱신할 것.
"""
import json
import sys
import io
from pathlib import Path
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

C_ON, C_OFF = "#3b78c3", "#9aa7b5"
C_SUP, C_OPP, C_MIX = "#2a6fdb", "#d9534f", "#b8b8b8"

# ── 1) ON/OFF 이동 차트 ────────────────────────────────────────────────
ab = json.loads((ROOT / "eval" / "ablation_results.json").read_text(encoding="utf-8"))
rows_on = [r for r in ab["rows"] if r["cond"] == "on" and r["ok"]]
rows_off = [r for r in ab["rows"] if r["cond"] == "off" and r["ok"]]

BEN = [("big_help", "큰 도움"), ("some_help", "조금 도움"), ("no_effect", "영향 없음"),
       ("slight_loss", "약간 손해"), ("big_loss", "큰 손해")]
INT = [("surely", "꼭 신청"), ("probably", "아마"), ("unsure", "글쎄"),
       ("probably_not", "아마 안 함"), ("no_need", "필요 없음")]


def pcts(rows, field, keys):
    c = Counter(r["survey"].get(field) for r in rows)
    n = sum(c.values())
    return [100 * c.get(k, 0) / n for k, _ in keys]


fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.2))
for ax, field, keys, t in ((axes[0], "benefit", BEN, "살림에 도움이 되나"),
                           (axes[1], "intent", INT, "신청할 건가")):
    on_v, off_v = pcts(rows_on, field, keys), pcts(rows_off, field, keys)
    x = range(len(keys))
    w = 0.38
    ax.bar([i - w / 2 for i in x], off_v, w, color=C_OFF, label="OFF (익명 시민)")
    ax.bar([i + w / 2 for i in x], on_v, w, color=C_ON, label="ON (인물 카드)")
    for i in x:
        if off_v[i] >= 3:
            ax.text(i - w / 2, off_v[i] + 2, f"{off_v[i]:.0f}%", ha="center",
                    fontsize=10, color="#667")
        if on_v[i] >= 3:
            ax.text(i + w / 2, on_v[i] + 2, f"{on_v[i]:.0f}%", ha="center",
                    fontsize=10, color=C_ON, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels([lab for _, lab in keys], fontsize=10.5)
    ax.set_ylim(0, 112)
    ax.set_ylabel("응답 비율 (%)")
    ax.set_title(t, fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.25)
fig.suptitle("같은 정책(청년월세), 인물 카드만 넣었을 뿐인데 — 답이 통째로 이동 (각 72응답)",
             fontsize=14, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.9))
fig.savefig(ROOT / "eval" / "ablation_shift_viz.png", dpi=140)
plt.close(fig)
print("saved: eval/ablation_shift_viz.png")

# ── 2) 행동 벤치마크 대표 3장면 ───────────────────────────────────────
B = json.loads((ROOT / "eval" / "behavior_bench_results.json").read_text(encoding="utf-8"))
SC = B["scenarios"]

fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.0))

# (1) 무임승차 폐지 — 세대 갈림 (반대율)
g = SC["경로 무임승차 폐지"]["by_group"]
ax = axes[0]
vals = [g["60세 이상"]["oppose"], g["60세 미만"]["oppose"]]
ax.bar(["60세 이상\n(n=7)", "60세 미만\n(n=17)"], vals, 0.5,
       color=[C_OPP, "#e8b6b4"])
for i, v in enumerate(vals):
    ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold")
ax.set_ylim(0, 112)
ax.set_ylabel("반대 (%)")
ax.set_title("무임승차 폐지 — 세대가 가른다", fontsize=12, fontweight="bold")
ax.grid(axis="y", alpha=0.25)

# (2) 성별 기여금 — 성별 갈림 (반대율)
g = SC["성별 균형 기여금"]["by_group"]
ax = axes[1]
vals = [g["여성"]["oppose"], g["남성"]["oppose"]]
ax.bar(["여성\n(n=11)", "남성\n(n=13)"], vals, 0.5, color=[C_OPP, "#e8b6b4"])
for i, v in enumerate(vals):
    ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold")
ax.set_ylim(0, 112)
ax.set_ylabel("반대 (%)")
ax.set_title("성별 기여금 — 여성 전원 반대\n(남성도 23%는 규범적 반대)",
             fontsize=12, fontweight="bold")
ax.grid(axis="y", alpha=0.25)

# (3) 반려묘 보급 — 공짜 함정 간파 (입장 분포)
ov = SC["전 국민 반려묘 보급"]["overall"]
ax = axes[2]
vals = [ov["support"], ov["oppose"], ov["mixed"]]
ax.bar(["찬성", "반대", "혼합·글쎄"], vals, 0.5, color=[C_SUP, C_OPP, C_MIX])
for i, v in enumerate(vals):
    ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold")
ax.set_ylim(0, 112)
ax.set_ylabel("비율 (%)")
ax.set_title("반려묘 보급 — 공짜에 안 넘어감\n(유일 찬성자 = 펫푸드 창업 꿈)",
             fontsize=12, fontweight="bold")
ax.grid(axis="y", alpha=0.25)

fig.suptitle(f"행동 벤치마크 v1 — 사전등록 체크 {B['n_pass']}/{B['n_checks']} 통과 "
             f"(가상 정책 5종 · 24명 · {B['model']})",
             fontsize=13.5, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.88))
fig.savefig(ROOT / "eval" / "behavior_bench_viz.png", dpi=140)
plt.close(fig)
print("saved: eval/behavior_bench_viz.png")
