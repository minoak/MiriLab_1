# -*- coding: utf-8 -*-
"""_rebuild_cache.py — 페르소나 캐시 재생성(상세 서사 컬럼 포함) + 인물 카드 스모크.

2026-06-06 react 재설계: meta 에 persona/professional/sports/arts/travel/culinary/
skills/bachelors_field/military_status 가 추가돼 캐시를 다시 만든다.
같은 (n=8, seed=42) → 같은 8명 (df.sample random_state 고정).

실행: python _rebuild_cache.py
"""
import sys
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from data.personas import load_personas

print("[1] 캐시 재생성 (force=True, n=8, seed=42) ...")
personas = load_personas(n=8, seed=42, force=True)
print(f"    -> {len(personas)}명 로드")

EXPECT = [
    "persona", "professional_persona", "cultural_background",
    "hobbies_and_interests", "career_goals_and_ambitions", "family_persona",
    "sports_persona", "arts_persona", "travel_persona", "culinary_persona",
    "skills_and_expertise", "bachelors_field", "military_status",
]

print("\n[2] meta 필드 보유율:")
for key in EXPECT:
    n = sum(1 for p in personas if (p.get("meta") or {}).get(key))
    print(f"    {key:32s} {n}/{len(personas)}")

print("\n[3] 인물 카드 샘플 (1번째):")
from prompts import _persona_card, build_react_messages
card = _persona_card(personas[0])
print(card)
print(f"\n    카드 길이: {len(card)}자")

print("\n[4] build_react_messages 스모크 (grounded/ablation):")
msgs_g = build_react_messages(personas[0], "[테스트 정책]\n내용", grounded=True)
msgs_a = build_react_messages(personas[0], "[테스트 정책]\n내용", grounded=False)
assert msgs_g[0]["role"] == "system" and msgs_g[1]["role"] == "user"
assert "[이 사람]" in msgs_g[1]["content"], "grounded user에 카드 없음"
assert "[이 사람]" not in msgs_a[1]["content"], "ablation에 카드가 샘"
assert "현실적으로 판단" not in msgs_g[0]["content"], "구 체크리스트 잔존!"
assert "반신반의" not in msgs_g[1]["content"], "government_trust 문장 잔존!"
assert "기울기(lean)" in msgs_g[1]["content"]
# mock 페르소나(서사 meta 없음) 우아한 축약 확인
mock_p = {"id": "m1", "name": "테스트", "description": "",
          "demographics": {"sex": "남자", "age": 40, "occupation": "회사원"},
          "persona_text": "평범한 회사원입니다.",
          "signals": {"income_level": "중간소득", "digital_literacy": 0.8},
          "meta": {}}
card_m = _persona_card(mock_p)
assert "■ 삶" in card_m and "살아온 배경" not in card_m
print("    OK — grounded/ablation 분기, 카드 폴백, 구 문구 제거 전부 확인")

print("\n[5] ReactionOut 스키마 순서 확인:")
from graph.nodes import ReactionOut
fields = list(ReactionOut.model_fields.keys())
print(f"    {fields}")
assert fields == ["text", "stance", "lean", "survey", "actions"], "필드 순서 불일치"
print("    OK — text 먼저(생성 순서 교정), lean + 설문(survey) 포함")

print("\nALL PASS")
