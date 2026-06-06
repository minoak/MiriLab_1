# -*- coding: utf-8 -*-
"""report.py — 정책 개선 종합 리포트 (두 축 + 개선안을 고정 양식으로).

'정책 개선' 탭의 A/B 검증을 대체하는 산출물. 시민반응축(SNS 반응·지표·퍼널)과
인생극장축(접근 여정 결과)을 **처음으로 한 군데에 종합**해, 입안자가 들고 갈 수 있는
한 장의 마크다운 리포트를 만든다.

설계 원칙(프로젝트 일관 철학 — "판단=LLM, 숫자·경로=결정론"):
- 숫자·인용·명단·분포는 전부 **결정론 코드**가 채운다(collect_report_data).
- LLM 은 정해진 4칸(한 줄 진단 / 진단 해석 / 개선 제안 / 수정안)의 산문만 쓴다.
  키가 없거나 호출이 실패하면 결정론 폴백 문구로 채워 **데모에서도 항상 완성된
  리포트**가 나온다(발표 안전망).
- 순수 모듈: streamlit 무의존, import 시 네트워크 0 (LLM 은 generate_report 실행
  시에만 지연 import). 같은 view + 폴백 모드면 같은 출력(결정론, 날짜 제외).

공개 API:
    collect_report_data(view) -> dict            # 결정론 수집(단독 테스트 가능)
    compose_report(data, sections) -> str        # 고정 양식 markdown 조립(순수)
    fallback_sections(data) -> dict              # LLM 없이 채우는 4칸(순수)
    generate_report(view, use_llm=True) -> dict  # {"markdown", "mode", "data"}
"""
from __future__ import annotations

import datetime
import json

import access_analysis as access
from policy_spec import tag_line


# 인생극장 결과 분포의 표시 순서/라벨 (contrast._resident_outcome dist_key 와 일치)
_DIST_LABELS = [
    ("received", "수혜"),
    ("inprogress", "진행 중"),
    ("blocked", "막힘"),
    ("unaware", "못 닿음"),
    ("out", "대상 아님"),
]

# 입장(stance) 표시 순서/라벨
_STANCE_LABELS = [("support", "찬성"), ("mixed", "혼합"), ("oppose", "반대")]

# 리포트에 인용할 시민 목소리 수 / 우선 지원 명단 표시 수
_MAX_QUOTES = 3
_MAX_PRIORITY_NAMES = 4


# ─────────────────────────────────────────────────────────────────────────
# 작은 헬퍼 (순수)
# ─────────────────────────────────────────────────────────────────────────
def _num(x, default=0.0) -> float:
    """안전 float 변환."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _score(reaction: dict, key: str, default: float = 50.0) -> float:
    """반응의 5축 점수 1개를 안전 추출."""
    return _num(((reaction or {}).get("scores") or {}).get(key, default), default)


def _policy_title(view: dict) -> str:
    """리포트 제목용 정책명: spec.name → 원문 첫 줄(30자) → '정책'."""
    spec = view.get("policy_spec") or {}
    name = str(spec.get("name") or "").strip()
    if name:
        return name
    text = str(view.get("policy") or "").strip()
    if text:
        return text.splitlines()[0][:30]
    return "정책"


def _stance_counts(reactions: list) -> dict:
    """입장 분포 {'support':n,'mixed':n,'oppose':n} (알 수 없는 입장은 혼합)."""
    counts = {key: 0 for key, _ in _STANCE_LABELS}
    for r in reactions or []:
        s = str((r or {}).get("stance", "")).strip().lower()
        counts[s if s in counts else "mixed"] += 1
    return counts


def _flat_text(x, limit: int = 160) -> str:
    """개행·연속 공백을 한 칸으로 접어 마크다운 구조 주입(##·> 줄바꿈)을 막는다."""
    return " ".join(str(x or "").split())[:limit]


def _stance_of(r: dict) -> str:
    """stance 를 정규화해 읽는다(_stance_counts 와 같은 기준 — 비대칭 방지)."""
    return str((r or {}).get("stance", "")).strip().lower()


def _pick_quotes(personas: list, reactions: list, k: int = _MAX_QUOTES) -> list:
    """대표 시민 목소리 최대 k개를 결정론적으로 고른다.

    찬성(수혜 체감 최고) 1 + 반대(불만 최고) 1 + 혼합·중립(이해도 최저) 1.
    각 항목: {name, age, stance, text}. 반응문이 빈 시민은 제외.
    """
    by_id = {p.get("id"): p for p in (personas or [])}

    def _entry(r: dict) -> dict:
        p = by_id.get(r.get("persona_id")) or {}
        demo = p.get("demographics") or {}
        return {
            "name": str(p.get("name") or r.get("persona_id") or "시민"),
            "age": demo.get("age"),
            "stance": _stance_of(r) or "mixed",
            "text": _flat_text(r.get("text")),
        }

    rs = [r for r in (reactions or []) if str((r or {}).get("text") or "").strip()]
    sup = [r for r in rs if _stance_of(r) == "support"]
    opp = [r for r in rs if _stance_of(r) == "oppose"]
    mix = [r for r in rs if _stance_of(r) not in ("support", "oppose")]

    quotes = []
    if sup:
        quotes.append(_entry(max(sup, key=lambda r: _score(r, "benefit"))))
    if opp:
        quotes.append(_entry(max(opp, key=lambda r: _score(r, "dissatisfaction"))))
    if mix:
        quotes.append(_entry(min(mix, key=lambda r: _score(r, "understanding"))))
    return quotes[:k]


def theater_is_current(view: dict) -> bool:
    """인생극장 결과가 *사이드바 단일 정책*의 것인지 출처를 판정한다.

    단일 실행(tab_village._render_runner)은 view["policies"]=[원문] 을 기록하고,
    패키지 데모(여러 정책)는 정책명 리스트를 기록한다 — 후자의 결과를 단일 정책
    리포트에 섞으면 안 되므로 게이트한다. 출처 기록이 없으면(구버전) 관대하게 True.
    """
    pols = view.get("policies") or []
    if not pols:
        return True
    cur = str(view.get("policy") or "").strip()
    return len(pols) == 1 and str(pols[0] or "").strip() == cur


def theater_data(view: dict):
    """인생극장 결과 요약. 미실행/출처 불일치(패키지 데모 결과)면 None.

    {n, dist:{received..out:n}, cases:[{role,name,age,headline,barrier,reached_via}],
     notes:[str]} — 전부 시뮬 *결과*에서 결정론 추출(contrast 의 산출물 재사용).
    리포트 3절과 '정책 사각지대' 카드(ui/tab_improve)가 같은 함수를 쓴다(단일 진실원).
    """
    if not isinstance(view, dict):
        return None
    sel = view.get("selection") or {}
    outcomes = sel.get("outcomes") or []
    if not outcomes or not theater_is_current(view):
        return None

    dist = {key: 0 for key, _ in _DIST_LABELS}
    for row in outcomes:
        key = (row or {}).get("dist_key")
        if key in dist:
            dist[key] += 1

    # 사례 = 대표(trio) 중 수혜·사각 — 라벨과 이야기가 같은 데서 나온 결과 기반 선별.
    cases = []
    for t in sel.get("trio") or []:
        if t.get("role_key") not in ("beneficiary", "blindspot"):
            continue
        persona = t.get("persona") or {}
        demo = persona.get("demographics") or {}
        score = t.get("score") or {}
        cases.append({
            "role": str(t.get("role") or ""),
            "name": str(persona.get("name") or persona.get("id") or "시민"),
            "age": demo.get("age"),
            "headline": str(t.get("headline") or ""),
            "barrier": str(score.get("barrier") or ""),
            "reached_via": str(score.get("reached_via") or ""),
        })

    notes = [str(x) for x in (sel.get("notes") or [])]
    return {"n": len(outcomes), "dist": dist, "cases": cases, "notes": notes}


# ─────────────────────────────────────────────────────────────────────────
# 1) 결정론 수집 — 두 축 + 개선안 재료를 한 dict 로
# ─────────────────────────────────────────────────────────────────────────
def collect_report_data(view) -> dict:
    """ViewModel(view)에서 리포트 재료 일체를 결정론으로 수집한다(LLM 0).

    view 가 비어 있어도 죽지 않고 빈 구조를 돌려준다(ui.model.build_view 와 같은 관대함).
    """
    if not isinstance(view, dict):
        view = {}
    personas = view.get("personas") or []
    reactions = view.get("reactions") or []
    metrics = view.get("metrics") or {}
    improvements = view.get("improvements") or {}

    analysis = access.analyze(view)

    return {
        "title": _policy_title(view),
        "date": datetime.date.today().isoformat(),
        "n": len(personas),
        "tags": tag_line(view.get("policy_spec") or {}),
        "policy_text": str(view.get("policy") or "").strip(),
        "metrics": {
            "정책수용도": round(_num(metrics.get("정책수용도")), 1),
            "신청의향지수": round(_num(metrics.get("신청의향지수")), 1),
            "사회혼란도": round(_num(metrics.get("사회혼란도")), 1),
        },
        "stance": _stance_counts(reactions),
        "funnel": analysis.get("funnel") or {},
        "barriers": analysis.get("barriers") or [],
        "main_bottleneck": analysis.get("main_bottleneck") or "",
        "priority": analysis.get("priority") or {},
        "helpdesk": analysis.get("helpdesk") or [],
        "quotes": _pick_quotes(personas, reactions),
        "theater": theater_data(view),
        # 인생극장 결과가 있긴 한데 다른 정책(패키지 데모)의 것이라 제외했는가(정직 노트용).
        "theater_foreign": bool((view.get("selection") or {}).get("outcomes"))
                           and not theater_is_current(view),
        "summary": str(view.get("summary") or "").strip(),
        "policy_fixes": [str(f).strip() for f in (improvements.get("policy_fixes") or [])
                         if str(f).strip()],
        "easy_text": str(improvements.get("easy_text") or "").strip(),
    }


# ─────────────────────────────────────────────────────────────────────────
# 2) LLM 4칸 — 한 줄 진단 / 진단 해석 / 개선 제안 / 수정안 (+ 결정론 폴백)
# ─────────────────────────────────────────────────────────────────────────
def fallback_sections(data: dict) -> dict:
    """LLM 없이 4칸을 채우는 결정론 폴백(데모·키 없음·호출 실패 공용)."""
    m = data.get("metrics") or {}
    bottleneck = data.get("main_bottleneck") or "뚜렷하지 않음"
    headline = (
        f"정책수용도 {m.get('정책수용도', 0)} · 신청의향 {m.get('신청의향지수', 0)} · "
        f"사회혼란도 {m.get('사회혼란도', 0)} — 주요 병목은 '{bottleneck}'입니다."
    )

    # 진단 해석: 퍼널 최대 이탈 단계 + 감지된 장벽 나열(전부 수집된 사실만).
    stages = (data.get("funnel") or {}).get("stages") or []
    drops = [s for s in stages if s.get("drop", 0) > 0]
    parts = []
    if drops:
        worst = max(drops, key=lambda s: s.get("drop", 0))
        parts.append(
            f"신청 여정에서 가장 큰 이탈은 '{worst.get('label')}' 단계"
            f"({worst.get('drop')}명, {worst.get('drop_label') or '이탈'})입니다."
        )
    barriers = data.get("barriers") or []
    if barriers:
        parts.append("감지된 장벽: " + ", ".join(
            f"{b.get('label')}({b.get('count')}명)" for b in barriers[:3]) + ".")
    theater = data.get("theater")
    if theater:
        dist = theater.get("dist") or {}
        miss = dist.get("blocked", 0) + dist.get("unaware", 0)
        if miss:
            parts.append(f"인생극장에서는 대상자 중 {miss}명이 막히거나 끝내 닿지 못했습니다.")
    diagnosis = " ".join(parts) or "표본에서 두드러진 병목이 발견되지 않았습니다."

    # 도움창구 제안은 4절 하단에 따로 실리므로 여기 재사용하지 않는다(중복 방지).
    proposals = list(data.get("policy_fixes") or [])

    revised = data.get("easy_text") or (
        "(수정안이 아직 없습니다 — 시뮬레이션을 실행하면 AI 수정안이 채워집니다.)"
    )
    return {
        "headline": headline,
        "diagnosis": diagnosis,
        "proposals": proposals,
        "revised_policy": revised,
    }


def _llm_sections(data: dict) -> dict:
    """LLM 으로 4칸을 채운다(구조화 출력). 호출측에서 예외를 폴백으로 처리한다."""
    from pydantic import BaseModel, Field  # 지연 import(키 없어도 모듈 import 가능)

    class ReportSections(BaseModel):
        """리포트의 LLM 작성 칸 4개. 숫자·고유명사는 입력 데이터에 있는 것만 사용."""
        headline: str = Field(description="한 줄 진단(80자 이내, 핵심 지표와 병목을 한 문장으로)")
        diagnosis: str = Field(description="진단 해석 2~4문장(병목이 왜 생기는지, 두 축 근거 인용)")
        proposals: list[str] = Field(description="개선 제안 3~6개(각 한 문장, 구체적 실행 단위)")
        revised_policy: str = Field(description="개선안을 반영해 다시 쓴 정책 수정안 전문(공고문 어투)")

    # LLM 에 주는 재료 = 수집된 사실 전부(숫자·인용·사례·기존 개선안).
    payload = {k: data.get(k) for k in (
        "title", "n", "metrics", "stance", "funnel", "barriers", "priority",
        "quotes", "theater", "summary", "policy_fixes", "easy_text",
    )}
    system = (
        "당신은 정책 시뮬레이션 결과를 입안자용 보고서로 정리하는 분석가입니다. "
        "반드시 지킬 것: (1) 아래 데이터에 있는 사실·숫자·이름만 사용하고 새로 지어내지 않는다. "
        "(2) 시민 이름은 데이터에 등장하는 이름만 쓴다. "
        "(3) 수치를 새로 계산하거나 바꾸지 않는다(해석만 한다). 백분율·비율(% 포함)은 "
        "한 번도 쓰지 말고, 데이터에 있는 인원수만 'N명' 형태로 그대로 인용한다. "
        "(4) 지표(정책수용도 등)는 0~100 지수이지 퍼센트가 아니다 — '%'를 붙이지 않는다. "
        "(5) 단정 대신 시뮬레이션 결과임을 전제로 쓴다."
    )
    user = (
        "[정책 원문]\n" + (data.get("policy_text") or "(없음)")[:2000] + "\n\n"
        "[시뮬레이션 데이터(JSON)]\n" + json.dumps(payload, ensure_ascii=False) + "\n\n"
        "위 데이터로 보고서의 4칸을 작성하세요.\n"
        "1) headline: 한 줄 진단.\n"
        "2) diagnosis: 진단 해석 — 퍼널·장벽(시민반응축)과 접근 여정 사례(인생극장축)를 "
        "근거로 병목의 원인을 설명. 인생극장 데이터(theater)가 null 이면 시민반응축만으로.\n"
        "3) proposals: 기존 개선안(policy_fixes)을 두 축 근거로 보강·구체화한 개선 제안 목록.\n"
        "4) revised_policy: easy_text 를 바탕으로 개선 제안을 반영해 다시 쓴 수정안 전문. "
        "easy_text 가 비어 있으면 정책 원문을 바탕으로 작성."
    )
    out = _llm_call_sections(ReportSections, system, user)
    return {
        "headline": (out.headline or "").strip(),
        "diagnosis": (out.diagnosis or "").strip(),
        "proposals": [p.strip() for p in (out.proposals or []) if p and p.strip()],
        "revised_policy": (out.revised_policy or "").strip(),
    }


def _llm_call_sections(schema, system: str, user: str):
    """structured_call 한 번(테스트에서 monkeypatch 하기 쉽게 분리)."""
    from graph.llm import structured_call

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    return structured_call(messages, schema, temperature=0.5)


# ─────────────────────────────────────────────────────────────────────────
# 3) 고정 양식 조립 (순수 markdown)
# ─────────────────────────────────────────────────────────────────────────
def _funnel_line(funnel: dict) -> str:
    """퍼널을 '응답 시민 12 → 정책 이해 8 → …' 화살표 한 줄로.

    첫 단계(key=target)는 '응답 시민'으로 바꿔 쓴다 — access_analysis 의 라벨
    '대상자'는 응답 전원이라, 3절(태그 기반 '대상 아님' n명)과 한 문서 안에서
    용어가 충돌하기 때문(표시만 교체, 원본 분석은 불변).
    """
    stages = (funnel or {}).get("stages") or []
    if not stages:
        return "데이터 없음"
    parts = []
    for s in stages:
        label = "응답 시민" if s.get("key") == "target" else s.get("label")
        parts.append(f"{label} {s.get('count')}명")
    return " → ".join(parts)


def _stance_line(stance: dict) -> str:
    return " · ".join(f"{label} {int((stance or {}).get(key, 0))}명"
                      for key, label in _STANCE_LABELS)


def _quote_lines(quotes: list) -> list:
    """시민 목소리 인용 블록(없으면 안내 한 줄)."""
    if not quotes:
        return ["- (인용할 시민 반응이 없습니다)"]
    stance_kr = dict(_STANCE_LABELS)
    lines = []
    for q in quotes:
        age = f"({q['age']}세)" if q.get("age") else ""
        label = stance_kr.get(q.get("stance"), "혼합")
        lines.append(f"> 💬 **{q['name']}{age}** [{label}] — “{q['text']}”")
    return lines


def _theater_block(theater, foreign: bool = False) -> list:
    """3절(접근 여정 사례) 본문 줄들. 미실행/출처 불일치면 안내문."""
    if not theater:
        if foreign:
            return [
                "> ⓘ 현재 인생극장 결과는 '여러 정책 함께 실험(패키지 데모)'의 것이라 "
                "이 리포트에는 싣지 않았습니다 — '정책 인생극장' 탭에서 사이드바 정책으로 "
                "다시 실행한 뒤 리포트를 재생성하세요.",
            ]
        return [
            "> ⓘ 정책 인생극장 미실행 — '정책 인생극장' 탭에서 실행하면 누가 어디서 "
            "막혔는지 접근 여정 사례가 여기에 추가됩니다.",
        ]
    dist = theater.get("dist") or {}
    dist_line = " · ".join(f"{label} {int(dist.get(key, 0))}명"
                           for key, label in _DIST_LABELS)
    lines = [f"- **결과 분포**: {dist_line}"]
    for c in theater.get("cases") or []:
        age = f"({c['age']}세)" if c.get("age") else ""
        detail = []
        if c.get("barrier"):
            detail.append(f"막힌 지점: {c['barrier']}")
        if c.get("reached_via"):
            detail.append(f"닿은 경로: {c['reached_via']}")
        tail = f" ({' / '.join(detail)})" if detail else ""
        lines.append(f"- **{c['role']} — {c['name']}{age}**: {c['headline']}{tail}")
    for note in theater.get("notes") or []:
        lines.append(f"- {note}")
    return lines


def compose_report(data: dict, sections: dict) -> str:
    """수집 데이터 + 4칸(sections)을 고정 양식 markdown 으로 조립한다(순수).

    양식은 사용자 합의로 고정: 1.요약 / 2.시민 반응 진단 / 3.접근 여정 사례 /
    4.개선 제안 / 5.수정안 전문 / 6.한계 노트. 칸의 위치·이름을 바꾸지 말 것.
    """
    data = data or {}
    sections = sections or {}
    m = data.get("metrics") or {}
    priority = data.get("priority") or {}

    head_meta = [data.get("date") or "", f"시뮬 코호트 {int(data.get('n') or 0)}명"]
    if data.get("tags"):
        head_meta.append(data["tags"])
    lines = [
        f"# 📋 정책 개선 리포트 — {data.get('title') or '정책'}",
        " · ".join(x for x in head_meta if x),
        "",
        "## 1. 요약",
        (f"- **핵심지표**: 정책수용도 {m.get('정책수용도', 0)} · "
         f"신청의향지수 {m.get('신청의향지수', 0)} · 사회혼란도 {m.get('사회혼란도', 0)}"),
        f"- **입장 분포**: {_stance_line(data.get('stance'))}",
        f"- **한 줄 진단**: {sections.get('headline') or '—'}",
        "",
        "## 2. 시민 반응 진단 (시민반응축)",
        f"- **신청 여정 퍼널(추정)**: {_funnel_line(data.get('funnel'))}",
    ]

    barriers = data.get("barriers") or []
    if barriers:
        top = " · ".join(f"{b.get('label')} {b.get('count')}명" for b in barriers[:3])
        lines.append(f"- **주요 병목**: {top}")
    else:
        lines.append("- **주요 병목**: 두드러진 장벽이 발견되지 않았습니다")

    lines.append("- **시민 목소리**")
    lines.extend(_quote_lines(data.get("quotes")))
    diagnosis = sections.get("diagnosis") or ""
    if diagnosis:
        lines.extend(["", diagnosis])

    lines.extend(["", "## 3. 접근 여정 사례 (인생극장축)"])
    lines.extend(_theater_block(data.get("theater"), bool(data.get("theater_foreign"))))

    lines.extend(["", "## 4. 개선 제안"])
    proposals = sections.get("proposals") or []
    if proposals:
        lines.extend(f"{i}. {p}" for i, p in enumerate(proposals, 1))
    else:
        lines.append("- (개선 제안이 아직 없습니다 — 시뮬레이션을 실행하면 "
                     "시민 반응 기반 제안이 채워집니다.)")
    helpdesk = data.get("helpdesk") or []
    if helpdesk:
        lines.append("")
        lines.append("**도움창구 운영 제안**")
        lines.extend(f"- {r}" for r in helpdesk)
    pri_count = int(priority.get("count") or 0)
    if pri_count:
        names = [str(x) for x in (priority.get("names") or [])]
        shown = ", ".join(names[:_MAX_PRIORITY_NAMES])
        more = f" 외 {len(names) - _MAX_PRIORITY_NAMES}명" if len(names) > _MAX_PRIORITY_NAMES else ""
        lines.append("")
        lines.append(
            f"**우선 지원 대상**: {pri_count}명 — 접근 가능성 "
            f"{priority.get('threshold_pct', 40)}% 미만 ({shown}{more})"
        )

    lines.extend([
        "",
        "## 5. 수정안 전문",
        sections.get("revised_policy") or "(수정안 없음)",
        "",
        "> ✏️ 이 수정안을 사이드바 '정책 입력'에 붙여 넣고 다시 실행하면, "
        "같은 시민들로 수정안을 재실험할 수 있습니다.",
        "",
        "## 6. 한계 노트",
        f"- 표본 {int(data.get('n') or 0)}명의 AI 시민 시뮬레이션 결과로, 실제 여론조사가 아닙니다.",
        "- LLM 응답의 비결정성으로 절대 수치는 실행마다 다소 변동합니다(방향성은 견고).",
        "- 신청 여정 퍼널·병목은 시민 반응과 페르소나 접근도에서 유도한 추정치입니다.",
    ])
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# 4) 공개 진입점
# ─────────────────────────────────────────────────────────────────────────
def generate_report(view, use_llm: bool = True) -> dict:
    """view 에서 리포트를 생성한다.

    Args:
        view: ui.model.build_view 결과(ViewModel dict).
        use_llm: True 면 키가 있을 때 LLM 으로 4칸을 채운다(1콜).
                 False / 키 없음 / 호출 실패 → 결정론 폴백(외부 호출 0).

    Returns:
        {"markdown": str, "mode": "llm"|"fallback", "llm_error": str|None,
         "data": collect_report_data 결과}
        llm_error 는 키가 있는데 LLM 호출이 실패해 폴백된 경우에만 채워진다
        (UI 가 '키 없으면 보강됩니다' 대신 정확한 실패 안내를 하도록).
    """
    data = collect_report_data(view)
    sections = fallback_sections(data)
    mode = "fallback"
    llm_error = None

    if use_llm:
        try:
            from graph.llm import has_real_key  # 지연 import

            if has_real_key():
                llm = _llm_sections(data)
                # 빈 칸은 폴백 유지(부분 실패에도 리포트는 항상 완성).
                sections.update({k: v for k, v in llm.items() if v})
                mode = "llm"
        except Exception as exc:  # 데모 안정성: 어떤 실패에도 리포트는 나온다.
            mode = "fallback"
            llm_error = f"{type(exc).__name__}: {exc}"

    return {"markdown": compose_report(data, sections), "mode": mode,
            "llm_error": llm_error, "data": data}
