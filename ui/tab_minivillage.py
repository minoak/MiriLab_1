# -*- coding: utf-8 -*-
"""ui/tab_minivillage.py — '미리마을' 정책 전파 시뮬레이션 탭 (Generative Agents).

미리마을(`미리랩/미리마을/`)은 메인 앱과 분리된 섬이되, **정책을 일상에 흘려보내는**
미리랩 정체성의 생생한 구현이다. 캐릭터 10명이 LLM 이 생성한 하루 스케줄대로 생활하고
만나면 대화하며, 그 대화로 정책 인지가 사람·만남을 타고 퍼진다(전파). 밤엔 각자
'일기'로 하루를 압축해 다음 날의 기억으로 넘긴다(reflection). 재생(playback)은 0콜.

[step2 = 정책 전파]
- 정책을 최상위 시나리오로 주입 → 프로토타입 시드(복지관 어르신 grandma·oldman)에서
  출발해 만남(대화)을 타고 퍼진다. '다음 날' 버튼으로 일기를 이어가며 며칠이든.
- 생성 = 실 LLM(키 필요). 키 없으면 폴백(정책 미반영 단조). 재생은 키 없이도.
- 엔진은 `미리마을/gen_schedules.py`(스케줄)·`gen_dialogues.py`(run_day: 순차 만남
  +전파+일기) 를 importlib 로 로드해 호출한다.

[임베드]
- standalone `index.html` 을 외부 의존 0 의 자기완결 HTML 로 조립 → `components.html`.
  데이터 JS 3개 인라인 + map/스프라이트 base64. 인라인 데이터의 '<','>' 는 유니코드
  이스케이프해 인라인 <script> 가 조기 종료/주석 파싱으로 깨지지 않게 한다(중요:
  LLM 대사가 meetings.js 로 들어오므로).

격리: 메인 state.py/graph/사이드바 미접촉(섬). 정책 '내용'만 [메인 가져오기] 로 공유.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from ui.rerun_util import rerun_fragment

# 미리마을 standalone 루트. 이 파일 = 미리랩/ui/tab_minivillage.py → 부모의 부모 = 미리랩.
MINIVILLAGE_ROOT = Path(__file__).resolve().parent.parent / "미리마을"
SIM_STATE_PATH = MINIVILLAGE_ROOT / "data" / "sim_state.json"

# 프로토타입 정책 진입 시드: 복지관에서 먼저 접하는 어르신들(사용자 지정).
# (진입구는 추후 프롬프트로 직접 제어 — 지금은 시나리오 상수.)
SEED_IDS = ("grandma", "oldman")

# index.html 의 <head> 가 로드하는 외부 데이터 JS (등장 순서대로).
_DATA_SCRIPTS = ("data/village_data.js", "data/anchors.js", "data/meetings.js")

# 스프라이트 id 목록 (SPRITE_DEFS.sheet = "assets/sprites/{id}.png" 와 1:1).
_SPRITE_IDS = (
    "minsu", "staff", "owner", "grandma", "sua",
    "junho", "miyoung", "oldman", "jimin", "daeun",
)
_PNG_MIME = "image/png"

# 표시용 라벨
_AW_LABEL = {"unaware": "🚫 모름", "aware": "👀 알게 됨",
             "interested": "🙋 관심", "acting": "✅ 행동"}
_STANCE_LABEL = {"unknown": "·", "support": "👍 찬성", "oppose": "👎 반대",
                 "mixed": "🤔 혼합", "anxious": "😟 불안"}
_AWARE_SET = {"aware", "interested", "acting"}


# =====================================================================
# 조립 (외부 의존 0 자기완결 HTML)
# =====================================================================
def _b64_png_uri(path: Path) -> str:
    return f"data:{_PNG_MIME};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _neutralize_inline_js(js: str) -> str:
    """인라인 <script> 안에서 '<','>' 를 유니코드 이스케이프로 바꾼다.

    HTML 파서는 <script> 내용에서도 `</script`, `<script`, `<!--` 토큰을 특별 취급해
    조기 종료/이중 이스케이프 상태로 빠진다. 데이터 JS 는 `const X = <JSON>;` 형태라
    '<','>' 가 문자열 값 안에만 있으므로, '\\u003c'/'\\u003e' 로 바꾸면 JS 엔진은
    값으로 '<','>' 를 그대로 복원하고 HTML 파서는 토큰을 못 본다(XSS 아님 = 렌더 보호).
    """
    return js.replace("<", "\\u003c").replace(">", "\\u003e")


def assemble_village_html(root: Path) -> str:
    """미리마을 standalone 을 외부 의존 0 의 자기완결 HTML 로 조립해 반환한다(순수)."""
    html = (root / "index.html").read_text(encoding="utf-8")

    # 1) 데이터 JS 3개 → 인라인 <script> (값 안의 '<','>' 무력화)
    for rel in _DATA_SCRIPTS:
        tag = f'<script src="{rel}"></script>'
        if tag not in html:
            raise AssertionError(f"index.html 에서 스크립트 태그를 못 찾음: {tag}")
        js = _neutralize_inline_js((root / rel).read_text(encoding="utf-8"))
        html = html.replace(tag, f"<script>\n{js}\n</script>")

    # 2) 지도 배경 map.png → base64 data URI
    if 'src="assets/map.png"' not in html:
        raise AssertionError("index.html 에서 map.png <img> 를 못 찾음")
    html = html.replace('src="assets/map.png"', f'src="{_b64_png_uri(root / "assets" / "map.png")}"')

    # 3) 스프라이트 10개 → base64 data URI
    for sid in _SPRITE_IDS:
        rel = f"assets/sprites/{sid}.png"
        if rel not in html:
            raise AssertionError(f"index.html 에서 스프라이트 경로를 못 찾음: {rel}")
        html = html.replace(rel, _b64_png_uri(root / "assets" / "sprites" / f"{sid}.png"))

    # 4) "외부 참조 0" 단언
    import re
    leftovers = re.findall(r'(?:src|href)\s*=\s*["\']\s*(?:\./)?(?:assets|data)/[^"\']*', html)
    leftovers += re.findall(r'(?:\./)?assets/sprites/[A-Za-z0-9_]+\.png', html)
    leftovers += re.findall(r'(?:\./)?assets/map\.png', html)
    if leftovers:
        raise AssertionError(f"인라인 안 된 외부 참조 잔존: {sorted(set(leftovers))[:5]}")

    return html


def _file_signature(root: Path) -> tuple:
    """조립에 영향을 주는 파일들의 (이름, mtime_ns) 서명 — @st.cache_data 키.

    생성(gen_schedules/run_day)이 village_data.js·meetings.js 를 새로 쓰면 mtime 이
    바뀌어 캐시가 무효화된다(=재조립). 우리 흐름은 항상 파일 쓰기로 갱신되므로 충분.
    """
    paths = [root / "index.html"]
    paths += [root / r for r in _DATA_SCRIPTS]
    paths.append(root / "assets" / "map.png")
    paths += [root / "assets" / "sprites" / f"{s}.png" for s in _SPRITE_IDS]
    sig = []
    for p in paths:
        try:
            sig.append((p.name, p.stat().st_mtime_ns))
        except OSError:
            sig.append((p.name, -1))
    return tuple(sig)


@st.cache_data(show_spinner=False, max_entries=4, ttl=3600)
def _build_cached(root_str: str, signature: tuple) -> str:
    """서명 기준 캐시 조립 래퍼. 누적 방지(max_entries) + 1시간 TTL."""
    return assemble_village_html(Path(root_str))


# =====================================================================
# 엔진(gen 스크립트) 로드 + 하루 생성/상태 영속
# =====================================================================
_GEN_MODULES: dict = {}


def _gen_sig() -> tuple:
    """gen 스크립트 mtime 서명 — 파일이 바뀌면 모듈을 재로드(개발 중 stale 방지)."""
    try:
        return tuple((MINIVILLAGE_ROOT / f).stat().st_mtime_ns
                     for f in ("gen_schedules.py", "gen_dialogues.py"))
    except OSError:
        return ()


def _sync_llm_provider(*mods) -> None:
    """메인 앱 '시민 모델' 선택기의 선택을 gen 모듈에 전파.

    gen 스크립트는 graph.llm 미의존(독립)이 설계라, 다리는 이쪽(메인 UI)에서 놓는다.
    CLI 단독 실행(python 미리마을/gen_*.py)은 .env 의 MIRILAB_LLM 을 그대로 따른다.
    """
    try:
        from graph import llm as _llm
        for m in mods:
            if hasattr(m, "set_provider"):
                m.set_provider(_llm.PROVIDER)
    except Exception:
        pass  # 동기화 실패 시 gen 은 .env 기본값으로 동작(생성 자체는 무해)


def _load_gen():
    """미리마을 gen_schedules·gen_dialogues 를 importlib 로 로드(파일 변경 시 재로드)."""
    sig = _gen_sig()
    if not ("gs" in _GEN_MODULES and _GEN_MODULES.get("_sig") == sig):
        for key, fname, modname in (("gs", "gen_schedules.py", "_miri_gen_schedules"),
                                    ("gd", "gen_dialogues.py", "_miri_gen_dialogues")):
            spec = importlib.util.spec_from_file_location(modname, str(MINIVILLAGE_ROOT / fname))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
            _GEN_MODULES[key] = mod
        _GEN_MODULES["_sig"] = sig
    gs, gd = _GEN_MODULES["gs"], _GEN_MODULES["gd"]
    # 캐시 적중이어도 매번 동기화 — 사용자가 사이드바에서 모델을 바꿨을 수 있다.
    _sync_llm_provider(gs, gd)
    return gs, gd


def _load_sim_state():
    try:
        return json.loads(SIM_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_sim_state(state: dict) -> None:
    SIM_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_day(policy: str, fresh: bool) -> None:
    """fresh=True: 다양화 스케줄 재생성 + 1일차. fresh=False: 저장된 상태로 다음 날.

    실 LLM(키 있으면) 또는 폴백. meetings.js(iframe) 갱신 + sim_state.json 누적.
    """
    gs, gd = _load_gen()
    use_llm = gd.has_real_key()
    if fresh:
        gs.generate(force_fallback=not use_llm)  # 스케줄(동선) 재생성 + village_data.js
        villagers = gd._load("villagers.json")["villagers"]
        states = gd.initial_states(villagers, aware_ids=SEED_IDS)
        day_num, history, pol = 1, [], policy
    else:
        sd = _load_sim_state() or {}
        states = sd.get("states") or {}
        day_num = int(sd.get("current_day", 0)) + 1
        history = sd.get("history") or []
        pol = sd.get("policy", policy)  # 진행 중인 시뮬은 같은 정책 유지
    new_states, rec = gd.run_day(pol, states, day_num)  # 순차 만남+전파+일기, meetings.js 갱신
    history.append({"day": rec["day"], "generated_with": rec["generated_with"],
                    "propagation": rec["propagation"], "diaries": rec["diaries"]})
    _save_sim_state({"policy": pol, "current_day": day_num, "states": new_states,
                     "history": history, "generated_with": rec["generated_with"]})


# =====================================================================
# 렌더
# =====================================================================
def _has_real_key() -> bool:
    try:
        _gs, gd = _load_gen()
        return bool(gd.has_real_key())
    except Exception:
        return False


_POLICY_KEY = "minivillage_policy"


def _pull_main_policy(text: str) -> None:
    """[메인 정책 가져오기] on_click 콜백.

    text_area(key=_POLICY_KEY) 가 이미 그려진 뒤 본문에서 같은 키를 수정하면
    StreamlitAPIException — 콜백은 다음 rerun 의 위젯 생성 *전*에 실행돼 합법.
    """
    st.session_state[_POLICY_KEY] = text


def _run_and_refresh(policy: str, fresh: bool, spinner_msg: str) -> None:
    """생성을 실행하고 성공 시에만 fragment 재실행. 실패는 friendly 에러로 격리.

    (run_day/_generate_day 의 어떤 예외도 fragment 밖으로 새 앱을 깨뜨리지 않게.
    run_day 는 끝에서야 파일을 쓰므로, 중간 실패 시 이전 sim_state 는 보존된다.)
    """
    with st.spinner(spinner_msg):
        try:
            _generate_day(policy, fresh=fresh)
        except Exception as e:
            st.error("미리마을 생성 중 오류가 발생했습니다(이전 상태는 보존됨).")
            st.exception(e)
            return
    rerun_fragment()


def _render_control_panel(view) -> None:
    """정책 입력 + [메인 가져오기] + [▶1일차]/[▶다음날]/[↺리셋]."""
    sd = _load_sim_state()
    # 정책칸 초기값: 진행 중 시뮬의 정책 > 세션 입력값 > 빈칸
    if _POLICY_KEY not in st.session_state:
        st.session_state[_POLICY_KEY] = (sd or {}).get("policy", "") if sd else ""

    with st.container(border=True):
        st.markdown("**🧪 정책 시나리오** — 최상위에 정책을 주입하면 마을에 퍼집니다")
        col_a, col_b = st.columns([4, 1])
        with col_a:
            st.text_area(
                "정책 원문", key=_POLICY_KEY, height=90,
                label_visibility="collapsed",
                placeholder="예) 만 19~34세 무주택 청년에게 월 20만원 임대료를 지원한다.",
            )
        with col_b:
            main_policy = (view or {}).get("policy") if isinstance(view, dict) else None
            st.button("⬇ 메인 정책\n가져오기", use_container_width=True,
                      disabled=not main_policy,
                      help="사이드바 '정책 입력'의 정책 내용을 가져옵니다(프롬프트는 미리마을 전용).",
                      on_click=_pull_main_policy, args=(main_policy or "",))

        if _has_real_key():
            st.caption("🔑 OpenAI 키 감지됨 — 실제 LLM 으로 생성합니다. "
                       "하루 생성 ≈ 만남·일기 20~30콜(~$0.02~0.04, 30~60초). 재생은 0콜.")
        else:
            st.caption("⚠️ OpenAI 키 없음 — 폴백(정책 미반영 단조)으로만 동작합니다. "
                       "전파 관측엔 `.env` 의 OPENAI_API_KEY 가 필요합니다.")

        policy = (st.session_state.get(_POLICY_KEY) or "").strip()
        has_sim = bool(sd and sd.get("history"))
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            if st.button("▶ 1일차 시작 (새 하루)", type="primary", use_container_width=True,
                         help="동선을 새로 뽑고 정책을 주입해 1일차를 생성합니다."):
                if not policy:
                    st.warning("정책을 입력하면 전파를 관측할 수 있어요(빈칸이면 평범한 하루).")
                _run_and_refresh(policy, True,
                                 "동선 생성 + 1일차 시뮬레이션 중... (실 LLM은 30~60초)")
        with c2:
            if st.button("▶ 다음 날", use_container_width=True, disabled=not has_sim,
                         help="어제 일기를 이어받아 다음 하루를 생성합니다(진행 중 정책 유지)."):
                _run_and_refresh(policy, False,
                                 "다음 날 시뮬레이션 중... (실 LLM은 30~60초)")
        with c3:
            if st.button("↺ 리셋", use_container_width=True, disabled=not has_sim,
                         help="시뮬레이션 기록을 비웁니다(0일차로)."):
                try:
                    SIM_STATE_PATH.unlink()
                except OSError:
                    pass
                rerun_fragment()

        if has_sim:
            st.caption("ℹ️ '다음 날'은 진행 중 시뮬의 정책을 그대로 이어갑니다(정책칸을 고쳐도 "
                       "무시). 다른 정책을 실험하려면 [↺ 리셋] 후 [▶ 1일차 시작]을 누르세요.")


def _name_map():
    try:
        _gs, gd = _load_gen()
        return {v["id"]: v["name"] for v in gd._load("villagers.json")["villagers"]}, \
               {l["key"]: l["label"] for l in gd._load("locations.json")["locations"]}
    except Exception:
        return {}, {}


def _render_report() -> None:
    """전파 리포트 — 인지율·사각지대 + 날짜별 전파 경로 + 각 시민 일기."""
    sd = _load_sim_state()
    if not sd or not sd.get("history"):
        st.info("위에서 정책을 입력하고 **▶ 1일차 시작**을 누르면, 정책이 마을에 "
                "어떻게 퍼지는지(누가 언제 알게 됐나)가 여기에 나타납니다.")
        return

    names, labels = _name_map()
    nm = lambda i: names.get(i, i)
    lb = lambda k: labels.get(k, k)
    states = sd.get("states") or {}
    history = sd.get("history") or []
    day = sd.get("current_day", len(history))
    policy = sd.get("policy", "")
    fb = sd.get("generated_with") == "fallback"

    total = len(states) or 10
    aware = [i for i, s in states.items() if s.get("awareness") in _AWARE_SET]
    blind = [i for i, s in states.items() if s.get("awareness") not in _AWARE_SET]

    st.divider()
    head = f"### 📣 {day}일차까지 — 정책이 {len(aware)}/{total}명에게 닿음"
    st.markdown(head)
    if policy:
        st.caption(f"시나리오: {policy[:80]}" + ("…" if len(policy) > 80 else ""))
    if fb:
        st.warning("⚠️ 폴백(키 없음)으로 생성됨 — 정책 반영이 단조롭습니다. 실 LLM 권장.")

    # 인지율 막대 + 사각지대
    c1, c2, c3 = st.columns(3)
    c1.metric("정책 인지", f"{len(aware)}/{total}명")
    interested = sum(1 for s in states.values() if s.get("awareness") in ("interested", "acting"))
    c2.metric("관심·행동", f"{interested}명")
    c3.metric("사각지대(끝내 모름)", f"{len(blind)}명")
    if blind:
        st.caption("🚫 아직 못 들은 사람: " + ", ".join(nm(i) for i in blind))

    # 날짜별 전파 경로
    with st.expander("🔗 전파 경로 (누가 → 누구에게, 언제·어디서)", expanded=True):
        any_edge = False
        for rec in history:
            edges = rec.get("propagation") or []
            if not edges:
                continue
            any_edge = True
            st.markdown(f"**{rec['day']}일차**")
            for e in edges:
                t = e.get("time", 0)
                hhmm = f"{t // 60:02d}:{t % 60:02d}"
                st.markdown(f"- {nm(e.get('from'))} → **{nm(e.get('to'))}**  "
                            f"<span style='color:#888;font-size:0.85em;'>"
                            f"{hhmm} · {lb(e.get('place'))}</span>", unsafe_allow_html=True)
        if not any_edge:
            st.caption("아직 전파가 일어나지 않았습니다(시드만 알고 있음). '다음 날'로 이어가 보세요.")

    # 각 시민의 일기 (최신 날 우선)
    st.markdown("#### 📔 시민들의 일기")
    for rec in reversed(history):
        with st.expander(f"{rec['day']}일차 밤 — 10명의 일기",
                         expanded=(rec is history[-1])):
            for vid, d in (rec.get("diaries") or {}).items():
                aw = _AW_LABEL.get(d.get("awareness"), d.get("awareness", ""))
                stc = _STANCE_LABEL.get(d.get("stance"), "")
                badge = f"<span style='font-size:0.8em;color:#666;'>{aw} · {stc}</span>"
                st.markdown(f"**{nm(vid)}** {badge}", unsafe_allow_html=True)
                st.markdown(f"<div style='color:#444;margin:-4px 0 8px 0;font-size:0.92em;'>"
                            f"{(d.get('diary') or '').strip()}</div>", unsafe_allow_html=True)


@st.fragment   # 탭 안 정책 생성/다음날 버튼의 rerun 이 전체 앱을 다시 그려 첫 탭으로 튕기지 않도록 조각 격리
def render_minivillage_tab(view=None) -> None:
    """'미리마을' 정책 전파 시뮬 탭."""
    st.subheader("🏘️ 미리마을 — 정책이 퍼지는 하루")
    st.caption(
        "정책을 최상위에 주입하면, 시민 10명이 스케줄대로 생활·대화하며 그 소식이 "
        "사람·만남을 타고 퍼집니다. 밤마다 각자 일기로 하루를 정리해 다음 날로 이어가요. "
        "복지관 어르신 두 분이 먼저 접한 상태에서 출발합니다(프로토타입 시드)."
    )

    # 제어판 + 전파 리포트
    _render_control_panel(view)
    _render_report()

    # 마을 재생(iframe) — 최신 날
    st.divider()
    st.markdown("##### 🎮 마을 재생 (브라우저 안에서 ▶시작 — 키 없이도 재생)")
    root = MINIVILLAGE_ROOT
    if not (root / "index.html").exists():
        st.error(f"미리마을을 찾을 수 없습니다: `{root}`")
        return
    try:
        html = _build_cached(str(root), _file_signature(root))
    except Exception as e:
        st.error("미리마을 화면을 조립하는 중 오류가 발생했습니다.")
        st.exception(e)
        return
    components.html(html, height=900, scrolling=True)
