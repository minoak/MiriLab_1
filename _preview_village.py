# -*- coding: utf-8 -*-
"""정책 인생극장 카드 미리보기 생성기 (브라우저 확인용, 키 불필요·LLM 0).

AppTest 는 unsafe_allow_html 의 시각(칩·색·콜아웃)을 못 보여준다. 이 스크립트는
ui.tab_village 의 *순수 HTML 빌더*(앱과 동일 코드)를 그대로 호출해 대조 3명의
카드(앞면 + 펼친 본문)를 한 장의 _preview_village.html 로 굽는다 → 브라우저로 확인.

실행:  python _preview_village.py   (프로젝트 루트에서)
"""
import io
import sys
from html import escape

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from data.personas import load_personas
from sample_policies import SAMPLES
from contrast import run_contrast
from ui.mock import sample_village
from graph.spaces import place_label
from ui.tab_village import (
    _events, _status_meta,
    _cover_card_html, _journey_strip_html, _outcome_callout_html,
    outcome_distribution, _distribution_bar_html, _distribution_legend_html,
)

POLICY = "청년 월세 한시 특별지원"   # 청년=수혜 / 중장년=경계 / 고령=사각 으로 갈림


def mock_sim(personas, policy_text, step_labels):
    return sample_village(personas, policy_text, step_labels=step_labels)


def _event_detail_html(events: list) -> str:
    """사건별 산문 HTML(미리보기용 — 앱의 _render_event_detail 과 같은 구조)."""
    parts = []
    seen = None
    for ev in events:
        emoji, label, color = _status_meta(ev["status"])
        steps = ev["steps"]
        place = place_label((steps[0] or {}).get("place", "home"))
        t0 = (steps[0] or {}).get("label", "")
        t1 = (steps[-1] or {}).get("label", "")
        when = t0 if t0 == t1 else f"{t0} ~ {t1}"
        parts.append(
            f"<div style='margin:12px 0 4px;'>"
            f"<span style='background:{color};color:#fff;padding:2px 11px;"
            f"border-radius:10px;font-size:0.82rem;font-weight:bold;'>{emoji} {label}</span>"
            f"<span style='color:#555;font-size:0.85rem;'> · {place}</span>"
            f"<span style='color:#aaa;font-size:0.74rem;'> {when}</span></div>"
        )
        via = ((steps[0] or {}).get("reached_via") or "").strip()
        if via:
            parts.append(
                f"<div style='color:#2980B9;font-size:0.8rem;margin:1px 0 3px;'>"
                f"↳ 경로 · {escape(via)}</div>"
            )
        if ev["status"] == "blocked":
            barrier = next(
                (s["barrier"].strip() for s in steps if (s.get("barrier") or "").strip()), "",
            )
            if barrier:
                parts.append(
                    f"<div style='color:#E74C3C;font-size:0.8rem;margin:1px 0 3px;'>"
                    f"⛔ 막힌 지점 · {escape(barrier)}</div>"
                )
        for step in steps:
            act = (step.get("action") or "").strip()
            if act and act != seen:
                parts.append(f"<p style='margin:2px 0;'>{escape(act)}</p>")
                seen = act
    return "".join(parts)


def _card_html(t: dict, resident: dict, quote: str = "") -> str:
    """카드 1장(커버 + 펼친 본문) — 앱과 동일한 카드뉴스 커버 빌더를 그대로 사용."""
    events = _events((resident or {}).get("timeline") or [])

    cover = _cover_card_html(t, resident, quote)   # 앱 공용 빌더(스타일 단일 진실원)
    body = (
        "<div style='background:#fff;border:1px solid #E8ECEF;border-radius:12px;"
        "padding:12px 16px;margin:-4px 0 20px;'>"
        "<b>🧭 접근 여정</b>"
        + _journey_strip_html(events)
        + _outcome_callout_html(events)
        + "<hr style='border:none;border-top:1px solid #eee;margin:10px 0;'>"
        + _event_detail_html(events)
        + "</div>"
    )
    return cover + body


def main():
    personas = load_personas(n=8, seed=42)
    res = run_contrast(personas, [SAMPLES[POLICY]], specs=None,
                       simulate=mock_sim, use_llm_spec=False)
    trio = res["selection"]["trio"]
    residents = {r.get("id"): r for r in res["village"]["residents"]}

    # 전체 풀 결과 분포(대표성 숫자) — 카드 위 헤드라인 층
    outcomes = res["selection"].get("outcomes") or []
    dist = outcome_distribution(outcomes)
    total = sum(d["count"] for d in dist)
    dist_block = (
        f"<h4>📈 전체 {total}명에게 이 정책이 어떻게 닿나</h4>"
        + _distribution_bar_html(dist, total)
        + _distribution_legend_html(dist)
        + "<div class='sub'>아래는 카테고리별 대표 + 같은 처지의 나머지 시민입니다.</div>"
    ) if total else ""

    # 카테고리별 그룹(대표 + 하위 전원). 정적 HTML 이라 전부 펼쳐 쌓는다.
    groups = res["selection"].get("groups") or {}
    GORDER = [("beneficiary", "🟢 수혜", "#27AE60"),
              ("borderline", "🟠 경계", "#F39C12"),
              ("blindspot", "🔴 사각지대", "#E74C3C")]
    sections = []
    for rk, label, color in GORDER:
        entries = groups.get(rk) or []
        if not entries:
            continue
        sections.append(
            f"<h3 style='color:{color};border-left:5px solid {color};"
            f"padding-left:10px;margin-top:24px;'>{label} — {len(entries)}명</h3>"
        )
        # 대표(첫 카드)에만 샘플 '한 마디'를 넣어 인용 타이포까지 확인한다
        # (mock 시뮬엔 reactions 가 없어 실제 인용은 앱에서만 보임).
        sections.append("".join(
            _card_html(
                e, residents.get((e.get("persona") or {}).get("id")),
                quote=("신청 방법이 복잡하면 저 같은 사람은 그냥 포기하게 돼요"
                       if i == 0 else ""),
            )
            for i, e in enumerate(entries)
        ))
    cards = "".join(sections)
    notes = "".join(f"<li>{escape(n)}</li>" for n in res["selection"].get("notes") or [])

    page = (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>정책 인생극장 — 카드 미리보기</title>"
        "<style>body{font-family:'Malgun Gothic',sans-serif;max-width:760px;"
        "margin:24px auto;padding:0 16px;color:#222;background:#fafafa;}"
        "h2{margin-bottom:2px;} .sub{color:#777;font-size:0.9rem;margin-bottom:8px;}</style>"
        "</head><body>"
        f"<h2>정책 인생극장 — 같은 정책, 다른 인생</h2>"
        f"<div class='sub'>정책: <b>{escape(POLICY)}</b> · mock 시뮬(키 불필요) · "
        "카드뉴스 스타일 커버(그라데이션·아바타·한 마디) + 접근 여정·결론 콜아웃 미리보기</div>"
        f"{dist_block}"
        f"{cards}"
        f"<h4>📊 정직한 노트</h4><ul>{notes}</ul>"
        "</body></html>"
    )
    with open("_preview_village.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("OK — _preview_village.html 생성")
    print("선별 3명:", [(t["role"], (t["persona"] or {}).get("name")) for t in trio])


if __name__ == "__main__":
    main()
