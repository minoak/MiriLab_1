# -*- coding: utf-8 -*-
"""대시보드 탭(= '시민 반응'): 핵심 지표 게이지 3종 + 시민 반응 히트맵 표.

히트맵: 시민 전원을 표 한 장에 담아 스크롤 없이 훑는다.
  - 5축 점수를 valence 색으로 칠함 — 긍정 지표(이해도/수혜/신청의향/공유)=파랑,
    불만도=레드(높을수록 부정 신호).
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
    ("benefit", "수혜가능성"),
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

    DataFrame 컬럼: _pid, _stance, 시민, 프로필, 입장, 이해도, 수혜가능성, 신청의향,
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
# 히트맵 표 HTML (components.html — 행 클릭 인라인 토글 + 헤더 정렬, 전부 JS)
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
  let h = '<td class="nm"><div class="n">' + r.name + '</div>'
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
  return '<div class="d-inner" style="border-left:4px solid ' + r.stanceColor + '">'
       + '<div class="quote">\\u201C' + r.text + '\\u201D</div>'
       + (acts ? '<div class="acts">' + acts + '</div>' : '') + '</div>';
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


def render_access_section(view) -> None:
    """신청 여정 분석(퍼널/연령접근성/병목)을 렌더. 반응이 없으면 아무것도 안 그린다.

    렌더한 경우 끝에 divider 를 붙여 아래 히트맵과 구분한다.
    """
    a = access.analyze(view)
    funnel = a.get("funnel") or {}
    if (funnel.get("base_n") or 0) <= 0:
        return

    st.subheader("신청 여정 분석")
    st.caption(
        "시민들이 매긴 반응(이해도·수혜·접근도·신청의향)으로 **추정한** 신청 여정입니다. "
        "실제 응답 시민 수가 기준이라 인원이 적게 보일 수 있어요."
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

    상단: 정책수용도 / 신청의향지수 / 사회혼란도 게이지 3종.
    하단: 시민 반응 히트맵 표(전원 한눈에 + 행 클릭 인라인 상세).
    view가 None이면 안내 후 종료한다.
    """
    if view is None:
        st.info("아직 시뮬레이션 결과가 없습니다. 정책을 입력하고 시뮬레이션을 실행해 주세요.")
        return

    # ── 상단: 핵심 지표 게이지 3종 (기존 그대로) ────────────────────
    metrics = view.get("metrics", {}) or {}

    st.subheader("핵심 지표")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.plotly_chart(gauge(metrics.get("정책수용도", 0), "정책수용도"),
                        use_container_width=True)
    with col2:
        st.plotly_chart(gauge(metrics.get("신청의향지수", 0), "신청의향지수"),
                        use_container_width=True)
    with col3:
        st.plotly_chart(gauge(metrics.get("사회혼란도", 0), "사회혼란도"),
                        use_container_width=True)

    st.divider()

    # ── 중단: 신청 여정 분석 (퍼널 / 연령접근성 / 병목 TOP3) ─────────
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
