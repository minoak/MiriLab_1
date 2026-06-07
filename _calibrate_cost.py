# -*- coding: utf-8 -*-
"""②③ 검증 실행 전 비용 캘리브레이션 (Gemini).

- 입력: 무료 countTokens API 로 실제 메시지 73개 전수 측정 (0원).
- 출력(+thinking): 셀당 2콜 = 총 8콜 실측 (~$0.05) — Gemini 3 는 thinking 토큰이
  출력 단가($3/1M)로 과금되므로 실콜 usage 없이는 출력 비용을 알 수 없다.
- 결과: 288콜 전체 비용 추정 내역 출력 + eval/cost_calibration.json 저장.

가격(2026-06 공식): 입력 $0.50/1M · 출력 $3.00/1M (thinking 포함).
"""
import json
import os
import sys
import urllib.request
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 읽기만

PRICE_IN, PRICE_OUT = 0.50, 3.00  # $/1M tokens
GMODEL = "gemini-3-flash-preview"
OUT_PATH = ROOT / "eval" / "cost_calibration.json"

CEILING_TEXT = ("[전 국민 일시금 지급]\n"
                "정부는 전 국민에게 1인당 10억 원을 일시금으로 지급한다.\n"
                "신청 절차 없이 전 국민의 계좌로 자동 입금되며, "
                "소득·연령·재산 조건은 없다.")
FLOOR_TEXT = ("[전 국민 일시금 지급]\n"
              "정부는 전 국민에게 1인당 1원을 일시금으로 지급한다.\n"
              "신청 절차 없이 전 국민의 계좌로 자동 입금되며, "
              "소득·연령·재산 조건은 없다.")


def count_tokens(api_key: str, system: str, user: str) -> int:
    """무료 countTokens — 실제 보낼 system+user 의 정확한 입력 토큰."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GMODEL}:countTokens?key={api_key}")
    # systemInstruction 은 countTokens 톱레벨에선 불가 — generateContentRequest 래퍼 필요.
    body = {
        "generateContentRequest": {
            "model": f"models/{GMODEL}",
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]},
        }
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["totalTokens"]


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    assert api_key, "GEMINI_API_KEY 없음"

    from data.personas import load_personas
    from prompts import build_react_messages
    from sample_policies import SAMPLES
    import graph.llm as llm

    llm.set_provider("gemini")
    personas = load_personas(24, 42)
    youth = SAMPLES["청년 월세 한시 특별지원"]

    # ── 셀별 실제 메시지 구성 (러너와 동일 경로) ──
    cells = {
        "ablation_on": [build_react_messages(p, youth, grounded=True) for p in personas],
        "ablation_off": [build_react_messages(personas[0], youth, grounded=False)],
        "ceiling": [build_react_messages(p, CEILING_TEXT, grounded=True) for p in personas],
        "floor": [build_react_messages(p, FLOOR_TEXT, grounded=True) for p in personas],
    }

    # ── 1) 입력 전수 측정 (무료) ──
    in_tok = {}
    for cell, msgs_list in cells.items():
        toks = [count_tokens(api_key, m[0]["content"], m[1]["content"])
                for m in msgs_list]
        in_tok[cell] = toks
        print(f"[countTokens] {cell:<13} n={len(toks):>2}  "
              f"mean={mean(toks):,.0f}  min={min(toks):,}  max={max(toks):,}")

    # ── 2) 출력 실측 (셀당 2콜 = 8콜, ~$0.05) ──
    from graph.nodes import ReactionOut
    client = llm.get_client()
    out_samples = {}
    for cell, msgs_list in cells.items():
        picks = msgs_list[:2] if len(msgs_list) >= 2 else msgs_list * 2
        rows = []
        for m in picks:
            resp = client.beta.chat.completions.parse(
                model=llm.MODEL, messages=m,
                response_format=ReactionOut, temperature=1.0)
            u = resp.usage
            det = getattr(u, "completion_tokens_details", None)
            reasoning = getattr(det, "reasoning_tokens", None) if det else None
            rows.append({"prompt": u.prompt_tokens,
                         "completion": u.completion_tokens,
                         "reasoning": reasoning,
                         "total": u.total_tokens})
            print(f"[real call]   {cell:<13} prompt={u.prompt_tokens:,} "
                  f"completion={u.completion_tokens:,} "
                  f"(reasoning={reasoning}) total={u.total_tokens:,}")
        out_samples[cell] = rows

    # ── 3) 288콜 외삽 ──
    # 입력 usage 의 prompt 가 countTokens 와 다르면(스키마 주입 오버헤드 등)
    # 실측 보정 계수를 적용한다.
    ratios = []
    for cell, rows in out_samples.items():
        ct = mean(in_tok[cell])
        for r in rows:
            ratios.append(r["prompt"] / ct if ct else 1.0)
    in_correction = mean(ratios)

    # 출력 = completion (thinking 포함이 completion 에 합산되는지 reasoning 필드로 확인)
    out_mean = mean(r["completion"] for rows in out_samples.values() for r in rows)
    # completion 에 reasoning 미포함 표기인 경우 대비: total - prompt 를 상한으로
    out_mean_hi = mean((r["total"] - r["prompt"]) for rows in out_samples.values()
                       for r in rows)

    plan = {  # 콜 수 계획: 24명 × 3회
        "ablation_on": 72, "ablation_off": 72, "ceiling": 72, "floor": 72,
    }
    total_in = sum(mean(in_tok[c]) * in_correction * n for c, n in plan.items())
    total_calls = sum(plan.values())
    total_out_lo = out_mean * total_calls
    total_out_hi = out_mean_hi * total_calls

    cost_in = total_in / 1e6 * PRICE_IN
    cost_out_lo = total_out_lo / 1e6 * PRICE_OUT
    cost_out_hi = total_out_hi / 1e6 * PRICE_OUT

    print()
    print("=" * 64)
    print(f"plan: {total_calls} calls  (24명 x 3회 x 4셀)")
    print(f"input : {total_in:,.0f} tok  (countTokens 전수 x 보정 "
          f"{in_correction:.3f}) -> ${cost_in:.2f}")
    print(f"output: {total_out_lo:,.0f} ~ {total_out_hi:,.0f} tok "
          f"(콜당 {out_mean:,.0f} ~ {out_mean_hi:,.0f}) "
          f"-> ${cost_out_lo:.2f} ~ ${cost_out_hi:.2f}")
    print(f"TOTAL : ${cost_in + cost_out_lo:.2f} ~ ${cost_in + cost_out_hi:.2f}")
    print("=" * 64)

    OUT_PATH.parent.mkdir(exist_ok=True)
    json.dump({
        "model": llm.MODEL, "price_per_1m": {"in": PRICE_IN, "out": PRICE_OUT},
        "input_tokens_by_cell": {k: {"mean": round(mean(v), 1), "n": len(v),
                                     "min": min(v), "max": max(v)}
                                 for k, v in in_tok.items()},
        "input_correction": round(in_correction, 4),
        "output_samples": out_samples,
        "plan_calls": plan,
        "estimate": {
            "total_input_tokens": round(total_in),
            "total_output_tokens": [round(total_out_lo), round(total_out_hi)],
            "cost_usd": [round(cost_in + cost_out_lo, 2),
                         round(cost_in + cost_out_hi, 2)],
        },
    }, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved:", OUT_PATH)


if __name__ == "__main__":
    main()
