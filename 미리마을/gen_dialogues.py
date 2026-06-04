# -*- coding: utf-8 -*-
"""gen_dialogues.py — 미리마을 '맥락 대화' 생성기 (A 단계: Generative Agents 의 conversation)

핵심: 캐릭터쌍이 만나는 순간을 스케줄에서 자동으로 찾아내고(=동선의 결과),
그 시점까지 각자 한 일 + 관계를 LLM 에 줘서 그날 서사가 묻어나는 대화를 생성한다.
하루치 만남+대화를 통째로 미리 생성(녹화)해 저장 -> index.html 이 시각·장소 기반으로 재생.

gen_schedules.py 와 같은 독립 실행 패턴(graph/ 의존 X, 자체 OpenAI, .env 는 부모 미리랩 것 읽기만).

[만남 추출]  schedules.json 의 두 캐릭터 블록을 비교해 '같은 시간 + 같은 공용장소' 겹침을 찾는다.
  - 집(houses)은 각자 다른 집이라 제외, 공용장소(카페/복지관/공원 등)만.
  - 관계(relationships) 있는 쌍만(서로 아는 사이라야 대화가 자연스럽다).
  - 같은 (쌍, 장소) 의 연속/근접 겹침은 한 만남으로 병합(merge_gap), 쌍당 하루 최대 횟수 제한.

[대화 생성]  만남마다 그 시각까지의 각자 행동 이력 + 인물 시트 + 관계를 프롬프트로 -> 3~5턴 대화.
  키 없으면(또는 --fallback) 결정론 폴백(맥락 약하지만 그럴듯).

출력(data/):
  meetings.json   : [{id,start,end,place,a,b,turns:[{s,t}]}, ...]  (start/end = 분)
  meetings.js     : const MEETINGS = [...]   (index.html 로드용, dialogues.js 대체)

실행:
  python 미리마을/gen_dialogues.py             # 키 있으면 LLM, 없으면 폴백
  python 미리마을/gen_dialogues.py --fallback  # 강제 폴백(비용 0)
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(HERE, "data")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

from openai import OpenAI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# 만남 추출 파라미터
MIN_OVERLAP = 20      # 최소 공존(분) — 둘 다 도착해 함께 머무는 시간이 이보다 짧으면 만남 아님
MERGE_GAP = 40        # 같은 쌍·장소가 이 간격(분) 이내로 다시 겹치면 한 만남으로 병합
MAX_PER_PAIR = 2      # 한 쌍의 하루 최대 만남 수(가장 긴 공존 우선)
ROUTE_FACTOR = 1.5    # 직선거리 -> 도로 우회 근사 계수(index.html BFS 경로가 직선보다 김)
SPEED_BASE = 26       # index.html createAgent 의 speed=26+((i%5)*3) 와 정합. /3.2 = px/시뮬분


# --------------------------------------------------------------------------
# OpenAI (gen_schedules 와 동일 독립 패턴)
# --------------------------------------------------------------------------
_client = None


def has_real_key() -> bool:
    key = os.getenv("OPENAI_API_KEY")
    return bool(key) and not key.startswith("sk-your-key")


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=3)
    return _client


def structured_call(messages, schema, temperature=0.8):
    resp = get_client().beta.chat.completions.parse(
        model=MODEL, messages=messages, response_format=schema, temperature=temperature,
    )
    return resp.choices[0].message.parsed


def run_threaded(items, fn, max_workers=8):
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))


# --------------------------------------------------------------------------
# 구조화 출력 스키마
# --------------------------------------------------------------------------
class DialogueTurn(BaseModel):
    speaker_id: str   # 두 참가자 id 중 하나
    text: str         # 한 사람의 한 마디


class MeetingDialogue(BaseModel):
    turns: List[DialogueTurn]


# --------------------------------------------------------------------------
# 입력 로드 / 유틸
# --------------------------------------------------------------------------
def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def parse_hm(s):
    h, m = str(s).strip().split(":")
    return int(h) * 60 + int(m)


def fmt_hm(t):
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"


# --------------------------------------------------------------------------
# 만남 추출 (스케줄 겹침 -> 병합 -> 쌍당 제한)
# --------------------------------------------------------------------------
def _load_anchors():
    """좌표 앵커: 사용자 최종 좌표(루트 anchors.json) 우선, 없으면 data/anchors.js 기본값."""
    import re
    p = os.path.join(HERE, "anchors.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    src = open(os.path.join(DATA_DIR, "anchors.js"), encoding="utf-8").read()
    return json.loads(re.search(r"const ANCHORS_DEFAULT\s*=\s*(\{.*\});", src, re.S).group(1))


def _arrival_times(vid, schedule, home, parr, spd):
    """직선거리×ROUTE_FACTOR / 속도로 각 블록 '도착 시각'을 누적 추정. [(key, arrive, end), ...].
    재생(index.html)이 캐릭터를 실제로 걸어 이동시키므로, '스케줄상 그 시각'이 아니라 '도착하는 시각'을 만남 기준으로 쓴다."""
    import math
    out = []
    prev = home.get(vid, [700.0, 500.0])
    prevt = 480.0  # 08:00
    for b in schedule:
        s = parse_hm(b["start_time"]); e = parse_hm(b["end_time"]); key = b["location_key"]
        xy = home.get(vid, prev) if key == "houses" else parr.get(key, prev)
        d = math.hypot(xy[0] - prev[0], xy[1] - prev[1]) * ROUTE_FACTOR
        arrive = max(s, prevt) + d / spd
        out.append((key, arrive, e))
        prev = xy; prevt = arrive
    return out


def extract_meetings(schedules, villagers, locations, anchors):
    public = {l["key"] for l in locations if l["key"] != "houses"}
    by_id = {v["id"]: v for v in villagers}
    parr = {k: v["arrival"] for k, v in anchors.get("places", {}).items()}
    home = {r: h["pos"] for h in anchors.get("houses", []) for r in h.get("residents", [])}
    spd = {v["id"]: (SPEED_BASE + (i % 5) * 3) / 3.2 for i, v in enumerate(villagers)}

    rels = set()
    for v in villagers:
        for r in v.get("relationships", []):
            if r in by_id:
                rels.add(tuple(sorted([v["id"], r])))

    # 각 캐릭터의 블록별 '실제 도착 시각' 추정
    arr = {vid: _arrival_times(vid, schedules.get(vid, []), home, parr, spd[vid]) for vid in by_id}

    # 1) 두 캐릭터가 같은 공용장소에 '함께 도착해 머무는' 공존 구간(도착 시각 기준)
    raw = defaultdict(list)  # (a,b,place) -> [(공존시작, 공존끝), ...]
    for a, b in rels:
        for ka, arra, ea in arr[a]:
            for kb, arrb, eb in arr[b]:
                if ka == kb and ka in public:
                    s, e = max(arra, arrb), min(ea, eb)  # 둘 다 도착한 시각 ~ 먼저 떠나는 시각
                    if e - s >= MIN_OVERLAP:
                        raw[(a, b, ka)].append((s, e))

    # 2) 같은 (쌍, 장소) 연속/근접 공존 병합
    merged = []  # (a,b,place,s,e)
    for (a, b, place), ivs in raw.items():
        ivs.sort()
        cs, ce = ivs[0]
        for s, e in ivs[1:]:
            if s - ce <= MERGE_GAP:
                ce = max(ce, e)
            else:
                merged.append((a, b, place, cs, ce))
                cs, ce = s, e
        merged.append((a, b, place, cs, ce))

    # 3) 쌍당 최대 횟수 제한(긴 공존 우선)
    by_pair = defaultdict(list)
    for a, b, place, s, e in merged:
        by_pair[(a, b)].append((a, b, place, s, e))
    kept = []
    for pair, lst in by_pair.items():
        lst.sort(key=lambda m: (m[4] - m[3]), reverse=True)
        kept.extend(lst[:MAX_PER_PAIR])

    kept.sort(key=lambda m: m[3])  # 시간순
    meetings = []
    for i, (a, b, place, s, e) in enumerate(kept):
        meetings.append({"id": f"m{i:02d}", "a": a, "b": b, "place": place,
                         "start": int(round(s)), "end": int(round(e))})
    return meetings


def context_before(schedule, vid, t, loc_label):
    """그 캐릭터가 만남 시각 t 이전에 한 일(집 제외)을 최근 순으로 몇 개."""
    acts = []
    for b in schedule.get(vid, []):
        s = parse_hm(b["start_time"])
        if s < t and b["location_key"] != "houses":
            acts.append(f"{b['start_time']} {loc_label.get(b['location_key'], b['location_key'])}에서 {b['action']}")
    return acts[-4:] if acts else ["아직 집에서 하루를 시작하는 참"]


# --------------------------------------------------------------------------
# 프롬프트 (대화 생성)
# --------------------------------------------------------------------------
def build_dialogue_system(villagers, locations):
    """대화용 공통 system(캐싱 prefix). 모든 만남 호출에서 동일."""
    cast = "\n".join(f"- {v['name']}({v['id']}): {v['age']}세 {v['occupation']}, {v['personality']}"
                     for v in villagers)
    return (
        "당신은 사회 시뮬레이션의 작가입니다. 미리마을 두 주민이 같은 장소에서 마주친 순간, "
        "그 자리에서 실제로 나눌 법한 자연스러운 한국어 대화를 씁니다.\n"
        "규칙:\n"
        "- 짧고 일상적인 구어체. 한 사람당 한두 문장. 전체 3~5턴.\n"
        "- 두 사람이 '오늘 지금까지 한 일'과 성격·관계가 대화에 자연스럽게 묻어나야 한다.\n"
        "- 인사로 시작해 자연스럽게 흘러가고, 헤어지는 분위기로 마무리해도 좋다.\n"
        "- 정책/거대담론은 넣지 않는다. 소소한 동네 일상.\n"
        "- speaker_id 는 반드시 주어진 두 참가자 id 중 하나.\n\n"
        f"[미리마을 주민]\n{cast}"
    )


def build_dialogue_user(m, by_id, loc_label, schedule):
    a, b = by_id[m["a"]], by_id[m["b"]]
    ctx_a = context_before(schedule, m["a"], m["start"], loc_label)
    ctx_b = context_before(schedule, m["b"], m["start"], loc_label)
    place = loc_label.get(m["place"], m["place"])
    rel_a = ", ".join(a.get("relationships", [])) or "없음"
    rel_b = ", ".join(b.get("relationships", [])) or "없음"
    return (
        f"[만남] {fmt_hm(m['start'])}, {place}에서 {a['name']} 와(과) {b['name']} 가 마주쳤습니다.\n\n"
        f"[{a['name']}({a['id']})] {a['age']}세 {a['occupation']}. {a['personality']}\n"
        f"  오늘 지금까지: " + " / ".join(ctx_a) + "\n\n"
        f"[{b['name']}({b['id']})] {b['age']}세 {b['occupation']}. {b['personality']}\n"
        f"  오늘 지금까지: " + " / ".join(ctx_b) + "\n\n"
        f"관계: {a['name']} 가 가깝게 여기는 사람 = {rel_a}; {b['name']} 가 가깝게 여기는 사람 = {rel_b}\n\n"
        f"이 두 사람이 {place}에서 지금 나눌 자연스러운 대화를 만들어 주세요. "
        f"speaker_id 는 '{m['a']}' 또는 '{m['b']}' 만 사용."
    )


# --------------------------------------------------------------------------
# 폴백(키 없을 때) — 맥락은 약하지만 장소/관계 기반의 그럴듯한 2~3턴
# --------------------------------------------------------------------------
def fallback_dialogue(m, by_id, loc_label):
    a, b = by_id[m["a"]], by_id[m["b"]]
    place = loc_label.get(m["place"], m["place"])
    return [
        {"s": m["a"], "t": f"{b['name']}님, {place}에서 다 만나네요."},
        {"s": m["b"], "t": "그러게요. 오늘 하루 어떻게 보내고 계세요?"},
        {"s": m["a"], "t": "그럭저럭 바쁘게요. 다음에 또 봬요."},
    ]


# --------------------------------------------------------------------------
# 오케스트레이션
# --------------------------------------------------------------------------
def generate(force_fallback=False):
    villagers = _load("villagers.json")["villagers"]
    locations = _load("locations.json")["locations"]
    schedules = _load("schedules.json")
    by_id = {v["id"]: v for v in villagers}
    loc_label = {l["key"]: l["label"] for l in locations}

    anchors = _load_anchors()
    meetings = extract_meetings(schedules, villagers, locations, anchors)
    print(f"[gen_dialogues] 만남 {len(meetings)}개 추출(도착 시뮬 기반)")

    use_llm = has_real_key() and not force_fallback
    if not use_llm:
        why = "강제 폴백" if force_fallback else "OpenAI 키 없음"
        print(f"[gen_dialogues] {why} -> 결정론 폴백 대화")
        for m in meetings:
            m["turns"] = fallback_dialogue(m, by_id, loc_label)
        generated_with = "fallback"
    else:
        print(f"[gen_dialogues] OpenAI({MODEL}) -> 맥락 대화 생성 ({len(meetings)}콜)")
        system = build_dialogue_system(villagers, locations)

        def gen_one(m):
            try:
                msgs = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": build_dialogue_user(m, by_id, loc_label, schedules)},
                ]
                result = structured_call(msgs, MeetingDialogue)
                valid = {m["a"], m["b"]}
                turns = [{"s": (t.speaker_id if t.speaker_id in valid else m["a"]), "t": t.text.strip()}
                         for t in result.turns if t.text.strip()]
                return turns or fallback_dialogue(m, by_id, loc_label)
            except Exception as ex:
                print(f"[gen_dialogues] {m['id']} 실패 -> 폴백: {ex}")
                return fallback_dialogue(m, by_id, loc_label)

        # 웜업(공통 system 캐시) 후 동시 호출
        if meetings:
            meetings[0]["turns"] = gen_one(meetings[0])
            for m, turns in zip(meetings[1:], run_threaded(meetings[1:], gen_one)):
                m["turns"] = turns
        generated_with = "llm"

    _write(meetings, generated_with)
    return meetings


def _write(meetings, generated_with):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "meetings.json"), "w", encoding="utf-8") as f:
        json.dump(meetings, f, ensure_ascii=False, indent=2)
    lines = [
        f"// 미리마을 맥락 대화 데이터 (gen_dialogues.py). generated_with: {generated_with}",
        "// 만남 = 스케줄 겹침에서 추출, turns = 그 시점 맥락 기반 대화. index.html 이 시각·장소로 재생.",
        "const MEETINGS = " + json.dumps(meetings, ensure_ascii=False, indent=2) + ";",
    ]
    with open(os.path.join(DATA_DIR, "meetings.js"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[gen_dialogues] 완료: meetings.json + meetings.js ({len(meetings)}개, {generated_with})")


if __name__ == "__main__":
    force = ("--fallback" in sys.argv) or (os.getenv("GEN_FALLBACK") == "1")
    generate(force_fallback=force)
