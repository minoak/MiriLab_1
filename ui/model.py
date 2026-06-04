"""ViewModel 빌더.

build_view(sim) -> dict(ViewModel)
SimState(혹은 그와 비슷한 dict)를 받아 UI 탭들이 바로 그려쓸 수 있는
평탄화된 ViewModel dict 로 변환한다.

설계 원칙
- 누락 필드에 관대하다. sim 이 부분적으로만 채워져 있어도(예: metrics 없음,
  scores 일부 결손) 절대 KeyError/TypeError 로 죽지 않는다.
- 외부 호출(OpenAI/HF/네트워크) 전혀 없음. 순수 파이썬 + 표준 라이브러리만.
- streamlit 불필요(import 안 함). 어떤 UI 프레임워크와도 독립.

반환 키
    policy            : str   정책 원문
    personas          : list  Persona dict 목록(원본 그대로 통과)
    reactions         : list  Reaction dict 목록(scores 보정 적용본)
    reactions_by_id   : dict  persona_id -> reaction(보정본)
    interactions      : list  Interaction dict 목록
    edges             : list  전파 엣지 목록
    summary           : str   갈등/합의 요약
    metrics           : dict  집계 지표(없으면 reactions 로부터 계산)
    improvements      : dict  {'easy_text':str, 'policy_fixes':[...]}
    village           : dict  미리 마을 시뮬 {steps, residents, aggregate} (없으면 {})
    policy_spec       : dict  정책 태그 명세(spec_from_tags). 없으면 {}
"""
from __future__ import annotations

# 5축 점수 키(순서 고정). state.Scores 와 일치.
SCORE_KEYS = ("understanding", "benefit", "intent", "dissatisfaction", "shareability")

# scores 누락 시 채울 기본값(0~100 중앙값). 게이지/카드가 깨지지 않도록.
DEFAULT_SCORE = 50



# ----------------------------------------------------------------------
# 작은 유틸: 안전한 형 변환/접근
# ----------------------------------------------------------------------
def _as_dict(x) -> dict:
    """x 가 dict 면 그대로, 아니면 빈 dict. (None/리스트/객체 방어)"""
    return x if isinstance(x, dict) else {}


def _as_list(x) -> list:
    """x 가 list 면 그대로, 아니면 빈 list."""
    return x if isinstance(x, list) else []


def _to_int_score(v, default: int = DEFAULT_SCORE) -> int:
    """점수 1개를 0~100 정수로 보정. 변환 실패/범위초과 모두 흡수."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return default
    # 0~100 클램프
    return max(0, min(100, n))


def _clean_scores(raw) -> dict:
    """Reaction.scores 를 5축 전부 채운 정수 dict 로 보정.

    - 누락 축은 DEFAULT_SCORE(50) 로 채움.
    - 알 수 없는 값은 무시(SCORE_KEYS 만 추림).
    """
    src = _as_dict(raw)
    return {k: _to_int_score(src.get(k, DEFAULT_SCORE)) for k in SCORE_KEYS}




# ----------------------------------------------------------------------
# metrics 계산: sim 에 metrics 가 없으면 reactions 의 scores 로 직접 집계
# ----------------------------------------------------------------------
def _compute_metrics(reactions: list) -> dict:
    """reactions(보정된 scores 포함)에서 집계 지표를 계산.

    반환 키
        understanding/benefit/intent/dissatisfaction/shareability : 축별 평균(0~100)
        정책수용도   : (이해도 + 수혜 + 신청의향)/3 - 불만도 보정 → 대략 0~100
        사회혼란도   : 반발 강도 = 시민 불만 평균
        신청의향지수 : 신청의향 평균
        n            : 집계에 쓰인 반응 수
    """
    n = len(reactions)
    if n == 0:
        # 빈 경우에도 키는 다 채워 UI 가 깨지지 않게.
        base = {k: 0 for k in SCORE_KEYS}
        base.update({
            "정책수용도": 0,
            "사회혼란도": 0,
            "신청의향지수": 0,
            "n": 0,
        })
        return base

    # 축별 합산 → 평균
    sums = {k: 0 for k in SCORE_KEYS}
    for r in reactions:
        sc = _as_dict(r).get("scores", {})
        for k in SCORE_KEYS:
            sums[k] += _to_int_score(sc.get(k, DEFAULT_SCORE))
    avg = {k: round(sums[k] / n, 1) for k in SCORE_KEYS}

    # 정책수용도: 긍정 3축 평균에서 불만도를 일부 차감(0~100 클램프).
    accept = (avg["understanding"] + avg["benefit"] + avg["intent"]) / 3.0
    accept = accept - 0.3 * avg["dissatisfaction"]
    accept = max(0.0, min(100.0, accept))

    # 사회혼란도: 반발 강도 = 시민 불만 평균(공통 공식). real/demo/fallback 동일.
    from metrics_common import social_unrest as _social_unrest
    unrest_val = _social_unrest(reactions)

    metrics = dict(avg)
    metrics.update({
        "정책수용도": round(accept, 1),
        "사회혼란도": round(unrest_val, 1),
        "신청의향지수": round(avg["intent"], 1),
        "n": n,
    })
    return metrics


# 집계노드(graph.nodes._compute_metrics)는 핵심 3지표를 영문 키로 낸다.
# 게이지/대시보드는 한글 키를 읽으므로 영문 → 한글 표시 키로 매핑한다.
_METRIC_ALIASES = {
    "정책수용도": "policy_acceptance",
    "사회혼란도": "social_unrest",
    "신청의향지수": "application_index",
}


def _merge_metrics(sim_metrics, reactions: list) -> dict:
    """sim 에 들어온 metrics 를 존중하되, 빠진 표준 키는 계산값으로 보강.

    실모드 집계노드(graph.nodes)는 핵심 3지표를 영문 키(policy_acceptance/
    social_unrest/application_index)로 낸다. 게이지는 한글 키를 읽으므로, 한글 키가
    직접 주어지지 않았을 때 영문 값을 매핑해 게이지가 '단순 평균 재계산본'이 아니라
    '집계노드의 정교한 지표'를 보게 한다. (mock/데모는 한글 키를 직접 주므로 우선됨.)
    """
    computed = _compute_metrics(reactions)
    given = _as_dict(sim_metrics)
    # 계산값을 바닥에 깔고, 주어진 값으로 덮어쓴다(주어진 값 우선).
    merged = dict(computed)
    for k, v in given.items():
        merged[k] = v
    # 영문 키 → 표시용 한글 키 매핑(한글 키가 직접 주어졌으면 그것을 우선).
    for kr, en in _METRIC_ALIASES.items():
        if kr not in given and en in merged:
            merged[kr] = merged[en]
    return merged


# ----------------------------------------------------------------------
# 공개 API
# ----------------------------------------------------------------------
def build_view(sim) -> dict:
    """SimState(dict)를 UI ViewModel(dict)로 변환한다.

    sim 이 dict 가 아니거나 None 이어도(방어적으로) 빈 ViewModel 을 돌려준다.
    """
    s = _as_dict(sim)

    # --- 원본 필드 추출(전부 관대하게) ---
    policy = str(s.get("policy", "") or "")
    personas = _as_list(s.get("personas"))
    raw_reactions = _as_list(s.get("reactions"))
    interactions = _as_list(s.get("interactions"))
    edges = _as_list(s.get("edges"))
    summary = str(s.get("summary", "") or "")
    improvements = _as_dict(s.get("improvements"))

    # --- reactions 정규화: scores 5축을 항상 채운 사본을 만든다 ---
    reactions: list = []
    reactions_by_id: dict = {}
    for r in raw_reactions:
        rd = _as_dict(r)
        if not rd:
            continue
        fixed = dict(rd)                      # 원본 훼손 없이 얕은 복사
        fixed["scores"] = _clean_scores(rd.get("scores"))
        # 누락 필드 최소 보정(카드 렌더 안전)
        fixed.setdefault("stance", "mixed")
        fixed.setdefault("text", "")
        fixed.setdefault("evidence", _as_list(rd.get("evidence")))
        fixed.setdefault("actions", _as_list(rd.get("actions")))
        fixed.setdefault("grounded", bool(rd.get("grounded", True)))
        pid = str(rd.get("persona_id", "") or "")
        fixed["persona_id"] = pid
        reactions.append(fixed)
        if pid:
            reactions_by_id[pid] = fixed

    # --- improvements 표준 키 보정 ---
    norm_improvements = {
        "easy_text": str(improvements.get("easy_text", "") or ""),
        "policy_fixes": _as_list(improvements.get("policy_fixes")),
    }
    # 혹시 다른 키가 더 있으면 보존(추가 정보 손실 방지)
    for k, v in improvements.items():
        if k not in norm_improvements:
            norm_improvements[k] = v

    # --- metrics: 있으면 존중 + 빠진 표준키 보강, 없으면 reactions 로 계산 ---
    metrics = _merge_metrics(s.get("metrics"), reactions)

    # --- village(미리 마을): 있으면 그대로 통과(없으면 빈 dict) ---
    village = _as_dict(s.get("village"))

    # --- 정책 인생극장(DESIGN v3): 대조 3명 선별 결과 + 정책 패키지(있으면 통과) ---
    selection = _as_dict(s.get("selection"))
    policies = _as_list(s.get("policies"))

    # --- 정책 태그(사이드바 직접 지정 명세): 있으면 그대로 통과 ---
    policy_spec = _as_dict(s.get("policy_spec"))

    return {
        "policy": policy,
        "personas": personas,
        "reactions": reactions,
        "reactions_by_id": reactions_by_id,
        "interactions": interactions,
        "edges": edges,
        "summary": summary,
        "metrics": metrics,
        "improvements": norm_improvements,
        "village": village,
        "selection": selection,
        "policies": policies,
        "policy_spec": policy_spec,
    }
