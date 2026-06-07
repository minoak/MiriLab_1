# -*- coding: utf-8 -*-
"""대시보드 탭(= '시민 반응'): 정책 결과 종합(축3 단일 진실원) + 시민 반응 히트맵 표.

정책 결과 종합(v1.2 — 설계방향서 §1.6): 게이지 3종(t0 지표·전원 모수)부터 낙차·깔때기
(결과 지표·대상자 모수)까지 모든 숫자가 axis3 한 곳에서 나온다. 신청 여정 분석은
'사전 가설(t0 추정)' expander 로 강등 — 실측 깔때기와 같은 시각물이 병존하던 혼란 제거.

히트맵: 시민 전원을 표 한 장에 담아 스크롤 없이 훑는다.
  - 5축 점수를 valence 색으로 칠함 — 긍정 지표(이해도/살림 영향/신청의향/공유)=파랑,
    불만도=레드(높을수록 부정 신호). ※살림 영향은 양극(0 손해~50 무관~100 혜택)이라
    낮은 값=손해 신호인데 색은 '옅은 파랑'으로만 보임 — 양극 색상은 추후 다듬기 거리.
  - **행 클릭 → 그 행 바로 아래에 '한마디'(반응문+행동)가 인라인 토글**(클라이언트 JS,
    rerun 없음). 헤더 클릭 정렬. → st.dataframe 으로는 행 사이 삽입이 불가해
    `components.html` 커스텀 표로 구현(village_map 와 동일 방식).
  - stance 분포 바 + 입장 필터(전체/찬성/혼합/반대)는 Streamlit 네이티브 유지.

정보·구조는 그대로 두고 '보여주는 방식'만 카드 그리드 → 스캔형 표로 바꾼 것.
"""
import json
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import access_analysis as access
from viz import gauge, STYLE


# 5축 점수 키 → 표 컬럼 라벨 (state.Scores 정의 순서 고정)
# 표시 축(공유가능성은 2026-06-03 표시에서 제거 — 어떤 게이지에도 안 쓰여 valence 명료화).
# 데이터(state.Scores)에는 shareability 가 그대로 남아 있다(표시만 뺀 것).
_SCORE_COLS = [
    ("understanding", "이해도"),
    # benefit 은 설문 전환(2026-06-06)으로 양극 의미: 0 손해 ~ 50 무관 ~ 100 혜택.
    # 구 라벨 '수혜가능성'은 이익만 가정해 오독 유발 → '살림 영향'으로 교체.
    ("benefit", "살림 영향"),
    ("intent", "신청의향"),
    ("dissatisfaction", "불만도"),
]
_SCORE_LABELS = [label for _, label in _SCORE_COLS]
# 불만도만 '높을수록 부정' → 레드 스케일. 나머지는 '높을수록 긍정' → 블루 스케일.
_NEG_LABELS = {"불만도"}
# 기본 정렬 컬럼(스크린샷과 동일: 신청의향 내림차순). 점수 컬럼 인덱스로 환산.
_DEFAULT_SORT_IDX = _SCORE_LABELS.index("신청의향")

# stance 키 → (한글 라벨, 이모지 점)
_STANCE = {
    "support": ("찬성", "🟢"),
    "oppose": ("반대", "🔴"),
    "mixed": ("혼합", "🟡"),
}

# 일탈 행동(behavior_class) → (배지 라벨, 색). comply/inaction/''(미측정)은 배지 없음.
# 일탈 행동 축(DESIGN §9) — 시민을 따로 빼지 않고 같은 표에 배지로만 표시한다.
_BEHAVIOR_BADGE = {
    "workaround": ("틈새·편법", "#E67E22"),
    "exploit": ("부정수급 시도", "#C0392B"),
    "complain": ("민원·행동화", "#8E44AD"),
}

# 히트맵 셀 색 — (white → base) 보간용 풀강도 색
_BLUE_BASE = (31, 127, 196)   # 긍정 지표
_RED_BASE = (231, 76, 60)     # 불만도(부정)


# ─────────────────────────────────────────────────────────────────────────
# 표시용 헬퍼 (순수)
# ─────────────────────────────────────────────────────────────────────────
def _to_int(v) -> int:
    """점수 값을 0~100 정수로 보정(None/문자/범위 밖 방어)."""
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def _short_region(province, district) -> str:
    """'서울특별시'+'관악구' → '서울 관악' 처럼 접미사를 떼어 짧게."""
    p = str(province or "")
    for suf in ("특별자치도", "특별자치시", "특별시", "광역시", "자치도", "자치시", "도"):
        if p.endswith(suf):
            p = p[: -len(suf)]
            break
    d = str(district or "")
    for suf in ("구", "군", "시"):
        if d.endswith(suf) and len(d) > 1:
            d = d[: -len(suf)]
            break
    return (p + " " + d).strip()


def _demo_line(persona: dict) -> str:
    """'28·남·서울 관악' 형태의 짧은 프로필 줄. 데모 없으면 description 폴백."""
    d = persona.get("demographics") or {}
    parts = []
    age = d.get("age")
    if age not in (None, "", []):
        parts.append(str(age))
    sex = d.get("sex")
    if sex:
        parts.append({"남성": "남", "여성": "여"}.get(sex, str(sex)))
    region = _short_region(d.get("province"), d.get("district"))
    if region:
        parts.append(region)
    line = "·".join(parts)
    return line or (persona.get("description") or "")


# ─────────────────────────────────────────────────────────────────────────
# 표 빌더 (순수 — streamlit 무의존, 테스트 용이)
# ─────────────────────────────────────────────────────────────────────────
def build_reaction_table(personas: list, reactions_by_id: dict):
    """페르소나+반응 → (DataFrame, counts).

    DataFrame 컬럼: _pid, _stance, 시민, 프로필, 입장, 이해도, 살림 영향, 신청의향,
                   불만도, 공유가능성. (_pid/_stance 는 내부용 — 표시 전 drop)
    counts: {'support','oppose','mixed','total'} 개수.
    반응이 없는 페르소나는 건너뛴다.
    """
    personas = personas or []
    reactions_by_id = reactions_by_id or {}
    rows = []
    counts = {"support": 0, "oppose": 0, "mixed": 0, "total": 0}

    for p in personas:
        pid = p.get("id")
        r = reactions_by_id.get(pid)
        if not r:
            continue
        stance = r.get("stance", "mixed")
        if stance not in _STANCE:
            stance = "mixed"
        label, emoji = _STANCE[stance]
        counts[stance] = counts.get(stance, 0) + 1
        counts["total"] += 1

        sc = r.get("scores") or {}
        row = {
            "_pid": pid,
            "_stance": stance,
            "시민": p.get("name") or "(이름 미상)",
            "프로필": _demo_line(p),
            "입장": f"{emoji} {label}",
        }
        for key, col in _SCORE_COLS:
            row[col] = _to_int(sc.get(key, 0))
        rows.append(row)

    columns = ["_pid", "_stance", "시민", "프로필", "입장"] + _SCORE_LABELS
    df = pd.DataFrame(rows, columns=columns)
    return df, counts


def _cell_css(val, neg: bool) -> str:
    """점수값(0~100)을 white→base 보간 배경색 + 가독 글자색 CSS 로."""
    t = _to_int(val) / 100.0
    base = _RED_BASE if neg else _BLUE_BASE
    r = int(round(255 + (base[0] - 255) * t))
    g = int(round(255 + (base[1] - 255) * t))
    b = int(round(255 + (base[2] - 255) * t))
    fg = "#ffffff" if t > 0.5 else "#1f3b54"
    return f"background-color: rgb({r},{g},{b}); color: {fg}; text-align: center; font-weight: 600;"


def _rgba(hexcolor: str, alpha: float) -> str:
    """'#27AE60' → 'rgba(39,174,96,0.14)' (배지 연한 배경용)."""
    h = str(hexcolor).lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 120, 120, 120
    return f"rgba({r},{g},{b},{alpha})"


def _stance_bar_html(counts: dict) -> str:
    """찬성/혼합/반대 비율을 가로 누적 막대 HTML 로."""
    total = counts.get("total", 0)
    if total <= 0:
        return ""
    segs = [
        (counts.get("support", 0), STYLE["stance_colors"]["support"]),
        (counts.get("mixed", 0), STYLE["stance_colors"]["mixed"]),
        (counts.get("oppose", 0), STYLE["stance_colors"]["oppose"]),
    ]
    parts = "".join(
        f"<div style='width:{c / total * 100:.1f}%;background:{col};'></div>"
        for c, col in segs if c > 0
    )
    return (
        "<div style='display:flex;height:14px;border-radius:7px;overflow:hidden;"
        f"margin:2px 0 6px;'>{parts}</div>"
    )


# ─────────────────────────────────────────────────────────────────────────
# 히트맵 표 HTML (iframe — 행 클릭 인라인 토글 + 헤더 정렬, 전부 JS)
# ─────────────────────────────────────────────────────────────────────────
_TABLE_TEMPLATE = """
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Malgun Gothic", "Apple SD Gothic Neo",
         sans-serif; color:#2C3E50; }
  .wrap { max-height: __WRAPMAX__px; overflow:auto; border:1px solid #ECEFF1;
          border-radius:10px; }
  table { width:100%; border-collapse:collapse; font-size:0.86rem; }
  thead th { position:sticky; top:0; z-index:2; background:#F7F8FA; color:#5A6B7B;
             font-weight:600; padding:11px 12px; border-bottom:2px solid #E8ECEF;
             text-align:center; white-space:nowrap; }
  thead th.nmh { text-align:left; }
  thead th.so { cursor:pointer; user-select:none; }
  thead th.so:hover { background:#EDF0F3; }
  thead th.neg { color:#C0392B; }
  .ar { color:#34495E; font-weight:700; }
  tbody td { border-bottom:1px solid #EEF1F3; }
  td.nm { padding:8px 12px; text-align:left; white-space:nowrap; }
  td.nm .n { font-weight:700; color:#2C3E50; }
  td.nm .s { font-size:0.74rem; color:#9AA7B2; margin-top:1px; }
  td.st { padding:8px 12px; text-align:center; white-space:nowrap; }
  td.sc { padding:11px 8px; }
  .badge { display:inline-block; padding:3px 12px; border-radius:12px;
           font-size:0.78rem; font-weight:600; white-space:nowrap; }
  .bv { display:inline-block; margin-left:6px; padding:1px 8px; border-radius:10px;
        font-size:0.68rem; font-weight:700; vertical-align:1px; white-space:nowrap; }
  .bnote { margin-top:8px; font-size:0.83rem; color:#4A3B5C; background:#F4EFF8;
           border-radius:8px; padding:7px 11px; line-height:1.45; }
  .bnote .bt { font-weight:700; }
  tr.cr { cursor:pointer; }
  tr.cr:hover td.nm, tr.cr:hover td.st { background:#F2F6FA; }
  tr.cr.open td.nm, tr.cr.open td.st { background:#EAF1F8; }
  tr.dr td { padding:0; background:#FBFCFD; }
  .d-inner { background:#F6F8FA; padding:11px 16px; border-radius:0 8px 8px 0;
             margin:6px 14px 12px 14px; }
  .quote { color:#2C3E50; font-size:0.9rem; line-height:1.5; }
  .acts { margin-top:8px; }
  .chip { display:inline-block; background:#EAF2F8; color:#21618C; padding:2px 10px;
          margin:3px 4px 0 0; border-radius:12px; font-size:0.74rem; }
</style></head><body>
<div class="wrap"><table>
  <thead><tr>
    <th class="nmh">시민</th>
    <th>입장</th>
    __SCORE_HEADERS__
  </tr></thead>
  <tbody id="tb"></tbody>
</table></div>
<script>
const DATA = __DATA__;
const NCOLS = __NCOLS__;
let sortCol = __SORTIDX__, sortDir = -1, openPid = null;

function rowMain(r) {
  let bv = r.behaviorLabel
    ? ' <span class="bv" style="background:' + r.behaviorBg + ';color:'
      + r.behaviorColor + '">' + r.behaviorLabel + '</span>'
    : '';
  let h = '<td class="nm"><div class="n">' + r.name + bv + '</div>'
        + '<div class="s">' + r.profile + '</div></td>';
  h += '<td class="st"><span class="badge" style="background:' + r.stanceBg
     + ';color:' + r.stanceColor + '">\\u25CF ' + r.stanceLabel + '</span></td>';
  for (let i = 0; i < r.scores.length; i++) {
    h += '<td class="sc" style="' + r.cellStyles[i] + '">' + r.scores[i] + '</td>';
  }
  return h;
}
function rowDetail(r) {
  let acts = r.actions.map(a => '<span class="chip">' + a + '</span>').join('');
  let bn = r.behaviorText
    ? '<div class="bnote">\\uD83E\\uDD2B <span class="bt">\\uC18D\\uB0B4'
      + (r.behaviorTag ? ' \\u00B7 ' + r.behaviorTag : '') + '</span> \\u2014 \\u201C'
      + r.behaviorText + '\\u201D</div>'
    : '';
  return '<div class="d-inner" style="border-left:4px solid ' + r.stanceColor + '">'
       + '<div class="quote">\\u201C' + r.text + '\\u201D</div>'
       + (acts ? '<div class="acts">' + acts + '</div>' : '') + bn + '</div>';
}
function render() {
  const rows = DATA.slice().sort((a, b) => sortDir * (a.scores[sortCol] - b.scores[sortCol]));
  let h = '';
  for (const r of rows) {
    const open = r.pid === openPid;
    h += '<tr class="cr' + (open ? ' open' : '') + '" data-pid="' + r.pid + '">'
       + rowMain(r) + '</tr>';
    if (open) h += '<tr class="dr"><td colspan="' + NCOLS + '">' + rowDetail(r) + '</td></tr>';
  }
  document.getElementById('tb').innerHTML = h;
  document.querySelectorAll('th.so').forEach(th => {
    const c = parseInt(th.dataset.col, 10);
    th.querySelector('.ar').textContent =
      (c === sortCol) ? (sortDir < 0 ? ' \\u2193' : ' \\u2191') : '';
  });
}
document.getElementById('tb').addEventListener('click', e => {
  const tr = e.target.closest('tr.cr');
  if (!tr) return;
  const pid = tr.getAttribute('data-pid');
  openPid = (openPid === pid) ? null : pid;
  render();
});
document.querySelectorAll('th.so').forEach(th => {
  th.addEventListener('click', () => {
    const c = parseInt(th.dataset.col, 10);
    if (sortCol === c) { sortDir = -sortDir; } else { sortCol = c; sortDir = -1; }
    render();
  });
});
render();
</script></body></html>
"""


def _build_table_html(view_df: pd.DataFrame, reactions_by_id: dict, wrap_max: int) -> str:
    """필터·정렬된 DataFrame → 자족형 HTML 표 문자열. 모든 사용자/LLM 텍스트는 escape."""
    data = []
    for _, row in view_df.iterrows():
        pid = row["_pid"]
        stance = row["_stance"]
        label, _emoji = _STANCE.get(stance, _STANCE["mixed"])
        scolor = STYLE["stance_colors"].get(stance, STYLE["stance_colors"]["mixed"])
        r = reactions_by_id.get(pid) or {}
        # 일탈 행동 배지(DESIGN §9) — comply/inaction/미측정은 라벨 '' → 배지 생략.
        b_label, b_color = _BEHAVIOR_BADGE.get(
            str(r.get("behavior_class") or ""), ("", ""))
        data.append({
            "pid": escape(str(pid)),
            "name": escape(str(row["시민"])),
            "profile": escape(str(row["프로필"])),
            "stanceLabel": label,                        # 우리 리터럴(안전)
            "stanceColor": scolor,
            "stanceBg": _rgba(scolor, 0.14),
            "scores": [int(row[c]) for c in _SCORE_LABELS],
            "cellStyles": [_cell_css(row[c], c in _NEG_LABELS) for c in _SCORE_LABELS],
            "text": escape(str(r.get("text") or "(반응 텍스트 없음)")),
            "actions": [escape(str(a)) for a in (r.get("actions") or [])],
            "behaviorLabel": b_label,                    # 우리 리터럴(안전)
            "behaviorColor": b_color,
            "behaviorBg": _rgba(b_color, 0.14) if b_color else "",
            "behaviorTag": escape(str(r.get("behavior_tag") or "")),
            "behaviorText": escape(str(r.get("behavior_text") or "")),
        })
    # </ 분리로 </script> 조기 종료 방지(텍스트는 이미 escape 됨 — 이중 안전망)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    # 점수 헤더는 _SCORE_LABELS 에서 생성(축 추가/제거에 자동 적응). 불만도=neg(레드).
    score_headers = "".join(
        f'<th class="so{" neg" if label in _NEG_LABELS else ""}" data-col="{i}">'
        f'{label}<span class="ar"></span></th>'
        for i, label in enumerate(_SCORE_LABELS)
    )
    return (
        _TABLE_TEMPLATE
        .replace("__SCORE_HEADERS__", score_headers)
        .replace("__NCOLS__", str(2 + len(_SCORE_LABELS)))
        .replace("__DATA__", payload)
        .replace("__SORTIDX__", str(_DEFAULT_SORT_IDX))
        .replace("__WRAPMAX__", str(wrap_max))
    )


# ─────────────────────────────────────────────────────────────────────────
# 신청 여정 분석 패널 (퍼널 / 연령대별 접근성 / 병목 요인) — 순수 HTML 빌더
# 모든 수치는 access_analysis 가 시민 반응에서 유도한 '추정'. 라이트 테마 인라인 스타일.
# ─────────────────────────────────────────────────────────────────────────
def _funnel_html(funnel: dict) -> str:
    """신청 단계별 퍼널 HTML. 단계 막대(너비 ∝ %)+사이사이 이탈 주석."""
    stages = funnel.get("stages") or []
    base = funnel.get("base_n") or 0
    if not stages or base <= 0:
        return ""
    rows = []
    last = len(stages) - 1
    for i, s in enumerate(stages):
        width = max(int(s.get("pct", 0)), 8)             # 너무 얇아 안 보이는 것 방지
        color = "#27AE60" if i == last else "#3E7CB1"    # 마지막 단계 = 성공 초록
        rows.append(
            "<div style='margin:3px 0;'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"height:34px;width:{width}%;min-width:130px;background:{color};"
            "border-radius:6px;padding:0 12px;color:#fff;font-weight:600;'>"
            f"<span style='font-size:0.85rem;'>{i + 1}. {escape(str(s.get('label', '')))}</span>"
            f"<span style='font-size:0.9rem;'>{int(s.get('count', 0))}명</span>"
            "</div></div>"
        )
        if i < last:
            nxt = stages[i + 1]
            if int(nxt.get("drop", 0)) > 0:
                rows.append(
                    "<div style='color:#C0392B;font-size:0.78rem;margin:1px 0 1px 14px;'>"
                    f"&#8595; {int(nxt['drop'])}명 이탈 ({escape(str(nxt.get('drop_label', '')))})"
                    "</div>"
                )
            else:
                rows.append("<div style='height:6px;'></div>")
    return "<div>" + "".join(rows) + "</div>"


def _age_access_html(rows: list) -> str:
    """연령대별 접근성 가로 막대 HTML.

    정직성: 밴드별 응답자 수(n)를 함께 보여준다. 표본이 없으면 막대 대신 '표본 없음',
    표본이 적으면(n<=2) 회색으로 흐리게 + '표본 적음' 표기(단일 응답을 통계처럼
    단정하지 않도록). 40% 미만은 레드(접근 취약 신호).
    """
    if not rows:
        return ""
    out = []
    for r in rows:
        pct = int(r.get("pct", 0))
        n = int(r.get("n", 0))
        band = escape(str(r.get("band", "")))
        if n <= 0:
            out.append(
                "<div style='display:flex;align-items:center;margin:7px 0;font-size:0.85rem;"
                "color:#B0B8C0;'>"
                f"<span style='width:128px;'>{band} <span style='font-size:0.72rem;'>(0명)</span></span>"
                "<div style='flex:1;margin:0 8px;'></div>"
                "<span style='width:64px;text-align:right;'>표본 없음</span>"
                "</div>"
            )
            continue
        faint = n <= 2  # 표본 적음 → 신뢰도 낮음 신호로 흐리게
        if faint:
            color = "#AEB6BF"
        else:
            color = "#E74C3C" if pct < 40 else "#2D7DD2"
        n_note = f"({n}명{'·표본적음' if faint else ''})"
        out.append(
            "<div style='display:flex;align-items:center;margin:7px 0;font-size:0.85rem;'>"
            f"<span style='width:128px;color:#5A6B7B;'>{band} "
            f"<span style='font-size:0.72rem;color:#9AA7B2;'>{n_note}</span></span>"
            "<div style='flex:1;background:#EEF1F3;border-radius:6px;height:16px;margin:0 8px;'>"
            f"<div style='width:{pct}%;background:{color};height:16px;border-radius:6px;'></div>"
            "</div>"
            f"<span style='width:42px;text-align:right;font-weight:700;color:#2C3E50;'>{pct}%</span>"
            "</div>"
        )
    return "".join(out)


_RANK_COLOR = {0: "#C0392B", 1: "#E67E22", 2: "#7F8C8D"}


def _barriers_html(barriers: list, top: int = 3) -> str:
    """병목 요인 TOP N 목록 HTML(순위색 + 인원수)."""
    items = (barriers or [])[:top]
    if not items:
        return "<div style='color:#9AA7B2;font-size:0.85rem;'>두드러진 병목 요인이 없습니다.</div>"
    out = []
    for i, b in enumerate(items):
        color = _RANK_COLOR.get(i, "#7F8C8D")
        out.append(
            "<div style='display:flex;justify-content:space-between;align-items:center;"
            "padding:8px 2px;border-bottom:1px solid #EEF1F3;font-size:0.88rem;'>"
            f"<span><b style='color:{color};'>{i + 1}.</b> {escape(str(b.get('label', '')))}</span>"
            f"<span style='color:{color};font-weight:700;'>{int(b.get('count', 0))}명</span>"
            "</div>"
        )
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────
# 축3 결과 섹션 — 낙차 헤드라인 + 깔때기 (설계방향서 §5·§8-5)
# 모든 수치는 view["axis3"](aggregate_axis3)에서만 읽는다(단일 진실원).
# 아래 access 섹션(축1 점수 기반 '추정')과 달리 이것은 축2 시뮬의 '실제 결과'다.
# ─────────────────────────────────────────────────────────────────────────
# 깔때기 단계 사이 갭의 처방 라벨(§5: 갭별 처방이 다르다 — 홍보/진입/심사)
_AXIS3_DROP_LABELS = ["갭: 홍보·전파", "갭: 진입(절차·신뢰)", "갭: 심사·처리"]


def _axis3_funnel_stages(a3: dict) -> dict:
    """aggregate_axis3 의 funnel → _funnel_html 입력 형태(순수 어댑터).

    단계는 부분집합이 아니라 대상자 모수의 독립 카운트라, 사이 표기는
    '이탈'이 아닌 인원 차(갭)다. 다음 단계가 더 크면(전향 유입) 갭 0 으로 두고
    전향 캡션이 설명한다.
    """
    n_target = a3.get("n_target") or 0
    stages = []
    prev = None
    for i, f in enumerate(a3.get("funnel") or []):
        cnt = int(f.get("count", 0))
        s = {
            "label": f.get("label", ""),
            "count": cnt,
            "pct": (cnt / n_target * 100) if n_target else 0,
        }
        if prev is not None:
            s["drop"] = max(0, prev - cnt)
            s["drop_label"] = _AXIS3_DROP_LABELS[min(i - 1, 2)]
        stages.append(s)
        prev = cnt
    return {"stages": stages, "base_n": n_target}


def render_axis3_section(view) -> None:
    """시간 전개 결과(축3) — 같은 모수(대상자)·같은 단위(인원 비율)의 낙차와 깔때기.

    '정책 결과 종합' 섹션의 둘째 층(v1.2): 위 게이지(t0 지표)와 같은 축3 집계에서
    나온 결과 지표를 잇는다. 축2·3 산출물이 있을 때만 채워지고,
    비신청형 정책은 낙차 헤드라인을 숨긴다.
    """
    from axis3 import is_application_policy

    a3 = view.get("axis3") or {}

    st.markdown("#### 시간 전개 결과 — 의향과 수령의 낙차")

    # 비신청형(만 나이 통일·종부세류): 신청·수령 깔때기가 무의미 — t0 지표 중심.
    if not is_application_policy(view.get("policy_spec")):
        st.caption(
            "이 정책은 **비신청형**(감면·자동 적용)으로 분류되어 신청·수령 깔때기와 "
            "낙차가 적용되지 않습니다. 위 첫 반응 지표(수용도·의향·혼란도)를 중심으로 보세요."
        )
        st.divider()
        return

    # 단계적 표시: 축2·3가 아직이면 자리 안내만(§5 — 축1 지표 먼저, 결과는 뒤 채움).
    if not a3:
        st.info(
            "사이드바 **시뮬레이션 실행** 한 번으로 인생극장(축2)까지 돌면 "
            "여기에 실제 결과(수령률·사각·낙차·깔때기)가 채워집니다."
        )
        st.divider()
        return

    n, n_target = int(a3.get("n", 0)), int(a3.get("n_target", 0))

    # 대상자 0 = 측정 불가(0%와 다름) — 정직하게 그 사실을 보여준다.
    if not n_target:
        st.warning(
            f"전체 {n}명 중 이 정책의 대상(나이·소득·가구 조건)에 드는 사람이 없어 "
            "낙차·수령률을 측정할 수 없습니다."
        )
        st.divider()
        return

    # ── 낙차 헤드라인: t0 적극 의향 → 종점 수령 (둘 다 대상자 모수·인원 비율) ──
    intent_pct = a3["intent_rate_t0"] * 100
    recv_pct = a3["received_rate"] * 100
    gap_pp = a3["gap"] * 100
    blind_pct = a3["blindspot_rate"] * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("t0 적극 의향 (대상자)", f"{intent_pct:.0f}%",
              help="시뮬 시작 시점, 대상자 중 '반드시/아마 신청' 비율 (intent≥60)")
    c2.metric("종점 수령 (대상자)", f"{recv_pct:.0f}%",
              help="시간 전개(축2)가 끝난 시점, 대상자 중 실제 수령 비율")
    c3.metric("낙차 (의향-수령)", f"{gap_pp:+.0f}%p",
              delta=f"{-gap_pp:+.0f}%p", delta_color="normal",
              help="양수 = 의향이 어딘가서 샜다(아래 깔때기로 위치 추적), "
                   "음수 = 전파가 의향을 끌어올렸다")
    c4.metric("사각지대 (막힘+못 닿음)", f"{blind_pct:.0f}%",
              help="대상자 중 blocked(집행 실패) + unaware(전파 실패) 비율")

    # 전향(§2: 모순이 아니라 추적된 변화) — 있을 때만 한 줄.
    if a3.get("n_conversion"):
        names = ", ".join(c["name"] for c in a3["conversions"][:3])
        more = f" 외 {a3['n_conversion'] - 3}명" if a3["n_conversion"] > 3 else ""
        st.caption(
            f"🔄 전향 {a3['n_conversion']}명 — t0 의향이 없었지만(intent<50) 시간 속 "
            f"계기를 거쳐 수령에 닿았습니다: {names}{more}"
        )

    # ── 깔때기: 의향 → 도달 → 신청 → 수령 (대상자 모수) ──
    st.markdown("**깔때기 — 어디서 새는가** "
                f"<span style='color:#9AA7B2;font-size:0.8rem;'>(모수 = 대상자 "
                f"{n_target}명 · 실제 시뮬 결과)</span>", unsafe_allow_html=True)
    st.markdown(_funnel_html(_axis3_funnel_stages(a3)), unsafe_allow_html=True)

    # ── 정직 캡션: 모수·기록 누락·다리 가드 ──
    notes = [f"전체 {n}명 중 대상자 {n_target}명 기준(비대상 {n - n_target}명 제외)"]
    if a3.get("missing_t0"):
        notes.append(f"t0 의향 기록이 없는 대상자 {a3['missing_t0']}명은 의향 단계에서 제외(분모는 유지)")
    g = a3.get("guard") or {}
    if g.get("retries"):
        notes.append(f"다리 가드 재생성 {g['retries']}건")
    if g.get("residuals"):
        notes.append(f"모순 감지 {g['residuals']}건(경로 누락 — 교정 표기)")
    st.caption(" · ".join(notes))

    st.divider()


def render_access_section(view) -> None:
    """신청 여정 분석 — 사전 가설(t0 점수 기반 추정). v1.2: expander 로 강등.

    실측 깔때기(위 '시간 전개 결과')가 진실원이 된 뒤로, 이 섹션은 '병목이 어디일지'를
    t0 반응만으로 미리 짚는 가설 층이다 — 연령 접근성·병목 TOP3 진단은 실측에 없는
    고유 정보라 유지. 반응이 없으면 아무것도 안 그린다.
    """
    a = access.analyze(view)
    funnel = a.get("funnel") or {}
    if (funnel.get("base_n") or 0) <= 0:
        return

    with st.expander("🔍 신청 여정 분석 — 사전 추정(t0 점수 기반)", expanded=False):
        st.caption(
            "시민들이 매긴 반응(이해도·살림 영향·접근도·신청의향)으로 **추정한** 신청 여정입니다. "
            "위 '시간 전개 결과' 깔때기가 시뮬의 **실측**이라면, 이것은 t0 반응만으로 본 "
            "사전 가설 — 병목 위치를 미리 짚는 용도예요. 실제 응답 시민 수가 기준이라 "
            "인원이 적게 보일 수 있어요."
        )

        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.markdown("**신청 단계별 병목 퍼널**")
            st.markdown(_funnel_html(funnel), unsafe_allow_html=True)
        with col_r:
            st.markdown("**연령대별 정책 접근성**")
            st.markdown(_age_access_html(a.get("age_access")), unsafe_allow_html=True)
            st.caption("괄호 = 해당 연령대 응답자 수 · 표본이 적은 구간(2명 이하)은 회색으로 표시")
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            st.markdown("**병목 요인 TOP 3**")
            st.markdown(_barriers_html(a.get("barriers")), unsafe_allow_html=True)

    st.divider()


# ─────────────────────────────────────────────────────────────────────────
# 메인 렌더
# ─────────────────────────────────────────────────────────────────────────
@st.fragment   # 입장 필터 라디오의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
def render_dashboard_tab(view):
    """ViewModel(view)을 받아 대시보드를 그린다.

    상단: 정책 결과 종합(축3 단일 진실원, v1.2) — 첫 반응 지표 게이지 3종(전원 모수)
          + 시간 전개 결과(낙차·깔때기, 대상자 모수) + 사전 가설 expander.
    하단: 시민 반응 히트맵 표(전원 한눈에 + 행 클릭 인라인 상세).
    view가 None이면 안내 후 종료한다.
    """
    if view is None:
        st.info("아직 시뮬레이션 결과가 없습니다. 정책을 입력하고 시뮬레이션을 실행해 주세요.")
        return

    # ── 상단: 정책 결과 종합(축3) — 모든 지표의 단일 진실원 (설계방향서 v1.2 §1.6) ──
    # 게이지 3종(t0 지표·전원 모수)도 축3 산출(t0_metrics)을 읽는다. 구 세션/저장본엔
    # axis3 가 없을 수 있어 metrics 로 폴백(같은 값 — _adopt_axis3_metrics 가 동기화).
    metrics = view.get("metrics", {}) or {}          # behavior_counts 등 보조 + 폴백
    a3 = view.get("axis3") or {}
    t0m = a3.get("t0_metrics") or metrics

    st.subheader("정책 결과 종합")
    # 생성 모델 표식 — 모델이 다르면 점수 분포도 달라서, 어느 모델 산출인지 박아둔다.
    if view.get("llm_model"):
        st.caption(f"생성 모델: `{view['llm_model']}` — 결과 비교는 같은 모델끼리만.")
    n_t0 = t0m.get("n") or len(view.get("reactions_by_id") or {})
    st.markdown(
        "#### 첫 반응 지표 "
        f"<span style='color:#9AA7B2;font-size:0.8rem;font-weight:400;'>(모수 = 시민 "
        f"{n_t0}명 전원 · 정책을 처음 접한 시점(t0)의 반응)</span>",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.plotly_chart(gauge(t0m.get("정책수용도", 0), "정책수용도"),
                        width="stretch")
    with col2:
        st.plotly_chart(gauge(t0m.get("신청의향지수", 0), "신청의향지수"),
                        width="stretch")
    with col3:
        st.plotly_chart(gauge(t0m.get("사회혼란도", 0), "사회혼란도"),
                        width="stretch")

    # ── 같은 섹션 둘째 층: 시간 전개 결과(축3) — 낙차·깔때기 (§8-5) ──
    render_axis3_section(view)

    # ── 사전 가설 층: 신청 여정 분석 (t0 점수 기반 추정 — v1.2 expander 강등) ──
    render_access_section(view)

    # ── 하단: 시민 반응 히트맵 ──────────────────────────────────────
    personas = view.get("personas", []) or []
    reactions_by_id = view.get("reactions_by_id", {}) or {}

    df, counts = build_reaction_table(personas, reactions_by_id)
    total = counts["total"]

    st.subheader("시민 반응")
    if df.empty:
        if not personas:
            st.info("표시할 페르소나가 없습니다.")
        else:
            st.info("아직 생성된 시민 반응이 없습니다.")
        return

    # stance 분포 바 + 범례
    st.markdown(_stance_bar_html(counts), unsafe_allow_html=True)
    st.caption(
        f"🟢 찬성 {counts['support']}  ·  🟡 혼합 {counts['mixed']}  ·  "
        f"🔴 반대 {counts['oppose']}  ·  총 {total}명"
    )

    # 일탈 행동 요약 줄(DESIGN §9) — 관측된 경우에만 표시.
    bc = metrics.get("behavior_counts") or {}
    n_dev = int(bc.get("workaround", 0)) + int(bc.get("exploit", 0))
    n_comp = int(bc.get("complain", 0))
    if n_dev or n_comp:
        st.caption(
            f"🤫 제도 틈새·부정수급 시도 {n_dev}명 · 📢 민원·행동화 {n_comp}명 — "
            "이름 옆 배지가 붙은 행을 클릭하면 속내가 보여요 (가능성 시나리오, 행동 예측 아님)"
        )

    # 입장 필터 — radio(horizontal). segmented_control/pills 는 AppTest 직렬화와
    # 충돌해 회귀 스모크를 깨뜨린다. radio 는 네이티브이고 테스트도 안정적.
    filter_opts = {
        f"전체 {total}": None,
        f"🟢 찬성 {counts['support']}": "support",
        f"🟡 혼합 {counts['mixed']}": "mixed",
        f"🔴 반대 {counts['oppose']}": "oppose",
    }
    labels = list(filter_opts)
    pick = st.radio(
        "입장 필터", labels, horizontal=True,
        label_visibility="collapsed", key="dash_stance_filter",
    )
    want = filter_opts.get(pick) if pick else None

    # 필터 + 기본 정렬(신청의향 ↓) — JS 도 같은 기본값으로 재정렬한다.
    view_df = df if want is None else df[df["_stance"] == want]
    view_df = view_df.sort_values("신청의향", ascending=False, kind="stable").reset_index(drop=True)

    if view_df.empty:
        st.info("해당 입장의 시민이 없습니다.")
        return

    # 히트맵 표 — 행 클릭 인라인 토글 + 헤더 정렬(클라이언트 JS)
    n = len(view_df)
    height = min(540, 64 + n * 46)
    components.html(
        _build_table_html(view_df, reactions_by_id, wrap_max=height - 12),
        height=height,
        scrolling=False,
    )

    st.caption(
        "행을 클릭하면 그 시민의 한마디가 펼쳐져요  ·  헤더를 클릭하면 정렬돼요  ·  "
        "🔴 불만도는 높을수록 부정 신호"
    )
