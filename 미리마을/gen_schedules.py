# -*- coding: utf-8 -*-
"""gen_schedules.py — 미리마을 하루 스케줄 생성기 (Generative Agents 의 planning)

독립 실행 모듈. 메인 미리랩(graph/)에 의존하지 않고 OpenAI 를 자체 호출한다.
=> 미리마을 폴더만 떼어내도 동작한다. (.env 는 부모 미리랩 것을 '읽기만' 한다)

Park et al.(2023) 방식: 하루의 큰 줄기를 먼저 잡고 시간 블록으로 분해.
실제 OpenAI 키가 없으면(또는 --fallback) 결정론 폴백으로 그럴듯한 하루를 만든다.

[프롬프트 캐싱 구조]  고정 -> 가변 순서로 쌓아 OpenAI 자동 prefix 캐싱을 노린다.
  (1) 마을 공통 prefix = system : 시스템 지시 + 장소 13곳 + 캐스트 10명 명단  <- 전원 공유(캐시 핵심)
  (2) 캐릭터 prefix   = user 앞 : 그 인물 시트 + 관계
  (3) 가변 요청       = user 뒤 : 오늘 하루 계획 요청
첫 1명을 먼저 호출해 공통 prefix 캐시를 데우고, 나머지를 동시 호출한다(웜업 패턴).

출력(data/):
  schedules.json    : { villager_id: [ {start_time,end_time,location_key,action}, ... ] }
  village_data.js   : const VILLAGERS / LOCATIONS / SCHEDULES (index.html 로드용)

실행(cwd 무관 — __file__ 기준 절대경로로 동작):
  python 미리마을/gen_schedules.py              # 키 있으면 LLM, 없으면 폴백
  python 미리마을/gen_schedules.py --fallback   # 강제 폴백(비용 0, 외부호출 0)
  python 미리마을/gen_schedules.py "장마가 시작된 평일"   # day_context 지정
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List

# --- 경로 설정: .env(부모 미리랩, 사용자 소유) 만 읽고 graph/ 코드엔 의존하지 않음 ---
HERE = os.path.dirname(os.path.abspath(__file__))   # .../미리랩/미리마을
ROOT = os.path.dirname(HERE)                         # .../미리랩

try:
    from dotenv import load_dotenv
    # 미리마을 자체 .env 가 있으면 우선, 없으면 부모 미리랩 .env 를 읽는다(읽기 전용).
    load_dotenv(os.path.join(HERE, ".env"))
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

from openai import OpenAI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

DATA_DIR = os.path.join(HERE, "data")

# LLM 프로바이더: openai(기본) / gemini — graph/llm.py 와 같은 분기의 독립 복제
# (미리마을은 graph.llm 미의존이 설계). CLI 단독 실행은 .env 의 MIRILAB_LLM 을
# 따르고, 메인 앱에서는 '시민 모델' 선택기가 set_provider() 로 전파한다
# (tab_minivillage 가 importlib 로드 후 호출).
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PROVIDER_MODELS = {
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": os.getenv("MIRILAB_GEMINI_MODEL", "gemini-3-flash-preview"),
}
PROVIDER = (os.getenv("MIRILAB_LLM") or "openai").strip().lower()
if PROVIDER not in PROVIDER_MODELS:
    PROVIDER = "openai"
MODEL = PROVIDER_MODELS[PROVIDER]

# 시뮬 하루 경계(분). 08:00 ~ 24:00.
DAY_START_MIN = 8 * 60
DAY_END_MIN = 24 * 60

DAY_CONTEXT = "특별한 일정이 없는 평범한 평일."


# --------------------------------------------------------------------------
# 자체 LLM 호출 (graph.llm 의존 제거 — 미리마을 독립용)
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
        # SDK 내장 재시도(레이트리밋/타임아웃 등)에 위임 — tenacity 등 추가 의존 없음.
        if PROVIDER == "gemini":
            client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"),
                            base_url=GEMINI_BASE_URL, max_retries=3)
        else:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=3)
        _clients[PROVIDER] = client
    return client


def structured_call(messages, schema, temperature=0.7):
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
class ScheduleBlock(BaseModel):
    start_time: str    # "HH:MM"
    end_time: str      # "HH:MM"
    location_key: str  # locations.json 의 key
    action: str        # 그 시간대의 구체 행동(한 문장)


class DailySchedule(BaseModel):
    villager_id: str
    blocks: List[ScheduleBlock]


# --------------------------------------------------------------------------
# 입력 로드
# --------------------------------------------------------------------------
def _load_json(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def load_inputs():
    villagers = _load_json("villagers.json")["villagers"]
    locations = _load_json("locations.json")["locations"]
    return villagers, locations


# --------------------------------------------------------------------------
# 시간 유틸
# --------------------------------------------------------------------------
def parse_hm(s):
    """'HH:MM' -> 분(int). 실패하면 None. '24:00' 허용."""
    try:
        h, m = str(s).strip().split(":")
        total = int(h) * 60 + int(m)
        return total if total >= 0 else None
    except Exception:
        return None


def fmt_hm(total):
    total = max(0, min(DAY_END_MIN, int(total)))
    return f"{total // 60:02d}:{total % 60:02d}"


# --------------------------------------------------------------------------
# 프롬프트 (캐싱 3층 구조: 고정 -> 가변)
# --------------------------------------------------------------------------
def build_village_context(villagers, locations):
    """(1) 마을 공통 prefix = system 메시지. 모든 캐릭터 호출에서 '동일'해야 캐시가 먹는다."""
    loc_lines = "\n".join(f"- {loc['key']} ({loc['label']})" for loc in locations)
    cast_lines = "\n".join(
        f"- {v['name']}({v['id']}): {v['age']}세 {v['occupation']}" for v in villagers
    )
    return (
        "당신은 사회 시뮬레이션의 작가입니다. "
        "Stanford Generative Agents(Park et al. 2023) 방식으로 한 인물의 하루를 설계합니다.\n"
        "절차: (1) 먼저 하루의 큰 줄기를 떠올린다(기상 -> 오전 -> 점심 -> 오후 -> 저녁 -> 귀가/취침). "
        "(2) 그 줄기를 시간 블록으로 분해한다.\n"
        "규칙:\n"
        "- 장소는 반드시 아래 location_key 목록 안에서만 고른다.\n"
        "- 인물의 직업, 성격, 생활 리듬, 관계에 맞는 자연스러운 하루여야 한다.\n"
        "- 하루 중 한 번은 카페·분수광장·마을공원·마을회관·복지관 같은 공용 공간에 들러 "
        "이웃과 어울리는 시간 블록을 넣는다(집·직장에만 머물지 말고, 이웃과 마주칠 수 있게).\n"
        "- 인물마다 동선을 다양하게(매일 똑같은 곳만 반복하지 않기).\n"
        "- 08:00 부터 24:00 까지 빈틈과 겹침 없이 시간순으로 덮는다.\n"
        "- 각 블록의 action 은 그 시간대의 구체적 행동을 한 문장으로 적는다.\n"
        "- 정책 이야기는 넣지 않는다(평범한 하루 — 정책 반응은 별도 단계에서 처리).\n\n"
        f"[미리마을 장소(location_key)]\n{loc_lines}\n\n"
        f"[미리마을 주민 명단(서로 아는 사이)]\n{cast_lines}"
    )


def build_character_request(villager, day_context):
    """(2) 캐릭터 prefix + (3) 가변 요청 = user 메시지."""
    rels = villager.get("relationships", [])
    rel_str = ", ".join(rels) if rels else "특별히 가까운 사람 없음"
    return (
        "[이 인물]\n"
        f"- 이름: {villager['name']} ({villager['age']}세 {villager['gender']})\n"
        f"- 직업: {villager['occupation']}\n"
        f"- 성격: {villager['personality']}\n"
        f"- 생활 리듬: {villager['daily_rhythm']}\n"
        f"- 집: {villager['home']} / 주 활동처: {villager['work']}\n"
        f"- 기상 무렵: {villager.get('wake_hint', '')} / 취침 무렵: {villager.get('sleep_hint', '')}\n"
        f"- 가까운 사람(관계): {rel_str}\n\n"
        f"[오늘]\n{day_context}\n\n"
        f"villager_id 는 '{villager['id']}' 로 하고, 위 인물의 하루 스케줄을 시간표 블록으로 만들어 주세요."
    )


def build_schedule_messages(villager, village_context, day_context):
    return [
        {"role": "system", "content": village_context},                       # (1) 고정
        {"role": "user", "content": build_character_request(villager, day_context)},  # (2)+(3)
    ]


# --------------------------------------------------------------------------
# 검증/정규화: 유효 키만, 08:00~24:00 연속 타일로(빈틈/겹침 제거)
# --------------------------------------------------------------------------
def normalize_blocks(raw_blocks, valid_keys, home_key):
    cleaned = []
    for b in raw_blocks:
        key = b.get("location_key")
        if key not in valid_keys:
            key = home_key  # 미지 키 -> 집으로 스냅
        s = parse_hm(b.get("start_time"))
        e = parse_hm(b.get("end_time"))
        action = (b.get("action") or "").strip() or "활동"
        if s is None or e is None or e <= s:
            continue
        cleaned.append([s, e, key, action])
    cleaned.sort(key=lambda x: x[0])

    tiled = []
    cursor = DAY_START_MIN
    for s, e, key, action in cleaned:
        s = max(s, DAY_START_MIN)
        e = min(e, DAY_END_MIN)
        if e <= cursor:
            continue  # 겹쳐서 이미 지난 구간 -> 버림
        if s > cursor:
            tiled.append([cursor, s, home_key, "집에서 휴식"])  # 빈틈 -> 집
        tiled.append([max(s, cursor), e, key, action])
        cursor = e
        if cursor >= DAY_END_MIN:
            break
    if cursor < DAY_END_MIN:
        tiled.append([cursor, DAY_END_MIN, home_key, "집에서 휴식"])

    return [
        {"start_time": fmt_hm(s), "end_time": fmt_hm(e), "location_key": k, "action": a}
        for s, e, k, a in tiled
    ]


# --------------------------------------------------------------------------
# 결정론 폴백 (키 없거나 LLM 실패 시)
# --------------------------------------------------------------------------
_WORK_ACTION = {
    "cafe": "카페에서 일하기",
    "community_center": "주민센터에서 민원 응대",
    "welfare_center": "복지관 프로그램 참여",
    "school": "학교에서 수업 듣기",
    "town_hall": "마을회관 자원봉사",
    "park_pond": "공원에서 소일하기",
    "daycare": "어린이집에서 지내기",
    "garden": "텃밭 가꾸며 작업하기",
}
_LEISURE = {
    "minsu": "fountain_plaza", "staff": "houses", "owner": "houses",
    "grandma": "garden", "sua": "cafe", "junho": "playground",
    "miyoung": "garden", "oldman": "park_pond", "jimin": "playground",
    "daeun": "park_pond",
}


def fallback_schedule(villager, valid_keys, home_key):
    vid = villager["id"]
    work = villager.get("work") if villager.get("work") in valid_keys else home_key
    work_action = _WORK_ACTION.get(work, "활동하기")
    leisure = _LEISURE.get(vid, "fountain_plaza")
    if leisure not in valid_keys:
        leisure = home_key
    lunch = "cafe" if "cafe" in valid_keys else home_key
    wake = parse_hm(villager.get("wake_hint")) or DAY_START_MIN
    morning = max(DAY_START_MIN, min(wake, 10 * 60))

    raw = []
    if morning > DAY_START_MIN:
        raw.append({"start_time": fmt_hm(DAY_START_MIN), "end_time": fmt_hm(morning),
                    "location_key": home_key, "action": "집에서 아침 준비"})
    raw.append({"start_time": fmt_hm(morning), "end_time": "12:00",
                "location_key": work, "action": work_action})
    raw.append({"start_time": "12:00", "end_time": "13:00",
                "location_key": lunch, "action": "점심 식사"})
    raw.append({"start_time": "13:00", "end_time": "17:00",
                "location_key": work, "action": work_action})
    raw.append({"start_time": "17:00", "end_time": "19:00",
                "location_key": leisure, "action": "여가 시간 보내기"})
    raw.append({"start_time": "19:00", "end_time": "24:00",
                "location_key": home_key, "action": "집에서 휴식"})
    return normalize_blocks(raw, valid_keys, home_key)


# --------------------------------------------------------------------------
# 생성 오케스트레이션
# --------------------------------------------------------------------------
def generate(day_context=DAY_CONTEXT, force_fallback=False):
    villagers, locations = load_inputs()
    valid_keys = {loc["key"] for loc in locations}
    home_key = "houses" if "houses" in valid_keys else locations[0]["key"]

    use_llm = has_real_key() and not force_fallback
    schedules = {}

    if not use_llm:
        why = "강제 폴백" if force_fallback else "OpenAI 키 없음"
        print(f"[gen_schedules] {why} -> 결정론 폴백으로 생성")
        for v in villagers:
            schedules[v["id"]] = fallback_schedule(v, valid_keys, home_key)
        generated_with = "fallback"
    else:
        print(f"[gen_schedules] {PROVIDER}({MODEL}) -> LLM 으로 생성 (캐싱 3층 프롬프트)")
        village_context = build_village_context(villagers, locations)  # (1) 전원 공유 prefix

        def gen_one(v):
            try:
                messages = build_schedule_messages(v, village_context, day_context)
                result = structured_call(messages, DailySchedule, temperature=0.7)
                raw = [b.model_dump() for b in result.blocks]
                return (v["id"], normalize_blocks(raw, valid_keys, home_key))
            except Exception as ex:
                print(f"[gen_schedules] {v['id']} LLM 실패 -> 개별 폴백: {ex}")
                return (v["id"], fallback_schedule(v, valid_keys, home_key))

        # 웜업: 첫 1명을 먼저 호출해 공통 prefix 캐시를 데운 뒤, 나머지를 동시 호출.
        first_id, first_blocks = gen_one(villagers[0])
        schedules[first_id] = first_blocks
        for vid, blocks in run_threaded(villagers[1:], gen_one, max_workers=8):
            schedules[vid] = blocks
        generated_with = "llm"

    _write_outputs(villagers, locations, schedules, generated_with)
    return schedules


def _write_outputs(villagers, locations, schedules, generated_with):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(os.path.join(DATA_DIR, "schedules.json"), "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)

    lines = [
        f"// 미리마을 생성 데이터 (gen_schedules.py). generated_with: {generated_with}",
        "// index.html 이 data/*.json fetch 실패(file://) 시 이 const 들을 폴백으로 사용한다.",
        "const VILLAGERS = " + json.dumps(villagers, ensure_ascii=False, indent=2) + ";",
        "const LOCATIONS = " + json.dumps(locations, ensure_ascii=False, indent=2) + ";",
        "const SCHEDULES = " + json.dumps(schedules, ensure_ascii=False, indent=2) + ";",
    ]
    with open(os.path.join(DATA_DIR, "village_data.js"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[gen_schedules] 완료: schedules.json + village_data.js "
          f"({len(schedules)}명, {generated_with})")


if __name__ == "__main__":
    force_fallback = ("--fallback" in sys.argv) or (os.getenv("GEN_FALLBACK") == "1")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ctx = " ".join(args) if args else DAY_CONTEXT
    generate(ctx, force_fallback=force_fallback)
