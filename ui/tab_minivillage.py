# -*- coding: utf-8 -*-
"""ui/tab_minivillage.py — '미리마을' 생활 시뮬레이션 탭 (Generative Agents).

미리마을(`미리랩/미리마을/`)은 메인 Streamlit 앱과 분리된 **독립 브라우저 시뮬**이다.
캐릭터 10명이 LLM 이 생성한 하루 스케줄대로 시간·장소를 따라 생활하고, 만나면
그날 맥락이 묻어나는 대화를 나눈다. **녹화 방식**이라 재생(playback)은 런타임
LLM 0콜 — 키가 없어도, 발표장에서도 그대로 돈다.

이 탭은 그 standalone `index.html` 을 **외부 의존 0 의 자기완결 HTML** 로 조립해
`components.html` 단일 iframe 으로 임베드한다. 조립 = index.html 이 부르는 외부
자산을 전부 인라인:
  - `<script src="data/*.js">` 3개  → 파일 내용을 인라인 `<script>` 로 치환
  - `<img src="assets/map.png">`     → base64 data URI
  - SPRITE_DEFS 의 `assets/sprites/*.png` 10개 → base64 data URI
조립 직전 "남은 외부 참조 0" 을 단언해 빠진 자산(=빈 사각형)이 없음을 보증한다.
(index.html 폰트는 system-ui, 외부 CSS/CDN/폰트 링크 없음 — grep 확인.)

캐싱: 조립 결과를 관련 파일들의 mtime 으로 캐시한다(`@st.cache_data`). 파일이
바뀌면(향후 정책 주입으로 데이터 JS 재생성 등) 자동 재조립, 아니면 캐시 재사용.
base64 인코딩이 ~10ms 로 충분히 싸서 2단 분리 없이 단일 캐시로 둔다.

격리: state.py / graph / 사이드바를 일절 쓰지 않는다(완전한 섬). render 시그니처는
다른 탭과 동일(view 1개)하되 현 단계(step1)에선 view 를 쓰지 않는다 — 정책 주입
제어판은 step2 에서 얹는다.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# 미리마을 standalone 루트. 이 파일 = 미리랩/ui/tab_minivillage.py → 부모의 부모 = 미리랩.
MINIVILLAGE_ROOT = Path(__file__).resolve().parent.parent / "미리마을"

# index.html 의 <head> 가 로드하는 외부 데이터 JS (등장 순서대로).
_DATA_SCRIPTS = ("data/village_data.js", "data/anchors.js", "data/meetings.js")

# 스프라이트 id 목록 (SPRITE_DEFS.sheet = "assets/sprites/{id}.png" 와 1:1).
_SPRITE_IDS = (
    "minsu", "staff", "owner", "grandma", "sua",
    "junho", "miyoung", "oldman", "jimin", "daeun",
)

_PNG_MIME = "image/png"


def _b64_png_uri(path: Path) -> str:
    """PNG 파일을 data:image/png;base64,... URI 로 인코딩한다."""
    return f"data:{_PNG_MIME};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def assemble_village_html(root: Path) -> str:
    """미리마을 standalone 을 외부 의존 0 의 자기완결 HTML 로 조립해 반환한다.

    streamlit 무의존(순수 함수 → 테스트 가능). 빠진 자산이 있으면 AssertionError 로
    조립 단계에서 바로 드러난다(런타임에 빈 사각형으로 새지 않게).
    """
    html = (root / "index.html").read_text(encoding="utf-8")

    # 1) 데이터 JS 3개 → 인라인 <script> ----------------------------------
    for rel in _DATA_SCRIPTS:
        tag = f'<script src="{rel}"></script>'
        if tag not in html:
            raise AssertionError(f"index.html 에서 스크립트 태그를 못 찾음: {tag}")
        js = (root / rel).read_text(encoding="utf-8")
        # 데이터 안에 </script> 가 있으면 인라인이 조기 종료됨 → 분해(방어적).
        js = js.replace("</script>", "<\\/script>")
        html = html.replace(tag, f"<script>\n{js}\n</script>")

    # 2) 지도 배경 map.png → base64 data URI -------------------------------
    if 'src="assets/map.png"' not in html:
        raise AssertionError("index.html 에서 map.png <img> 를 못 찾음")
    html = html.replace('src="assets/map.png"', f'src="{_b64_png_uri(root / "assets" / "map.png")}"')

    # 3) 스프라이트 10개 → base64 data URI (SPRITE_DEFS.sheet 값) ----------
    for sid in _SPRITE_IDS:
        rel = f"assets/sprites/{sid}.png"
        if rel not in html:
            raise AssertionError(f"index.html 에서 스프라이트 경로를 못 찾음: {rel}")
        html = html.replace(rel, _b64_png_uri(root / "assets" / "sprites" / f"{sid}.png"))

    # 4) "외부 참조 0" 단언 — 빠진 자산은 빈 칸이 되므로 미리 잡는다 -------
    leftovers = re.findall(r'(?:src|href)\s*=\s*["\']\s*(?:\./)?(?:assets|data)/[^"\']*', html)
    leftovers += re.findall(r'(?:\./)?assets/sprites/[A-Za-z0-9_]+\.png', html)
    leftovers += re.findall(r'(?:\./)?assets/map\.png', html)
    if leftovers:
        raise AssertionError(f"인라인 안 된 외부 참조 잔존: {sorted(set(leftovers))[:5]}")

    return html


def _file_signature(root: Path) -> tuple:
    """조립에 영향을 주는 파일들의 (이름, mtime_ns) 서명 — @st.cache_data 키.

    파일이 하나라도 바뀌면 서명이 달라져 캐시가 무효화된다(=재조립).
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


@st.cache_data(show_spinner=False)
def _build_cached(root_str: str, signature: tuple) -> str:
    """서명 기준으로 캐시되는 조립 래퍼. signature 가 같으면 즉시 캐시 반환."""
    return assemble_village_html(Path(root_str))


def render_minivillage_tab(view=None) -> None:
    """'미리마을' 탭을 그린다. (step1 = 기본 하루를 그대로 임베드)"""
    st.subheader("🏘️ 미리마을 — 시민들의 하루")
    st.caption(
        "가상 시민 10명이 LLM 이 생성한 하루 스케줄대로 생활하고, 만나면 그날 맥락이 "
        "묻어나는 대화를 나눕니다. 화면 안의 ▶시작·속도·좌표편집은 모두 브라우저에서만 "
        "동작하며(녹화 재생), 키가 없어도 그대로 재생됩니다."
    )
    st.info(
        "ℹ️ 지금 미리마을은 **정책이 반영되지 않은 '기본 하루'**입니다. "
        "정책 주입은 다음 단계(step2)에서 추가됩니다."
    )

    root = MINIVILLAGE_ROOT
    if not (root / "index.html").exists():
        st.error(f"미리마을을 찾을 수 없습니다: `{root}`")
        return

    try:
        html = _build_cached(str(root), _file_signature(root))
    except Exception as e:  # 조립 실패 시 화면을 깨뜨리지 않고 사유를 보여준다.
        st.error("미리마을 화면을 조립하는 중 오류가 발생했습니다.")
        st.exception(e)
        return

    # height 는 1086px 지도 + 우측 패널을 넉넉히 담도록 잡되, 내부 영역이 자체
    # 스크롤되므로 화면에 맞춰 조절 가능(육안 확인 후 튜닝).
    components.html(html, height=900, scrolling=True)
