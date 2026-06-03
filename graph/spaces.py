# -*- coding: utf-8 -*-
"""graph/spaces.py — 미리 마을 공간 트리 (정책 접근 채널).

Park et al.(Generative Agents)의 공간 트리(World→장소→오브젝트)를
'정책 접근 채널'로 재해석한 환경 정의다. 핵심 가치:

  어느 장소에 닿느냐가 곧 정책 접근 격차다.
  - 복지로(온라인): 디지털 능숙한 청년·고학력에 유리, 디지털 약자엔 진입장벽.
  - 주민센터(오프라인): 보편 창구지만 거동 불편·지방은 접근성 문제.
  - 복지관: 고령·취약층의 정보 거점. 청년은 잘 닿지 않음.
  - 직장/시장: 동료·상인·이웃의 구전(口傳) 채널. 경제활동 인구 중심.
  - 집: 사적 공간. 어느 채널에도 닿지 못하면 여기 머문다 = 사각지대 신호.

import 시점에 네트워크/LLM 호출 없음. 순수 데이터 + 문자열 조립만.

공개 API:
    PLACE_KEYS, PLACE_LABELS, PLACES, STATUS_LABELS
    place_label(key) -> str
    status_label(key) -> str
    space_menu_text() -> str            # 프롬프트 주입용 장소 메뉴
    village_tree() -> dict (SpaceNode)  # World→장소 트리 (state.SpaceNode 계약)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 장소(정책 접근 채널) 정의 — 순서 = 표시/메뉴 순서
# ---------------------------------------------------------------------------
# 각 항목:
#   key      : 코드/LLM 출력용 안정 키 (영문, 변경 금지 = 약한 계약)
#   name     : 한글 표시명
#   role     : 정책 채널로서의 의미 한 줄
#   favored  : 이 채널에 잘 닿는 사람(유리한 층)
#   barrier  : 이 채널의 진입장벽(불리한 층)
PLACES = [
    {
        "key": "online_portal",
        "name": "복지로(온라인)",
        "role": "디지털 신청 채널. 집·휴대폰에서 정책을 검색하고 바로 신청한다.",
        "favored": "디지털에 능숙한 청년·고학력층",
        "barrier": "고령·저디지털층은 로그인·서류 단계에서 막히기 쉬움",
    },
    {
        "key": "community_center",
        "name": "주민센터(행정복지센터)",
        "role": "오프라인 신청·문의 창구. 직원이 직접 도와줄 수 있다.",
        "favored": "거동이 가능하고 시간을 낼 수 있는 사람",
        "barrier": "거동 불편·지방 거주·생업으로 방문이 어려운 사람",
    },
    {
        "key": "welfare_center",
        "name": "복지관",
        "role": "고령·취약층의 정보 거점. 복지사·어르신 모임을 통해 소식이 돈다.",
        "favored": "복지관을 이용하는 고령·취약층",
        "barrier": "청년·직장인은 거의 방문하지 않아 정보가 닿지 않음",
    },
    {
        "key": "work_market",
        "name": "직장·시장",
        "role": "동료·상인·이웃을 통한 구전(口傳) 정보 채널.",
        "favored": "경제활동 인구, 사회 연결망이 넓은 사람",
        "barrier": "1인 가구·연결망이 빈약한 사람은 소문이 닿지 않음",
    },
    {
        "key": "home",
        "name": "집",
        "role": "사적 공간. 어느 채널에도 닿지 못했거나, 신청을 포기·관망하는 상태.",
        "favored": "가족이 대신 정보를 물어다 주는 경우는 집에서도 닿음",
        "barrier": "고립·무관심·불신이면 정책에 끝내 닿지 못함 = 사각지대",
    },
]

# 빠른 조회용 파생물
PLACE_KEYS = [p["key"] for p in PLACES]
PLACE_LABELS = {p["key"]: p["name"] for p in PLACES}
_PLACE_BY_KEY = {p["key"]: p for p in PLACES}

# 정책 관여 단계(VillageStep.policy_status)의 한글 라벨
STATUS_LABELS = {
    "unaware": "모름",
    "aware": "알게 됨",
    "applied": "신청함",
    "received": "수령·혜택",
    "blocked": "시도했으나 막힘",
}


# ---------------------------------------------------------------------------
# 라벨 헬퍼 (알 수 없는 키도 죽지 않게)
# ---------------------------------------------------------------------------
def place_label(key: str) -> str:
    """장소 키 -> 한글명. 모르는 키면 키 그대로 반환."""
    return PLACE_LABELS.get(key, str(key or "집"))


def status_label(key: str) -> str:
    """정책 관여 상태 키 -> 한글명. 모르는 키면 키 그대로."""
    return STATUS_LABELS.get(key, str(key or "모름"))


# ---------------------------------------------------------------------------
# 프롬프트 주입용 장소 메뉴
# ---------------------------------------------------------------------------
def space_menu_text() -> str:
    """LLM 이 '이번 시점 주민이 닿은 장소'를 고르도록 제시하는 메뉴 문자열.

    각 줄: `key (한글명): 의미 — 유리: ... / 장벽: ...`
    village 프롬프트가 이 텍스트를 그대로 끼워 넣는다.
    """
    lines = []
    for p in PLACES:
        lines.append(
            f"- {p['key']} ({p['name']}): {p['role']} "
            f"(유리: {p['favored']} / 장벽: {p['barrier']})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 공간 트리 (state.SpaceNode 계약) — 표시/확장용
# ---------------------------------------------------------------------------
def village_tree() -> dict:
    """미리 마을의 World→장소 트리를 SpaceNode dict 로 반환한다.

    state.SpaceNode 계약(name/role/children/objects/state)을 따른다.
    오브젝트는 §4.1 확장 예시(채널의 구체적 상태)를 일부 채운다.
    """
    _objects = {
        "online_portal": ["복지로 앱: 로그인 단계 복잡함", "본인인증 필요"],
        "community_center": ["민원 창구", "신청 서식 비치", "직원 안내"],
        "welfare_center": ["어르신 사랑방", "복지사 상담", "게시판"],
        "work_market": ["동료 단톡방", "상인회", "이웃 입소문"],
        "home": ["TV·뉴스", "가족 단톡방", "우편물"],
    }
    children = []
    for p in PLACES:
        children.append({
            "name": p["name"],
            "role": p["role"],
            "children": [],
            "objects": _objects.get(p["key"], []),
            "state": {"key": p["key"], "favored": p["favored"], "barrier": p["barrier"]},
        })
    return {
        "name": "미리 마을",
        "role": "정책이 시민에게 닿는 경로를 담은 가상 마을(World)",
        "children": children,
        "objects": [],
        "state": {},
    }
