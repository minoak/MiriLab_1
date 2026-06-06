# -*- coding: utf-8 -*-
"""미리랩 발표자료(.pptx) 생성 스크립트.

사용법:  python _make_pptx.py
출력:    notebooks/미리랩_발표.pptx  (19슬라이드, 발표자 노트 포함)

- 내용 출처: notebooks/발표_구현정리.md + eval/cluster_report.md + eval 시각화 2종
- 스크린샷 자리는 회색 점선 박스(📸)로 비워둠 — 캡처 후 교체
- 다시 만들려면 이 스크립트만 재실행 (기존 pptx 덮어씀)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

try:  # 점선 테두리 (없으면 실선으로 폴백)
    from pptx.enum.line import MSO_LINE

    DASH = MSO_LINE.DASH
except Exception:  # pragma: no cover
    DASH = None

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "notebooks" / "미리랩_발표.pptx"
ASSETS = ROOT / "notebooks" / "_pptx_assets"

# ---------------------------------------------------------------- 팔레트
NAVY = RGBColor(0x1F, 0x3A, 0x5F)      # 본문 제목/메인
BLUE = RGBColor(0x2D, 0x6C, 0xDF)      # 포인트
INK = RGBColor(0x1F, 0x29, 0x37)       # 본문 텍스트
SUB = RGBColor(0x6B, 0x72, 0x80)       # 보조 텍스트
GREEN = RGBColor(0x2E, 0x9E, 0x6B)     # 수혜
ORANGE = RGBColor(0xE8, 0x90, 0x2A)    # 경계
RED = RGBColor(0xD9, 0x53, 0x4F)       # 사각지대
CARD = RGBColor(0xF4, 0xF6, 0xFA)      # 카드 배경
LINE = RGBColor(0xDD, 0xE3, 0xEC)      # 카드 테두리
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PALE_NAVY = RGBColor(0xEA, 0xF0, 0xF8)
PALE_GREEN = RGBColor(0xEA, 0xF6, 0xF0)
PALE_ORANGE = RGBColor(0xFD, 0xF3, 0xE4)
PALE_RED = RGBColor(0xFC, 0xEC, 0xEB)
GRAY_BG = RGBColor(0xF1, 0xF3, 0xF7)
GRAY_BORDER = RGBColor(0x9A, 0xA5, 0xB1)

FONT = "맑은 고딕"
SW, SH = 13.333, 7.5  # 슬라이드 크기(인치)


# ---------------------------------------------------------------- 헬퍼
def _font(run, *, size=14, bold=False, color=INK, italic=False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    f.name = FONT
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", FONT)


def tb(slide, x, y, w, h, *, anchor=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    if anchor:
        tf.vertical_anchor = anchor
    return tf


def para(tf, content, *, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
         after=4, before=0, lh=1.12, first=False, italic=False):
    """content: str 또는 [(str, {스타일 오버라이드}), ...]"""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_after = Pt(after)
    p.space_before = Pt(before)
    p.line_spacing = lh
    if isinstance(content, str):
        content = [(content, {})]
    for text, ov in content:
        r = p.add_run()
        r.text = text
        _font(r, size=ov.get("size", size), bold=ov.get("bold", bold),
              color=ov.get("color", color), italic=ov.get("italic", italic))
    return p


def box(slide, x, y, w, h, *, fill=CARD, line=LINE, lw=0.75, dash=False,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            s.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
        if dash and DASH is not None:
            s.line.dash_style = DASH
    s.shadow.inherit = False
    s.text_frame.word_wrap = True
    s.text_frame.margin_left = s.text_frame.margin_right = Inches(0.12)
    s.text_frame.margin_top = s.text_frame.margin_bottom = Inches(0.06)
    return s


def chip(slide, x, y, text, *, fill=NAVY, color=WHITE, size=11, w=1.6, h=0.3):
    c = box(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    tf = c.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, text, size=size, bold=True, color=color, align=PP_ALIGN.CENTER,
         after=0, first=True)
    return c


def header(slide, no, sec, title, *, accent=NAVY, title_size=27):
    chip(slide, 0.6, 0.42, sec, fill=accent, w=1.75, h=0.32)
    t = tb(slide, 0.6, 0.82, SW - 1.2, 0.75)
    para(t, title, size=title_size, bold=True, color=NAVY, first=True, after=0)
    # 푸터
    f = tb(slide, 0.6, SH - 0.36, SW - 1.2, 0.3)
    para(f, [("미리랩", {"bold": True, "color": SUB}),
             ("  ·  AI 시민 사회 정책 실험실", {"color": SUB})],
         size=9, first=True, after=0)
    n = tb(slide, SW - 1.2, SH - 0.36, 0.6, 0.3)
    para(n, str(no), size=9, color=SUB, align=PP_ALIGN.RIGHT, first=True, after=0)


def shot(slide, x, y, w, h, label, sub="앱에서 캡처한 뒤, 이 박스를 지우고 이미지를 넣어주세요"):
    s = box(slide, x, y, w, h, fill=GRAY_BG, line=GRAY_BORDER, lw=1.2,
            dash=True, radius=0.04)
    tf = s.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, "📸 " + label, size=14, bold=True, color=SUB,
         align=PP_ALIGN.CENTER, first=True, after=2)
    para(tf, sub, size=10, color=GRAY_BORDER, align=PP_ALIGN.CENTER, after=0)
    return s


def img_fit(slide, path, x, y, w, h):
    """비율 유지로 (x,y,w,h) 박스 안에 이미지 배치(가운데 정렬)."""
    iw, ih = Image.open(path).size
    box_ratio, img_ratio = w / h, iw / ih
    if img_ratio >= box_ratio:
        dw, dh = w, w / img_ratio
    else:
        dh, dw = h, h * img_ratio
    px = x + (w - dw) / 2
    py = y + (h - dh) / 2
    return slide.shapes.add_picture(str(path), Inches(px), Inches(py),
                                    Inches(dw), Inches(dh))


def note(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def role_card(slide, x, y, w, h, color, pale, title, lines, *, title_size=14,
              body_size=11.5):
    box(slide, x, y, w, h, fill=pale, line=color, lw=1.0)
    box(slide, x, y, 0.07, h, fill=color, line=None, radius=0.5)
    tf = tb(slide, x + 0.2, y + 0.12, w - 0.35, h - 0.24)
    para(tf, title, size=title_size, bold=True, color=color, first=True, after=4)
    for ln in lines:
        para(tf, ln, size=body_size, color=INK, after=2, lh=1.15)


def flow_box(slide, x, y, w, h, title, body, *, fill=PALE_NAVY, line_c=NAVY,
             tcolor=NAVY, tsize=12.5, bsize=10.5):
    box(slide, x, y, w, h, fill=fill, line=line_c, lw=1.0)
    tf = tb(slide, x + 0.12, y + 0.08, w - 0.24, h - 0.16)
    para(tf, title, size=tsize, bold=True, color=tcolor, first=True, after=2)
    if body:
        for ln in body if isinstance(body, list) else [body]:
            para(tf, ln, size=bsize, color=INK, after=1, lh=1.12)


def arrow_text(slide, x, y, w, ch="→", *, size=18, color=SUB):
    t = tb(slide, x, y, w, 0.4)
    para(t, ch, size=size, bold=True, color=color, align=PP_ALIGN.CENTER,
         first=True, after=0)


def bullets(tf, items, *, size=13, after=5, lh=1.18, first_done=False):
    for i, it in enumerate(items):
        if isinstance(it, tuple):
            text, ov = it
        else:
            text, ov = it, {}
        content = [("•  ", {"color": ov.get("bullet_color", BLUE), "bold": True})]
        if isinstance(text, list):  # 이미 (run, style) 리스트인 경우
            content.extend(text)
        else:
            content.append((text, ov))
        para(tf, content, size=ov.get("size", size), after=ov.get("after", after),
             lh=lh, first=(i == 0 and not first_done))


# ---------------------------------------------------------------- 스프라이트 준비
def prep_sprites():
    ASSETS.mkdir(exist_ok=True)
    defs = json.loads((ROOT / "미리마을" / "assets" / "sprite_defs.json")
                      .read_text(encoding="utf-8"))
    out = {}
    for key, d in defs.items():
        sheet = ROOT / "미리마을" / d["sheet"].replace("/", os.sep)
        if not sheet.exists():
            continue
        cell = d.get("cell", 48)
        img = Image.open(sheet).convert("RGBA")
        # 정면(down) 행의 가운데 프레임
        row = d.get("rowMap", {}).get("down", 0)
        frame = img.crop((cell, row * cell, cell * 2, (row + 1) * cell))
        if frame.getbbox() is None:  # 빈 프레임이면 첫 프레임
            frame = img.crop((0, row * cell, cell, (row + 1) * cell))
        frame = frame.resize((cell * 4, cell * 4), Image.NEAREST)
        p = ASSETS / f"sprite_{key}.png"
        frame.save(p)
        out[key] = p
    return out


# ================================================================ 슬라이드들
def s01_title(prs, sprites):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # 상단 컬러 바
    box(slide, 0, 0, SW, 0.18, fill=NAVY, line=None,
        shape=MSO_SHAPE.RECTANGLE)
    t = tb(slide, 1.0, 1.55, SW - 2.0, 3.6)
    para(t, "미리랩", size=64, bold=True, color=NAVY, first=True, after=2)
    para(t, "MiriLab — AI 시민 사회 정책 실험실", size=20, color=BLUE,
         bold=True, after=18)
    para(t, "정책을 배포하기 전에,", size=22, color=INK, after=2)
    para(t, [("실제 한국 인구통계 기반 ", {}),
             ("AI 가상 시민", {"bold": True, "color": BLUE}),
             ("에게 먼저 물어본다.", {})], size=22, color=INK, after=16)
    para(t, [("수혜 ", {"bold": True, "color": GREEN}),
             ("·  ", {"color": SUB}),
             ("경계 ", {"bold": True, "color": ORANGE}),
             ("·  ", {"color": SUB}),
             ("사각지대 ", {"bold": True, "color": RED}),
             ("— 같은 정책, 다른 인생", {"color": SUB})], size=15, after=0)
    # 하단: 스프라이트 행렬
    keys = ["minsu", "sua", "owner", "staff", "grandma", "oldman", "miyoung",
            "junho", "jimin", "daeun"]
    x = 1.0
    for k in keys:
        p = sprites.get(k)
        if p:
            slide.shapes.add_picture(str(p), Inches(x), Inches(5.6),
                                     Inches(0.62), Inches(0.62))
            x += 0.78
    info = tb(slide, 1.0, 6.55, SW - 2.0, 0.6)
    para(info, "DLthon 2  ·  팀명/발표자 (채워주세요)  ·  2026. 06.",
         size=13, color=SUB, first=True, after=0)
    note(slide, "안녕하세요, 저희는 '미리랩'을 만들었습니다. "
         "미리랩은 정책을 배포하기 '전에' AI 가상 시민 사회에서 '미리' 반응을 실험하는 "
         "랩(Lab)입니다. 아래 캐릭터들은 실제로 저희 시뮬레이션 속에서 살아가는 "
         "가상 시민들인데, 발표 마지막에 이 친구들이 마을에서 직접 움직이는 모습을 "
         "보여드리겠습니다. (팀명·발표자 이름은 슬라이드에 채워주세요)")


def s02_agenda(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 2, "발표 흐름", "오늘 이야기의 순서 — 약 12~15분")
    rows = [
        ("01", "문제와 컨셉", "정책은 왜 시민에게 닿지 못하는가 → 미리랩의 답", "약 2분", NAVY),
        ("02", "시스템", "페르소나 파이프라인 + 두 축(시민 반응 / 정책 인생극장)", "약 3분", BLUE),
        ("03", "시행착오", "왜 이 모양이 되었나 — 막다른 길 3가지", "약 3분", ORANGE),
        ("04", "신뢰성 검증", "ablation + 집단화·견고성·설득력 (정량)", "약 2.5분", GREEN),
        ("05", "확장 구현", "게시판 RAG + 미리마을 + 60초 라이브 재생 데모", "약 3분", RED),
        ("06", "한계와 마무리", "팀 규율 → 정직한 한계 → 핵심 메시지 → Q&A", "약 2분", SUB),
    ]
    y = 1.75
    for no, sec, desc, time, color in rows:
        box(slide, 0.6, y, 12.13, 0.74, fill=CARD, line=LINE)
        c = box(slide, 0.78, y + 0.13, 0.48, 0.48, fill=color, line=None,
                shape=MSO_SHAPE.OVAL)
        tfc = c.text_frame
        tfc.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tfc, no, size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
             first=True, after=0)
        t = tb(slide, 1.5, y + 0.09, 9.4, 0.6, anchor=MSO_ANCHOR.MIDDLE)
        para(t, [(sec + "   ", {"bold": True, "size": 15, "color": NAVY}),
                 (desc, {"color": SUB, "size": 12.5})], first=True, after=0)
        tt = tb(slide, 11.0, y + 0.09, 1.55, 0.6, anchor=MSO_ANCHOR.MIDDLE)
        para(tt, time, size=12, bold=True, color=color, align=PP_ALIGN.RIGHT,
             first=True, after=0)
        y += 0.86
    note(slide, "발표는 여섯 부분입니다. 문제의식에서 출발해, 시스템 두 축을 보여드리고, "
         "이 모양에 도달하기까지의 시행착오를 솔직하게 공유합니다. 그리고 '이걸 믿을 수 "
         "있나'에 대한 정량 검증, 마지막으로 확장 구현(게시판 RAG와 미리마을)과 한계를 "
         "말씀드립니다. — 섹션 단위로 발표자를 나누기 좋게 구성했습니다. 10분 버전이 "
         "필요하면 02·04·05를 한 장씩 줄이는 걸 추천합니다.")


def s03_problem(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 3, "01 문제", "정책은 왜 시민에게 닿지 못하는가")
    cards = [
        ("정보 격차", "내가 대상자인지\n조차 모른다"),
        ("이해도 부족", "문구가 어렵고\n신청 조건이 불명확하다"),
        ("디지털 장벽", "시니어에겐 온라인 신청\n자체가 벽이다"),
        ("도달 실패", "발표돼도 닿지 않는다\n— “그림의 떡”"),
    ]
    x = 0.6
    for title, body in cards:
        box(slide, x, 1.85, 2.93, 1.75, fill=PALE_RED, line=RED, lw=1.0)
        tf = tb(slide, x + 0.18, 2.05, 2.6, 1.4)
        para(tf, title, size=16, bold=True, color=RED, first=True, after=6)
        for ln in body.split("\n"):
            para(tf, ln, size=12.5, color=INK, after=1, lh=1.2)
        x += 3.07
    # 하단 핵심 대비
    box(slide, 0.6, 4.0, 12.13, 2.6, fill=PALE_NAVY, line=NAVY, lw=1.0)
    tf = tb(slide, 0.95, 4.25, 11.5, 2.2)
    para(tf, "기존 서비스의 한계", size=15, bold=True, color=NAVY, first=True,
         after=8)
    para(tf, [("정부24 챗봇 · 복지로  →  정책을 ", {}),
              ("‘찾는’ 사람", {"bold": True, "color": BLUE}),
              ("을 돕는다 (검색·매칭)", {})], size=15, after=6)
    para(tf, [("그러나 정책을 ", {}),
              ("‘만드는’ 사람(입안자)", {"bold": True, "color": RED}),
              ("이 “이 정책, 배포하면 누가 못 받을까?”를", {})], size=15,
         after=2)
    para(tf, "배포 전에 미리 볼 수 있는 도구는 없다.", size=15, bold=True, after=0)
    note(slide, "정부와 지자체는 매년 수천 건의 정책을 발표하지만, 정작 필요한 사람에게 "
         "닿지 못하는 구조적 누수가 반복됩니다. 모르거나, 어렵거나, 디지털이 벽이거나, "
         "발표돼도 닿지 않거나. 기존 서비스는 전부 정책을 '찾는' 시민을 돕는 도구입니다. "
         "정책을 '만드는' 입안자가 배포 전에 '누가 못 받을지'를 미리 보는 도구는 없습니다. "
         "저희는 바로 그 빈자리를 노렸습니다.")


def s04_concept(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 4, "01 컨셉", "미리랩 — 정책을 시민 입장에서 ‘미리’ 실험한다")
    box(slide, 0.6, 1.75, 12.13, 1.05, fill=PALE_NAVY, line=NAVY, lw=1.0)
    tf = tb(slide, 0.95, 1.95, 11.5, 0.7, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, [("“누가 이해 못 하고 · 누가 신청 못 하고 · 어디서 막히는지”",
               {"bold": True, "color": NAVY}),
              ("를 배포 전에 보여준다", {})], size=17, first=True, after=0,
         align=PP_ALIGN.CENTER)
    # 핵심 장면: 같은 정책, 다른 인생
    t = tb(slide, 0.6, 3.05, 12.13, 0.45)
    para(t, [("핵심 장면 — 같은 ‘청년 월세 지원’ 정책, 6개월 후",
              {"bold": True, "size": 15, "color": INK})], first=True, after=0)
    role_card(slide, 0.6, 3.6, 3.93, 2.3, GREEN, PALE_GREEN, "수혜  ·  A (26세 청년)",
              ["복지로에서 5분 만에 신청,", "월세 부담이 줄어", "첫 저축을 시작했다."],
              body_size=13)
    role_card(slide, 4.7, 3.6, 3.93, 2.3, ORANGE, PALE_ORANGE, "경계  ·  B (46세 중장년)",
              ["본인은 대상이 아니지만", "자녀를 위해 알아보고", "대신 신청해 준다."],
              body_size=13)
    role_card(slide, 8.8, 3.6, 3.93, 2.3, RED, PALE_RED, "사각지대  ·  C (74세 고령)",
              ["6개월이 지나도", "정책의 존재조차", "알지 못했다."], body_size=13)
    t2 = tb(slide, 0.6, 6.15, 12.13, 0.6)
    para(t2, "“같은 정책, 다른 인생.” — 미리랩은 이 갈림을 배포 전에 보여준다",
         size=18, bold=True, color=NAVY, align=PP_ALIGN.CENTER, first=True, after=0)
    note(slide, "미리랩의 한 줄 포지셔닝입니다. 같은 청년 월세 정책이라도 26세 청년은 "
         "5분 만에 신청해 혜택을 받고, 46세 중장년은 자녀를 위해 대신 신청해 주고, "
         "74세 어르신은 6개월이 지나도 존재조차 모릅니다. '같은 정책, 다른 인생' — "
         "이 갈림을 배포 전에 미리 보여주는 것이 미리랩입니다. 이 세 가지 색(수혜·경계·"
         "사각)이 오늘 발표 전체를 관통하는 색입니다.")


def s05_system(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 5, "02 시스템", "시스템 한눈에 — 페르소나 위의 두 축")
    flow_box(slide, 3.27, 1.7, 6.8, 1.0, "페르소나 파이프라인  (data/personas.py)",
             "nvidia/Nemotron-Personas-Korea → 결정론 signals 파생 → 캐시",
             fill=PALE_NAVY, line_c=NAVY, tsize=13, bsize=11)
    arrow_text(slide, 5.0, 2.72, 1.2, "↓")
    arrow_text(slide, 7.2, 2.72, 1.2, "↓")
    flow_box(slide, 0.6, 3.12, 6.0, 2.0, "축 A — 시민 반응 (집단의 온도)",
             ["react → interact → aggregate  (LangGraph 3노드)",
              "시민 전원 5축 점수 (이해 · 수혜 · 의향 · 불만 · 공유)",
              "게이지 3종 + 시민 반응 히트맵 + 신청 여정 분석",
              "집계 → 수정안 → 같은 시민으로 A/B 재검증 (개선 폐루프)"],
             fill=PALE_GREEN, line_c=GREEN, tcolor=GREEN, tsize=14, bsize=11.5)
    flow_box(slide, 6.93, 3.12, 5.8, 2.0, "축 B — 정책 인생극장 (개인의 궤적)",
             ["전원 시간경과 시뮬 (1 · 3 · 6개월)",
              "실제 결과에서 대조 3명 선별 (수혜/경계/사각)",
              "접근 여정 추적 — 경로(reached_via) · 막힘(barrier)",
              "전체 풀 분포 헤드라인 (대표성 보완)"],
             fill=PALE_ORANGE, line_c=ORANGE, tcolor=ORANGE, tsize=14, bsize=11.5)
    arrow_text(slide, 6.07, 5.14, 1.2, "↓")
    flow_box(slide, 0.6, 5.55, 12.13, 1.15, "Streamlit 7탭 앱  (app.py)",
             ["정책 입력 · 시민 반응 · 정책 인생극장 · SNS 채팅방 · 정책 개선 · 게시판(RAG) · 미리마을",
              "mock 모드 = API 키 없이 전체 UI 데모 가능 (발표 안전망)"],
             fill=CARD, line_c=NAVY, tsize=13, bsize=11.5)
    note(slide, "전체 구조입니다. 바닥에는 실제 한국 인구통계 기반 페르소나 파이프라인이 "
         "있고, 그 위에 두 축이 섭니다. 축 A '시민 반응'은 집단의 온도 — 시민 전원이 "
         "정책에 점수와 입장으로 반응하고 게이지·히트맵으로 집계됩니다. 축 B '정책 "
         "인생극장'은 개인의 궤적 — 1·3·6개월 시간 경과 속에서 각자의 인생이 어떻게 "
         "갈리는지 봅니다. 이 모든 게 Streamlit 7탭 앱으로 통합돼 있고, API 키가 없어도 "
         "mock 모드로 전체 데모가 돌아갑니다. 발표 중 네트워크가 죽어도 데모는 안 죽습니다.")


def s06_persona(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 6, "02 시스템", "페르소나 — “손으로 만들지 않는다”")
    tf = tb(slide, 0.6, 1.75, 5.9, 4.6)
    para(tf, "원칙: 그럴듯한 가짜 대신, 실제 통계", size=16, bold=True,
         color=NAVY, first=True, after=8)
    bullets(tf, [
        ([("nvidia/Nemotron-Personas-Korea", {"bold": True, "color": BLUE}),
          ("  — 통계청·대법원·건보공단 기반 합성 데이터셋", {})], {}),
        ("약 100만 행 × 26컬럼, CC BY 4.0 (상업 활용 가능)", {}),
        ("첫 샤드(220MB)만 + seed 고정 샘플링 + 로컬 캐시", {}),
        ([("→ 재현성 ", {"bold": True}),
          ("(발표마다 같은 시민, 오프라인에서도 동작)", {"color": SUB})], {}),
    ], size=13.5, after=7, first_done=True)
    para(tf, "", size=6, after=2)
    para(tf, "왜 중요한가", size=15, bold=True, color=NAVY, after=6)
    para(tf, "개요 초안은 “페르소나 20~30명 직접 설계”였다. 손으로 만들면 "
         "우리가 보고 싶은 반응을 심게 된다. 실제 분포에서 샘플링하면 "
         "‘시드 안에 이미 사각지대 인물이 들어 있다.’",
         size=13, color=INK, after=0, lh=1.3)
    # 우측: 결정론 신호 표
    bx, by, bw = 6.85, 1.75, 5.88
    box(slide, bx, by, bw, 4.6, fill=CARD, line=LINE)
    tf2 = tb(slide, bx + 0.25, by + 0.2, bw - 0.5, 4.2)
    para(tf2, "데이터에 없는 신호는 결정론으로 유도 (LLM 0콜)", size=14,
         bold=True, color=NAVY, first=True, after=8)
    rows = [
        ("digital_literacy", "나이 기본점수 × 학력 배율 × 직업 가감 (65세↑ 급락)"),
        ("income_level", "직업 키워드 우선 (무직·학생→low, 전문직→high) + 학력 보정"),
        ("government_trust", "uuid 해시 지터 0.5±0.1 — 같은 사람은 항상 같은 값"),
        ("social_network", "가구·직업 기반 태그 (독거→복지관·경로당, 자녀→가족 단톡방)"),
    ]
    for name, desc in rows:
        para(tf2, [(name, {"bold": True, "color": BLUE, "size": 12.5})], after=1)
        para(tf2, desc, size=11.5, color=INK, after=7, lh=1.15)
    para(tf2, "같은 입력 → 항상 같은 출력. “판단은 LLM, 사실은 코드” 철학의 시작.",
         size=11.5, bold=True, color=SUB, after=0)
    note(slide, "페르소나는 손으로 만들지 않았습니다. NVIDIA가 통계청 등 실제 통계로 "
         "합성한 100만 행 데이터셋에서 seed 고정으로 샘플링합니다. 손으로 만들면 보고 "
         "싶은 반응을 심게 되니까요. 실제 분포에서 뽑으면 사각지대 인물이 '이미 시드 안에' "
         "들어 있습니다. 데이터셋에 없는 디지털 문해력·소득 같은 신호는 LLM이 아니라 "
         "순수 파이썬 규칙으로 유도해서, 같은 입력이면 항상 같은 값이 나옵니다 — "
         "재현성이 발표 안정성이기도 합니다.")


def s07_axis_a(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 7, "02 시스템", "축 A — 시민 반응: 집단의 온도를 잰다")
    # 좌측 플로우 + 설명
    fx, fw = 0.6, 5.6
    flow_box(slide, fx, 1.8, fw, 0.92, "① react — 1차 반응",
             "시민 각자: 입장(찬/반/혼합) + 5축 점수 (이해·수혜·의향·불만·공유, 0~100)",
             fill=PALE_GREEN, line_c=GREEN, tcolor=GREEN, tsize=12.5, bsize=10.5)
    arrow_text(slide, fx + fw / 2 - 0.6, 2.74, 1.2, "↓", size=14)
    flow_box(slide, fx, 3.08, fw, 0.83, "② interact — 2차 상호작용",
             "다른 시민들의 반응 요약을 보고 입장 변화",
             fill=PALE_GREEN, line_c=GREEN, tcolor=GREEN, tsize=12.5, bsize=10.5)
    arrow_text(slide, fx + fw / 2 - 0.6, 3.93, 1.2, "↓", size=14)
    flow_box(slide, fx, 4.27, fw, 0.92, "③ aggregate — 집계·제안",
             "갈등/합의 요약 + 수정안(개선 반영 정책) 생성",
             fill=PALE_GREEN, line_c=GREEN, tcolor=GREEN, tsize=12.5, bsize=10.5)
    tf = tb(slide, fx, 5.4, fw, 1.55)
    para(tf, "화면 산출", size=13, bold=True, color=NAVY, first=True, after=4)
    bullets(tf, [
        ("게이지 3종 — 정책수용도 · 신청의향지수 · 사회혼란도(=불만 평균)", {}),
        ("시민 전원 × 점수 히트맵 (행 클릭 → 그 시민의 ‘한마디’)", {}),
        ("신청 여정 분석 — 퍼널 · 연령대 접근성 · 병목 TOP3", {}),
        ("정책 개선 탭 — 수정안을 같은 시민 코호트로 A/B 재검증", {}),
    ], size=11, after=2.5, first_done=True)
    # 우측 스크린샷
    shot(slide, 6.5, 1.8, 6.23, 5.0, "‘시민 반응’ 탭 캡처",
         "게이지 3종 + 히트맵이 같이 보이는 화면 추천")
    note(slide, "축 A는 LangGraph 3노드 파이프라인입니다. 시민 각자가 정책에 1차 "
         "반응하고(react), 다른 시민의 반응을 본 뒤 입장을 바꾸기도 하고(interact), "
         "마지막에 분석가 노드가 집계해서 수정안까지 제안합니다(aggregate). 화면에는 "
         "게이지 3종과 시민 전원의 히트맵이 뜨고, 행을 클릭하면 그 시민의 생생한 "
         "한마디가 보입니다. 그리고 여기서 끝나지 않고 — 진단된 병목으로 수정안을 만들어 "
         "'같은 시민'에게 다시 실험하는 A/B 폐루프까지 닫혀 있습니다. 진단→수정→재실험, "
         "그래서 '실험실'입니다. (캡처는 데모 시뮬 돌린 직후 시민 반응 탭 화면을 권장) "
         "[Q&A 대비 — 사회혼란도 정의: 3번의 재정의 끝에 '반발 강도 = 불만 점수 평균'으로 "
         "확정. v1 양극화는 '전쟁=전원 반대'에서 혼란도가 낮게 나와 폐기(이름≠측정), "
         "v2 사각지대(benefit−intent)는 데모에서 0이라 폐기. 찬반 갈림은 stance 분포 바가, "
         "'왜' 화났는지는 서사가 맡음 — 정량은 게이지, 정성은 서사로 분리.]")


def s08_axis_b(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 8, "02 시스템", "축 B — 정책 인생극장: 개인의 궤적을 따라간다")
    fx, fw = 0.6, 5.6
    flow_box(slide, fx, 1.8, fw, 0.86, "① 전원 시간경과 시뮬 (1 · 3 · 6개월)",
             "시점마다: 장소 + 경로 + 행동 서사 + 상태 + 막힌 지점",
             fill=PALE_ORANGE, line_c=ORANGE, tcolor=ORANGE, tsize=12.5, bsize=10.5)
    arrow_text(slide, fx + fw / 2 - 0.6, 2.68, 1.2, "↓", size=14)
    flow_box(slide, fx, 3.02, fw, 0.86, "② 실제 결과에서 대조 3명 선별",
             "받음 → 수혜 / 진행 중 → 경계 / 막힘·못 닿음 → 사각",
             fill=PALE_ORANGE, line_c=ORANGE, tcolor=ORANGE, tsize=12.5, bsize=10.5)
    arrow_text(slide, fx + fw / 2 - 0.6, 3.9, 1.2, "↓", size=14)
    flow_box(slide, fx, 4.24, fw, 0.95, "③ 접근 여정 카드",
             "🧭 알게됨 → 신청 → ⛔막힘  (경로·막힌 지점·삶의 변화)",
             fill=PALE_ORANGE, line_c=ORANGE, tcolor=ORANGE, tsize=12.5, bsize=10.5)
    tf = tb(slide, fx, 5.42, fw, 1.4)
    para(tf, [("채널 5곳이 사각지대의 표현 장치  ",
               {"bold": True, "color": NAVY, "size": 13})], first=True, after=4)
    para(tf, "복지로(온라인) · 주민센터 · 복지관 · 직장/시장 · 집", size=12,
         color=INK, after=3)
    para(tf, "청년은 복지로에서 5분 — 고령은 어디에도 못 닿아 ‘집’에 갇힌다.",
         size=12, bold=True, color=RED, after=0)
    shot(slide, 6.5, 1.8, 6.23, 5.0, "‘정책 인생극장’ 탭 캡처",
         "대조 3명 카드 + 여정 띠(알게됨→신청→막힘)가 보이는 화면 추천")
    note(slide, "축 B 정책 인생극장입니다. 시민 전원을 1·3·6개월 시간 경과 속에서 "
         "살게 하고, 그 '실제 결과'에서 수혜·경계·사각 세 사람을 뽑아 카드로 보여줍니다. "
         "카드를 펼치면 '알게 됨 → 신청 → 서류에서 막힘' 같은 여정 띠와 함께, 어떤 "
         "경로로 알게 됐고 어디서 막혔는지가 서사로 나옵니다. 장소 5곳이 사각지대의 "
         "표현 장치인데, 청년은 복지로에서 5분이면 끝나는 일이 고령 어르신에겐 어느 "
         "채널로도 닿지 못하는 일이 됩니다.")


def s09_scope(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 9, "03 시행착오", "스코프의 진화 — 무엇을, 왜 덜어냈나",
           accent=ORANGE)
    flow_box(slide, 0.6, 1.75, 12.13, 0.78, "출발 — 8기능 비전",
             "RAG · 시민 Agent · SNS 채팅 · 감성 대시보드 · 전파 그래프 · 게시판 자동답변 · A/B 테스트 · 쉬운 글 변환",
             fill=CARD, line_c=SUB, tcolor=INK, tsize=12.5, bsize=10.5)
    arrow_text(slide, 6.07, 2.55, 1.2, "↓", size=14)
    steps = [
        ("① 전파 그래프 폐기", "통계에서 무작위 샘플링한 페르소나는 서로 모르는 독립 "
         "개인 — 그 사이에 ‘전파 엣지’를 그리는 건 근거 없는 연출이다.",
         RED, PALE_RED),
        ("② 24명 마을 → 대조 3명", "24명 × 여러 시점은 해커톤에 무겁고 “24명이 "
         "대표성 있냐”는 공격에 약하다. 수혜/경계/사각 3명이면 갈림이 한 화면에.",
         ORANGE, PALE_ORANGE),
        ("③ “예측”이라 부르지 않는다", "맞히는 도구라고 주장하는 순간 검증 "
         "공격을 받는다. ‘영향 시나리오’로 포지셔닝하고, 신뢰성은 ablation으로 "
         "방어한다.", BLUE, PALE_NAVY),
    ]
    x = 0.6
    for title, body, c, pale in steps:
        box(slide, x, 2.95, 3.93, 2.5, fill=pale, line=c, lw=1.0)
        tf = tb(slide, x + 0.2, 3.13, 3.55, 2.2)
        para(tf, title, size=14, bold=True, color=c, first=True, after=6)
        para(tf, body, size=11.5, color=INK, after=0, lh=1.28)
        x += 4.1
    box(slide, 0.6, 5.7, 12.13, 0.95, fill=PALE_GREEN, line=GREEN, lw=1.0)
    tf = tb(slide, 0.95, 5.85, 11.5, 0.7, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, [("좁힌 것은 버린 게 아니라 확장 경로 — ", {"bold": True, "color": GREEN}),
              ("전파는 ‘미리마을’로, RAG는 ‘게시판’으로 결국 돌아왔다 (05장)",
               {"color": INK})], size=14, first=True, after=0, align=PP_ALIGN.CENTER)
    note(slide, "여기부터가 저희 발표의 진짜 내용입니다. 미리랩은 한 번에 설계되지 "
         "않았고, 세 번 크게 방향을 틀었습니다. 전파 그래프는 '서로 모르는 통계 샘플에 "
         "전파 엣지를 그리는 건 연출'이라서 버렸고, 24명 마을은 무겁고 대표성 공격에 "
         "약해서 대조 3명으로 좁혔고, '예측'이라는 단어는 검증 공격을 부르기 때문에 "
         "'영향 시나리오'로 포지셔닝을 바꿨습니다. 중요한 건 — 좁힌 것들이 버려진 게 "
         "아니라 뒤에서 다른 모습으로 돌아온다는 점입니다.")


def s10_two_judges(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 10, "03 시행착오", "시행착오 ① — ‘두 심판 문제’: 예측을 버리고 결과로",
           accent=ORANGE)
    tf = tb(slide, 0.6, 1.8, 12.13, 1.5)
    para(tf, [("증상  ", {"bold": True, "color": RED, "size": 14}),
              ("‘경계’로 뽑힌 신민재의 카드 서사가 “월세를 받았다” — 라벨과 이야기가 모순",
               {"size": 14})], first=True, after=6)
    para(tf, [("원인  ", {"bold": True, "color": RED, "size": 14}),
              ("심판이 둘 — 라벨은 시뮬 ", {"size": 14}),
              ("전", {"bold": True, "size": 14}),
              (" 점수 매트릭스가, 이야기는 시뮬 ", {"size": 14}),
              ("후", {"bold": True, "size": 14}),
              (" LLM이 정한다. 두 심판은 당연히 어긋난다.", {"size": 14})], after=6)
    para(tf, [("통찰  ", {"bold": True, "color": BLUE, "size": 14}),
              ("수혜/경계/사각은 점수가 아니라 ", {"size": 14}),
              ("결과(받음 / 막힘 / 못 닿음)", {"bold": True, "color": BLUE, "size": 14}),
              ("다.", {"size": 14})], after=0)
    # Before / After
    box(slide, 0.6, 3.55, 5.9, 2.9, fill=PALE_RED, line=RED, lw=1.0)
    tf1 = tb(slide, 0.85, 3.75, 5.4, 2.5)
    para(tf1, "Before — 수치 예측 선별", size=14.5, bold=True, color=RED,
         first=True, after=6)
    bullets(tf1, [
        ("시뮬 전에 점수 매트릭스로 3명을 ‘점친다’", {"bullet_color": RED}),
        ("라벨 따로, 서사 따로 → 구조적으로 어긋남", {"bullet_color": RED}),
        ("반응 점수로 뽑아도 같은 함정 — 임수빈은 자기 수혜성을 18점으로 "
         "매기지만 실제론 요건에 막힌 사각지대", {"bullet_color": RED}),
    ], size=12, after=5, first_done=True)
    box(slide, 6.83, 3.55, 5.9, 2.9, fill=PALE_GREEN, line=GREEN, lw=1.0)
    tf2 = tb(slide, 7.08, 3.75, 5.4, 2.5)
    para(tf2, "After — 결과 기반 선별", size=14.5, bold=True, color=GREEN,
         first=True, after=6)
    bullets(tf2, [
        ([("전원을 먼저 ‘살게’ 한 뒤", {"bold": True}),
          (", 실제 궤적의 결과에서 3명을 고른다", {})], {"bullet_color": GREEN}),
        ("라벨과 이야기가 같은 궤적에서 나옴 → 어긋날 수 없음", {"bullet_color": GREEN}),
        ("심판은 하나. 전원 시뮬 비용도 확인 결과 OK", {"bullet_color": GREEN}),
    ], size=12, after=5, first_done=True)
    note(slide, "첫 번째 시행착오, 저희가 '두 심판 문제'라고 부르는 버그입니다. 처음엔 "
         "시뮬레이션 전에 점수로 세 명을 '예측'해서 뽑았는데, 경계로 뽑힌 사람의 "
         "이야기가 '월세를 받았다'로 나오는 모순이 생겼습니다. 라벨을 정하는 심판과 "
         "이야기를 쓰는 심판이 달랐던 거죠. 핵심 통찰은 — 수혜·경계·사각은 점수가 "
         "아니라 '결과'라는 것. 그래서 전원을 먼저 살게 한 뒤 실제 결과에서 뽑는 "
         "방식으로 바꿨고, 이제 라벨과 이야기는 구조적으로 어긋날 수 없습니다.")


def s11_billion(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 11, "03 시행착오", "시행착오 ② — “전 국민 10억 지급” 버그",
           accent=ORANGE)
    steps = [
        ("실험", "극단 정책 “전 국민에게 10억 지급” 입력", RED, PALE_RED),
        ("증상", "전원 찬성 · 혼란도 21 — 시민이 ‘이해득실 계산기’처럼 내 혜택만 따짐",
         RED, PALE_RED),
        ("처방", "프롬프트 최상단에 “현실적으로 판단하라” — 재원·물가·증세·형평성·"
         "과대공약 의심 (+ 합리적 정책엔 냉소 금지)", BLUE, PALE_NAVY),
        ("결과", "10억 지급 → 전원 반대로 전환. 현실성 판단 작동 확인", GREEN, PALE_GREEN),
    ]
    y = 1.8
    for tag, body, c, pale in steps:
        chip(slide, 0.6, y + 0.12, tag, fill=c, w=1.1, h=0.34)
        box(slide, 1.9, y, 10.83, 0.62, fill=pale, line=c, lw=0.75)
        tf = tb(slide, 2.1, y + 0.05, 10.4, 0.52, anchor=MSO_ANCHOR.MIDDLE)
        para(tf, body, size=12.5, color=INK, first=True, after=0)
        y += 0.78
    box(slide, 0.6, 5.0, 12.13, 1.7, fill=PALE_ORANGE, line=ORANGE, lw=1.0)
    tf = tb(slide, 0.95, 5.2, 11.5, 1.35)
    para(tf, [("정직한 노트 — 과교정", {"bold": True, "color": ORANGE, "size": 14.5})],
         first=True, after=5)
    para(tf, "현실성 원칙을 넣자 정상 정책(청년 월세)의 혼란도까지 다소 올랐다. "
         "모든 정책에 기본 우려가 깔리는 ‘과교정’ 신호.", size=13, after=3, lh=1.25)
    para(tf, [("→ ‘우려를 정책이 무리한 정도에 비례시키는’ 미세 튜닝은 ", {"size": 13}),
              ("남은 과제로 기록", {"bold": True, "size": 13}),
              (" — 시행착오를 숨기지 않는다.", {"size": 13, "color": SUB})], after=0)
    note(slide, "두 번째 시행착오. 일부러 극단 정책 '전 국민 10억 지급'을 넣어봤더니 "
         "전원 찬성이 나왔습니다. 시민들이 실현 가능성이나 부작용은 안 보고 '내가 "
         "받느냐'만 따지는 계산기였던 거죠. 프롬프트 최상단에 '현실적으로 판단하라'는 "
         "원칙을 넣었더니 10억 지급은 전원 반대로 바뀌었습니다. 다만 정직하게 — "
         "정상 정책의 혼란도까지 살짝 올라가는 과교정이 생겼고, 이 미세 튜닝은 남은 "
         "과제로 기록해 뒀습니다. 저희는 시행착오를 숨기지 않고 그대로 보여드립니다.")


def s12_guards(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 12, "03 시행착오", "시행착오 ③ — 판단은 LLM에게, 불변식은 코드로",
           accent=ORANGE)
    box(slide, 0.6, 1.75, 12.13, 0.85, fill=PALE_NAVY, line=NAVY, lw=1.0)
    tf = tb(slide, 0.95, 1.9, 11.5, 0.6, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, [("LLM은 확률적이다 — 서사와 판단은 LLM이, ", {"size": 15}),
              ("어겨선 안 되는 규칙은 코드 가드가 보증한다", {"bold": True, "color": NAVY, "size": 15})],
         first=True, after=0, align=PP_ALIGN.CENTER)
    cards = [
        ("상태 비퇴행 가드", [
            "버그: ‘신청 → 모름’으로 궤적이 퇴행 (서류에 막혀 포기한 걸 LLM이 ‘몰랐다’로 오기)",
            "가드: 상태는 되돌아가지 않는다 — applied→unaware면 ‘막힘’으로 자동 교정",
            "결과: 조유정이 “자격은 되는데 서류에 막힘” 최고의 사각 사례가 됨"],
         GREEN, PALE_GREEN),
        ("태그 대상 게이트", [
            "버그: 46세 박성인이 ‘청년’ 정책의 사각지대로 오라벨",
            "가드: 대상 여부 = 태그(나이·소득·가구)로 판정하는 ‘사실’, 결과 = LLM 궤적 — 둘을 분리",
            "결과: 비대상자는 ‘무관’으로 정직하게 분류"],
         ORANGE, PALE_ORANGE),
        ("전파 게이트", [
            "무대: 잠시 후 소개할 ‘미리마을’ — 정책 소식이 사람을 타고 퍼지는 시뮬",
            "위험: LLM이 근거 없이 ‘어느새 다 알게 됨’으로 부풀릴 수 있음",
            "가드: 모르던 사람은 ‘아는 사람과 만났을 때만’ 새로 안다 — 코드가 강제",
            "결과: 전파 경로 추적이 신뢰 가능해짐 (인지 누수 0)"],
         RED, PALE_RED),
    ]
    x = 0.6
    for title, lines, c, pale in cards:
        box(slide, x, 2.85, 3.93, 3.75, fill=pale, line=c, lw=1.0)
        tf = tb(slide, x + 0.2, 3.05, 3.55, 3.4)
        para(tf, title, size=14, bold=True, color=c, first=True, after=7)
        for i, ln in enumerate(lines):
            tag = ["", "", ""][i] if False else None
            para(tf, ln, size=10.8, color=INK, after=7, lh=1.22)
        x += 4.1
    note(slide, "세 번째는 버그 하나가 아니라, 반복해서 발견한 설계 패턴입니다. LLM은 "
         "확률적이라 가끔 말이 안 되는 출력을 냅니다 — 신청했던 사람이 '몰랐다'로 "
         "퇴행하거나, 46세를 청년 정책 사각지대로 잘못 라벨하거나, 모르던 사람이 "
         "어느새 다 알게 되거나. 저희 답은 일관됩니다: 서사와 판단은 LLM에게 맡기되, "
         "어겨선 안 되는 규칙(상태는 안 되돌아간다 / 대상 여부는 사실이다 / 모르는 "
         "사람은 만나야 안다)은 코드 가드가 보증합니다. 이 철학이 시스템 전체를 "
         "관통합니다.")


def s13_ablation(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 13, "04 검증", "신뢰성 ① — ablation: 반응은 페르소나에서 나오는가",
           accent=GREEN)
    tf = tb(slide, 0.6, 1.7, 6.3, 2.4)
    para(tf, [("방법 (Park et al. 스타일 컴포넌트 ablation)",
               {"bold": True, "color": NAVY, "size": 14})], first=True, after=5)
    para(tf, [("grounding ON", {"bold": True, "color": GREEN, "size": 12.5}),
              (" = 페르소나(나이·소득·디지털·신뢰) 주입   vs   ", {"size": 12.5}),
              ("OFF", {"bold": True, "color": RED, "size": 12.5}),
              (" = 익명 시민", {"size": 12.5})], after=8)
    bullets(tf, [
        ([("인물 간 점수 표준편차 21 → 9로 붕괴", {"bold": True}),
          ("  (OFF면 시민들이 비슷하게 뭉개짐)", {"color": SUB})], {}),
        ([("collapse score +0.25~0.29", {"bold": True}),
          ("  — 반복 실행마다 일관되게 양수", {"color": SUB})], {}),
        ([("수렴 타당도: digital_literacy ↔ 이해도  r = 0.6~0.8", {"bold": True}),
          ("  (OFF면 r은 0 부근)", {"color": SUB})], {}),
    ], size=12.5, after=6, first_done=True)
    # 우측 정성 사례
    box(slide, 7.1, 1.7, 5.63, 2.4, fill=CARD, line=LINE)
    tf2 = tb(slide, 7.35, 1.88, 5.15, 2.1)
    para(tf2, "숫자를 사람 말로 — 신선옥 (60세, 무직)", size=13, bold=True,
         color=NAVY, first=True, after=6)
    para(tf2, [("ON   ", {"bold": True, "color": GREEN, "size": 12.5}),
               ("“나에게는 해당이 없다” — 반대 · 수혜 0", {"size": 12.5})], after=4)
    para(tf2, [("OFF  ", {"bold": True, "color": RED, "size": 12.5}),
               ("“좋은 정책이다” — 찬성 · 수혜 90", {"size": 12.5})], after=8)
    para(tf2, "페르소나를 빼는 순간, 60세 무직 시민이 청년 정책의 수혜자가 "
         "‘된다’. grounding이 차이를 만든다.", size=11.5, color=SUB,
         after=0, lh=1.25)
    img_fit(slide, ROOT / "eval" / "ablation_viz.png", 0.6, 4.25, 12.13, 2.7)
    note(slide, "이제 '이걸 믿을 수 있나'에 답합니다. 미리랩은 예측 정확도를 주장하지 "
         "않는 대신, Generative Agents 논문과 같은 방식의 컴포넌트 ablation으로 "
         "방어합니다. 페르소나 주입을 켠 것과 끈 것을 비교하면 — 인물 간 점수 표준편차가 "
         "21에서 9로 붕괴하고, 디지털 문해력과 이해도 점수의 상관이 0.6~0.8에서 0으로 떨어집니다. "
         "오른쪽 사례가 직관적입니다: 같은 60세 무직 시민이 페르소나를 빼는 순간 청년 "
         "정책에 '수혜 90점'을 줍니다. 반응이 페르소나에서 나온다는 증거입니다.")


def s14_cluster(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 14, "04 검증", "신뢰성 ② — 720회 반복: 집단화 · 견고성 · 설득력",
           accent=GREEN)
    tf = tb(slide, 0.6, 1.7, 5.7, 5.0)
    para(tf, [("방법  ", {"bold": True, "color": NAVY, "size": 13.5}),
              ("페르소나 24명 × 30회 반복 = 720회 반응 + LLM-judge 채점",
               {"size": 13})], first=True, after=2)
    para(tf, "비용 약 $0.3 — 검증을 ‘반복 가능한 일상’으로 만드는 가격",
         size=11, color=SUB, after=9)
    rows = [
        ("집단화", "연령이 반응을 가른다 — eta² 수혜 0.81 · 의향 0.77 (이해도는 0.36 — "
         "이해는 비슷해도 ‘내 혜택이냐’는 세대로 갈림)", BLUE),
        ("완전 분리", "청년(대상)은 찬성 207·반대 0 — 노인은 찬성 0·반대 214", NAVY),
        ("견고성", "같은 시민을 30회 돌려도 입장 안정성 82% (무작위면 약 33%) — "
         "집단 구도는 우연이 아니다", GREEN),
        ("설득력", "LLM-judge 평균 68점 — 각 집단이 자기 처지에 맞는 논리를 편다 "
         "(“66세 간호사 입장에서 보자면…”)", ORANGE),
    ]
    for tag, body, c in rows:
        para(tf, [(tag, {"bold": True, "color": c, "size": 13}),
                  ("   " + body, {"size": 11.8})], after=9, lh=1.25)
    para(tf, [("정직한 노트  ", {"bold": True, "color": SUB, "size": 12}),
              ("LLM은 비결정적이라 절대값은 출렁인다(eta² 0.94→0.81 등). "
               "그러나 방향은 항상 일관 — eta²>0.7, collapse>0.", {"size": 11.5, "color": SUB})],
         after=0, lh=1.25)
    img_fit(slide, ROOT / "eval" / "cluster_viz.png", 6.55, 1.65, 6.2, 5.1)
    note(slide, "두 번째 검증은 '한 번의 우연이 아니냐'에 대한 답입니다. 24명을 30회씩, "
         "총 720회 반응을 모았습니다. 연령이 수혜·의향 점수를 가르는 정도(eta 제곱)가 "
         "0.8 수준 — 반응이 무작위 잡음이 아니라 인구통계 집단으로 구조화된다는 뜻입니다. "
         "입장은 완전 분리됐고(청년 반대 0, 노인 찬성 0), 같은 시민을 반복해도 입장이 "
         "82% 유지됩니다. 무작위면 33%죠. 그리고 정직하게: LLM이라 절대값은 매번 "
         "출렁이지만, 방향은 항상 일관됩니다. 절대값이 아니라 구조를 믿어 달라는 게 "
         "저희 주장입니다.")


def s15_board(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 15, "05 확장", "게시판 RAG — 좁힌 확장 경로가 팀의 손으로 돌아오다",
           accent=RED)
    tf = tb(slide, 0.6, 1.8, 5.7, 4.9)
    para(tf, "정책 문의 게시판 + 문서 근거 답변", size=15.5, bold=True,
         color=NAVY, first=True, after=8)
    bullets(tf, [
        ([("질문 → 검색된 근거 ‘안에서만’ 답변", {"bold": True}),
          ("  (환각 억제)", {"color": SUB})], {}),
        ("현재 정책은 항상 기본 근거 + PDF/TXT/MD 업로드로 문서 확장", {}),
        ("Chroma 벡터 검색 + OpenAI 임베딩 → 근거·품질지표 함께 표시", {}),
        ("API 키가 없으면 추출식 폴백 — 데모는 항상 동작", {}),
    ], size=12.5, after=7, first_done=True)
    para(tf, "", size=4, after=2)
    box(slide, 0.6, 4.7, 5.7, 1.95, fill=PALE_GREEN, line=GREEN, lw=1.0)
    tf2 = tb(slide, 0.85, 4.88, 5.2, 1.6)
    para(tf2, "협업 방식이 곧 설계였다", size=13.5, bold=True, color=GREEN,
         first=True, after=5)
    para(tf2, "본체에 ‘자리(시임)와 반환 계약’만 미리 설계해 두고, 팀원이 "
         "독립 패키지로 RAG 엔진을 구현 → 마지막에 끼워 넣음. 모듈 경계를 지킨 "
         "덕에 본체는 한 줄도 안 깨졌다.", size=11.8, color=INK, after=0, lh=1.3)
    shot(slide, 6.6, 1.8, 6.13, 4.85, "‘게시판’ 탭 캡처",
         "질문 → 답변 + 📎근거 + 품질지표 표가 보이는 화면 추천")
    note(slide, "확장 파트 첫 번째, 게시판 RAG입니다. 2일차에 'MVP에서 제외'로 좁혔던 "
         "RAG가 마지막에 팀의 손으로 돌아왔습니다. 시민이나 입안자가 정책 문서에 "
         "질문하면, 벡터 검색으로 찾은 근거 '안에서만' 답하고 근거와 품질지표를 함께 "
         "보여줍니다. 협업 방식이 포인트인데 — 본체에는 자리와 반환 계약만 설계해 두고 "
         "팀원이 독립 패키지로 구현해서 마지막에 끼워 넣었습니다. 키가 없으면 추출식 "
         "폴백으로 동작하니 데모도 안전합니다.")


def s16_village1(prs, sprites):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 16, "05 확장", "미리마을 — 시민이 ‘살아가는’ 마을 (Generative Agents)",
           accent=RED)
    tf = tb(slide, 0.6, 1.75, 6.1, 3.1)
    para(tf, [("Park et al. (2023) ", {"bold": True, "color": BLUE}),
              ("의 원형 — 에이전트가 공간에서 자기 스케줄대로 살아가는 마을",
               {})], size=13.5, first=True, after=8, lh=1.25)
    bullets(tf, [
        ([("10명 손제작 고정 캐스트", {"bold": True}),
          (" — 무작위 통계 샘플엔 ‘관계’가 없다. 전파 무대엔 서로 아는 마을이 필요 "
           "(축 A·B와 목적이 다른 의도된 선택)", {})], {}),
        ("LLM이 각자의 하루 일과(시간 → 장소 → 행동)를 생성", {}),
        ([("“녹화 후 재생” — 하루를 미리 생성, 브라우저는 LLM 0콜로 재생",
           {"bold": True}), ("  (즉시·반복·오프라인 = 발표 안전망)", {"color": SUB})], {}),
        ("도로 waypoint 652개 → 그래프 + BFS 길찾기로 실제 ‘도보’ 이동", {}),
        ("마주치면 — 그날 동선·관계가 묻어나는 맥락 대화", {}),
    ], size=12, after=5.5, first_done=True)
    box(slide, 0.6, 4.95, 6.1, 1.7, fill=PALE_ORANGE, line=ORANGE, lw=1.0)
    tf2 = tb(slide, 0.85, 5.1, 5.6, 1.45)
    para(tf2, "시행착오 — “스케줄은 순간이동, 재생은 도보”", size=13,
         bold=True, color=ORANGE, first=True, after=4)
    para(tf2, "LLM이 짠 스케줄은 이동시간 0을 가정 → 막상 재생하니 만남 14개 중 "
         "7개가 ‘도착 전에 끝남’. 실제 걸어서 도착하는 시간을 시뮬해 만남을 "
         "다시 뽑자 발화 6/6 보장.", size=11.5, color=INK, after=0, lh=1.28)
    # 우측: 마을 맵 + 창발 한 줄
    img_fit(slide, ROOT / "미리마을" / "assets" / "map.png", 6.95, 1.75, 5.8, 4.0)
    box(slide, 6.95, 5.85, 5.8, 0.8, fill=PALE_GREEN, line=GREEN, lw=1.0)
    tf3 = tb(slide, 7.15, 5.95, 5.4, 0.62, anchor=MSO_ANCHOR.MIDDLE)
    para(tf3, [("창발 —  ", {"bold": True, "color": GREEN, "size": 12}),
               ("시키지 않았는데 — 민수·수아가 광장 산책을 약속하고, 같은 카페 "
                "사장이 세 손님과 ‘각자의 하루’로 다른 대화를 한다",
                {"size": 11.3})], first=True, after=0, lh=1.2)
    note(slide, "마지막 확장, 미리마을입니다. Generative Agents 논문의 원형 — "
         "에이전트가 공간에서 스케줄대로 살아가는 마을을 포켓몬식 오버월드로 "
         "구현했습니다. LLM이 10명 각자의 하루를 생성하면 브라우저는 LLM 호출 없이 "
         "재생만 합니다. 발표 중에도 안전하죠. 재미있는 시행착오가 있었는데, LLM이 짠 "
         "스케줄은 순간이동을 가정해서 막상 걸어가면 만남의 절반이 증발했습니다. 실제 "
         "도보 시간을 시뮬해서 만남을 다시 뽑았고요. 그리고 시키지 않았는데 캐릭터들이 "
         "서로를 일정에 엮고, 같은 카페 사장이 손님마다 다른 대화를 하는 '창발'이 "
         "나타났습니다. [Q&A 대비 — \"손으로 안 만든다더니 모순 아니냐\": 축 A·B의 "
         "통계 샘플은 '대표성'이 목적이라 무작위 추출이 맞고, 미리마을은 '전파'가 "
         "목적이라 서로 아는 관계가 필수입니다. 무작위 샘플엔 관계가 없으니 손제작 — "
         "목적이 다르면 재료도 다릅니다.]")


def s17_village2(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 17, "05 확장", "미리마을 × 정책 — 소식은 누구에게, 어떤 경로로 닿는가",
           accent=RED)
    box(slide, 0.6, 1.75, 12.13, 0.8, fill=PALE_NAVY, line=NAVY, lw=1.0)
    tf = tb(slide, 0.95, 1.88, 11.5, 0.58, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, [("질문의 전환:  “정책이 각자에게 어떤 효과인가”  →  ",
               {"size": 14.5}),
              ("“정책 ‘소식’이 누구에게 · 어떤 경로로 닿는가”",
               {"bold": True, "color": NAVY, "size": 14.5})], first=True, after=0,
         align=PP_ALIGN.CENTER)
    fx = 0.6
    flow_box(slide, fx, 2.8, 2.7, 1.5, "① 시드 주입",
             "복지관 어르신 2명만 정책을 알고 시작", fill=PALE_RED, line_c=RED,
             tcolor=RED, tsize=12.5, bsize=11)
    arrow_text(slide, fx + 2.72, 3.35, 0.5, "→", size=16)
    flow_box(slide, fx + 3.24, 2.8, 2.7, 1.5, "② 만남 전파",
             "스케줄대로 살다 마주친 대화에서 소식이 옮음", fill=PALE_ORANGE,
             line_c=ORANGE, tcolor=ORANGE, tsize=12.5, bsize=11)
    arrow_text(slide, fx + 5.96, 3.35, 0.5, "→", size=16)
    flow_box(slide, fx + 6.48, 2.8, 2.7, 1.5, "③ 밤 일기 (reflection)",
             "하루를 일기로 압축 → 다음날의 기억으로", fill=PALE_NAVY, line_c=BLUE,
             tcolor=BLUE, tsize=12.5, bsize=11)
    arrow_text(slide, fx + 9.2, 3.35, 0.5, "→", size=16)
    flow_box(slide, fx + 9.72, 2.8, 2.41, 1.5, "④ [▶다음날]",
             "며칠이고 이어서 — 전파의 시간 구조", fill=PALE_GREEN, line_c=GREEN,
             tcolor=GREEN, tsize=12.5, bsize=11)
    # 결과 숫자
    box(slide, 0.6, 4.55, 5.9, 2.1, fill=CARD, line=LINE)
    tf2 = tb(slide, 0.85, 4.72, 5.4, 1.8)
    para(tf2, "1일차 실측 (실제 LLM)", size=13.5, bold=True, color=NAVY,
         first=True, after=6)
    bullets(tf2, [
        ([("10명 중 8명에게 전파", {"bold": True}),
          (" — 카페가 허브 역할", {"color": SUB})], {}),
        ([("사각지대 2명", {"bold": True, "color": RED}),
          (" — 동선이 겹치지 않은 모자(母子)", {"color": SUB})], {}),
        ([("근거 없는 인지 누수 0", {"bold": True, "color": GREEN}),
          (" — 전파 게이트가 코드로 보증", {"color": SUB})], {}),
    ], size=12, after=5, first_done=True)
    box(slide, 6.83, 4.55, 5.9, 2.1, fill=PALE_GREEN, line=GREEN, lw=1.0)
    tf3 = tb(slide, 7.08, 4.72, 5.4, 1.8)
    para(tf3, "폐기했던 ‘전파’가 정당하게 부활", size=13.5, bold=True,
         color=GREEN, first=True, after=6)
    para(tf3, "축 A의 전파 그래프는 ‘서로 모르는 통계 샘플’이라 버렸다(03장). "
         "미리마을은 서로 아는 고정 캐스트 — 여기서의 전파는 연출이 아니라 "
         "관계와 동선의 결과다.", size=12, color=INK, after=0, lh=1.3)
    t_demo = tb(slide, 0.6, 6.72, 12.13, 0.36)
    para(t_demo, "🎬 여기서 라이브 데모 — 미리마을 재생 60~90초 (재생은 LLM 0콜 "
         "= 네트워크가 죽어도 안전)", size=12.5, bold=True, color=RED,
         align=PP_ALIGN.CENTER, first=True, after=0)
    note(slide, "미리마을에 정책을 주입하면 질문이 바뀝니다. '효과가 어떤가'가 아니라 "
         "'소식이 누구에게, 어떤 경로로 닿는가'. 복지관 어르신 두 분만 아는 상태로 "
         "시작하면, 마을 사람들이 스케줄대로 살다가 마주친 대화에서 소식이 옮습니다. "
         "밤에는 각자 일기로 하루를 압축해 다음날의 기억이 되고요. 실측 결과 하루 만에 "
         "10명 중 8명에게 퍼졌는데, 동선이 안 겹친 두 명이 사각지대로 남았습니다. "
         "12장에서 보신 '전파 게이트'가 바로 이 무대의 코드 가드입니다. 그리고 중요한 것 — "
         "처음에 버렸던 '전파'가 여기서 부활했습니다. 여긴 서로 아는 마을이라 전파가 "
         "연출이 아니라 관계와 동선의 결과이기 때문입니다. → 이 슬라이드 직후 미리마을 "
         "재생 데모(60~90초): 발표 첫 장에서 약속한 '이 친구들이 직접 움직이는 모습'을 "
         "여기서 회수합니다. 녹화 재생이라 LLM 0콜, 발표장 네트워크와 무관하게 안전.")


def s18_discipline(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 18, "06 마무리", "4일 · 4명 — 서로를 깨지 않기 위한 규율",
           accent=SUB)
    cards = [
        ("state.py = 팀 계약", "공유 스키마는 기존 필드 변경 금지, 추가만(additive). "
         "4명이 같은 계약을 읽고 쓴다."),
        ("mock 모드 = 발표 안전망", "API 키·네트워크 없이 전체 UI 시연. "
         "발표 중 장애에도 데모는 죽지 않는다."),
        ("import 부작용 0", "어떤 모듈도 import 시 네트워크/LLM 호출 없음. "
         "실행은 버튼을 눌렀을 때만."),
        ("헤드리스 회귀 스크립트", "선별·게이지·히트맵·전체 앱 스모크 — "
         "변경할 때마다 키 없이 자동 검증."),
        ("탭 격리", "한 탭이 죽어도 다른 탭은 산다 — 각 탭을 try/except로 격리."),
        ("XSS 방어", "LLM 자유 텍스트·시민 이름은 화면에 닿기 전 전부 escape."),
    ]
    positions = [(0.6, 1.85), (6.83, 1.85), (0.6, 3.35), (6.83, 3.35),
                 (0.6, 4.85), (6.83, 4.85)]
    for (title, body), (x, y) in zip(cards, positions):
        box(slide, x, y, 5.9, 1.35, fill=CARD, line=LINE)
        tf = tb(slide, x + 0.22, y + 0.13, 5.5, 1.1)
        para(tf, title, size=13.5, bold=True, color=NAVY, first=True, after=3)
        para(tf, body, size=11, color=INK, after=0, lh=1.2)
    t = tb(slide, 0.6, 6.4, 12.13, 0.5)
    para(t, "역할 분담 — (발표 전 채워주세요: 데이터/페르소나 · Agent/프롬프트 · "
         "대시보드/지표 · UI/시각화)", size=11.5, color=SUB,
         align=PP_ALIGN.CENTER, first=True, after=0)
    note(slide, "기능 얘기를 마치기 전에, 4일 동안 4명이 서로의 작업을 깨지 않게 한 "
         "규율을 짧게 소개합니다. 공유 스키마는 변경 금지·추가만 허용하는 팀 계약으로 "
         "묶었고, 키 없이 도는 mock 모드와 헤드리스 회귀 스크립트 덕분에 누가 무엇을 "
         "바꿔도 안전하게 검증했습니다. 게시판 RAG가 마지막 날 본체를 한 줄도 안 깨고 "
         "들어올 수 있었던 게 이 규율의 실증입니다. (시간이 빠듯하면 이 장은 한 문장으로 "
         "줄이고 넘어가도 됩니다. 역할 분담 줄은 실제 팀 구성으로 채워주세요.)")


def s19_limits(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide, 19, "06 마무리", "한계 — 검증 공격을 받기 전에, 우리가 먼저 말한다",
           accent=SUB)
    items = [
        ("미래를 맞히는 도구가 아니다", "일관되게 ‘영향 시나리오’로 포지셔닝. "
         "신뢰성은 예측 정확도가 아니라 ablation·집단화·견고성으로 방어한다."),
        ("소득 판정은 근사다", "직업→소득 버킷은 휴리스틱. 나이는 하드 체크지만 "
         "소득은 그만큼 확실하지 않다."),
        ("현실성 프롬프트의 과교정", "정상 정책의 혼란도도 다소 올라간다 — "
         "미세 튜닝은 남은 과제."),
        ("표본이 작다", "시민 8~24명. 통계적 일반화가 아니라 ‘구조가 나타나는지’의 "
         "시연이다. 3명 대조는 의도된 좁힘 — 위에 전체 분포 헤드라인으로 보완."),
        ("LLM-judge의 순환", "LLM이 LLM을 채점하는 한계 — 절대 점수보다 집단 간 "
         "비교와 대표 예시로 해석한다."),
    ]
    y = 1.8
    for title, body in items:
        box(slide, 0.6, y, 12.13, 0.87, fill=CARD, line=LINE)
        tf = tb(slide, 0.88, y + 0.08, 11.6, 0.72)
        para(tf, [(title + "   ", {"bold": True, "color": NAVY, "size": 13}),
                  (body, {"size": 11.8, "color": INK})], first=True, after=0,
             lh=1.18)
        y += 0.97
    note(slide, "마무리 전에 한계를 저희 입으로 먼저 말씀드립니다. 미리랩은 미래를 "
         "맞히는 도구가 아니고, 그렇게 주장하지도 않습니다. 소득 판정은 휴리스틱 "
         "근사이고, 현실성 프롬프트엔 과교정이 남아 있고, 표본은 작습니다. LLM이 "
         "LLM을 채점하는 순환 한계도 있고요. 저희가 보여드린 건 '정확한 예측'이 "
         "아니라 — 페르소나에 근거하고, 반복해도 재현되고, 집단으로 구조화되는 "
         "'영향 시나리오'입니다. 이 정직한 선 긋기가 저희 설계의 일부입니다.")


def s19_closing(prs, sprites):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box(slide, 0, 0, SW, 0.18, fill=NAVY, line=None, shape=MSO_SHAPE.RECTANGLE)
    t = tb(slide, 1.0, 1.15, SW - 2.0, 2.3)
    para(t, "“같은 정책, 다른 인생.”", size=40, bold=True, color=NAVY,
         first=True, after=10, align=PP_ALIGN.CENTER)
    para(t, [("미리랩은 그 갈림을 ", {"size": 18}),
             ("배포 전에", {"bold": True, "color": BLUE, "size": 18}),
             (" 보여줍니다", {"size": 18})], after=4, align=PP_ALIGN.CENTER)
    para(t, "— 누가 이해 못 하고 · 누가 신청 못 하고 · 어디서 막히는지",
         size=15, color=SUB, after=0, align=PP_ALIGN.CENTER)
    # 다음 단계
    nx = 0.7
    nexts = [
        ("실데이터 대조", "실제 신청률·인지율 통계와 방향 대조 — 1순위"),
        ("페르소나 RAG", "정책 태그를 검색 키로 · 스키마 확보"),
        ("미리마을 확장", "누적 기억(B단계) · 적응 스케줄"),
        ("튜닝 고도화", "현실성 과교정 보정 · 게이지 정밀화"),
    ]
    for title, body in nexts:
        box(slide, nx, 3.75, 2.88, 1.35, fill=PALE_NAVY, line=NAVY, lw=0.75)
        tf = tb(slide, nx + 0.18, 3.9, 2.55, 1.1)
        para(tf, "다음 — " + title, size=12, bold=True, color=NAVY, first=True,
             after=3)
        para(tf, body, size=10.5, color=INK, after=0, lh=1.18)
        nx += 3.06
    # 스프라이트 + 감사
    keys = ["grandma", "minsu", "sua", "owner", "oldman"]
    x = (SW - len(keys) * 0.75) / 2
    for k in keys:
        p = sprites.get(k)
        if p:
            slide.shapes.add_picture(str(p), Inches(x), Inches(5.35),
                                     Inches(0.6), Inches(0.6))
            x += 0.75
    t2 = tb(slide, 1.0, 6.15, SW - 2.0, 0.9)
    para(t2, "감사합니다 — Q&A", size=22, bold=True, color=NAVY,
         align=PP_ALIGN.CENTER, first=True, after=4)
    para(t2, "데이터 nvidia/Nemotron-Personas-Korea (CC BY 4.0) · LangGraph · "
         "Streamlit · gpt-4o-mini · Generative Agents (Park et al., 2023)",
         size=10, color=SUB, align=PP_ALIGN.CENTER, after=0)
    note(slide, "정리하면 — 미리랩은 실제 인구통계 기반 가상 시민에게 정책을 먼저 "
         "물어봐서, '같은 정책, 다른 인생'의 갈림을 배포 전에 보여주는 실험실입니다. "
         "다음 단계의 1순위는 실데이터 대조 — 실제 청년월세 신청률·인지율 통계와 "
         "시뮬 방향을 맞대보는 외적 타당도 확보입니다. 이어서 페르소나 RAG, 미리마을 "
         "누적 기억, 프롬프트 튜닝이 준비돼 있습니다. 들어주셔서 감사합니다. "
         "(Q&A 예상 질문: ①'실제 사람 반응과 맞는지 확인했나' → 정직하게: 아직 내적 "
         "검증(ablation·집단화·견고성)까지이고, 실통계와의 방향 대조가 다음 1순위라고 "
         "답변. Park et al.도 human eval과 비교했음을 인지하고 있다고 덧붙이면 강함 "
         "②비용은 → 시뮬 1회 약 1.3센트, 720회 검증도 약 $0.3 ③실제 입안자가 어떻게 "
         "쓰나 → 4장 컨셉의 사각지대 발견 + 7장 A/B 폐루프로 답변)")


# ---------------------------------------------------------------- 메인
def main():
    sprites = prep_sprites()
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)

    s01_title(prs, sprites)
    s02_agenda(prs)
    s03_problem(prs)
    s04_concept(prs)
    s05_system(prs)
    s06_persona(prs)
    s07_axis_a(prs)
    s08_axis_b(prs)
    s09_scope(prs)
    s10_two_judges(prs)
    s11_billion(prs)
    s12_guards(prs)
    s13_ablation(prs)
    s14_cluster(prs)
    s15_board(prs)
    s16_village1(prs, sprites)
    s17_village2(prs)
    s18_discipline(prs)
    s19_limits(prs)
    s19_closing(prs, sprites)

    OUT.parent.mkdir(exist_ok=True)
    prs.save(OUT)
    print("[OK] saved:", OUT)
    print("[OK] slides:", len(prs.slides.__iter__.__self__._sldIdLst))


if __name__ == "__main__":
    main()
