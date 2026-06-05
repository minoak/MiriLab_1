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
from itertools import combinations
from types import SimpleNamespace
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
MIN_OVERLAP = 12      # 최소 공존(분) — 짧아도 짧은 대화는 가능(전파 통로 확보 위해 20→12 완화)
MERGE_GAP = 40        # 같은 쌍·장소가 이 간격(분) 이내로 다시 겹치면 한 만남으로 병합
MAX_PER_PAIR = 3      # 한 쌍의 하루 최대 만남 수(가장 긴 공존 우선, 2→3 완화)
ROUTE_FACTOR = 0.8    # 직선거리 -> 도로 우회 근사 계수. 이동시간을 덜 흐르게(1.5→0.8):
#   맵이 커서 도보 ~1시간이 걸려 같은 장소(특히 어르신↔카페)서도 엇갈려 만남이 끊겼다.
#   0.8 이면 어르신이 이웃과 연결되고, 전파가 며칠에 걸쳐 점진적으로 퍼진다(관측 목적).
#   ⚠ iframe 재생은 자체 도보 속도 + '도착 대기'라, 긴 블록(카페 60~90분)은 그대로 재생되나
#   짧은 겹침 일부는 '도착 지연 놓침'으로 보일 수 있다(전파 리포트는 이 meetings 기준이 정답).
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

    # 관계(아는 사이) 집합 — 이제 만남을 '막는 게이트'가 아니라 대화 친밀도 플래그로만 쓴다.
    rels = set()
    for v in villagers:
        for r in v.get("relationships", []):
            if r in by_id:
                rels.add(tuple(sorted([v["id"], r])))

    # 각 캐릭터의 블록별 '실제 도착 시각' 추정
    arr = {vid: _arrival_times(vid, schedules.get(vid, []), home, parr, spd[vid]) for vid in by_id}

    # 1) 두 캐릭터가 같은 공용장소에 '함께 도착해 머무는' 공존 구간(도착 시각 기준).
    #    전파를 보려면 통로가 많아야 한다 → 아는 사이로 제한하지 않고 '같은 장소면 만남'.
    ids = [v["id"] for v in villagers]
    idx = {vid: i for i, vid in enumerate(ids)}
    raw = defaultdict(list)  # (a,b,place) -> [(공존시작, 공존끝), ...]
    for a, b in combinations(ids, 2):
        for ka, arra, ea in arr[a]:
            for kb, arrb, eb in arr[b]:
                if ka == kb and ka in public:
                    s, e = max(arra, arrb), min(ea, eb)  # 둘 다 도착한 시각 ~ 먼저 떠나는 시각
                    if e - s >= MIN_OVERLAP:
                        raw[(a, b, ka)].append((s, e))

    # 1.5) 집 만남 — 같은 집 식구만(anchors residents). 저녁 등 집에 함께 있을 때 가족 대화.
    #      독거(grandma)·1인 가구는 식구가 없어 집 만남이 없다(밖 만남에만 의존 — 현실 일관).
    housemates = set()
    for h in anchors.get("houses", []):
        res = [r for r in h.get("residents", []) if r in by_id]
        for ha, hb in combinations(res, 2):
            housemates.add(tuple(sorted([ha, hb], key=lambda x: idx[x])))  # ids 순서 유지
    for a, b in housemates:
        for ka, arra, ea in arr[a]:
            if ka != "houses":
                continue
            for kb, arrb, eb in arr[b]:
                if kb != "houses":
                    continue
                s, e = max(arra, arrb), min(ea, eb)
                if e - s >= MIN_OVERLAP:
                    raw[(a, b, "houses")].append((s, e))

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
                         "start": int(round(s)), "end": int(round(e)),
                         "close": tuple(sorted([a, b])) in rels})  # 친밀도(대화 톤용)
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


# ==========================================================================
# 정책 전파 시뮬레이션 (순차 + 누적 기억/일기) — step2
#
# 기존 generate()(만남별 독립 병렬 대화)와 달리, 하루의 만남을 '시간순으로' 굴리며
# 각 캐릭터가 그때까지 들은·느낀 것을 다음 대화로 들고 간다. 밤엔 그날을 '일기'로
# 압축해 다음 날의 기억(어제)으로 넘긴다(Generative Agents 의 reflection).
# 정책은 최상위(시나리오 상수)로 system 프리픽스에 실리고, 누가 아느냐는 만남에서
# LLM 이 판단(전달/반응)하며 그 결과(인지/입장 변화)를 구조화해 보고한다.
# ==========================================================================

AWARE_LEVELS = ("unaware", "aware", "interested", "acting")
STANCE_LEVELS = ("unknown", "support", "oppose", "mixed", "anxious")
AWARE_SET = {"aware", "interested", "acting"}  # '안다'로 치는 상태


class CharDelta(BaseModel):
    villager_id: str       # 두 참가자 id 중 하나(위치 매칭 보조)
    learned_policy: bool   # 이 대화로 정책을 '처음' 알게 됐나
    awareness: str         # 대화 뒤 상태: unaware|aware|interested|acting
    stance: str            # unknown|support|oppose|mixed|anxious
    note: str              # 그 인물의 한 줄 메모(오늘 일에 추가됨)


class MeetingResult(BaseModel):
    turns: List[DialogueTurn]   # 대화 (위 DialogueTurn 재사용)
    a_delta: CharDelta          # 첫 번째 참가자([A])의 변화
    b_delta: CharDelta          # 두 번째 참가자([B])의 변화


class DiaryOut(BaseModel):
    diary: str                  # 1인칭 일기(2~4문장)
    awareness: str
    stance: str


def initial_states(villagers, aware_ids=()):
    """1일차 시작 상태. aware_ids = 정책을 먼저 접한 시드(프로토타입=복지관 어르신들)."""
    aware_ids = set(aware_ids)
    return {
        v["id"]: {
            "awareness": "aware" if v["id"] in aware_ids else "unaware",
            "stance": "unknown",
            "diary": "",
        }
        for v in villagers
    }


def _delta(vid, awareness, stance="unknown", learned=False, note=""):
    """폴백/수동 델타(LLM CharDelta 와 같은 속성)."""
    return SimpleNamespace(villager_id=vid, learned_policy=learned,
                           awareness=awareness, stance=stance, note=note)


def _norm(val, allowed, default):
    return val if val in allowed else default


def _policy_tokens(policy):
    """정책에서 누수 탐지용 토큰(2자+) + '정책'. 빈 정책이면 빈 집합(스크럽 안 함)."""
    import re
    toks = {t for t in re.split(r"[^0-9A-Za-z가-힣]+", policy or "") if len(t) >= 2}
    if toks:
        toks.add("정책")
    return toks


def _bind_deltas(da, db, a_id, b_id):
    """a_delta/b_delta 를 villager_id 로 올바른 참가자에 매칭(어긋나면 위치 기준)."""
    if getattr(da, "villager_id", None) == b_id and getattr(db, "villager_id", None) == a_id:
        return db, da
    return da, db


# --- 정책 주입 프롬프트 (system = 캐싱 prefix, 전원/전 만남 공유) ---------
def build_meeting_system(villagers, locations, policy):
    cast = "\n".join(
        f"- {v['name']}({v['id']}): {v['age']}세 {v['occupation']}, {v['personality']}"
        for v in villagers
    )
    if (policy or "").strip():
        situation = (
            "[오늘 마을의 정책 상황]\n"
            "최근 다음 정책이 발표되어 마을에 '퍼지는 중'입니다:\n"
            f'"""\n{policy.strip()}\n"""\n'
            "- 각 인물은 이 정책을 이미 알 수도, 전혀 모를 수도 있습니다(만남 정보에 현재 인지 상태가 주어집니다).\n"
            "- 한 사람만 알고 상대는 모르면, 대화에서 자연스럽게 알려줄 수도(또는 화제가 안 될 수도) 있습니다.\n"
            "- 둘 다 모르면 정책 이야기는 나오지 않습니다(평범한 잡담).\n"
            "- 아는 사람은 자기 처지(나이·직업·형편)에 맞는 생각·감정(관심/찬성/반대/불안/무관심)을 드러냅니다.\n"
        )
    else:
        situation = "[상황] 특별한 정책 없이 평범한 동네 일상입니다.\n"
    return (
        "당신은 사회 시뮬레이션의 작가입니다. 미리마을 두 주민이 같은 장소에서 마주친 순간, "
        "그 자리에서 실제로 나눌 법한 자연스러운 한국어 대화를 쓰고, 대화 뒤 각자의 변화를 보고합니다.\n\n"
        + situation +
        "\n규칙:\n"
        "- 짧고 일상적인 구어체. 한 사람당 한두 문장, 전체 3~5턴.\n"
        "- 두 사람의 '오늘 한 일'·성격·관계가 자연스럽게 묻어나야 한다.\n"
        "- 친한 사이면 편하게, 잘 모르는 사이면 가볍고 예의 있게.\n"
        "- speaker_id 는 반드시 주어진 두 참가자 id 중 하나.\n"
        "- 변화 보고(a_delta=[A], b_delta=[B]): villager_id, "
        "learned_policy(이 대화로 정책을 '처음' 알게 됐으면 true), "
        "awareness(unaware|aware|interested|acting), stance(unknown|support|oppose|mixed|anxious), "
        "note(그 인물의 오늘 한 줄 메모).\n\n"
        f"[미리마을 주민]\n{cast}"
    )


def build_meeting_user(m, by_id, loc_label, schedules, today, close):
    a, b = by_id[m["a"]], by_id[m["b"]]
    ca = context_before(schedules, m["a"], m["start"], loc_label)
    cb = context_before(schedules, m["b"], m["start"], loc_label)
    place = loc_label.get(m["place"], m["place"])
    rel = "친한 사이" if close else "잘 모르는/평소 왕래 적은 사이"
    ta, tb = today[m["a"]], today[m["b"]]
    a_aw, b_aw = ta["awareness"] in AWARE_SET, tb["awareness"] in AWARE_SET
    if not a_aw and not b_aw:
        rule = ("⚠️ 두 사람 다 이 정책을 '전혀 모릅니다' → 대화에 정책 이야기가 "
                "절대 나오면 안 됩니다(그냥 평범한 동네 잡담). 둘 다 learned_policy=false, awareness=unaware.")
    elif a_aw != b_aw:
        knower = a["name"] if a_aw else b["name"]
        rule = (f"한 사람({knower})만 정책을 압니다 → 아는 쪽이 자연스럽게 알려줄 수도(또는 화제가 "
                "안 될 수도) 있습니다. 모르던 쪽이 이 대화로 알게 되면 그쪽만 learned_policy=true.")
    else:
        rule = "두 사람 다 정책을 압니다 → 정책에 대한 서로의 생각·감정을 나눌 수 있습니다."
    return (
        f"[만남] {fmt_hm(m['start'])}, {place}에서 {a['name']}과(와) {b['name']}이 마주쳤습니다. ({rel})\n\n"
        f"[A] {a['name']}({a['id']}) {a['age']}세 {a['occupation']}. {a['personality']}\n"
        f"  어제 일기: {ta['diary'] or '(없음)'}\n"
        f"  오늘 지금까지: " + " / ".join(ca) + "\n"
        f"  현재 정책 인지={ta['awareness']}, 입장={ta['stance']}\n\n"
        f"[B] {b['name']}({b['id']}) {b['age']}세 {b['occupation']}. {b['personality']}\n"
        f"  어제 일기: {tb['diary'] or '(없음)'}\n"
        f"  오늘 지금까지: " + " / ".join(cb) + "\n"
        f"  현재 정책 인지={tb['awareness']}, 입장={tb['stance']}\n\n"
        f"[이 만남의 정책 규칙] {rule}\n\n"
        f"이 둘이 {place}에서 지금 나눌 대화를 만들고, 대화 뒤 각자의 변화를 보고하세요. "
        f"speaker_id 와 villager_id 는 '{m['a']}'(A) 또는 '{m['b']}'(B)만 사용."
    )


def build_diary_messages(v, today, schedule, loc_label, policy):
    acts = [f"{b['start_time']} {loc_label.get(b['location_key'], b['location_key'])}에서 {b['action']}"
            for b in schedule] or ["집에서 하루를 보냄"]
    convo = today["log"] or ["오늘은 특별히 깊은 대화는 없었음"]
    aware = today["awareness"] in AWARE_SET
    # 모르는 사람에겐 정책을 아예 보여주지 않는다(일기 텍스트가 정책을 흘리지 않게).
    pol = (f"(오늘 마을엔 다음 정책이 퍼지는 중: {policy.strip()})\n"
           if (policy or "").strip() and aware else "")
    guard = ("" if aware else
             "※ 당신은 아직 이 정책을 전혀 모릅니다 — 일기에 정책 이야기를 쓰지 말고, "
             "정책 인지는 반드시 unaware 로 보고하세요.\n")
    return [
        {"role": "system", "content": (
            "당신은 미리마을 주민이 하루를 마치고 집에서 쓰는 1인칭 일기를 대신 써 줍니다. "
            "그날 있었던 일을 짧게 압축하되, 정책에 대해 알게 됐거나 느낀 게 있으면 솔직히 담습니다.")},
        {"role": "user", "content": (
            f"[{v['name']}({v['id']})] {v['age']}세 {v['occupation']}. {v['personality']}\n"
            f"어제 일기: {today['diary'] or '(없음)'}\n"
            f"{pol}{guard}"
            "오늘 한 일: " + " / ".join(acts) + "\n"
            "오늘 나눈 대화/들은 것: " + " / ".join(convo) + "\n"
            f"하루를 마친 지금 정책 인지={today['awareness']}, 입장={today['stance']}.\n\n"
            "이 사람의 1인칭 일기(2~4문장, 구어체)를 쓰고, 하루를 마친 시점의 "
            "정책 인지(unaware|aware|interested|acting)와 입장(unknown|support|oppose|mixed|anxious)을 보고하세요.")},
    ]


# --- 폴백(키 없음/실패) — 결정론 전달 + 간단 일기 -------------------------
def _fallback_meeting(m, by_id, loc_label, today):
    a, b = m["a"], m["b"]
    place = loc_label.get(m["place"], m["place"])
    a_aware = today[a]["awareness"] in AWARE_SET
    b_aware = today[b]["awareness"] in AWARE_SET
    turns = [
        {"s": a, "t": f"{by_id[b]['name']}님, {place}에서 만나네요."},
        {"s": b, "t": "그러게요. 잘 지내시죠?"},
    ]
    da = _delta(a, today[a]["awareness"], today[a]["stance"])
    db = _delta(b, today[b]["awareness"], today[b]["stance"])
    if a_aware and not b_aware:
        turns.append({"s": a, "t": "참, 그 새 정책 소식 들으셨어요? 한번 알아보세요."})
        db = _delta(b, "aware", "unknown", learned=True, note=f"{by_id[a]['name']}에게 새 정책 얘기를 들음")
    elif b_aware and not a_aware:
        turns.append({"s": b, "t": "참, 그 새 정책 소식 들으셨어요? 한번 알아보세요."})
        da = _delta(a, "aware", "unknown", learned=True, note=f"{by_id[b]['name']}에게 새 정책 얘기를 들음")
    return turns, da, db


def _fallback_diary(v, today):
    if today["awareness"] in AWARE_SET:
        diary = f"오늘 새 정책 얘기를 접했다. {v['occupation']}인 나에게 이게 어떤 의미일지 곱씹게 된다."
    else:
        diary = "오늘은 평소처럼 하루를 보냈다. 특별한 소식은 없었다."
    return {"diary": diary, "awareness": today["awareness"], "stance": today["stance"]}


def _apply_delta(today, vid, delta, vid_was, other_id, other_was, m, day, propagation):
    """LLM/폴백 델타를 상태에 반영하고, '새로 알게 됨'이면 전파 엣지를 기록.

    전파 게이트(중요): 모르던 사람은 '상대가 이미 아는 경우'에만 새로 알 수 있다.
    LLM 이 근거 없이(상대도 모르는데) 정책을 아는 것으로 만들면 시드·관계망을 무시하는
    누수가 된다 → 아는 사람과의 만남에서만 전파되도록 코드가 보증한다.
    (판단·대사·감정은 LLM, 전파 경로는 결정론 가드 — 이 프로젝트의 일관된 분리.)
    """
    aw = _norm(getattr(delta, "awareness", ""), AWARE_LEVELS, today[vid]["awareness"])
    if vid_was == "unaware" and aw in AWARE_SET and other_was not in AWARE_SET:
        aw = "unaware"   # 출처 없음 → 인지 무효(자생적 누수 차단)
    today[vid]["awareness"] = aw
    # 입장은 '아는' 상태에서만 의미가 있다(모르면 unknown 유지).
    if aw in AWARE_SET:
        today[vid]["stance"] = _norm(getattr(delta, "stance", ""), STANCE_LEVELS, today[vid]["stance"])
    note = (getattr(delta, "note", "") or "").strip()
    if note and aw in AWARE_SET:   # 모르는 사람의 메모는 일기로 정책을 흘릴 수 있어 제외
        today[vid]["log"].append(f"{fmt_hm(m['start'])} {m['place']}: {note}")
    if vid_was == "unaware" and aw in AWARE_SET:   # 이 만남에서 아는 상대로부터 새로 알게 됨
        propagation.append({"from": other_id, "to": vid, "place": m["place"],
                            "time": int(m["start"]), "day": day})


# --- 하루 시뮬 (한 클릭 = 하루) ------------------------------------------
def run_day(policy, states, day_num, force_fallback=False, write_meetings=True):
    """하루를 시간순 만남으로 굴리고 밤에 일기로 압축한다.

    policy         : 최상위 정책 시나리오(빈 문자열이면 평범한 하루)
    states         : {vid: {awareness, stance, diary}} — 어제 끝 상태(=오늘 시작)
    day_num        : 며칠째
    write_meetings : True 면 meetings.js/json 갱신(iframe 재생용). 테스트는 False.
    반환           : (new_states, day_record)
    """
    villagers = _load("villagers.json")["villagers"]
    locations = _load("locations.json")["locations"]
    schedules = _load("schedules.json")
    by_id = {v["id"]: v for v in villagers}
    loc_label = {l["key"]: l["label"] for l in locations}
    anchors = _load_anchors()
    meetings = extract_meetings(schedules, villagers, locations, anchors)  # 시간순·완화

    today = {
        vid: {"awareness": states[vid]["awareness"], "stance": states[vid]["stance"],
              "diary": states[vid].get("diary", ""), "log": []}
        for vid in by_id
    }
    propagation = []
    use_llm = has_real_key() and not force_fallback
    system = build_meeting_system(villagers, locations, policy) if use_llm else None

    # 1) 만남을 '시간순으로' 순차 처리(앞 대화가 뒤 대화의 인지에 영향 → 전파)
    for m in meetings:
        a, b = m["a"], m["b"]
        a_was, b_was = today[a]["awareness"], today[b]["awareness"]
        if use_llm:
            try:
                msgs = [{"role": "system", "content": system},
                        {"role": "user", "content":
                            build_meeting_user(m, by_id, loc_label, schedules, today, m.get("close"))}]
                res = structured_call(msgs, MeetingResult)
                valid = {a, b}
                turns = [{"s": (t.speaker_id if t.speaker_id in valid else a), "t": t.text.strip()}
                         for t in res.turns if t.text.strip()]
                da, db = _bind_deltas(res.a_delta, res.b_delta, a, b)
                if not turns:
                    turns, da, db = _fallback_meeting(m, by_id, loc_label, today)
            except Exception as ex:
                print(f"[run_day] {m['id']} 실패 -> 폴백: {ex}")
                turns, da, db = _fallback_meeting(m, by_id, loc_label, today)
        else:
            turns, da, db = _fallback_meeting(m, by_id, loc_label, today)
        m["turns"] = turns
        _apply_delta(today, a, da, a_was, b, b_was, m, day_num, propagation)
        _apply_delta(today, b, db, b_was, a, a_was, m, day_num, propagation)

    # 2) 밤: 각자 '오늘'을 일기로 압축(서로 독립 → 병렬)
    def diary_one(v):
        vid = v["id"]
        if use_llm:
            try:
                res = structured_call(
                    build_diary_messages(v, today[vid], schedules.get(vid, []), loc_label, policy),
                    DiaryOut)
                return vid, {"diary": (res.diary or "").strip(),
                             "awareness": _norm(res.awareness, AWARE_LEVELS, today[vid]["awareness"]),
                             "stance": _norm(res.stance, STANCE_LEVELS, today[vid]["stance"])}
            except Exception as ex:
                print(f"[run_day] {vid} 일기 실패 -> 폴백: {ex}")
        return vid, _fallback_diary(v, today[vid])

    diary_pairs = run_threaded(villagers, diary_one) if use_llm else [diary_one(v) for v in villagers]
    diaries = dict(diary_pairs)
    # 인지(사실)는 만남 게이트(today)가 정한다 — 일기 LLM 이 못 만난 사람을 '알게 됨'으로
    # 부풀리지 못하게(전파 누수 차단). 일기는 '이미 아는 사람'의 심화(aware→interested→acting)
    # 와 입장·서사만 반영한다. unaware 면 입장은 unknown.
    ptokens = _policy_tokens(policy)   # 모르는 사람 일기의 정책 누수 차단용
    new_states = {}
    for vid in by_id:
        gated = today[vid]["awareness"]
        d = diaries[vid]
        diary_text = d["diary"]
        if gated == "unaware":
            aw, stc = "unaware", "unknown"
            # 모르는 사람 일기에 정책이 새면(LLM 이 guard 무시) 폴백으로 교체(결정론 보증).
            if diary_text and any(t in diary_text for t in ptokens):
                diary_text = _fallback_diary(by_id[vid], today[vid])["diary"]
        else:
            aw = d["awareness"] if d["awareness"] in AWARE_SET else gated  # 심화 허용·강등 금지
            stc = d["stance"]
        new_states[vid] = {"awareness": aw, "stance": stc, "diary": diary_text}
        d["awareness"], d["stance"], d["diary"] = aw, stc, diary_text  # 표시(리포트) 일치

    # 3) iframe 재생용 meetings.js 갱신(이번 날) + 일자 기록 반환
    m_iframe = [{"id": m["id"], "a": m["a"], "b": m["b"], "place": m["place"],
                 "start": m["start"], "end": m["end"], "turns": m.get("turns", [])}
                for m in meetings]
    generated_with = "llm" if use_llm else "fallback"
    if write_meetings:
        _write(m_iframe, generated_with)

    day_record = {"day": day_num, "policy": policy, "generated_with": generated_with,
                  "meetings": m_iframe, "diaries": diaries, "propagation": propagation}
    return new_states, day_record


if __name__ == "__main__":
    force = ("--fallback" in sys.argv) or (os.getenv("GEN_FALLBACK") == "1")
    generate(force_fallback=force)
