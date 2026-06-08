# -*- coding: utf-8 -*-
"""gen_dialogues.py — 미리마을 '맥락 대화' 생성기 (A 단계: Generative Agents 의 conversation)

핵심: 캐릭터쌍이 만나는 순간을 스케줄에서 자동으로 찾아내고(=동선의 결과),
그 시점까지 각자 한 일 + 관계를 LLM 에 줘서 그날 서사가 묻어나는 대화를 생성한다.
하루치 만남+대화를 통째로 미리 생성(녹화)해 저장 -> index.html 이 시각·장소 기반으로 재생.

gen_schedules.py 와 같은 독립 실행 패턴(graph/ 의존 X, 자체 LLM 클라이언트, .env 는 부모 미리랩 것 읽기만).

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

# LLM 프로바이더: openai(기본) / gemini — graph/llm.py 와 같은 분기의 독립 복제
# (gen_schedules 와 동일). 메인 앱에선 tab_minivillage 가 set_provider() 로 전파.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PROVIDER_MODELS = {
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": os.getenv("MIRILAB_GEMINI_MODEL", "gemini-3-flash-preview"),
}
PROVIDER = (os.getenv("MIRILAB_LLM") or "openai").strip().lower()
if PROVIDER not in PROVIDER_MODELS:
    PROVIDER = "openai"
MODEL = PROVIDER_MODELS[PROVIDER]

# 만남 추출 파라미터
MIN_OVERLAP = 12      # 최소 공존(분) — 짧아도 짧은 대화는 가능(전파 통로 확보 위해 20→12 완화)
MERGE_GAP = 40        # 같은 장소·같은 인원 구성이 이 간격(분) 이내로 이어지면 한 장면으로 병합
MAX_PER_PAIR = 1      # (레거시) 옛 쌍 추출용 — 그룹 스윕에선 미사용. 하위호환 상수로만 남김.
PAST_DIARY_DAYS = 5   # 만남·일기 프롬프트에 실어줄 '지난 일기' 최근 일수(2~4문장 × N → 토큰 적정)
ROUTE_FACTOR = 0.8    # 직선거리 -> 도로 우회 근사 계수. 이동시간을 덜 흐르게(1.5→0.8):
#   맵이 커서 도보 ~1시간이 걸려 같은 장소(특히 어르신↔카페)서도 엇갈려 만남이 끊겼다.
#   0.8 이면 어르신이 이웃과 연결되고, 전파가 며칠에 걸쳐 점진적으로 퍼진다(관측 목적).
#   ⚠ iframe 재생은 자체 도보 속도 + '도착 대기'라, 긴 블록(카페 60~90분)은 그대로 재생되나
#   짧은 겹침 일부는 '도착 지연 놓침'으로 보일 수 있다(전파 리포트는 이 meetings 기준이 정답).
SPEED_BASE = 26       # index.html createAgent 의 speed=26+((i%5)*3) 와 정합. /3.2 = px/시뮬분


# --------------------------------------------------------------------------
# LLM 클라이언트 (gen_schedules 와 동일 독립 패턴)
# --------------------------------------------------------------------------
_clients = {}  # 프로바이더별 클라이언트 캐시(전환 왕복에도 재생성 없음)


def set_provider(name):
    """프로바이더 런타임 전환(메인 앱 '시민 모델' 선택기 → tab_minivillage 가 호출)."""
    global PROVIDER, MODEL
    name = (name or "").strip().lower()
    if name not in PROVIDER_MODELS:
        raise ValueError(f"알 수 없는 프로바이더: {name!r}")
    PROVIDER = name
    MODEL = PROVIDER_MODELS[name]


def has_real_key() -> bool:
    if PROVIDER == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    key = os.getenv("OPENAI_API_KEY")
    return bool(key) and not key.startswith("sk-your-key")


def get_client() -> OpenAI:
    client = _clients.get(PROVIDER)
    if client is None:
        if PROVIDER == "gemini":
            client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"),
                            base_url=GEMINI_BASE_URL, max_retries=3)
        else:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=3)
        _clients[PROVIDER] = client
    return client


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


def _stable_scenes(intervals):
    """한 장소의 체류구간들 → '같은 인원이 함께 있는' 안정 구간(장면)으로 분해.

    intervals = [(start, end, vid), ...] (같은 장소). 시간 경계마다 그때 함께 있는
    사람 집합이 일정한 구간을 잘라, 2명 이상이 MIN_OVERLAP 이상 함께한 장면만 남긴다.
    사람이 들고 나면 집합이 바뀌어 새 장면이 된다(카페에 한 명 합류 → 다음 장면).
    인접한 동일 인원 구간은 한 장면으로 병합.
    반환 = [(s, e, (vid, ...)), ...] (시간순).
    """
    if not intervals:
        return []
    bounds = sorted({s for s, _, _ in intervals} | {e for _, e, _ in intervals})
    raw = []  # [s, e, (vids...)]
    for s, e in zip(bounds, bounds[1:]):
        if e <= s:
            continue
        present = tuple(sorted(vid for (a, b, vid) in intervals if a <= s and b >= e))
        if len(present) >= 2:
            raw.append([s, e, present])
    merged = []
    for s, e, ppl in raw:
        if merged and merged[-1][2] == ppl and s - merged[-1][1] <= MERGE_GAP:
            merged[-1][1] = e   # 같은 인원 연속 → 한 장면으로 늘림
        else:
            merged.append([s, e, ppl])
    return [(s, e, ppl) for s, e, ppl in merged if e - s >= MIN_OVERLAP]


def extract_meetings(schedules, villagers, locations, anchors):
    """장소·시간 스윕으로 '같은 자리에 함께 있는 사람들'을 한 장면(만남)으로 묶는다.

    예전엔 쌍(2명)으로만 쪼갰지만, 한 장소에 3명+이 모이면 그 자리에서 함께 대화한다
    (카페에 셋이면 셋이서). parts = 그 장면의 참가자 전원. a/b 는 parts[0]/parts[1] 로
    하위호환(레거시 2인 경로·테스트). **이동시간은 무시** — iframe 이 도착을 기다리며
    시간을 멈추므로 '스케줄상 같은 장소·시간'이면 만남으로 충분하다.
    """
    public = {l["key"] for l in locations if l["key"] != "houses"}
    by_id = {v["id"]: v for v in villagers}
    ids = [v["id"] for v in villagers]
    idx = {vid: i for i, vid in enumerate(ids)}
    # 관계(아는 사이) — 만남 게이트가 아니라 대화 친밀도 플래그로만 쓴다.
    rels = set()
    for v in villagers:
        for r in v.get("relationships", []):
            if r in by_id:
                rels.add(tuple(sorted([v["id"], r])))

    # 공용장소별 체류 구간 수집(집 제외)
    by_place = defaultdict(list)   # place_key -> [(s, e, vid)]
    for vid in by_id:
        for b in schedules.get(vid, []):
            s, e = parse_hm(b["start_time"]), parse_hm(b["end_time"])
            if s is None or e is None or e <= s:
                continue
            if b["location_key"] in public:
                by_place[b["location_key"]].append((s, e, vid))

    # 집(가족) 장면 — 같은 집 식구만, 집별로 따로 스윕(독거·1인 가구는 식구가 없어 제외).
    house_intervals = defaultdict(list)  # house_id -> [(s, e, vid)]
    for h in anchors.get("houses", []):
        res = [r for r in h.get("residents", []) if r in by_id]
        if len(res) < 2:
            continue
        for vid in res:
            for b in schedules.get(vid, []):
                s, e = parse_hm(b["start_time"]), parse_hm(b["end_time"])
                if s is None or e is None or e <= s:
                    continue
                if b["location_key"] == "houses":
                    house_intervals[h["id"]].append((s, e, vid))

    scenes = []  # (place, s, e, [parts])
    for place, ivs in by_place.items():
        for s, e, ppl in _stable_scenes(ivs):
            scenes.append((place, s, e, list(ppl)))
    for _hid, ivs in house_intervals.items():
        for s, e, ppl in _stable_scenes(ivs):
            scenes.append(("houses", s, e, list(ppl)))

    scenes.sort(key=lambda sc: (sc[1], sc[2]))  # 시간순
    meetings = []
    for i, (place, s, e, parts) in enumerate(scenes):
        parts = sorted(parts, key=lambda x: idx[x])  # ids 순서 고정(재현성)
        # close = 그룹 전원이 서로 아는 사이인가(대화 톤용). 한 쌍이라도 모르면 False.
        close = all(tuple(sorted([x, y])) in rels for x, y in combinations(parts, 2))
        meetings.append({"id": f"m{i:02d}", "place": place,
                         "start": int(round(s)), "end": int(round(e)),
                         "parts": parts, "a": parts[0], "b": parts[1],  # 하위호환
                         "close": close})
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
        why = "강제 폴백" if force_fallback else "LLM 키 없음"
        print(f"[gen_dialogues] {why} -> 결정론 폴백 대화")
        for m in meetings:
            m["turns"] = fallback_dialogue(m, by_id, loc_label)
        generated_with = "fallback"
    else:
        print(f"[gen_dialogues] {PROVIDER}({MODEL}) -> 맥락 대화 생성 ({len(meetings)}콜)")
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
    villager_id: str       # 참가자 id 중 하나(매칭 보조)
    learned_policy: bool   # 이 대화로 정책을 '처음' 알게 됐나
    awareness: str         # 대화 뒤 상태: unaware|aware|interested|acting
    stance: str            # unknown|support|oppose|mixed|anxious
    learned_from: str = ""  # 정책을 누구에게 들었나(그룹 전파 출처 id). 없으면 빈 문자열.
    note: str              # 그 인물의 한 줄 메모(오늘 일에 추가됨)


class MeetingResult(BaseModel):
    turns: List[DialogueTurn]   # 대화 (위 DialogueTurn 재사용)
    deltas: List[CharDelta]     # 참가자별 변화(참가자 수만큼 — 그룹 대화 일반화)


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


def _bind_group_deltas(deltas, parts):
    """LLM 이 보고한 deltas(참가자별)를 villager_id 로 매칭 → {vid: delta}.
    id 가 어긋나거나 누락되면 남은 델타를 위치 순으로 채운다(빠진 참가자는 None 처리)."""
    out = {}
    pset = set(parts)
    for d in deltas or []:
        vid = getattr(d, "villager_id", None)
        if vid in pset and vid not in out:
            out[vid] = d
    leftover = [d for d in (deltas or []) if getattr(d, "villager_id", None) not in pset]
    for p in parts:
        if p not in out and leftover:
            out[p] = leftover.pop(0)
    return out


def _past_diary_block(past):
    """past = [(day, text), ...] 오름차순 → '지난 일기:' 블록(최근 PAST_DIARY_DAYS 일).
    빈 입력이면 빈 문자열(1일차·테스트는 과거가 없어 기존 동작과 동일)."""
    if not past:
        return ""
    lines = [f"  {day}일차: {text}" for day, text in past[-PAST_DIARY_DAYS:] if text]
    return ("지난 일기:\n" + "\n".join(lines) + "\n") if lines else ""


# --- 정책 주입 프롬프트 (system = 캐싱 prefix, 전원/전 만남 공유) ---------
def build_meeting_system(villagers, locations, policy):
    cast = "\n".join(
        f"- {v['name']}({v['id']}): {v['age']}세 {v['occupation']}, {v['personality']}"
        for v in villagers
    )
    # 2026-06-06 재설계: 같은 억제문("여러 화제 중 하나")을 반복하던 패치타워 철거 —
    # 세계 사실은 한 번씩만, 중립으로. 대화에 정책이 나올지는 그 자리 사람들의 사이·상황·
    # 관심이 정한다. 전파 게이트(누가 알게 되나)는 코드(_apply_delta_group)가 보증한다.
    if (policy or "").strip():
        situation = (
            "[동네 사정]\n"
            "최근 이런 정책이 발표됐고, 아는 사람들 사이에서 가끔 화제에 오릅니다 — "
            "일·가족·날씨·건강·동네 소식 같은 여느 화제들 중 하나로.\n"
            f'"""\n{policy.strip()}\n"""\n'
            "- 정책 얘기가 나올지는 그 자리 사람들의 사이·상황·관심에 달렸습니다. 안 나와도 됩니다.\n"
            "- 아는 사람이 꺼내면, 모르던 사람이 그 자리에서 알게 될 수 있습니다(들은 만큼만).\n"
            "- 아무도 모르면 정책 이야기는 나오지 않습니다.\n"
        )
    else:
        situation = "[동네 사정] 특별한 정책 없이 평범한 일상입니다.\n"
    return (
        "당신은 미리마을의 기록자입니다. 같은 장소에 함께 있는 주민들이 그 순간 "
        "실제로 나눌 법한 대화를 쓰고, 대화 뒤 각자의 변화를 보고합니다.\n\n"
        + situation +
        "\n규칙:\n"
        "- 각자의 말은 그 사람이 평소 하는 말 그대로. 짧은 구어체, 한 사람당 한두 문장.\n"
        "- 참가자가 셋 이상이면 두세 명만 주고받아도 되고, 곁의 사람이 끼어들어도 자연스럽습니다.\n"
        "- speaker_id 는 반드시 주어진 참가자 id 중 하나.\n"
        "- 변화 보고(deltas): 참가자마다 한 항목씩 — villager_id, "
        "learned_policy(이 대화로 정책을 '처음' 알게 됐으면 true), "
        "awareness(unaware|aware|interested|acting), stance(unknown|support|oppose|mixed|anxious), "
        "learned_from(정책을 들려준 사람 id, 해당 없으면 빈 문자열), "
        "note(그 인물의 오늘 한 줄 메모).\n\n"
        f"[미리마을 주민]\n{cast}"
    )


def build_meeting_user(m, by_id, loc_label, schedules, today, past_diaries=None):
    parts = m.get("parts") or [m["a"], m["b"]]
    place = loc_label.get(m["place"], m["place"])
    rel = "서로 잘 아는 사이" if m.get("close") else "일부는 평소 왕래가 적은 사이"
    past_diaries = past_diaries or {}

    aware_parts = [p for p in parts if today[p]["awareness"] in AWARE_SET]
    unaware_parts = [p for p in parts if p not in aware_parts]
    if not aware_parts:
        rule = ("이 자리의 누구도 정책을 모릅니다 → 정책 이야기는 나오지 않습니다. "
                "전원 learned_policy=false, awareness=unaware.")
    elif not unaware_parts:
        rule = "모두 정책을 압니다. 얘기할 수도, 안 할 수도 있습니다."
    else:
        knowers = ", ".join(by_id[p]["name"] for p in aware_parts)
        rule = (f"{knowers} 은(는) 정책을 압니다. 꺼낼지는 그들에게 달렸습니다 — "
                "꺼내서 모르던 사람이 들으면 그 사람만 learned_policy=true(+learned_from=들려준 사람 id), "
                "안 나오면 그대로(awareness 유지).")

    blocks = []
    for p in parts:
        t = today[p]
        ctx = context_before(schedules, p, m["start"], loc_label)
        blocks.append(
            f"[{by_id[p]['name']}({p})] {by_id[p]['age']}세 {by_id[p]['occupation']}. {by_id[p]['personality']}\n"
            f"  {_past_diary_block(past_diaries.get(p))}"
            f"  오늘 지금까지: " + " / ".join(ctx) + "\n"
            f"  오늘 겪은 일: " + (" / ".join(t["log"]) or "(아직 없음)") + "\n"
            f"  현재 정책 인지={t['awareness']}, 입장={t['stance']}"
        )
    names = "·".join(by_id[p]["name"] for p in parts)
    return (
        f"[만남] {fmt_hm(m['start'])}, {place}에서 {names} 가 함께 있습니다. ({rel})\n\n"
        + "\n\n".join(blocks) + "\n\n"
        f"[이 자리의 정책 규칙] {rule}\n\n"
        f"이 사람들이 {place}에서 지금 나눌 대화를 만들고, 대화 뒤 각자의 변화를 deltas 로 보고하세요. "
        f"speaker_id 와 villager_id 는 참가자 id({', '.join(parts)})만 사용."
    )


def build_diary_messages(v, today, schedule, loc_label, past=None):
    """하루를 마친 1인칭 일기.

    ★ 2026-06-08 변경: 정책 전문을 '아는 사람'에게 재주입하던 트리거(pol)와
    '모르는 사람' guard 를 제거. 사람은 정책 원문을 외우지 않는다 — 그날 자기가
    겪고 들은 일(today['log'])만 떠올려 쓴다. 모르는 사람의 log 엔 정책 사건이
    애초에 없으므로(만남 게이트·메모 스크럽), 자연히 정책 얘기를 쓰지 않는다.
    과거 일기(past)를 함께 줘 며칠에 걸친 연속 서사가 이어지게 한다.
    """
    acts = [f"{b['start_time']} {loc_label.get(b['location_key'], b['location_key'])}에서 {b['action']}"
            for b in schedule] or ["집에서 하루를 보냄"]
    convo = today["log"] or ["오늘은 특별히 깊은 대화는 없었음"]
    return [
        {"role": "system", "content": (
            "당신은 미리마을 주민이 하루를 마치고 집에서 쓰는 1인칭 일기를 대신 써 줍니다. "
            "그날 있었던 일을 그 사람의 평소 말로 짧게 압축합니다. 무엇을 적을 만했는지는 "
            "그 사람의 하루가 정합니다.")},
        {"role": "user", "content": (
            f"[{v['name']}({v['id']})] {v['age']}세 {v['occupation']}. {v['personality']}\n"
            f"{_past_diary_block(past)}"
            "오늘 한 일: " + " / ".join(acts) + "\n"
            "오늘 겪고 들은 일: " + " / ".join(convo) + "\n"
            f"하루를 마친 지금 정책 인지={today['awareness']}, 입장={today['stance']}.\n\n"
            "오늘 실제로 겪거나 들은 일만 적고, 듣지 않은 정책 내용은 지어내지 마세요. "
            "이 사람의 1인칭 일기(2~4문장, 구어체)를 쓰고, 하루를 마친 시점의 "
            "정책 인지(unaware|aware|interested|acting)와 입장(unknown|support|oppose|mixed|anxious)을 "
            "보고하세요.")},
    ]


# --- 폴백(키 없음/실패) — 결정론 전달 + 간단 일기 -------------------------
def _fallback_meeting(m, by_id, loc_label, today):
    """그룹 폴백: 아는 사람(있으면 첫 번째)이 모르던 사람들에게 전달. {vid: delta} 반환."""
    parts = m.get("parts") or [m["a"], m["b"]]
    place = loc_label.get(m["place"], m["place"])
    aware = [p for p in parts if today[p]["awareness"] in AWARE_SET]
    teller = aware[0] if aware else None
    turns = [{"s": parts[0], "t": f"{place}에서 다들 만나네요."}]
    if len(parts) > 1:
        turns.append({"s": parts[1], "t": "그러게요. 잘 지내시죠?"})
    deltas = {}
    for p in parts:
        if teller and p != teller and today[p]["awareness"] not in AWARE_SET:
            deltas[p] = _delta(p, "aware", "unknown", learned=True,
                               note=f"{by_id[teller]['name']}에게 새 정책 얘기를 들음")
            if len(turns) < 5:
                turns.append({"s": teller, "t": f"참, {by_id[p]['name']}님, 그 새 정책 소식 들으셨어요?"})
        else:
            deltas[p] = _delta(p, today[p]["awareness"], today[p]["stance"])
    return turns, deltas


def _fallback_diary(v, today):
    if today["awareness"] in AWARE_SET:
        diary = f"오늘 새 정책 얘기를 접했다. {v['occupation']}인 나에게 이게 어떤 의미일지 곱씹게 된다."
    else:
        diary = "오늘은 평소처럼 하루를 보냈다. 특별한 소식은 없었다."
    return {"diary": diary, "awareness": today["awareness"], "stance": today["stance"]}


def _apply_delta_group(today, vid, delta, prev_aware, aware_before, m, day, propagation, ptokens):
    """그룹 델타를 상태에 반영하고, '새로 알게 됨'이면 전파 엣지를 기록.

    전파 게이트(중요): 모르던 사람은 '그 자리에 이미 아는 사람이 있을 때'에만 새로 알 수 있다.
    LLM 이 근거 없이(아무도 모르는데) 정책을 아는 것으로 만들면 시드·관계망을 무시하는
    누수가 된다 → 아는 사람이 함께 있는 자리에서만 전파되도록 코드가 보증한다.
    출처(from)는 LLM 의 learned_from 을 쓰되, 그 자리 '아는 사람' 중 하나여야 인정한다
    (아니면 첫 번째 아는 사람으로 보정). 판단·대사는 LLM, 전파 경로는 결정론 가드.

    prev_aware   = 이 만남 직전 vid 의 awareness
    aware_before = 이 만남 직전 '아는 사람' 참가자 id 목록(전파 출처 후보)
    """
    aw = _norm(getattr(delta, "awareness", "") if delta else "", AWARE_LEVELS, prev_aware)
    other_knowers = [p for p in aware_before if p != vid]
    if prev_aware == "unaware" and aw in AWARE_SET and not other_knowers:
        aw = "unaware"   # 출처 없음 → 인지 무효(자생적 누수 차단)
    today[vid]["awareness"] = aw
    # 입장은 '아는' 상태에서만 의미가 있다(모르면 unknown 유지).
    if aw in AWARE_SET:
        today[vid]["stance"] = _norm(getattr(delta, "stance", "") if delta else "",
                                     STANCE_LEVELS, today[vid]["stance"])
    note = ((getattr(delta, "note", "") if delta else "") or "").strip()
    # 메모=본인의 대화 기록(낮의 후속 만남 + 밤 일기에 주입). 모르는 사람 메모도 보존하되,
    # 정책 토큰이 새어 있으면 그 메모만 버린다(일기·후속 만남으로 흘러가는 누수 차단).
    if note and (aw in AWARE_SET or not any(t in note for t in ptokens)):
        today[vid]["log"].append(f"{fmt_hm(m['start'])} {m['place']}: {note}")
    if prev_aware == "unaware" and aw in AWARE_SET and other_knowers:  # 새로 알게 됨
        lf = (getattr(delta, "learned_from", "") if delta else "") or ""
        src = lf if lf in other_knowers else other_knowers[0]
        propagation.append({"from": src, "to": vid, "place": m["place"],
                            "time": int(m["start"]), "day": day})


# --- 하루 시뮬 (한 클릭 = 하루) ------------------------------------------
def run_day(policy, states, day_num, force_fallback=False, write_meetings=True, past_diaries=None):
    """하루를 시간순 만남으로 굴리고 밤에 일기로 압축한다.

    policy         : 최상위 정책 시나리오(빈 문자열이면 평범한 하루)
    states         : {vid: {awareness, stance, diary}} — 어제 끝 상태(=오늘 시작)
    day_num        : 며칠째
    write_meetings : True 면 meetings.js/json 갱신(iframe 재생용). 테스트는 False.
    past_diaries   : {vid: [(day, diary_text), ...]} — 지난 며칠 일기(만남·일기 프롬프트에 주입).
                     None 이면 과거 없이(1일차·테스트 기존 동작과 동일).
    반환           : (new_states, day_record)
    """
    villagers = _load("villagers.json")["villagers"]
    locations = _load("locations.json")["locations"]
    schedules = _load("schedules.json")
    by_id = {v["id"]: v for v in villagers}
    loc_label = {l["key"]: l["label"] for l in locations}
    anchors = _load_anchors()
    meetings = extract_meetings(schedules, villagers, locations, anchors)  # 시간순·그룹
    past_diaries = past_diaries or {}

    today = {
        vid: {"awareness": states[vid]["awareness"], "stance": states[vid]["stance"],
              "diary": states[vid].get("diary", ""), "log": []}
        for vid in by_id
    }
    propagation = []
    use_llm = has_real_key() and not force_fallback
    system = build_meeting_system(villagers, locations, policy) if use_llm else None
    ptokens = _policy_tokens(policy)   # 모르는 사람 메모·일기의 정책 누수 차단용

    # 1) 만남을 '시간순으로' 순차 처리(앞 대화가 뒤 대화의 인지에 영향 → 전파)
    for m in meetings:
        parts = m["parts"]
        was = {p: today[p]["awareness"] for p in parts}            # 만남 직전 상태
        aware_before = [p for p in parts if was[p] in AWARE_SET]   # 전파 출처 후보
        if use_llm:
            try:
                msgs = [{"role": "system", "content": system},
                        {"role": "user", "content":
                            build_meeting_user(m, by_id, loc_label, schedules, today, past_diaries)}]
                res = structured_call(msgs, MeetingResult)
                valid = set(parts)
                turns = [{"s": (t.speaker_id if t.speaker_id in valid else parts[0]), "t": t.text.strip()}
                         for t in res.turns if t.text.strip()]
                deltas = _bind_group_deltas(res.deltas, parts)
                if not turns:
                    turns, deltas = _fallback_meeting(m, by_id, loc_label, today)
            except Exception as ex:
                print(f"[run_day] {m['id']} 실패 -> 폴백: {ex}")
                turns, deltas = _fallback_meeting(m, by_id, loc_label, today)
        else:
            turns, deltas = _fallback_meeting(m, by_id, loc_label, today)
        m["turns"] = turns
        for p in parts:
            _apply_delta_group(today, p, deltas.get(p), was[p], aware_before,
                               m, day_num, propagation, ptokens)

    # 2) 밤: 각자 '오늘'을 일기로 압축(서로 독립 → 병렬)
    def diary_one(v):
        vid = v["id"]
        if use_llm:
            try:
                res = structured_call(
                    build_diary_messages(v, today[vid], schedules.get(vid, []), loc_label,
                                         past_diaries.get(vid)),
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
    m_iframe = [{"id": m["id"], "parts": m["parts"], "a": m["a"], "b": m["b"],
                 "place": m["place"], "start": m["start"], "end": m["end"],
                 "turns": m.get("turns", [])}
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
