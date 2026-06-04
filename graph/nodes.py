"""LangGraph 노드 모음. 담당: 오케스트레이션.

각 노드는 SimState 에 머지될 dict 를 반환한다.
모든 LLM 호출은 '함수 실행 시점'에만 일어난다(import 시 네트워크 호출 금지).

흐름: react(시민별 반응) -> interact(전파/상호작용) -> aggregate(집계+요약).
LLM 응답은 pydantic 스키마로 구조화 파싱하고, 실패 시 안전한 폴백을 둔다.
"""
from typing import Optional, Literal

from pydantic import BaseModel, Field

from graph.llm import structured_call, run_threaded
from graph.sentiment import score_sentiment
from prompts import (
    build_react_messages,
    build_interact_messages,
    build_aggregate_messages,
)
from state import SimState


# ──────────────────────────────────────────────────────────────────────────
# pydantic 응답 스키마 (OpenAI 구조화 출력용)
# ──────────────────────────────────────────────────────────────────────────
class ScoresModel(BaseModel):
    """시민 1명의 5축 점수. 모두 0~100 정수."""
    understanding: int = Field(ge=0, le=100, description="이해도")
    benefit: int = Field(ge=0, le=100, description="수혜 가능성")
    intent: int = Field(ge=0, le=100, description="신청 의향")
    dissatisfaction: int = Field(ge=0, le=100, description="불만도")
    shareability: int = Field(ge=0, le=100, description="공유 가능성")


class ReactionOut(BaseModel):
    """react 노드의 시민 반응 구조화 출력."""
    stance: Literal["support", "oppose", "mixed"]
    text: str
    scores: ScoresModel
    actions: list[str] = Field(default_factory=list)


class InteractOut(BaseModel):
    """interact 노드의 상호작용(채팅 응답) 구조화 출력."""
    reply: str
    new_stance: Optional[str] = None
    references: list[str] = Field(default_factory=list)


class AggregateOut(BaseModel):
    """aggregate 노드의 요약/수정안/개선안 구조화 출력.

    easy_text 는 역사적 키 이름은 유지하되 의미가 '개선안을 반영해 다시 쓴 정책 수정안'으로
    바뀌었다(쉬운글 변환 기능 폐지). 정책 개선 탭 A/B 비교에서 '수정안' 후보로 미리 채워진다.
    """
    summary: str
    easy_text: str = Field(
        description="시민이 겪은 문제를 해소하도록 개선안을 반영해 다시 쓴 정책 원문(수정안)."
    )
    policy_fixes: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────────────────
_NEUTRAL_SCORES = {
    "understanding": 50,
    "benefit": 50,
    "intent": 50,
    "dissatisfaction": 50,
    "shareability": 50,
}


def _mean(values: list) -> float:
    """빈 리스트면 0.0 을 반환하는 안전한 평균."""
    nums = [float(v) for v in values if v is not None]
    return sum(nums) / len(nums) if nums else 0.0


def _ratio(flags: list) -> float:
    """True 비율(0~1). 빈 리스트면 0.0."""
    return (sum(1 for f in flags if f) / len(flags)) if flags else 0.0


def _age_band(age) -> str:
    """연령을 10세 단위 밴드 문자열로. 값이 없으면 '미상'."""
    try:
        a = int(age)
    except (TypeError, ValueError):
        return "미상"
    if a < 20:
        return "10대 이하"
    if a >= 70:
        return "70대 이상"
    return f"{(a // 10) * 10}대"


def _persona_index(personas: list) -> tuple:
    """페르소나 id / 이름 -> persona 매핑 두 개를 만든다(상호작용 참조 해석용)."""
    by_id = {}
    by_name = {}
    for p in personas:
        pid = p.get("id")
        if pid:
            by_id[pid] = p
        name = (p.get("name") or "").strip()
        if name:
            by_name[name] = p
    return by_id, by_name


# ──────────────────────────────────────────────────────────────────────────
# 1) react 노드 — 시민별 1차 반응 생성
# ──────────────────────────────────────────────────────────────────────────
def react_node(state: SimState) -> dict:
    """각 페르소나마다 정책에 대한 1차 반응을 LLM 으로 생성한다(동시 호출).

    개별 호출이 실패하면 그 시민은 중립(mixed, 점수 50) 폴백 Reaction 으로 채운다.
    """
    policy = state.get("policy", "")
    personas = state.get("personas", []) or []
    grounded = state.get("grounded", True)

    def _one(persona: dict) -> dict:
        # 페르소나 1명에 대한 반응 생성 + Reaction dict 변환.
        pid = persona.get("id")
        try:
            msgs = build_react_messages(persona, policy, grounded=grounded)
            out: ReactionOut = structured_call(msgs, ReactionOut, temperature=0.8)
            return {
                "persona_id": pid,
                "stance": out.stance,
                "text": out.text,
                "evidence": [],
                "scores": out.scores.model_dump(),
                "actions": list(out.actions or []),
                "grounded": grounded,
            }
        except Exception:
            # 개별 시민 실패 → 시뮬레이션 전체를 멈추지 않고 중립 폴백.
            return {
                "persona_id": pid,
                "stance": "mixed",
                "text": "(응답 생성 실패)",
                "evidence": [],
                "scores": dict(_NEUTRAL_SCORES),
                "actions": [],
                "grounded": grounded,
            }

    reactions = run_threaded(personas, _one, max_workers=8)
    return {"reactions": reactions}


# ──────────────────────────────────────────────────────────────────────────
# 2) interact 노드 — 전파/상호작용 라운드
# ──────────────────────────────────────────────────────────────────────────
def _build_digest(reactions: list, by_id: dict, k: int = 6) -> str:
    """공유 가능성(shareability) 상위 K명의 반응을 1문장씩 모은 digest 문자열."""
    ranked = sorted(
        reactions,
        key=lambda r: (r.get("scores") or {}).get("shareability", 0),
        reverse=True,
    )[:k]
    lines = []
    for r in ranked:
        persona = by_id.get(r.get("persona_id"))
        name = (persona or {}).get("name") or r.get("persona_id") or "익명"
        stance_kr = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}.get(
            r.get("stance"), "혼합"
        )
        # 반응 텍스트의 첫 문장만 1줄로 압축.
        text = (r.get("text") or "").strip().replace("\n", " ")
        first = text.split(".")[0].strip()
        snippet = (first[:80] + "…") if len(first) > 80 else first
        lines.append(f"- {name}({stance_kr}): {snippet}")
    return "\n".join(lines)


def _resolve_target(out_refs: list, persona: dict, by_id: dict, by_name: dict):
    """상호작용 응답이 누구를 참조했는지 해석한다.

    1순위: InteractOut.references 의 id/이름 매칭.
    2순위: 페르소나 signals.social_network 의 이웃.
    못 찾으면 None(채팅방 전체 broadcast).
    """
    self_id = persona.get("id")
    # 1) 명시적 references 우선.
    for ref in out_refs or []:
        ref_s = (str(ref) or "").strip()
        if not ref_s:
            continue
        if ref_s in by_id and ref_s != self_id:
            return ref_s
        if ref_s in by_name:
            cand = by_name[ref_s].get("id")
            if cand and cand != self_id:
                return cand
    # 2) 사회적 네트워크 이웃으로 폴백.
    network = (persona.get("signals") or {}).get("social_network") or []
    for nb in network:
        nb_s = (str(nb) or "").strip()
        if nb_s in by_id and nb_s != self_id:
            return nb_s
        if nb_s in by_name:
            cand = by_name[nb_s].get("id")
            if cand and cand != self_id:
                return cand
    return None


def _feed_digest(feed: list, k: int = 6) -> str:
    """누적 대화 피드에서 '가장 최근 k개 발언'을 1줄씩 모은 digest.

    _build_digest 가 shareability 상위(고정)만 보여줬던 것과 달리,
    피드 끝(=가장 최근 발언)을 보여줘 라운드가 진행될수록 대화가 실제로
    '쌓이고 이어지게' 한다(게시판/채팅방 타임라인처럼).
    """
    recent = feed[-k:] if (k and len(feed) > k) else feed
    lines = []
    for item in recent:
        stance_kr = {"support": "찬성", "oppose": "반대", "mixed": "혼합"}.get(
            item.get("stance"), "혼합"
        )
        text = (item.get("text") or "").strip().replace("\n", " ")
        first = text.split(".")[0].strip()
        snippet = (first[:80] + "…") if len(first) > 80 else first
        name = item.get("name") or "익명"
        lines.append(f"- {name}({stance_kr}): {snippet}")
    return "\n".join(lines)


def interact_node(state: SimState) -> dict:
    """페르소나들이 '누적되는 게시판 피드'를 보고 라운드마다 한 마디씩 단다.

    핵심: 각 라운드의 댓글(reply)을 피드에 누적해, 다음 라운드 시민들이
    '이전 턴에 새로 올라온 댓글'까지 보게 한다. (이전 버전은 1차 react
    반응만 반복해 보여줘, 라운드가 진행돼도 대화가 제자리였다.)

    interactions(채팅 레코드)와 edges(전파 그래프 엣지)를 함께 반환한다.
    """
    policy = state.get("policy", "")
    personas = state.get("personas", []) or []
    reactions = state.get("reactions", []) or []
    rounds = max(1, min(int(state.get("rounds", 1) or 1), 2))  # 1~2 라운드로 제한.

    by_id, by_name = _persona_index(personas)
    # 라운드 동안 갱신될 입장(stance) 추적. 초기값은 react 결과.
    stance_now = {
        r.get("persona_id"): r.get("stance", "mixed") for r in reactions
    }

    # 누적 대화 피드: 1차 react 반응을 시드로 시작. 라운드마다 reply 가 쌓인다.
    feed: list = []
    for r in reactions:
        persona = by_id.get(r.get("persona_id"))
        feed.append(
            {
                "name": (persona or {}).get("name") or r.get("persona_id") or "익명",
                "stance": r.get("stance", "mixed"),
                "text": r.get("text", ""),
            }
        )

    interactions: list = []
    edges: list = []

    for rnd in range(1, rounds + 1):
        # 이번 라운드 모든 시민은 '라운드 시작 시점의 최근 피드'를 본다(턴 배치).
        cur_digest = _feed_digest(feed, k=6)

        def _one(persona: dict) -> dict:
            # 페르소나 1명의 이번 라운드 상호작용 생성.
            pid = persona.get("id")
            try:
                msgs = build_interact_messages(persona, policy, cur_digest)
                out: InteractOut = structured_call(msgs, InteractOut, temperature=0.7)
                target = _resolve_target(out.references, persona, by_id, by_name)
                return {
                    "persona_id": pid,
                    "reply": out.reply,
                    "new_stance": out.new_stance,
                    "target": target,
                }
            except Exception:
                # 실패 시 이웃에게 broadcast 한 빈약한 레코드.
                target = _resolve_target([], persona, by_id, by_name)
                return {
                    "persona_id": pid,
                    "reply": "(상호작용 생성 실패)",
                    "new_stance": None,
                    "target": target,
                }

        results = run_threaded(personas, _one, max_workers=8)

        # 레코드/엣지 생성 + 입장 갱신 + 이번 턴 댓글을 피드에 누적.
        for res in results:
            pid = res["persona_id"]
            target = res["target"]
            shift = res["new_stance"]
            # 입장은 '실제로 바뀐 경우만' 반영(이전과 같으면 무시 → herding 완화).
            prev = stance_now.get(pid)
            changed = shift in ("support", "oppose", "mixed") and shift != prev
            if changed:
                stance_now[pid] = shift
            interactions.append(
                {
                    "round": rnd,
                    "from_id": pid,
                    "to_id": target,           # None = 게시판 전체(원글)에 댓글
                    "text": res["reply"],
                    "stance_shift": shift if changed else None,
                }
            )
            # 엣지는 참조 대상이 있을 때만(broadcast 는 그래프 노이즈라 제외).
            if target:
                edges.append({"from": pid, "to": target, "round": rnd})
            # 이번 턴 댓글을 피드 끝에 누적 → 다음 라운드가 본다.
            persona = by_id.get(pid)
            feed.append(
                {
                    "name": (persona or {}).get("name") or pid or "익명",
                    "stance": stance_now.get(pid, "mixed"),
                    "text": res["reply"],
                }
            )

    return {"interactions": interactions, "edges": edges}


# ──────────────────────────────────────────────────────────────────────────
# 3) aggregate 노드 — 순수 파이썬 metrics + LLM 요약
# ──────────────────────────────────────────────────────────────────────────
def _compute_metrics(reactions: list, personas: list) -> dict:
    """LLM 없이 순수 파이썬으로 핵심 지표를 계산한다."""
    by_id, _ = _persona_index(personas)

    # 5축 점수 벡터 추출.
    understanding = [(r.get("scores") or {}).get("understanding", 50) for r in reactions]
    benefit = [(r.get("scores") or {}).get("benefit", 50) for r in reactions]
    intent = [(r.get("scores") or {}).get("intent", 50) for r in reactions]
    dissatisfaction = [(r.get("scores") or {}).get("dissatisfaction", 50) for r in reactions]
    shareability = [(r.get("scores") or {}).get("shareability", 50) for r in reactions]

    m_understanding = _mean(understanding)
    m_benefit = _mean(benefit)
    m_intent = _mean(intent)
    m_dissat = _mean(dissatisfaction)
    m_share = _mean(shareability)

    n = len(reactions)

    # 입장 분포.
    n_support = sum(1 for r in reactions if r.get("stance") == "support")
    n_oppose = sum(1 for r in reactions if r.get("stance") == "oppose")
    n_mixed = sum(1 for r in reactions if r.get("stance") == "mixed")

    # stance 불일치도: 찬/반이 팽팽할수록 큼(0~1). 둘 중 작은 쪽 비율 * 2.
    decided = n_support + n_oppose
    if decided > 0:
        minority = min(n_support, n_oppose)
        stance_conflict = (minority / decided) * 2.0  # 0(한쪽 쏠림)~1(5:5)
    else:
        stance_conflict = 0.0

    # 저이해(understanding<40) 비율.
    low_understand_ratio = _ratio([u < 40 for u in understanding])
    # 신청의향 적극층(intent>=60) 비율.
    high_intent_ratio = _ratio([i >= 60 for i in intent])

    # 정책수용도: 신청의향·이해도 ↑, 불만 ↓ 가중 블렌드(0~100).
    acceptance = (
        0.45 * m_intent
        + 0.30 * m_understanding
        + 0.25 * (100.0 - m_dissat)
    )

    # 사회혼란도(0~100): 반발 강도 = 시민 불만 평균.
    # metrics_common 으로 통일(real/demo/fallback 동일).
    from metrics_common import social_unrest as _social_unrest
    social_unrest = _social_unrest(reactions)

    # 신청의향지수: 평균 의향과 적극층 비율의 블렌드(0~100).
    application_index = 0.6 * m_intent + 0.4 * (high_intent_ratio * 100.0)

    # 감성 평균: 텍스트 + 점수 기반 [-1, 1].
    sentiments = []
    for r in reactions:
        try:
            sentiments.append(score_sentiment(r.get("text", ""), r.get("scores")))
        except Exception:
            sentiments.append(0.0)
    m_sentiment = _mean(sentiments)

    # 세그먼트별 평균 신청의향: income_level 별 / 연령대별.
    seg_income: dict = {}
    seg_age: dict = {}
    for r in reactions:
        persona = by_id.get(r.get("persona_id")) or {}
        i_val = (r.get("scores") or {}).get("intent", 50)
        # 소득 수준 세그먼트.
        income = (persona.get("signals") or {}).get("income_level") or "미상"
        seg_income.setdefault(income, []).append(i_val)
        # 연령대 세그먼트.
        band = _age_band((persona.get("demographics") or {}).get("age"))
        seg_age.setdefault(band, []).append(i_val)

    seg_income_mean = {k: round(_mean(v), 1) for k, v in seg_income.items()}
    seg_age_mean = {k: round(_mean(v), 1) for k, v in seg_age.items()}

    return {
        # 핵심 3지표(0~100).
        "policy_acceptance": round(acceptance, 1),   # 정책수용도
        "social_unrest": round(social_unrest, 1),     # 사회혼란도
        "application_index": round(application_index, 1),  # 신청의향지수
        # 5축 평균.
        "axis_means": {
            "understanding": round(m_understanding, 1),
            "benefit": round(m_benefit, 1),
            "intent": round(m_intent, 1),
            "dissatisfaction": round(m_dissat, 1),
            "shareability": round(m_share, 1),
        },
        # 입장 분포 및 보조 지표.
        "stance_counts": {"support": n_support, "oppose": n_oppose, "mixed": n_mixed},
        "stance_conflict": round(stance_conflict, 3),
        "low_understanding_ratio": round(low_understand_ratio, 3),
        "high_intent_ratio": round(high_intent_ratio, 3),
        "sentiment_mean": round(m_sentiment, 3),
        # 세그먼트.
        "segments": {
            "by_income": seg_income_mean,
            "by_age": seg_age_mean,
        },
        "n": n,
    }


def _metrics_digest(metrics: dict) -> str:
    """LLM 요약 프롬프트에 넣을 metrics 요약 문자열."""
    axis = metrics.get("axis_means", {})
    sc = metrics.get("stance_counts", {})
    lines = [
        f"정책수용도 {metrics.get('policy_acceptance')} / 100",
        f"사회혼란도 {metrics.get('social_unrest')} / 100",
        f"신청의향지수 {metrics.get('application_index')} / 100",
        (
            "5축 평균 — 이해도 {u} / 수혜 {b} / 의향 {i} / 불만 {d} / 공유 {s}".format(
                u=axis.get("understanding"),
                b=axis.get("benefit"),
                i=axis.get("intent"),
                d=axis.get("dissatisfaction"),
                s=axis.get("shareability"),
            )
        ),
        f"입장 분포 — 찬성 {sc.get('support', 0)} / 반대 {sc.get('oppose', 0)} / 혼합 {sc.get('mixed', 0)}",
    ]
    return "\n".join(lines)


def aggregate_node(state: SimState) -> dict:
    """반응을 집계해 지표를 산출하고, LLM 으로 요약/쉬운설명/개선안을 만든다.

    metrics 는 순수 파이썬으로 먼저 계산(LLM 비의존), 요약만 LLM 1회 호출.
    """
    policy = state.get("policy", "")
    personas = state.get("personas", []) or []
    reactions = state.get("reactions", []) or []

    # 1) 순수 파이썬 지표 계산.
    metrics = _compute_metrics(reactions, personas)
    digest = _metrics_digest(metrics)

    # 2) LLM 요약 1회(실패해도 metrics 는 보존).
    summary = ""
    improvements = {"easy_text": "", "policy_fixes": []}
    try:
        msgs = build_aggregate_messages(policy, metrics, digest)
        out: AggregateOut = structured_call(msgs, AggregateOut, temperature=0.2)
        summary = out.summary
        improvements = {
            "easy_text": out.easy_text,
            "policy_fixes": list(out.policy_fixes or []),
        }
    except Exception:
        # 요약 실패 시에도 데모가 멈추지 않도록 지표 기반 폴백 문구 제공.
        summary = (
            "요약 생성에 실패했습니다. 지표상 정책수용도 "
            f"{metrics.get('policy_acceptance')}, 사회혼란도 "
            f"{metrics.get('social_unrest')} 수준입니다."
        )
        improvements = {"easy_text": "", "policy_fixes": []}

    return {"summary": summary, "metrics": metrics, "improvements": improvements}
