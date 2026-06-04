# -*- coding: utf-8 -*-
"""신청 여정 분석 + 정책 개선(AS) 미리보기 — streamlit 서버 없이 브라우저로 본다.

순수 HTML 빌더(tab_dashboard/_card_html)를 그대로 호출해 한 페이지로 합쳐 저장한다.
AppTest 가 못 보는 색감·레이아웃을 브라우저로 눈으로 확인하는 용도(메모리 패턴).

실행: python _preview_access.py  → _preview_access.html 생성(브라우저로 열기).
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ui.mock import sample_simstate
from ui.model import build_view
import access_analysis as AA
from ui.tab_dashboard import _funnel_html, _age_access_html, _barriers_html
from ui.tab_improve import _card_html


def _bullets(items):
    lis = "".join(f"<li>{i}</li>" for i in items)
    return f"<ul style='margin:6px 0 0 0;padding-left:20px;line-height:1.7;'>{lis}</ul>"


def main():
    sim = sample_simstate(n=12)
    view = build_view(sim)
    # 데모 흐름과 동일하게 청년월세 spec 주입(자격 게이트 작동)
    view["policy_spec"] = {
        "name": "청년 월세 한시 특별지원", "age": (19, 34),
        "income": ("low", "mid"), "family_kw": None, "channel": "online_portal",
    }

    a = AA.analyze(view)
    fixes = (view.get("improvements") or {}).get("policy_fixes") or []

    # 요약 카드 3개 (개선폭은 A/B 실행 후 채워지므로 예시 표기)
    cards = (
        "<div style='display:flex;gap:12px;'>"
        + "<div style='flex:1;'>" + _card_html("주요 병목", a["main_bottleneck"] or "없음", "#C0392B") + "</div>"
        + "<div style='flex:1;'>" + _card_html("도움창구 개선폭", "+20.9%p", "#27AE60", "수정안 신청의향 변화") + "</div>"
        + "<div style='flex:1;'>" + _card_html("우선 지원 시민", f"{a['priority']['count']}명", "#2D7DD2",
                                               f"접근 가능성 {a['priority']['threshold_pct']}% 미만") + "</div>"
        + "</div>"
    )

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>미리랩 미리보기 — 신청 여정 + 정책 개선(AS)</title>
<style>
  body {{ font-family:-apple-system,'Malgun Gothic',sans-serif; color:#2C3E50;
         background:#fff; max-width:980px; margin:24px auto; padding:0 16px; }}
  h2 {{ border-bottom:2px solid #ECEFF1; padding-bottom:6px; margin-top:34px; }}
  h3 {{ margin:18px 0 6px; }}
  .grid {{ display:flex; gap:18px; }}
  .col-l {{ flex:3; }} .col-r {{ flex:2; }}
  .muted {{ color:#7A8794; font-size:0.85rem; }}
</style></head><body>
<h1>미리랩 미리보기</h1>
<p class='muted'>mock 12명 + 청년 월세 spec 기준. 실제 데이터로 계산한 값이며, 퍼널/병목은 시민 반응 추정.</p>

<h2>정책 개선 (AS)</h2>
{cards}
<h3>정책 문구·절차 수정</h3>
{_bullets(fixes)}
<h3>도움창구 운영 제안</h3>
{_bullets(a['helpdesk'])}

<h2>시민 반응 — 신청 여정 분석</h2>
<p class='muted'>시민들이 매긴 반응으로 추정한 신청 여정입니다. 실제 응답 시민 수가 기준이라 인원이 적게 보일 수 있어요.</p>
<div class='grid'>
  <div class='col-l'>
    <h3>신청 단계별 병목 퍼널</h3>
    {_funnel_html(a['funnel'])}
  </div>
  <div class='col-r'>
    <h3>연령대별 정책 접근성</h3>
    {_age_access_html(a['age_access'])}
    <h3 style='margin-top:18px;'>병목 요인 TOP 3</h3>
    {_barriers_html(a['barriers'])}
  </div>
</div>
</body></html>"""

    out = "_preview_access.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"생성: {out}")
    print(f"  주요 병목 = {a['main_bottleneck']}, 우선 지원 = {a['priority']['count']}명")
    print(f"  퍼널 = {[s['count'] for s in a['funnel']['stages']]} (base {a['funnel']['base_n']})")
    print(f"  연령 접근성 = {[(r['band'], r['pct']) for r in a['age_access']]}")
    print(f"  병목 = {[(b['label'], b['count']) for b in a['barriers']]}")


if __name__ == "__main__":
    main()
