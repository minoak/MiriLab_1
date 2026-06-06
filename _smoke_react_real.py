# -*- coding: utf-8 -*-
"""_smoke_react_real.py — 설문(survey) 전환 react 실 LLM 스모크 (4콜, ~0.2센트).

확인: (1) 새 ReactionOut(text→stance→lean→survey→actions) 구조화 출력 동작
      (2) 후광 차단 — 비대상 노인이 청년 정책에 benefit=no_effect(50)·intent 낮음
          (구버전 버그: 호감이 benefit 70/intent 57 로 번짐)
      (3) 종부세(손해 측) — benefit 의 harm 쪽 선택지 동작
실행: python _smoke_react_real.py
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

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 읽기만

from data.personas import load_personas
from prompts import build_react_messages
from graph.llm import structured_call, has_real_key
from graph.nodes import ReactionOut, survey_to_scores
from sample_policies import SAMPLES

assert has_real_key(), "실키 없음 — 스모크 불가"

# _run_gap_eval.py POLICIES["property_tax"] 와 동일 원문(갭 실험 비교용 사본).
PROPERTY_TAX = (
    "[종합부동산세 강화]\n"
    "부동산 시장 안정과 과세 형평을 위해 종합부동산세를 강화합니다.\n"
    "내용: 다주택자(조정대상지역 2주택 이상 보유)에 대한 세율을 기존 최고 "
    "3.2%에서 최고 6.0%까지 인상합니다. 법인 보유 주택에는 최고세율을 "
    "일괄 적용합니다.\n"
    "대상: 고가 주택 보유자 및 다주택자.\n"
    "시행: 다음 연도 납부분부터 적용되며, 별도 신청 없이 고지서가 발송됩니다."
)

personas = load_personas(n=8, seed=42)
by_name = {p["name"]: p for p in personas}

YOUTH_RENT = SAMPLES["청년 월세 한시 특별지원"]
# (페르소나, 정책라벨, 정책원문) — 노인 2명 = 후광 검증 / 청년 1명 = 대상 유지 검증
CASES = [
    (by_name["장원주"], "청년월세", YOUTH_RENT),   # 66세 — 비대상
    (by_name["정명숙"], "청년월세", YOUTH_RENT),   # 60세 — 비대상
    (by_name["신민재"], "청년월세", YOUTH_RENT),   # 24세 — 대상(단 부모 동거)
    (by_name["장원주"], "종부세", PROPERTY_TAX),   # 손해 측 선택지 동작 확인
]

for p, label, policy in CASES:
    d = p.get("demographics") or {}
    print("=" * 70)
    print(f"[{label}] {p['name']} ({d.get('age')}세 {d.get('sex')} · {d.get('occupation')})")
    msgs = build_react_messages(p, policy, grounded=True)
    out: ReactionOut = structured_call(msgs, ReactionOut, temperature=1.0)
    s = survey_to_scores(out.survey)
    sv = out.survey
    print(f"  입장: {out.stance} / 기울기: {out.lean} / 대상 자가인식: {sv.eligibility}")
    print(f"  우리집: {sv.household_note}")
    print(f"  설문: 이해 {sv.understanding}({s['understanding']})"
          f" · 살림영향 {sv.benefit}({s['benefit']})"
          f" · 의향 {sv.intent}({s['intent']})"
          f" · 불만 {sv.dissatisfaction}({s['dissatisfaction']})"
          f" · 공유 {sv.shareability}({s['shareability']})")
    print(f"  반응: {out.text}")
    print(f"  행동: {out.actions}")
