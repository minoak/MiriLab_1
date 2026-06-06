# -*- coding: utf-8 -*-
"""react 구조 개편 사전 프로브 — 현행(A) vs 신구조(B) 가벼운 비교. (dev 섬, 제품 무접촉)

B = 사용자 제안 구조의 최소 재현(단일 변인 묶음):
  ① 인물 독해 패스: 정책을 보여주기 전에 "이 사람이 어떤 사람인지"를 먼저 생성
     (페르소나당 1회, 정책 무관 — 캐릭터 해석이 정책에 물들지 않게 별도 호출)
  ② 발표 프레임: "뉴스에서 이런 기사를 봤습니다"(기정사실) →
     "정부가 이런 정책을 추진한다고 발표했다는 소식"(발표≠시행)
  ③ 믿음의 자유 한 줄: 기존 '주의 자유' 문장 옆에 같은 결로 추가.
질문 시퀀스·설문(측정 도구)·스키마는 현행 그대로 재사용 — 비교 대상을
'근거화+프레임'으로 한정한다. 캐스팅 패스는 양쪽 다 생략(단일 변인 유지).

읽을 것:
  - 10억(비현실): B에서 반응이 갈라지는가. 목표는 '전원 반대'가 아니라 분포
    (안 믿는 다수 + 기대 소수 + 우려 소수). 전원 찬성도 전원 반대도 실패.
  - 청년월세(정상): A와 B의 지표가 비슷하게 유지되는가 — 과교정 감지기
    (v2 체크리스트의 실패가 여기서 났었다: 10억 잡고 정상 정책까지 의심세).

산출: eval/probe_react_v2.json (전체 덤프) + eval/probe_react_v2.md (나란히 읽기용)
실행: python _probe_react_v2.py    (실키 필요. 독해 24 + react 96 = 120콜 ≈ $0.06)
"""
import sys, io, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pydantic import BaseModel

from data.personas import load_personas
from prompts import build_react_messages, _persona_card
from sample_policies import DEFAULT_POLICY
from graph.llm import has_real_key, structured_call, run_threaded
from graph.nodes import ReactionOut

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "eval" / "probe_react_v2.json"
OUT_MD = ROOT / "eval" / "probe_react_v2.md"

# 비현실 스트레스 정책 — 6/3 v2 체크리스트 때 쓰던 시나리오의 재현.
# 신청 절차를 남겨 intent 문항이 의미를 갖게 한다(자동지급이면 의향 문항이 공중에 뜸).
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


class ReadingOut(BaseModel):
    """인물 독해 패스 출력 — 이 사람이 어떤 사람인지 한 문단."""
    reading: str


def build_reading_messages(persona: dict) -> list:
    """정책 무관 인물 독해 요청. 조향 없음 — 소개일 뿐 판단 지시가 아니다."""
    system = (
        "다음 인물 정보를 읽고, 이 사람이 어떤 사람인지 한 문단으로 적습니다.\n"
        "처지, 성향, 요즘 신경 쓰는 것, 세상을 보는 감각이 드러나게 —\n"
        "평가하거나 미화하지 않고, 이 사람을 모르는 사람에게 소개하듯 담백하게."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _persona_card(persona)},
    ]


def build_react_messages_v2(persona: dict, policy: str, reading: str) -> list:
    """B 구조 = 현행 messages 위에 ①독해 주입 ②발표 프레임 ③믿음 자유.

    문자열 치환 기반(프로브 한정 — 본 구현은 prompts.py 재구성으로).
    치환 실패는 조용히 넘기지 않고 assert 로 죽인다(현행 프롬프트가 바뀌면 갱신).
    """
    msgs = build_react_messages(persona, policy, grounded=True)
    user = msgs[1]["content"]

    # ① 인물 독해 — 인물 카드 끝([오늘] 직전)에 삽입
    assert "[오늘]" in user, "현행 과제 프레임에 [오늘] 없음 — 프로브 갱신 필요"
    user = user.replace(
        "[오늘]", "[이 사람 읽기]\n" + reading.strip() + "\n\n[오늘]", 1)

    # ② 발표 프레임 — 기사(기정사실) → 추진 발표(발표는 늘 하고, 되는 건 따로)
    old_frame = "뉴스에서 이런 기사를 봤습니다."
    assert old_frame in user, "현행 뉴스 프레임 문장 변경됨 — 프로브 갱신 필요"
    user = user.replace(
        old_frame, "정부가 이런 정책을 추진한다고 발표했다는 소식을 접했습니다.", 1)
    assert "[기사 내용]" in user
    user = user.replace("[기사 내용]", "[발표 내용]", 1)

    # ③ 주의 자유 문장을 발표 어휘로 잇고, 같은 결로 믿음의 자유 한 줄
    old_att = (
        "기사를 얼마나 꼼꼼히 읽을지는 당신에게 달렸습니다 — 관심 밖이면\n"
        "제목과 앞부분만 보고 넘기는 것도 자연스럽습니다."
    )
    assert old_att in user, "현행 주의-자유 문장 변경됨 — 프로브 갱신 필요"
    user = user.replace(
        old_att,
        "발표를 얼마나 꼼꼼히 들여다볼지는 당신에게 달렸습니다 — 관심 밖이면\n"
        "제목만 듣고 넘기는 것도 자연스럽습니다.\n"
        "발표 내용을 얼마나 믿을지도 당신에게 달렸습니다.",
        1,
    )
    return [msgs[0], {"role": "user", "content": user}]


def _call_react(messages):
    """react 1콜 — 제품과 같은 temperature 1.0. 실패는 None."""
    try:
        out = structured_call(messages, ReactionOut, temperature=1.0)
        return json.loads(out.model_dump_json())
    except Exception as e:  # noqa: BLE001 — 프로브: 한 명 실패가 전체를 못 죽이게
        print(f"  [warn] react 실패: {e}")
        return None


def _summarize(rows: list) -> dict:
    """stance/lean/intent/dissat 토큰 분포 집계(빈도 dict)."""
    def count(key, getter):
        c = {}
        for r in rows:
            if not r:
                continue
            v = getter(r)
            c[v] = c.get(v, 0) + 1
        return c
    return {
        "n_ok": sum(1 for r in rows if r),
        "stance": count("stance", lambda r: r["stance"]),
        "lean": count("lean", lambda r: r.get("lean", "none")),
        "intent": count("intent", lambda r: (r.get("survey") or {}).get("intent")),
        "dissatisfaction": count(
            "dissat", lambda r: (r.get("survey") or {}).get("dissatisfaction")),
        "eligibility": count(
            "elig", lambda r: (r.get("survey") or {}).get("eligibility")),
    }


def _fmt_dist(c: dict, order: list) -> str:
    return " / ".join(f"{k} {c.get(k, 0)}" for k in order if c.get(k, 0)) or "-"


def main() -> None:
    if not has_real_key():
        print("[SKIP] OPENAI_API_KEY 없음 — 이 프로브는 실모드 전용입니다.")
        sys.exit(0)

    personas = load_personas(24, seed=42)
    print(f"인물 독해 패스: {len(personas)}명 (정책 무관, 1회)")
    readings = run_threaded(
        personas,
        lambda p: structured_call(build_reading_messages(p), ReadingOut,
                                  temperature=0.7).reading,
        max_workers=8,
    )
    readings_by_id = {p["id"]: r for p, r in zip(personas, readings)}

    results: dict = {}
    for pname, ptext in POLICIES:
        print(f"\n=== {pname} ===")
        print("  A(현행) 24콜...")
        rows_a = run_threaded(
            personas, lambda p: _call_react(build_react_messages(p, ptext)),
            max_workers=8)
        print("  B(신구조) 24콜...")
        rows_b = run_threaded(
            personas,
            lambda p: _call_react(
                build_react_messages_v2(p, ptext, readings_by_id[p["id"]])),
            max_workers=8)
        results[pname] = {"A": rows_a, "B": rows_b}

        for tag, rows in (("A 현행", rows_a), ("B 신구조", rows_b)):
            s = _summarize(rows)
            print(f"  [{tag}] n={s['n_ok']}  "
                  f"입장: {_fmt_dist(s['stance'], ['support', 'mixed', 'oppose'])}")
            print(f"           의향: {_fmt_dist(s['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}")
            print(f"           불만: {_fmt_dist(s['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}")

    # ── 산출물 저장 ──
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "design": "A=현행(뉴스 프레임) vs B=인물독해+발표프레임+믿음자유 (설문·스키마 동일, 캐스팅 생략)",
        "model_note": "react temperature 1.0 (제품 동일), 독해 0.7",
        "personas": [{"id": p["id"], "name": p.get("name"),
                      "age": (p.get("demographics") or {}).get("age")} for p in personas],
        "readings": readings_by_id,
        "results": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    md = ["# react 구조 프로브 — A(현행) vs B(인물독해+발표프레임+믿음자유)\n"]
    md.append("> 단일 변인 묶음 비교. 설문·스키마·temperature 동일, 캐스팅 생략.\n")
    md.append("\n## 인물 독해 샘플 (B의 패스 0 산출물)\n")
    for p in personas[:3]:
        md.append(f"**{p.get('name')}** ({(p.get('demographics') or {}).get('age')}세)\n")
        md.append(f"> {readings_by_id[p['id']]}\n")
    for pname, _ in POLICIES:
        md.append(f"\n## {pname}\n")
        rows_a, rows_b = results[pname]["A"], results[pname]["B"]
        sa, sb = _summarize(rows_a), _summarize(rows_b)
        md.append(f"- A 입장: {_fmt_dist(sa['stance'], ['support', 'mixed', 'oppose'])}"
                  f"  ·  B 입장: {_fmt_dist(sb['stance'], ['support', 'mixed', 'oppose'])}\n")
        md.append(f"- A 의향: {_fmt_dist(sa['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}"
                  f"  ·  B 의향: {_fmt_dist(sb['intent'], ['surely', 'probably', 'unsure', 'probably_not', 'no_need'])}\n")
        md.append(f"- A 불만: {_fmt_dist(sa['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}"
                  f"  ·  B 불만: {_fmt_dist(sb['dissatisfaction'], ['very', 'somewhat', 'not_much', 'none'])}\n")
        md.append("\n| 시민 | A 입장 | A 한마디 | B 입장 | B 한마디 |\n|---|---|---|---|---|\n")
        for p, ra, rb in zip(personas, rows_a, rows_b):
            name = f"{p.get('name')}({(p.get('demographics') or {}).get('age')})"
            def cell(r):
                if not r:
                    return "(실패)", ""
                txt = (r.get("text") or "").replace("\n", " ").replace("|", "/")
                return r.get("stance", "?"), (txt[:90] + ("…" if len(txt) > 90 else ""))
            st_a, tx_a = cell(ra)
            st_b, tx_b = cell(rb)
            md.append(f"| {name} | {st_a} | {tx_a} | {st_b} | {tx_b} |\n")
    OUT_MD.write_text("".join(md), encoding="utf-8")

    print(f"\n저장: {OUT_JSON.name} / {OUT_MD.name} (eval/)")
    print("읽는 법: 10억은 B가 갈라지는가(전원 한쪽이면 실패), "
          "청년월세는 A와 B가 비슷한가(다르면 과교정).")


if __name__ == "__main__":
    main()
