# -*- coding: utf-8 -*-
"""일탈 행동 축(DESIGN §9) — LLM 없이 순수 로직 검증.

검증 항목:
  1. ReactionOut 하위 호환: behavior 필드 없이도 파싱되고 기본값이 채워진다.
  2. 설문 무오염(구조): behavior 필드는 생성 순서상 survey **뒤**에 있다.
  3. 집계: nodes._compute_metrics 가 behavior_counts/deviance_rate/complaint_rate 를
     올바르게 계산하고, ''(미측정)은 분모에서 제외한다. model._compute_metrics 동일.
  4. 프롬프트: react 과제에 속내 문항, cast 주입 시에만 [속사정], ablation 은 무시.
     캐스팅 명단 번호, interact 의 [당신만 아는 속내], 인생극장 속내 줄.
  5. mock/ViewModel: sample_simstate → build_view 통과 후 behavior/casting 보존,
     mock 캐스팅 발현자와 반응 behavior 일관.
  6. UI 빌더: 히트맵 HTML 에 배지·속내(escape 포함), 개선탭 _deviant_rows 정렬.
  7. run_casting 빈 명단 → {} (LLM 호출 없음).
실행: python _test_behavior.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from graph.nodes import (
    ReactionOut, SurveyModel, CastingOut, CastMember,
    _compute_metrics as nodes_metrics, _behavior_digest,
    run_casting, DEVIANCE_THRESHOLD,
)
from prompts import (
    _react_task, build_react_messages, build_casting_messages,
    build_interact_messages, _reaction_text,
)
from ui.mock import sample_simstate
from ui.model import build_view, _compute_metrics as model_metrics


# ── 1) ReactionOut 하위 호환 + 기본값 ─────────────────────────────────────
_SURVEY = {
    "eligibility": "target", "understanding": "well", "household_note": "상관 있다",
    "benefit": "some_help", "intent": "probably", "dissatisfaction": "not_much",
    "shareability": "sometimes",
}
r = ReactionOut(text="좋네요", stance="support", survey=SurveyModel(**_SURVEY))
assert r.behavior_class == "comply" and r.behavior_tag == "" and r.behavior_text == "", (
    r.behavior_class, r.behavior_tag, r.behavior_text)
print("✅ ReactionOut 하위 호환: behavior 기본값 (comply/''/'')")

# ── 2) 설문 무오염(구조): 필드 순서 = 생성 순서, behavior 는 survey 뒤 ─────
fields = list(ReactionOut.model_fields)
assert fields.index("survey") < fields.index("behavior_text") < fields.index("behavior_class"), fields
print("✅ 생성 순서: survey → behavior_text → behavior_class (5축 측정 오염 구조 차단)")

# ── 3) 집계: behavior_counts / deviance_rate / complaint_rate ────────────
def mk(bc, n=1):
    return [{"persona_id": f"x{bc}{k}",
             "scores": {"understanding": 50, "benefit": 50, "intent": 50,
                        "dissatisfaction": 50, "shareability": 50},
             "stance": "mixed", "behavior_class": bc,
             "behavior_tag": "t" if bc not in ("comply", "inaction", "") else "",
             "behavior_text": "속내" if bc not in ("comply", "inaction", "") else ""}
            for k in range(n)]

rx = mk("comply", 5) + mk("workaround", 2) + mk("exploit", 1) + mk("complain", 2) + mk("", 2)
m = nodes_metrics(rx, [])
assert m["behavior_counts"] == {"comply": 5, "workaround": 2, "exploit": 1, "complain": 2}, m["behavior_counts"]
assert abs(m["deviance_rate"] - 3 / 10) < 1e-6, m["deviance_rate"]      # ''(미측정 2명) 분모 제외
assert abs(m["complaint_rate"] - 2 / 10) < 1e-6, m["complaint_rate"]
mm = model_metrics(rx)
assert mm["behavior_counts"] == m["behavior_counts"], mm["behavior_counts"]
assert abs(mm["deviance_rate"] - m["deviance_rate"]) < 1e-6
empty = nodes_metrics(mk("", 3), [])
assert empty["behavior_counts"] == {} and empty["deviance_rate"] == 0.0, empty
print("✅ 집계: behavior_counts/deviance_rate/complaint_rate — 미측정('') 분모 제외, nodes==model")

# behavior digest — 이름·태그·속내가 들어가고, 없으면 빈 문자열.
personas_d = [{"id": rx[5]["persona_id"], "name": "김편법"}]
d = _behavior_digest(rx, personas_d)
assert "김편법" in d and "편법" in d and "속내" in d, d
assert _behavior_digest(mk("comply", 3), []) == ""
print("✅ aggregate digest: 관측된 속내만 블록 생성(없으면 생략)")

# ── 4) 프롬프트 ───────────────────────────────────────────────────────────
task = _react_task("정책 원문")
for needle in ("behavior_text", "behavior_tag", "behavior_class", "workaround",
               "exploit", "complain", "위조·회피 요령은 적지 않습니다"):
    assert needle in task, needle
print("✅ react 과제: 속내 문항 6) + 안전 가드 문구 포함")

persona = {"id": "p1", "name": "홍길동", "demographics": {"age": 30},
           "persona_text": "시민", "signals": {}, "meta": {}}
cast = {"tag": "위장 전입 검토", "rationale": "요건과 실질의 어긋남"}
with_cast = build_react_messages(persona, "정책", grounded=True, cast=cast)[1]["content"]
no_cast = build_react_messages(persona, "정책", grounded=True)[1]["content"]
ablation = build_react_messages(persona, "정책", grounded=False, cast=cast)[1]["content"]
assert "■ 속사정" in with_cast and "위장 전입 검토" in with_cast
assert "■ 속사정" not in no_cast
assert "■ 속사정" not in ablation and "홍길동" not in ablation   # ablation: 카드/속사정 둘 다 없음
print("✅ [속사정] 블록: cast 주입 시에만, ablation(grounded=False)은 캐스팅 무시")

roster_msgs = build_casting_messages([persona, dict(persona, id="p2", name="김철수")], "정책")
u = roster_msgs[1]["content"]
assert "1. " in u and "2. " in u and "index" in u and str(60) in u, u
print("✅ 캐스팅 프롬프트: 번호 명단 + 임계값 안내")

own = {"stance": "support", "text": "찬성이요", "behavior_text": "전입만 옮겨둘까 싶다"}
inter = build_interact_messages(persona, "정책", "(댓글)", own=own)[1]["content"]
inter_plain = build_interact_messages(persona, "정책", "(댓글)",
                                      own={"stance": "support", "text": "찬성이요"})[1]["content"]
assert "[당신만 아는 속내]" in inter and "전입만 옮겨둘까" in inter
assert "[당신만 아는 속내]" not in inter_plain
print("✅ interact: 속내는 '꺼낼지 감출지' 허용 블록으로만(없으면 생략)")

rt = _reaction_text({"stance": "support", "text": "좋아요", "scores": {},
                     "behavior_text": "친구 집에 전입해둘까", "behavior_tag": "위장 전입 검토"})
assert "마음에 품은 속내" in rt and "위장 전입 검토" in rt
rt_plain = _reaction_text({"stance": "support", "text": "좋아요", "scores": {}})
assert "마음에 품은 속내" not in rt_plain
print("✅ 인생극장 grounding: 속내 줄(있을 때만)")

# ── 5) mock → ViewModel 통과 ─────────────────────────────────────────────
sim = sample_simstate()
view = build_view(sim)
rbid = view["reactions_by_id"]
assert rbid["p11"]["behavior_class"] == "exploit" and rbid["p11"]["behavior_tag"], rbid["p11"]
assert rbid["p05"]["behavior_class"] == "workaround"
assert rbid["p03"]["behavior_class"] == "complain" and rbid["p08"]["behavior_class"] == "complain"
assert rbid["p02"]["behavior_class"] == "comply" and rbid["p02"]["behavior_text"] == ""
members = view["casting"]["members"]
manifest_ids = {pid for pid, e in members.items() if e.get("manifest")}
deviant_ids = {pid for pid, r0 in rbid.items()
               if r0["behavior_class"] in ("workaround", "exploit", "complain")}
assert manifest_ids == deviant_ids == {"p03", "p05", "p08", "p11"}, (manifest_ids, deviant_ids)
assert view["casting"]["threshold"] == DEVIANCE_THRESHOLD
bc_mock = view["metrics"]["behavior_counts"]
assert bc_mock.get("exploit") == 1 and bc_mock.get("workaround") == 1 and bc_mock.get("complain") == 2, bc_mock
# n 슬라이스: keep_ids 밖 캐스팅은 잘려나간다.
view8 = build_view(sample_simstate(n=8))
assert set(view8["casting"]["members"]) <= {p["id"] for p in view8["personas"]}
print("✅ mock→ViewModel: behavior/casting 보존 · 발현자==일탈 반응자 일관 · n 슬라이스 안전")

# ── 6) UI 빌더 ───────────────────────────────────────────────────────────
from ui.tab_dashboard import build_reaction_table, _build_table_html
df, _counts = build_reaction_table(view["personas"], rbid)
html = _build_table_html(df, rbid, wrap_max=500)
assert "부정수급 시도" in html and "위장 전입 검토" in html and "bnote" in html
# escape 확인: 악의적 텍스트가 그대로 박히지 않는다.
evil = dict(rbid["p11"]); evil["behavior_text"] = "<script>alert(1)</script>"
html_evil = _build_table_html(df, {**rbid, "p11": evil}, wrap_max=500)
assert "<script>alert(1)</script>" not in html_evil
print("✅ 히트맵: 배지+속내 렌더 · LLM 텍스트 escape")

from ui.tab_improve import _deviant_rows
rows = _deviant_rows(view)
assert [t[0] for t in rows] == ["exploit", "workaround", "complain", "complain"], rows
assert rows[0][2] == "임수빈", rows[0]
print("✅ 개선탭 _deviant_rows: 심각도순(부정수급→편법→민원) 정렬")

# ── 7) run_casting 빈 명단 — LLM 호출 없이 {} ────────────────────────────
assert run_casting([], "정책") == {}
print("✅ run_casting([]) == {} (호출 0)")

# CastingOut 스키마 자체 점검
co = CastingOut(members=[CastMember(index=1, score=70, tag="t", rationale="r")])
assert co.members[0].score == 70
print("✅ CastingOut 스키마 OK")

print("\n전체 통과 — 일탈 행동 축(DESIGN §9) 순수 로직 검증 완료")
