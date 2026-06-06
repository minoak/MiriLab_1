# -*- coding: utf-8 -*-
"""모델 질감 프로브 — gpt-4o-mini(현행) vs Gemini Flash. (dev 섬, 제품 무접촉)

목적: 프롬프트·스키마·temperature 전부 동일하게 두고 **모델만** 바꿔,
말투 질감(입말 자연성)과 측정 분포가 어떻게 달라지는지 본다.
mini 쪽은 재호출하지 않는다 — _probe_react_v2 가 저장한 A(현행) 결과를 재사용.

구글 OpenAI 호환 엔드포인트라 코드 경로도 동일(client.beta.chat.completions.parse).
검증 포인트: ①한마디 질감 ②ReactionOut(Literal enum) 구조화 출력 통과율
③stance/의향/불만 분포 드리프트(모델 교체 = 최대급 측정 도구 변경임을 수치로).

실행:
  python _probe_model_gemini.py --smoke   # 1콜 호환성 확인
  python _probe_model_gemini.py           # 본판 2정책×24명 = 48콜
  python _probe_model_gemini.py --model gemini-3.5-flash   # 모델 교체 비교
산출: eval/probe_model_gemini.json + eval/probe_model_gemini.md
"""
import sys, io, os, json, time, argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from dotenv import load_dotenv
from openai import OpenAI

from data.personas import load_personas
from prompts import build_react_messages
from sample_policies import DEFAULT_POLICY
from graph.llm import run_threaded
from graph.nodes import ReactionOut

ROOT = Path(__file__).resolve().parent
SRC_JSON = ROOT / "eval" / "probe_react_v2.json"   # mini A(현행) 결과 — 재사용
OUT_JSON = ROOT / "eval" / "probe_model_gemini.json"
OUT_MD = ROOT / "eval" / "probe_model_gemini.md"

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

# ⚠️ _probe_react_v2.ABSURD 와 글자까지 동일해야 비교가 유효하다.
#    (모듈 import 는 stdout 이중 래핑을 일으켜 일부러 복사 — 백테스트 크래시 교훈)
ABSURD = (
    "전 국민 1인당 10억 원 지급 정책\n"
    "정부는 전 국민 1인당 10억 원을 일시금으로 지급합니다. 소득·연령·재산 조건 없이\n"
    "대한민국 국민 누구나 받을 수 있습니다. 다음 달부터 정부 누리집과 주민센터에서\n"
    "신청을 받아 순차 지급할 예정입니다."
)
POLICIES = [
    ("10억지급(비현실)", ABSURD),
    ("청년월세(정상)", DEFAULT_POLICY),
]


def get_gemini_client() -> OpenAI:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("[SKIP] GEMINI_API_KEY 가 .env 에 없습니다.")
        sys.exit(0)
    return OpenAI(base_url=GEMINI_BASE, api_key=key)


def call_react(client: OpenAI, model: str, messages: list, retries: int = 3):
    """react 1콜 — 제품과 같은 temperature 1.0. 429/일시 오류는 백오프 재시도."""
    last = None
    for attempt in range(retries):
        try:
            resp = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=ReactionOut,
                temperature=1.0,
            )
            return json.loads(resp.choices[0].message.parsed.model_dump_json()), None
        except Exception as e:  # noqa: BLE001 — 프로브: 오류 종류를 수집해 보고
            last = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))   # 무료 티어 분당 제한 대비 백오프
    return None, last


def _summarize(rows: list) -> dict:
    def count(getter):
        c = {}
        for r in rows:
            if not r:
                continue
            v = getter(r)
            c[v] = c.get(v, 0) + 1
        return c
    return {
        "n_ok": sum(1 for r in rows if r),
        "stance": count(lambda r: r["stance"]),
        "intent": count(lambda r: (r.get("survey") or {}).get("intent")),
        "dissatisfaction": count(lambda r: (r.get("survey") or {}).get("dissatisfaction")),
    }


def _fmt(c: dict, order: list) -> str:
    return " / ".join(f"{k} {c.get(k, 0)}" for k in order if c.get(k, 0)) or "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3-flash-preview")
    ap.add_argument("--smoke", action="store_true", help="1콜 호환성 확인만")
    args = ap.parse_args()

    load_dotenv()
    client = get_gemini_client()
    personas = load_personas(24, seed=42)

    if args.smoke:
        p = personas[0]
        print(f"[스모크] {args.model} · {p.get('name')} · 청년월세 1콜...")
        row, err = call_react(client, args.model, build_react_messages(p, DEFAULT_POLICY))
        if err:
            print(f"[FAIL] {err}")
            sys.exit(1)
        print(f"  stance={row['stance']} intent={(row.get('survey') or {}).get('intent')}")
        print(f"  text: {row['text'][:120]}")
        print("[OK] 구조화 출력(enum 스키마) 호환 확인")
        return

    if not SRC_JSON.exists():
        print(f"[FAIL] {SRC_JSON.name} 없음 — _probe_react_v2.py 를 먼저 실행하세요.")
        sys.exit(1)
    src = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    mini_results = src["results"]   # {정책: {"A": [...], "B": [...]}}

    results: dict = {}
    errors: list = []
    for pname, ptext in POLICIES:
        print(f"\n=== {pname} — {args.model} 24콜 ===")
        out = run_threaded(
            personas,
            lambda p: call_react(client, args.model, build_react_messages(p, ptext)),
            max_workers=4,   # 무료 티어 분당 제한 고려
        )
        rows = [r for r, _ in out]
        errors += [e for _, e in out if e]
        results[pname] = rows

        sm, sg = _summarize(mini_results[pname]["A"]), _summarize(rows)
        print(f"  [mini  ] n={sm['n_ok']}  입장: {_fmt(sm['stance'], ['support', 'mixed', 'oppose'])}")
        print(f"  [gemini] n={sg['n_ok']}  입장: {_fmt(sg['stance'], ['support', 'mixed', 'oppose'])}")
        print(f"           의향: {_fmt(sg['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}"
              f"  (mini: {_fmt(sm['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])})")
        print(f"           불만: {_fmt(sg['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}"
              f"  (mini: {_fmt(sm['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])})")

    if errors:
        print(f"\n[warn] 실패 {len(errors)}건 — 첫 사례: {errors[0]}")

    OUT_JSON.write_text(json.dumps({
        "model": args.model,
        "design": "프롬프트·스키마·temp 동일, 모델만 교체. mini=probe_react_v2 A 재사용.",
        "results": results,
        "errors": errors,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [f"# 모델 질감 프로브 — gpt-4o-mini vs {args.model}\n",
          "> 같은 프롬프트(현행)·같은 스키마·temp 1.0. mini 열은 probe_react_v2 의 A 재사용.\n"]
    for pname, _ in POLICIES:
        rows_g = results[pname]
        rows_m = mini_results[pname]["A"]
        sm, sg = _summarize(rows_m), _summarize(rows_g)
        md.append(f"\n## {pname}\n")
        md.append(f"- mini 입장: {_fmt(sm['stance'], ['support', 'mixed', 'oppose'])}"
                  f"  ·  gemini 입장: {_fmt(sg['stance'], ['support', 'mixed', 'oppose'])}\n")
        md.append(f"- mini 의향: {_fmt(sm['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}"
                  f"  ·  gemini 의향: {_fmt(sg['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}\n")
        md.append(f"- mini 불만: {_fmt(sm['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}"
                  f"  ·  gemini 불만: {_fmt(sg['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}\n")
        md.append(f"\n| 시민 | mini 입장 | mini 한마디 | {args.model} 입장 | {args.model} 한마디 |\n"
                  "|---|---|---|---|---|\n")
        for p, rm, rg in zip(personas, rows_m, rows_g):
            name = f"{p.get('name')}({(p.get('demographics') or {}).get('age')})"
            def cell(r):
                if not r:
                    return "(실패)", ""
                txt = (r.get("text") or "").replace("\n", " ").replace("|", "/")
                return r.get("stance", "?"), (txt[:90] + ("…" if len(txt) > 90 else ""))
            st_m, tx_m = cell(rm)
            st_g, tx_g = cell(rg)
            md.append(f"| {name} | {st_m} | {tx_m} | {st_g} | {tx_g} |\n")
    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n저장: {OUT_JSON.name} / {OUT_MD.name} (eval/)")


if __name__ == "__main__":
    main()
