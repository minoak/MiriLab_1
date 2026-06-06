# -*- coding: utf-8 -*-
"""_test_survey.py — 설문(survey) 측정 도구 키리스 단위테스트 (LLM 0콜).

검증: SURVEY_ITEMS(단일 소스) ↔ SurveyModel(스키마) ↔ SURVEY_SCORE_MAP(변환)
      ↔ _react_task(프롬프트) ↔ state.Scores(계약) 5자 동기화.
      + eligibility 응답 분기(효과 문항보다 먼저, scored=False).
실행: python _test_survey.py
"""
import sys
import io
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from prompts import SURVEY_ITEMS, SURVEY_SCORE_MAP, _react_task
from graph.nodes import SurveyModel, ReactionOut, survey_to_scores, _NEUTRAL_SCORES

FAIL = 0


def check(name, cond, detail=""):
    global FAIL
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))


AXES = ["understanding", "benefit", "intent", "dissatisfaction", "shareability"]
scored_items = [it for it in SURVEY_ITEMS if it.get("scored", True)]
all_fields = [it["field"] for it in SURVEY_ITEMS]

# 1. 점수 5축 = state.Scores 와 일치 / eligibility 는 분기 문항(첫 번째, 비점수)
check("점수 5축 일치", [it["field"] for it in scored_items] == AXES)
check("eligibility 분기 문항이 맨 앞", all_fields[0] == "eligibility")
check("eligibility 는 SCORE_MAP 제외", "eligibility" not in SURVEY_SCORE_MAP)

# 2. 점수 범위 0~100 + 단조감소(선택지 순서 = 점수 내림차순) + 핵심 앵커
for it in scored_items:
    scores = [score for _t, _l, score in it["options"]]
    check(f"{it['field']} 점수 범위", all(0 <= s <= 100 for s in scores), str(scores))
    check(f"{it['field']} 단조감소", scores == sorted(scores, reverse=True), str(scores))
check("benefit 양극 앵커(no_effect=50)", SURVEY_SCORE_MAP["benefit"]["no_effect"] == 50)
check("benefit 손해 측 존재(big_harm=0)", SURVEY_SCORE_MAP["benefit"]["big_harm"] == 0)
check("intent 비대상 선택지(no_need=0)", SURVEY_SCORE_MAP["intent"]["no_need"] == 0)

# 3. SurveyModel Literal 토큰 == SURVEY_ITEMS 토큰 (순서 포함, 주관식 제외)
for it in SURVEY_ITEMS:
    if it.get("open"):
        ann = SurveyModel.model_fields[it["field"]].annotation
        check(f"{it['field']} 주관식 str", ann is str)
        continue
    ann = SurveyModel.model_fields[it["field"]].annotation
    lits = list(get_args(ann))
    toks = [tok for tok, _l, _s in it["options"]]
    check(f"{it['field']} 스키마 토큰 동기화", lits == toks, f"{lits} != {toks}")

# 4. 스키마 필드 순서 = 생성 순서: 분기(eligibility) → 이해 → 주관식 프로브
#    (household_note, benefit/intent 직전) → 효과·나머지 문항
check("SurveyModel 필드 순서", list(SurveyModel.model_fields.keys())
      == ["eligibility", "understanding", "household_note",
          "benefit", "intent", "dissatisfaction", "shareability"])
check("SURVEY_ITEMS 순서 = 스키마 순서",
      all_fields == list(SurveyModel.model_fields.keys()))

# 5. 스키마 description 에 문항 원문 포함(모델이 스키마만 봐도 같은 질문)
for it in SURVEY_ITEMS:
    desc = SurveyModel.model_fields[it["field"]].description or ""
    check(f"{it['field']} description 문항 포함", it["question"] in desc)

# 6. survey_to_scores 결정론 변환 — 5축만, 보조 문항(eligibility/주관식) 비변환
sample = SurveyModel(eligibility="not_target", understanding="well",
                     household_note="우리 집과는 상관없다",
                     benefit="no_effect", intent="no_need",
                     dissatisfaction="not_much", shareability="rarely")
mapped = survey_to_scores(sample)
check("변환 결과", mapped == {"understanding": 90, "benefit": 50, "intent": 0,
                          "dissatisfaction": 30, "shareability": 35}, str(mapped))
check("eligibility 변환 제외", "eligibility" not in mapped)
check("household_note 변환 제외", "household_note" not in mapped)
base_kw = {it["field"]: (it["options"][0][0] if it["options"] else "(없음)")
           for it in SURVEY_ITEMS}
for it in scored_items:
    for tok, _l, score in it["options"]:
        kw = dict(base_kw)
        kw[it["field"]] = tok
        got = survey_to_scores(SurveyModel(**kw))[it["field"]]
        check(f"{it['field']}={tok} -> {score}", got == score, f"got {got}")

# 7. ReactionOut 필드 순서 = 생성 순서 (text 먼저, survey 가 scores 대체).
#    behavior_* (일탈 행동 축, DESIGN §9)는 survey **뒤** — 설문 응답이 먼저
#    확정된 뒤 속내가 나오므로 행동 채널이 5축 측정을 오염시키지 못한다.
check("ReactionOut 순서", list(ReactionOut.model_fields.keys())
      == ["text", "stance", "lean", "survey", "actions",
          "behavior_text", "behavior_tag", "behavior_class"])

# 8. 프롬프트(_react_task)에 전 문항·전 토큰 포함 + 구 문구 제거
task = _react_task("[테스트 정책]")
for it in SURVEY_ITEMS:
    check(f"프롬프트에 {it['field']} 문항", it["question"] in task)
    for tok, label, _s in it["options"]:
        check(f"프롬프트에 {it['field']}.{tok}", f"{tok}({label})" in task)
check("구 문구 제거: '형식상 채우는 칸'", "형식상 채우는 칸" not in task)
check("구 문구 제거: '숫자로 옮기기'", "숫자로" not in task)
check("lean 문항 유지", "기울기(lean)" in task)
check("설문 항목 존재", "설문(survey)" in task)

# 9. 폴백 중립 점수 키 = 5축 일치 (react 실패 경로)
check("폴백 키 일치", sorted(_NEUTRAL_SCORES.keys()) == sorted(AXES))

# 10. react_node 배선 (LLM 모킹, 키리스) — 정상 매핑 + 폴백 shape
import graph.nodes as gn

_canned = ReactionOut(text="t", stance="support", lean="none",
                      survey=sample, actions=["a"])
_orig_call = gn.structured_call
try:
    gn.structured_call = lambda *a, **k: _canned
    res = gn.react_node({"policy": "p", "personas": [{"id": "x1"}],
                         "grounded": True})
    r = res["reactions"][0]
    check("react_node scores=설문 매핑", r["scores"] == mapped, str(r["scores"]))
    check("react_node survey 토큰 저장",
          r.get("survey", {}).get("eligibility") == "not_target"
          and r["survey"].get("household_note") == "우리 집과는 상관없다")
    check("react_node lean 통과", r["lean"] == "none")

    def _boom(*a, **k):
        raise RuntimeError("boom")
    gn.structured_call = _boom
    res2 = gn.react_node({"policy": "p", "personas": [{"id": "x1"}],
                          "grounded": True})
    r2 = res2["reactions"][0]
    check("react_node 폴백 scores=중립", r2["scores"] == _NEUTRAL_SCORES)
    check("react_node 폴백 survey={}", r2.get("survey") == {})
finally:
    gn.structured_call = _orig_call

print()
if FAIL:
    print(f"{FAIL}건 실패")
    sys.exit(1)
print("ALL PASS")
