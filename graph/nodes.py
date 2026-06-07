"""LangGraph 노드 모음. 담당: 오케스트레이션.

각 노드는 SimState 에 머지될 dict 를 반환한다.
모든 LLM 호출은 '함수 실행 시점'에만 일어난다(import 시 네트워크 호출 금지).

흐름: react(시민별 반응) -> interact(전파/상호작용) -> aggregate(집계+요약).
LLM 응답은 pydantic 스키마로 구조화 파싱하고, 실패 시 안전한 폴백을 둔다.
"""
import logging
from typing import Optional, Literal

from pydantic import BaseModel, Field

from graph.llm import structured_call, run_threaded
from graph.sentiment import score_sentiment
from prompts import (
    build_react_messages,
    build_interact_messages,
    build_aggregate_messages,
    build_casting_messages,
    SURVEY_ITEMS,
    SURVEY_SCORE_MAP,
)
from state import SimState


_LOG = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# pydantic 응답 스키마 (OpenAI 구조화 출력용)
# ──────────────────────────────────────────────────────────────────────────
def _survey_q(field: str) -> str:
    """SURVEY_ITEMS(단일 소스)에서 문항+선택지 설명문을 만든다(스키마 description)."""
    it = next(i for i in SURVEY_ITEMS if i["field"] == field)
    if not it["options"]:  # 주관식
        return it["question"]
    opts = " / ".join(f"{tok}({label})" for tok, label, _score in it["options"])
    return f"{it['question']} — {opts}"


class SurveyModel(BaseModel):
    """여론조사 설문 응답 — LLM 은 선택지 토큰만 고른다.

    0~100 점수 변환은 survey_to_scores()가 prompts.SURVEY_SCORE_MAP 으로
    결정론 수행한다('판단=LLM, 단위·경로=코드'). 구버전(0~100 자유 정수)은
    LLM 캘리브레이션 한계(70/80 뭉침) + 정서 후광(반응문 분위기가 전 축에
    번짐)으로 비대상자 benefit/intent 가 부풀었다 — 설문 전환으로 구조 차단
    (2026-06-06). 문항·선택지의 단일 소스 = prompts.SURVEY_ITEMS.
    """
    # 응답 분기 — 효과 문항보다 먼저 생성돼야 함(필드 순서 = 생성 순서).
    eligibility: Literal["target", "partial", "not_target", "unsure"] = Field(
        description=_survey_q("eligibility"))
    understanding: Literal["well", "mostly", "partly", "barely"] = Field(
        description=_survey_q("understanding"))
    # 주관식 프로브 — benefit/intent 직전에 '우리 집 기준'을 말로 먼저 쓰게 한다.
    household_note: str = Field(description=_survey_q("household_note"))
    benefit: Literal["big_help", "some_help", "no_effect", "some_harm", "big_harm"] = Field(
        description=_survey_q("benefit"))
    intent: Literal["surely", "probably", "unsure", "probably_not", "no_need"] = Field(
        description=_survey_q("intent"))
    dissatisfaction: Literal["very", "somewhat", "not_much", "none"] = Field(
        description=_survey_q("dissatisfaction"))
    shareability: Literal["often", "sometimes", "rarely", "never"] = Field(
        description=_survey_q("shareability"))


def survey_to_scores(survey: "SurveyModel") -> dict:
    """설문 응답(선택지 토큰) → state.Scores(0~100 정수). 결정론 변환.

    SURVEY_SCORE_MAP 의 5축만 변환한다(eligibility 등 보조 문항은 제외 —
    원본 토큰은 Reaction['survey'] 에 그대로 남는다).
    다운스트림(게이지·퍼널·히트맵)은 기존 Scores 계약을 그대로 읽는다.
    """
    data = survey.model_dump()
    return {
        field: mapping[data[field]]
        for field, mapping in SURVEY_SCORE_MAP.items()
    }


class ReactionOut(BaseModel):
    """react 노드의 시민 반응 구조화 출력.

    필드 순서 = 생성 순서: 반응문(text)을 먼저 말하게 하고 입장(stance)은
    거기서 도출되게 한다 — 입장을 먼저 찍으면 반응문이 사후 합리화가 되는
    결함 교정 (2026-06-06). lean 은 여론조사식 강제선택 기울기로, 실측
    여론조사(강제선택 문항)와 같은 단위의 찬성률을 만들기 위한 보조 측정.
    scores(자유 정수) → survey(설문 선택지)로 교체 — 점수는 코드가 변환.

    behavior_* (일탈 행동 축, DESIGN §9)는 **survey 뒤**에 둔다 — 생성 순서상
    설문 응답이 먼저 확정된 뒤에 속내가 나오므로, 행동 채널이 5축 측정을
    오염시키지 못한다(구조적 차단). 말이 먼저(text), 분류는 그 말에서(class).
    """
    text: str
    stance: Literal["support", "oppose", "mixed"]
    lean: Literal["support", "oppose", "none"] = "none"
    survey: SurveyModel
    actions: list[str] = Field(default_factory=list)
    behavior_text: str = Field(
        default="",
        description="속내 한두 문장 — 공식 절차 밖에서 실제로 어떻게 움직일지. 특별한 속내가 없으면 빈 문자열.")
    behavior_tag: str = Field(
        default="",
        description="속내 행동의 짧은 이름표(자유 — 예: 위장 전입 검토, 집단 민원). 없으면 빈 문자열.")
    behavior_class: Literal["comply", "workaround", "exploit", "complain", "inaction"] = Field(
        default="comply",
        description="속내 행동 대분류: comply(그대로 신청·이용)/workaround(합법적 틈새·편법)/"
                    "exploit(자격·서류를 꾸미는 부정수급 시도)/complain(민원·항의·공론화)/inaction(아무것도 안 함)")


class CastMember(BaseModel):
    """캐스팅 패스의 인물 1명 평가(DESIGN §9). index 는 명단 번호(1부터)."""
    index: int = Field(description="인물 명단의 번호(1부터, 명단 그대로)")
    score: int = Field(description="일탈 성향 0~100 — 대부분의 인물은 60 미만이 자연스럽다")
    tag: str = Field(default="", description="60점 이상만: 할 법한 행동의 짧은 이름표(자유). 미만이면 빈 문자열")
    rationale: str = Field(default="", description="점수의 근거 한 줄 — 이 인물의 처지 어디에서 나오는가")


class CastingOut(BaseModel):
    """캐스팅 패스 구조화 출력 — 명단 전체에 대한 평가 목록."""
    members: list[CastMember] = Field(default_factory=list)


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


def _policy_focus(policy: str) -> str:
    """정책 원문에서 결정론 폴백용 핵심 분야를 고른다."""
    text = str(policy or "")
    if any(k in text for k in ("월세", "임대료", "무주택", "주택")):
        return "주거비"
    if any(k in text for k in ("디지털", "스마트폰", "키오스크", "교육", "기기")):
        return "디지털 교육"
    if any(k in text for k in ("출산", "출생", "아동", "바우처", "국민행복카드")):
        return "출산·양육"
    if any(k in text for k in ("긴급", "위기", "생계", "의료비", "환수")):
        return "긴급 생계"
    if any(k in text for k in ("저축", "계좌", "자산", "근로")):
        return "자산 형성"
    return "정책"


def _fallback_reaction(persona: dict, policy: str, grounded: bool) -> dict:
    """react 호출 실패 시 화면에 실패 문구 대신 쓸 결정론 시민 반응."""
    pid = persona.get("id")
    demo = persona.get("demographics") or {}
    signals = persona.get("signals") or {}
    focus = _policy_focus(policy)
    age = demo.get("age")
    occupation = demo.get("occupation") or "시민"
    person_label = f"{age}세 {occupation}" if age not in (None, "") else f"{occupation}"
    try:
        digital = float(signals.get("digital_literacy", 0.5))
    except (TypeError, ValueError):
        digital = 0.5
    try:
        trust = float(signals.get("government_trust", 0.5))
    except (TypeError, ValueError):
        trust = 0.5

    if trust < 0.35:
        stance = "oppose"
        text = (
            f"{focus} 지원 취지는 이해하지만, 실제 대상 기준과 확인 절차가 분명하지 않으면 "
            f"{person_label} 입장에서는 쉽게 믿고 움직이기 어렵습니다."
        )
        scores = {
            "understanding": 48,
            "benefit": 38,
            "intent": 28,
            "dissatisfaction": 72,
            "shareability": 58,
        }
    elif digital < 0.35:
        stance = "mixed"
        text = (
            f"{focus} 정책은 필요해 보이지만, 온라인 신청이나 안내가 어렵게 되어 있으면 "
            "주변 도움 없이 끝까지 신청하기 힘들 것 같습니다."
        )
        scores = {
            "understanding": 52,
            "benefit": 55,
            "intent": 42,
            "dissatisfaction": 56,
            "shareability": 52,
        }
    else:
        stance = "mixed"
        text = (
            f"{focus} 지원 방향은 긍정적으로 보입니다. 다만 내가 대상인지, 어떤 서류나 "
            "절차가 필요한지 바로 확인할 수 있어야 실제 신청으로 이어질 것 같습니다."
        )
        scores = {
            "understanding": 58,
            "benefit": 54,
            "intent": 50,
            "dissatisfaction": 44,
            "shareability": 55,
        }

    # LLM 호출 실패 시에는 자연스러운 문구만 대체하고, 측정 축 점수는 임의 추론하지 않는다.
    scores = dict(_NEUTRAL_SCORES)
    return {
        "persona_id": pid,
        "stance": stance,
        "lean": "none",
        "text": text,
        "evidence": [],
        "scores": scores,
        "survey": {},
        "actions": ["대상 여부 확인", "신청 경로 확인"],
        "grounded": grounded,
        "behavior_class": "",
        "behavior_tag": "",
        "behavior_text": "",
        "fallback": True,
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
# 1) react 노드 — (캐스팅 1회 →) 시민별 1차 반응 생성
# ──────────────────────────────────────────────────────────────────────────
# 일탈 성향 발현 임계값(DESIGN §9). 고정 비율이 아니라 임계값 자연 발생 —
# 정책에 따라 발현 인물이 0명일 수도, 여럿일 수도 있다.
DEVIANCE_THRESHOLD = 60


def run_casting(personas: list, policy: str) -> dict:
    """react 전 캐스팅 1회(DESIGN §9) — LLM 이 인물별 일탈 성향을 평가한다.

    반환: {'threshold': int, 'members': {persona_id: {'score','tag','rationale',
    'manifest'}}}. manifest(발현) 판정은 코드가 한다(score >= 임계값).
    실패하면 {} — react 는 힌트 없이 평소처럼 돈다(우아한 강등).
    """
    if not personas:
        return {}
    try:
        msgs = build_casting_messages(personas, policy)
        # 판단 과제 — 안정성을 위해 낮은 temperature.
        out: CastingOut = structured_call(msgs, CastingOut, temperature=0.4)
        members: dict = {}
        for m in out.members or []:
            # 명단 번호(1부터) → persona 역매핑. 범위 밖 번호는 버린다.
            if not (1 <= int(m.index) <= len(personas)):
                continue
            pid = personas[int(m.index) - 1].get("id")
            if not pid:
                continue
            score = max(0, min(100, int(m.score)))
            members[pid] = {
                "score": score,
                "tag": (m.tag or "").strip(),
                "rationale": (m.rationale or "").strip(),
                "manifest": score >= DEVIANCE_THRESHOLD,
            }
        return {"threshold": DEVIANCE_THRESHOLD, "members": members}
    except Exception:
        return {}


def react_node(state: SimState) -> dict:
    """각 페르소나마다 정책에 대한 1차 반응을 LLM 으로 생성한다(동시 호출).

    grounded 일 때는 먼저 캐스팅 1회로 일탈 성향을 평가하고, 임계값 이상
    발현 인물의 프롬프트에만 [속사정] 힌트를 주입한다(DESIGN §9).
    ablation(grounded=False)은 캐스팅을 건너뛴다 — 단일 변인(카드 유무) 유지.

    개별 호출이 실패하면 그 시민은 중립(mixed, 점수 50) 폴백 Reaction 으로 채운다.
    """
    policy = state.get("policy", "")
    personas = state.get("personas", []) or []
    grounded = state.get("grounded", True)

    casting = run_casting(personas, policy) if grounded else {}
    cast_members = casting.get("members", {}) if casting else {}

    def _one(persona: dict) -> dict:
        # 페르소나 1명에 대한 반응 생성 + Reaction dict 변환.
        pid = persona.get("id")
        try:
            entry = cast_members.get(pid) or {}
            cast = (
                {"tag": entry.get("tag", ""), "rationale": entry.get("rationale", "")}
                if entry.get("manifest")
                else None
            )
            msgs = build_react_messages(persona, policy, grounded=grounded, cast=cast)
            # temperature 1.0: T<1 은 최빈 응답을 수학적으로 더 뾰족하게 만들어
            # 만장일치 쏠림을 강화한다 — 분포 복원 목적의 상향 (2026-06-06).
            out: ReactionOut = structured_call(msgs, ReactionOut, temperature=1.0)
            return {
                "persona_id": pid,
                "stance": out.stance,
                "lean": out.lean,
                "text": out.text,
                "evidence": [],
                "scores": survey_to_scores(out.survey),
                "survey": out.survey.model_dump(),
                "actions": list(out.actions or []),
                "grounded": grounded,
                # 일탈 행동 축(DESIGN §9) — survey 뒤에 생성돼 5축 무오염.
                "behavior_class": out.behavior_class,
                "behavior_tag": (out.behavior_tag or "").strip(),
                "behavior_text": (out.behavior_text or "").strip(),
            }
        except Exception:
            # 개별 시민 실패 → 시뮬레이션 전체를 멈추지 않고 자연스러운 반응으로 폴백.
            return _fallback_reaction(persona, policy, grounded)

    reactions = run_threaded(personas, _one, max_workers=8)
    return {"reactions": reactions, "casting": casting}


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


def _fallback_interaction_reply(persona: dict, reaction: dict | None, digest: str) -> dict:
    """LLM 상호작용 실패 시에도 사용자에게 실패 문구 대신 자연스러운 댓글을 제공한다."""
    reaction = reaction or {}
    stance = reaction.get("stance") or "mixed"
    text = (reaction.get("text") or "").strip().replace("\n", " ")
    first = text.split(".")[0].strip() if text else ""
    actions = reaction.get("actions") if isinstance(reaction.get("actions"), list) else []
    action = actions[0] if actions else ""
    network = (persona.get("signals") or {}).get("social_network") or []
    network_label = network[0] if network else "주변 사람들"

    if stance == "support":
        if first:
            reply = f"{first}. {network_label}에도 이 내용을 공유해 보겠습니다."
        else:
            reply = "조건이 맞는 시민에게는 도움이 될 것 같아서 주변에도 공유해 보겠습니다."
    elif stance == "oppose":
        if first:
            reply = f"{first}. 다른 분들 의견을 봐도 기준과 절차는 더 명확해야 할 것 같습니다."
        else:
            reply = "취지는 이해하지만 대상 기준과 신청 절차가 더 명확해야 할 것 같습니다."
    else:
        if first:
            reply = f"{first}. 다른 시민들 의견을 보니 조건을 한 번 더 확인해야겠네요."
        else:
            reply = "다른 시민들 반응을 보니 좋은 점과 헷갈리는 점이 같이 보여서 조건을 더 확인해야겠습니다."

    if action and action not in reply:
        reply += f" 우선 {action}부터 해볼 생각입니다."

    return {
        "reply": reply,
        "new_stance": None,
    }


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
    # 자기 1차 반응문 — interact 프롬프트의 자기 일관성 grounding 재료.
    react_text = {
        r.get("persona_id"): r.get("text", "") for r in reactions
    }
    # 자기 속내(일탈 행동 축) — 댓글에서 꺼낼지 감출지는 그 사람이 정한다(DESIGN §9).
    react_behavior = {
        r.get("persona_id"): r.get("behavior_text", "") for r in reactions
    }
    reaction_by_id = {
        r.get("persona_id"): r for r in reactions if isinstance(r, dict)
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
                # own = 현재 입장(라운드마다 갱신) + 1차 반응문 — 자기 일관성.
                own = {
                    "stance": stance_now.get(pid),
                    "text": react_text.get(pid, ""),
                    "behavior_text": react_behavior.get(pid, ""),
                }
                msgs = build_interact_messages(persona, policy, cur_digest, own=own)
                out: InteractOut = structured_call(msgs, InteractOut, temperature=0.7)
                target = _resolve_target(out.references, persona, by_id, by_name)
                return {
                    "persona_id": pid,
                    "reply": out.reply,
                    "new_stance": out.new_stance,
                    "target": target,
                }
            except Exception as exc:
                # 실패 시에도 화면에 "(상호작용 생성 실패)"를 노출하지 않는다.
                # API/모델 오류는 로그로 남기고, 기존 1차 반응 기반 결정론 댓글로 폴백한다.
                _LOG.warning("상호작용 생성 실패, 결정론 댓글로 폴백: %s", exc)
                target = _resolve_target([], persona, by_id, by_name)
                fallback = _fallback_interaction_reply(
                    persona, reaction_by_id.get(pid), cur_digest
                )
                return {
                    "persona_id": pid,
                    "reply": fallback["reply"],
                    "new_stance": fallback["new_stance"],
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
            stance_shift = f"{prev}→{shift}" if changed else None
            interactions.append(
                {
                    "round": rnd,
                    "from_id": pid,
                    "to_id": target,           # None = 게시판 전체(원글)에 댓글
                    "text": res["reply"],
                    "stance_shift": stance_shift,
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

    # 핵심 3지표(0~100): 공식은 metrics_common 단일 소스(설계방향서 v1.2 §8-12) —
    # 집계 노드와 화면(축3 t0 지표)이 같은 함수로 같은 값을 본다.
    from metrics_common import (
        application_index as _application_index,
        policy_acceptance as _policy_acceptance,
        social_unrest as _social_unrest,
    )
    # 정책수용도: 신청의향·이해도 ↑, 불만 ↓ 가중 블렌드.
    acceptance = _policy_acceptance(reactions)
    # 사회혼란도: 반발 강도 = 시민 불만 평균.
    social_unrest = _social_unrest(reactions)
    # 신청의향지수: 평균 의향과 적극층 비율(intent≥60)의 블렌드.
    application_index = _application_index(reactions)

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

    # 일탈 행동 분포(DESIGN §9) — behavior_class 집계. stance 분포와 같은 패턴:
    # LLM 이 고른 enum 을 코드가 센다. ''(미측정: 폴백/구버전 데이터)은 분모에서 제외.
    behavior_counts: dict = {}
    for r in reactions:
        bc = (r.get("behavior_class") or "").strip()
        if bc:
            behavior_counts[bc] = behavior_counts.get(bc, 0) + 1
    measured = sum(behavior_counts.values())
    n_deviant = behavior_counts.get("workaround", 0) + behavior_counts.get("exploit", 0)
    n_complain = behavior_counts.get("complain", 0)
    deviance_rate = (n_deviant / measured) if measured else 0.0      # 편법+부정수급 시도율
    complaint_rate = (n_complain / measured) if measured else 0.0    # 민원·행동화율

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
        # 일탈 행동 축(DESIGN §9).
        "behavior_counts": behavior_counts,
        "deviance_rate": round(deviance_rate, 3),
        "complaint_rate": round(complaint_rate, 3),
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


def _behavior_digest(reactions: list, personas: list, k: int = 8) -> str:
    """관측된 일탈 속내(behavior)를 분석가 프롬프트용 블록으로(DESIGN §9).

    편법·부정수급 시도·민원 예고가 있으면 개선안(policy_fixes)이 그 허점에
    직접 답할 수 있게 한다. 없으면 빈 문자열(블록 생략). 최대 k건으로 상한.
    """
    by_id, _ = _persona_index(personas)
    label = {"workaround": "편법", "exploit": "부정수급 시도", "complain": "민원·행동화"}
    lines = []
    for r in reactions:
        bc = (r.get("behavior_class") or "").strip()
        txt = (r.get("behavior_text") or "").strip().replace("\n", " ")
        if bc not in label or not txt:
            continue
        persona = by_id.get(r.get("persona_id")) or {}
        name = persona.get("name") or r.get("persona_id") or "익명"
        tag = (r.get("behavior_tag") or "").strip() or label[bc]
        if len(txt) > 120:
            txt = txt[:120].rstrip() + "…"
        lines.append(f"- {name} [{label[bc]} · {tag}]: {txt}")
        if len(lines) >= k:
            break
    if not lines:
        return ""
    return "관측된 속내 행동(편법·부정수급 시도·민원 예고) — 개선안이 이 허점에 답해야 함:\n" + "\n".join(lines)


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
    # 일탈 속내가 관측됐으면 분석가가 허점에 직접 답하도록 함께 전달(DESIGN §9).
    behavior_block = _behavior_digest(reactions, personas)
    if behavior_block:
        digest = digest + "\n\n" + behavior_block

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
