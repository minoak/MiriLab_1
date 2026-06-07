# -*- coding: utf-8 -*-
"""ui/village_map.py — 미리 마을 "오버월드" 맵 (포켓몬 게임형 시각화).

정책 시행 후 시점(예: 시행 1/3/6개월)이 흐르며, 인구통계에 grounding된 시민
(페르소나)이 마을의 장소(=정책 접근 채널)를 돌아다니는 모습을 보여준다.
핵심 메시지: "같은 정책, 다른 결과 — 누구는 수령, 누구는 집에만 갇힘(사각지대)".

두 렌더러를 한 모듈에 담아 데모 안전망을 둔다(tab_network 의 pyvis→matplotlib
폴백과 동형):
  - _render_animated : streamlit.components.v1.html 단일 iframe. 잔디 타일맵 위에
    건물 5개 + 시민 이모지 스프라이트. 시점 전환 시 CSS transition 으로 시민이
    건물 사이를 "걸어" 이동. ▶재생 버튼 + 슬라이더(서버 왕복 없음). 메인 경로.
  - _render_static   : JS 0. st.markdown(unsafe_allow_html) 로 그린 CSS Grid 타일맵
    + st.select_slider. iframe 실패/명시적 강등 시 폴백.

데이터는 build_view 결과(view)의 검증된 경로만 사용한다:
  view["personas"][].{id, name, demographics.age, demographics.sex}
  view["village"]["steps"]
  view["village"]["residents"][].{id, name, timeline[].{place, policy_status, economic, wellbeing, label}}
  view["village"]["aggregate"]["home_bound"][].id
페르소나 id == 주민 id == 점유자 id (mock.py:661 / graph.village 동형, 검증됨).
실제(LLM) 모드와 mock 모드가 동일한 village 구조를 내므로 두 모드 모두 동작한다.
"""
from __future__ import annotations

import json
import streamlit as st
import streamlit.components.v1 as components

from graph.spaces import PLACE_KEYS, place_label, status_label
# ⚠ DORMANT — 이 오버월드 맵 모듈은 현재 어디에서도 import/호출되지 않는다(인생극장은
# 카드 서사로 통일됨, tab_village docstring 참조). 부활 시 검증 필요.
# 상태색: tab_village 가 _STATUS_COLOR → _STATUS_META(이모지·라벨·색 3-튜플)로 바뀌었으므로
# 색만 추출해 과거 {상태: 색} dict(_STATUS_COLOR) 형태로 재구성한다(import 안전).
from ui.tab_village import _status_meta
_STATUS_COLOR = {
    k: _status_meta(k)[2]
    for k in ("unaware", "aware", "applied", "received", "blocked")
}


# ---------------------------------------------------------------------------
# 페르소나 lookup + 스프라이트 매핑
# ---------------------------------------------------------------------------
def _persona_index(personas: list) -> dict:
    """personas -> {str(id): {"age": int|None, "sex": str}}.

    village.residents 에는 age/sex 가 없으므로 같은 view 의 personas 에서 id 로 조인한다.
    """
    idx: dict = {}
    for p in personas or []:
        demo = (p.get("demographics") or {}) if isinstance(p, dict) else {}
        idx[str(p.get("id"))] = {"age": demo.get("age"), "sex": demo.get("sex")}
    return idx


def _as_int(v):
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _is_female(sex) -> bool:
    s = str(sex or "")
    return ("여" in s) or s.lower().startswith(("f", "w"))


def _is_male(sex) -> bool:
    s = str(sex or "")
    return ("남" in s) or s.lower().startswith("m")


def _sprite_for(age, sex, pid: str) -> str:
    """나이/성별 -> 사람 이모지(포켓몬 NPC 톤). 미상이면 결정론적 중립 이모지.

    실제 데이터 sex 값이 "남성"/"여성" 전체 단어이므로 == 비교가 아니라
    포함/startswith 로 판정한다(== 비교는 전원 한쪽으로 쏠리는 버그).
    """
    a = _as_int(age)
    if a is not None:
        f, m = _is_female(sex), _is_male(sex)
        if a >= 65:
            return "👵" if f else ("👴" if m else "🧓")
        if a <= 19:
            return "👧" if f else ("👦" if m else "🧒")
        return "👩" if f else ("👨" if m else "🧑")
    # demographics 미연결(LLM 모드 id 불일치 등): id 해시로 약한 다양성 부여
    pool = ["🧑", "🧒", "🧓", "👤", "🙂", "🧍"]
    key = str(pid or "")
    return pool[(sum(ord(c) for c in key) if key else 0) % len(pool)]


def _esc(s) -> str:
    """HTML 텍스트 이스케이프(이름 등)."""
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# 공통 데이터: 시점 라벨 + 시점별 장소 점유
# ---------------------------------------------------------------------------
def _step_labels(village: dict) -> list:
    steps = village.get("steps") or []
    if steps:
        return list(steps)
    residents = village.get("residents") or []
    if residents:
        tl = residents[0].get("timeline") or []
        return [t.get("label", f"시점 {i + 1}") for i, t in enumerate(tl)]
    return []


def _home_ids(village: dict) -> set:
    agg = village.get("aggregate") or {}
    return {h.get("id") for h in (agg.get("home_bound") or [])}


def _places_at_step(village: dict, step_idx: int) -> dict:
    """선택 시점에 각 장소에 있는 주민 목록. residents[].timeline 을 단일 진실원으로 사용.

    반환: {place_key: [{"id","name","status"}...]}  (PLACE_KEYS 순서로 키 보장)
    """
    groups: dict = {k: [] for k in PLACE_KEYS}
    for r in village.get("residents") or []:
        tl = r.get("timeline") or []
        if not tl:
            continue
        t = tl[min(step_idx, len(tl) - 1)]
        place = t.get("place") or "home"
        groups.setdefault(place, [])
        groups[place].append({
            "id": r.get("id"),
            "name": r.get("name", ""),
            "status": t.get("policy_status", "unaware"),
        })
    return groups


# ---------------------------------------------------------------------------
# 메인 렌더러: components.v1.html 오버월드 (JS 워크 애니메이션)
# ---------------------------------------------------------------------------
def _build_payload(village: dict, personas: list, autoplay: bool = False) -> dict:
    """JS 오버월드에 주입할 자기완결 데이터. 검증된 경로만 사용."""
    pidx = _persona_index(personas)
    residents = village.get("residents") or []
    home_ids = _home_ids(village)

    people = []
    for r in residents:
        rid = r.get("id")
        demo = pidx.get(str(rid), {})
        frames = []
        for t in (r.get("timeline") or []):
            frames.append({
                "place": t.get("place") or "home",
                "status": t.get("policy_status", "unaware"),
                "econ": t.get("economic"),
                "wb": t.get("wellbeing"),
            })
        people.append({
            "id": rid,
            "name": r.get("name", ""),
            "sprite": _sprite_for(demo.get("age"), demo.get("sex"), rid),
            "home_bound": rid in home_ids,
            "frames": frames,
        })

    return {
        "stepLabels": _step_labels(village),
        "placeKeys": list(PLACE_KEYS),
        "placeLabels": {k: place_label(k) for k in PLACE_KEYS},
        "statusColors": dict(_STATUS_COLOR),
        "statusLabels": {k: status_label(k)
                         for k in ("unaware", "aware", "applied", "received", "blocked")},
        "people": people,
        "autoplay": bool(autoplay),
    }


# 자기완결 HTML/CSS/JS. __DATA__ 는 json 으로 치환된다. (f-string 아님 — 중괄호 그대로)
_OVERWORLD_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;}
body{margin:0;font-family:'Malgun Gothic','Apple SD Gothic Neo','Segoe UI Emoji',sans-serif;
  background:#F7FBF9;color:#2C3E50;}
#wrap{width:780px;margin:0 auto;padding:6px;}
#map{position:relative;width:760px;height:460px;border-radius:14px;overflow:hidden;
  background:#8ed06a;
  background-image:
    linear-gradient(rgba(255,255,255,.10) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.10) 1px,transparent 1px),
    radial-gradient(circle at 28% 18%,rgba(255,255,255,.14),transparent 42%);
  background-size:38px 38px,38px 38px,100% 100%;
  border:4px solid #5b8c3e;box-shadow:inset 0 0 0 3px #a6dd86;}
.path{position:absolute;background:#e8d8a8;opacity:.75;border-radius:8px;}
.bldg{position:absolute;width:140px;height:78px;border-radius:10px;
  background:#fff7e8;border:3px solid #8a6d3b;box-shadow:0 4px 0 #6f5630;
  text-align:center;padding-top:4px;z-index:2;}
.bldg .roof{font-size:1.7rem;line-height:1.15;}
.bldg .bname{font-size:.72rem;font-weight:700;color:#5b4326;}
.bldg .bcnt{font-size:.64rem;color:#8a6d3b;}
.cit{position:absolute;width:34px;text-align:center;z-index:6;
  transition:left .85s ease,top .85s ease;}
.cit .face{font-size:1.4rem;line-height:28px;display:inline-block;width:30px;height:30px;
  border:3px solid #9E9E9E;border-radius:50%;background:rgba(255,255,255,.7);}
.cit .nm{font-size:.6rem;color:#22313f;white-space:nowrap;
  text-shadow:0 1px 0 #fff,0 -1px 0 #fff,1px 0 0 #fff,-1px 0 0 #fff;}
.cit.blind .face{animation:pulse 1.2s infinite;}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(110,110,110,0);}
  50%{box-shadow:0 0 0 6px rgba(110,110,110,.45);}}
#bar{display:flex;align-items:center;gap:10px;margin:10px 2px 4px;}
#play{cursor:pointer;border:none;border-radius:8px;padding:6px 14px;
  background:#2c3e50;color:#fff;font-size:.85rem;font-weight:700;}
#play:hover{background:#1b2733;}
#slider{flex:1;}
#lbl{font-weight:700;font-size:.9rem;min-width:104px;text-align:right;}
#legend{font-size:.72rem;margin:4px 2px;display:flex;gap:12px;flex-wrap:wrap;}
#legend span b{display:inline-block;width:10px;height:10px;border-radius:50%;
  border:2px solid #fff;margin-right:3px;vertical-align:middle;}
</style></head><body><div id="wrap">
<div id="map"></div>
<div id="bar">
  <button id="play">▶ 재생</button>
  <input id="slider" type="range" min="0" value="0" step="1">
  <span id="lbl"></span>
</div>
<div id="legend"></div>
</div>
<script>
const D = __DATA__;
const POS = {online_portal:[36,28],community_center:[310,18],welfare_center:[584,28],
  work_market:[120,300],home:[560,300]};
const ICON = {online_portal:"💻",community_center:"🏛️",welfare_center:"🏥",
  work_market:"🏪",home:"🏠"};
const BLD_H = 78;
const map = document.getElementById('map');
function addPath(x,y,w,h){const d=document.createElement('div');d.className='path';
  d.style.left=x+'px';d.style.top=y+'px';d.style.width=w+'px';d.style.height=h+'px';
  map.appendChild(d);}
addPath(150,150,470,24); addPath(360,158,24,158);
for(const k of D.placeKeys){
  const p=POS[k]||POS.home;
  const b=document.createElement('div');b.className='bldg';
  b.style.left=p[0]+'px';b.style.top=p[1]+'px';
  b.innerHTML="<div class='roof'>"+(ICON[k]||"🏠")+"</div>"+
    "<div class='bname'>"+(D.placeLabels[k]||k)+"</div>"+
    "<div class='bcnt' id='cnt_"+k+"'></div>";
  map.appendChild(b);
}
const nodes={};
D.people.forEach(p=>{
  const el=document.createElement('div');
  el.className='cit'+(p.home_bound?' blind':'');
  el.innerHTML="<div class='face'>"+p.sprite+"</div><div class='nm'></div>";
  el.querySelector('.nm').textContent=p.name;   // 이름은 신뢰불가 → HTML 파싱 안 함(XSS 방지)
  map.appendChild(el); nodes[p.id]=el;
});
const slider=document.getElementById('slider');
const lbl=document.getElementById('lbl');
const playBtn=document.getElementById('play');
slider.max=Math.max(0,(D.stepLabels.length-1));
let curStep=0, timer=null;
function applyStep(s){
  const counts={};
  D.people.forEach(p=>{
    const fi=Math.min(s,Math.max(0,p.frames.length-1));
    const f=p.frames[fi]||{place:'home',status:'unaware'};
    const base=POS[f.place]||POS.home;
    const i=(counts[f.place]||0); counts[f.place]=i+1;
    const col=i%4, row=Math.floor(i/4);            // 4열(상단 2행=8명까지 안전)
    let x=base[0]+2+col*34, y=base[1]+BLD_H+4+row*32;
    if(x>760-32) x=760-32;                          // 우측 경계 클램프
    if(y>460-34) y=460-34;                          // 하단 경계 클램프(다수 군집해도 잘림 방지)
    const el=nodes[p.id];
    el.style.left=x+'px'; el.style.top=y+'px';
    const face=el.querySelector('.face');
    face.style.borderColor=D.statusColors[f.status]||'#9E9E9E';
    el.title=p.name+" · "+(D.statusLabels[f.status]||f.status)+
      " · 경제 "+(f.econ==null?'-':f.econ)+" / 심리 "+(f.wb==null?'-':f.wb);
  });
  for(const k of D.placeKeys){
    const c=document.getElementById('cnt_'+k);
    if(c) c.textContent=(counts[k]||0)+"명";
  }
  lbl.textContent=D.stepLabels[s]||('시점 '+(s+1));
  slider.value=s; curStep=s;
}
function stop(){if(timer){clearInterval(timer);timer=null;}playBtn.textContent='▶ 재생';}
function play(){
  if(timer){stop();return;}
  playBtn.textContent='⏸ 정지';
  if(curStep>=D.stepLabels.length-1) curStep=-1;
  timer=setInterval(()=>{
    const s=curStep+1;
    if(s>D.stepLabels.length-1){stop();return;}
    applyStep(s);
  },1150);
}
slider.oninput=e=>{stop();applyStep(+e.target.value);};
playBtn.onclick=play;
const leg=document.getElementById('legend');
const order=[["unaware","모름"],["aware","알게됨"],["applied","신청"],["received","수령"],["blocked","막힘"]];
leg.innerHTML=order.map(o=>"<span><b style='background:"+(D.statusColors[o[0]]||'#9E9E9E')+
  "'></b>"+o[1]+"</span>").join("")+
  "<span>🔒 회색 점멸 = 집에만 머무는 사각지대</span>";
applyStep(0);
if(D.autoplay) setTimeout(play,700);
</script></body></html>"""


def _render_animated(payload: dict):
    """JS 오버월드 iframe 주입. </script> 조기 종료 차단(보안)."""
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _OVERWORLD_HTML.replace("__DATA__", data)
    components.html(html, height=600, scrolling=False)


# ---------------------------------------------------------------------------
# 폴백 렌더러: JS-free CSS Grid 타일맵
# ---------------------------------------------------------------------------
_PLACE_META = {
    "online_portal":    {"area": "a", "icon": "💻"},
    "community_center": {"area": "b", "icon": "🏛️"},
    "welfare_center":   {"area": "c", "icon": "🏥"},
    "work_market":      {"area": "d", "icon": "🏪"},
    "home":             {"area": "e", "icon": "🏠"},
}

_STATIC_CSS = """<style>
.mlmap{display:grid;grid-template-columns:repeat(3,1fr);
  grid-template-rows:repeat(2,minmax(118px,auto));
  grid-template-areas:'a b c' 'd plaza e';gap:10px;padding:14px;border-radius:14px;
  background:repeating-linear-gradient(45deg,#bfe3a0 0 18px,#b6dd95 18px 36px);
  border:3px solid #5b8c3e;}
.mlbld{border:3px solid #8a6d3b;border-radius:12px;padding:8px;background:#fff7e8;
  box-shadow:0 3px 0 #6f5630;}
.mlbld h4{margin:0 0 6px;font-size:.9rem;color:#5b4326;}
.mlppl{display:flex;flex-wrap:wrap;gap:8px;min-height:40px;align-content:flex-start;}
.mls{width:54px;text-align:center;}
.mlf{position:relative;font-size:1.6rem;line-height:1;}
.mld{position:absolute;right:8px;bottom:0;width:11px;height:11px;border-radius:50%;
  border:2px solid #fff;}
.mln{font-size:.64rem;color:#22313f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.mlhome{border-color:#9E9E9E;border-style:dashed;background:#f3f3f3;}
.mlplaza{grid-area:plaza;display:flex;align-items:center;justify-content:center;
  color:#5a7d3a;font-size:.82rem;font-weight:700;}
.mlempty{color:#9aa;font-size:.72rem;}
</style>"""


def _static_sprite(occ: dict, pidx: dict, home_ids: set) -> str:
    demo = pidx.get(str(occ.get("id")), {})
    emoji = _sprite_for(demo.get("age"), demo.get("sex"), occ.get("id"))
    dot = _STATUS_COLOR.get(occ.get("status", "unaware"), "#9E9E9E")
    lock = "🔒" if occ.get("id") in home_ids else ""
    name = _esc(occ.get("name", ""))
    return (f"<div class='mls' title='{name} · {status_label(occ.get('status', 'unaware'))}'>"
            f"<div class='mlf'>{emoji}<span class='mld' style='background:{dot}'></span></div>"
            f"<div class='mln'>{name}{lock}</div></div>")


def _render_static(village: dict, personas: list):
    """JS 0 정적 타일맵 + 시점 select_slider 폴백."""
    labels = _step_labels(village)
    if not labels:
        st.info("맵을 그릴 시점 데이터가 없습니다.")
        return
    if len(labels) > 1:
        sel = st.select_slider("시점", options=labels, value=labels[0],
                               key="village_map_static_step")
        idx = labels.index(sel)
    else:
        idx = 0
        st.caption(f"시점: {labels[0]}")

    pidx = _persona_index(personas)
    home_ids = _home_ids(village)
    groups = _places_at_step(village, idx)

    cells = [_STATIC_CSS, "<div class='mlmap'>"]
    for key in PLACE_KEYS:
        meta = _PLACE_META.get(key, {"area": "a", "icon": "🏠"})
        people = groups.get(key) or []
        sprites = "".join(_static_sprite(p, pidx, home_ids) for p in people) \
            or "<span class='mlempty'>—</span>"
        home_cls = " mlhome" if key == "home" else ""
        cells.append(
            f"<div class='mlbld{home_cls}' style='grid-area:{meta['area']};'>"
            f"<h4>{meta['icon']} {place_label(key)} <small>({len(people)}명)</small></h4>"
            f"<div class='mlppl'>{sprites}</div></div>")
    cells.append("<div class='mlplaza'>🌳 미리 마을 광장 🌳</div></div>")
    st.markdown("".join(cells), unsafe_allow_html=True)
    st.markdown(_legend_md(), unsafe_allow_html=True)


def _legend_md() -> str:
    order = [("unaware", "모름"), ("aware", "알게됨"), ("applied", "신청"),
             ("received", "수령"), ("blocked", "막힘")]
    parts = []
    for k, t in order:
        c = _STATUS_COLOR.get(k, "#9E9E9E")
        parts.append(
            "<span style='font-size:.74rem;margin-right:12px'>"
            "<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
            f"background:{c};border:2px solid #fff;margin-right:3px'></span>{t}</span>")
    parts.append("<span style='font-size:.74rem'>🔒 집에만 머무는 사각지대</span>")
    return "<div>" + "".join(parts) + "</div>"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def render_village_map(village: dict, personas: list,
                       prefer_animation: bool = True, autoplay: bool = False):
    """미리 마을 오버월드 맵 진입점.

    village 가 비어있으면 안내 후 return. 애니 렌더 실패 시 정적 맵으로 자동 강등.
    데모 안전망: 라디오 토글로 발표 중 1클릭 정적 전환 가능.
    """
    village = village or {}
    if not (village.get("residents") or []):
        st.info("마을 시뮬 데이터가 없어 맵을 그릴 수 없습니다.")
        return

    mode = st.radio(
        "맵 보기 모드",
        ["🎮 애니메이션 맵", "📋 정적 맵"],
        index=0 if prefer_animation else 1,
        horizontal=True,
        key="village_map_mode",
        label_visibility="collapsed",
    )

    if mode.startswith("🎮"):
        try:
            payload = _build_payload(village, personas, autoplay=autoplay)
            if not payload["people"]:
                st.info("표시할 주민이 없습니다.")
                return
            _render_animated(payload)
            return
        except Exception as e:  # 어떤 이유로든 애니 실패 → 정적 폴백
            st.caption(f"(애니메이션 맵을 표시할 수 없어 정적 맵으로 전환합니다: {e})")

    _render_static(village, personas)
