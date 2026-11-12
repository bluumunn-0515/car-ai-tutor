#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""10분 학위과제 발표용 방어 PPT 생성 (python-pptx)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUT_MAIN = ROOT / "presentation_defense_10min.pptx"
OUT_COPY = ROOT / "\ubc1c\ud45c\uc790\ub8cc_\ud559\uc704\uacfc\uc81c_10min.pptx"

NAVY = RGBColor(0x1A, 0x36, 0x5D)
ACCENT_BLUE = RGBColor(0x2B, 0x6C, 0xB0)
ACCENT_ORANGE = RGBColor(0xED, 0x89, 0x36)
LIGHT_GRAY = RGBColor(0xF7, 0xFA, 0xFC)
MID_GRAY = RGBColor(0xE2, 0xE8, 0xF0)
TEXT_DARK = RGBColor(0x2D, 0x37, 0x48)
TEXT_MUTED = RGBColor(0x71, 0x85, 0x94)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Malgun Gothic"
FOOTER_TEXT = "\ubb38\ud604\ucca0 | \uc0dd\uc131\ud615 AI \uc790\ub3d9\ucc28 \uace0\uc7a5\uc9c4\ub2e8 \ud559\uc2b5\uc9c0\uc6d0 \uc571"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def _set_font(run, size: int, *, bold: bool = False, color: RGBColor = TEXT_DARK):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return run


def _apply_bg(slide, color: RGBColor = LIGHT_GRAY):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_top_bar(slide, title: str | None = None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_W, Inches(0.55))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    if title:
        box = slide.shapes.add_textbox(Inches(0.45), Inches(0.08), Inches(12), Inches(0.42))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = title
        _set_font(run, 20, bold=True, color=WHITE)


def _add_footer(slide, page_num: int):
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.45), Inches(7.05), Inches(12.4), Pt(1.5))
    line.fill.solid()
    line.fill.fore_color.rgb = MID_GRAY
    line.line.fill.background()
    left = slide.shapes.add_textbox(Inches(0.45), Inches(7.08), Inches(9.5), Inches(0.35))
    run = left.text_frame.paragraphs[0].add_run()
    run.text = FOOTER_TEXT
    _set_font(run, 9, color=TEXT_MUTED)
    right = slide.shapes.add_textbox(Inches(11.8), Inches(7.05), Inches(1.0), Inches(0.35))
    p2 = right.text_frame.paragraphs[0]
    p2.alignment = PP_ALIGN.RIGHT
    run2 = p2.add_run()
    run2.text = str(page_num)
    _set_font(run2, 10, bold=True, color=ACCENT_BLUE)


def _add_bullets(slide, items, *, left=0.55, top=1.05, width=12.2, height=5.75, size=18, line_space=1.25):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for i, text in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(int(size * line_space * 0.35))
        p.line_spacing = line_space
        run = p.add_run()
        run.text = ("\u2022 " + text) if not text.startswith("\u2022") else text
        _set_font(run, size, color=TEXT_DARK)


def _add_image(slide, rel_path: str, left: float, top: float, width: float):
    path = ROOT / rel_path
    if path.is_file():
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(width))


def _slide_title(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_W, Inches(4.2))
    band.fill.solid()
    band.fill.fore_color.rgb = NAVY
    band.line.fill.background()
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(4.2), SLIDE_W, Inches(0.12))
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT_ORANGE
    accent.line.fill.background()
    bottom = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(4.32), SLIDE_W, Inches(3.18))
    bottom.fill.solid()
    bottom.fill.fore_color.rgb = LIGHT_GRAY
    bottom.line.fill.background()
    title_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.15), Inches(12), Inches(2.2))
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "\uc0dd\uc131\ud615 AI\ub97c \ud65c\uc6a9\ud55c\n\uc790\ub3d9\ucc28 \uace0\uc7a5\uc9c4\ub2e8 \ud559\uc2b5\uc9c0\uc6d0 \uc571 \uac1c\ubc1c"
    _set_font(r, 32, bold=True, color=WHITE)
    sub = tf.add_paragraph()
    sub.space_before = Pt(14)
    r2 = sub.add_run()
    r2.text = "\ud2b9\uc131\ud654\uace0 \u2018\uc790\ub3d9\ucc28 \uc804\uae30\u00b7\uc804\uc790 \uc81c\uc5b4\u2019 \uc2e4\uc2b5 \uc218\uc5c5\uc744 \uc911\uc2ec\uc73c\ub85c"
    _set_font(r2, 18, color=RGBColor(0xCB, 0xE0, 0xF5))
    info = slide.shapes.add_textbox(Inches(0.7), Inches(4.75), Inches(12), Inches(2.2))
    tfi = info.text_frame
    for i, (k, v) in enumerate(
        [
            ("\ubc1c\ud45c\uc790", "\ubb38\ud604\ucca0"),
            ("\uc18c\uc18d", "\uc219\uba85\uc5ec\uc790\ub300\ud559\uad50 \uad50\uc721\ub300\ud559\uc6d0 AI\uc735\ud569\uad50\uc721\uc804\uacf5"),
            ("\uc9c0\ub3c4\uad50\uc218", "\uae40\uc720\uacbd \u00b7 \uc720\ud3c9\uc900"),
            ("\uc77c\uc2dc", "2026\ub144 4\uc6d4  |  \uc11d\uc0ac \ud559\uc704 \uacfc\uc81c"),
        ]
    ):
        p = tfi.paragraphs[0] if i == 0 else tfi.add_paragraph()
        p.space_after = Pt(10)
        rl = p.add_run()
        rl.text = f"{k}  "
        _set_font(rl, 16, bold=True, color=NAVY)
        rv = p.add_run()
        rv.text = v
        _set_font(rv, 16, color=TEXT_DARK)
    _add_footer(slide, 1)


def _slide_agenda(prs: Presentation, page: int):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _apply_bg(slide)
    _add_top_bar(slide, "\ubc1c\ud45c \uad6c\uc131 (10\ubd84)")
    rows = [
        ("1", "\uc5f0\uad6c \uac1c\uc694", "1\ubd84"),
        ("2", "\uc5f0\uad6c \ubc30\uacbd\u00b7\ubb38\uc81c", "2\ubd84"),
        ("3", "\ubaa9\uc801 \ubc0f \uc774\ub860\uc801 \ud2f0", "1\ubd84"),
        ("4", "\ud575\uc2ec \uc774\ub860\uacfc \uc571 \uc5f0\uacb0", "4\ubd84"),
        ("5", "\uc124\uacc4\u00b7\uac1c\ubc1c \ubc0f \uac80\uc99d", "2\ubd84"),
    ]
    y = 1.35
    for num, topic, t in rows:
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(y), Inches(11.5), Inches(0.95))
        card.fill.solid()
        card.fill.fore_color.rgb = WHITE
        card.line.color.rgb = MID_GRAY
        nb = slide.shapes.add_textbox(Inches(1.15), Inches(y + 0.18), Inches(0.6), Inches(0.5))
        rnum = nb.text_frame.paragraphs[0].add_run()
        rnum.text = num
        _set_font(rnum, 22, bold=True, color=ACCENT_ORANGE)
        tb = slide.shapes.add_textbox(Inches(1.85), Inches(y + 0.22), Inches(8.5), Inches(0.5))
        rtop = tb.text_frame.paragraphs[0].add_run()
        rtop.text = topic
        _set_font(rtop, 20, bold=True, color=NAVY)
        tt = slide.shapes.add_textbox(Inches(10.5), Inches(y + 0.22), Inches(1.5), Inches(0.5))
        tt.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        rt = tt.text_frame.paragraphs[0].add_run()
        rt.text = t
        _set_font(rt, 16, color=ACCENT_BLUE)
        y += 1.1
    _add_footer(slide, page)


def _slide_thanks(prs: Presentation, page: int):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _apply_bg(slide)
    center = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.0), Inches(1.8), Inches(9.3), Inches(3.8))
    center.fill.solid()
    center.fill.fore_color.rgb = WHITE
    center.line.color.rgb = ACCENT_BLUE
    box = slide.shapes.add_textbox(Inches(2.4), Inches(2.35), Inches(8.5), Inches(2.8))
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    rth = p.add_run()
    rth.text = "\uac10\uc0ac\ud569\ub2c8\ub2e4"
    _set_font(rth, 40, bold=True, color=NAVY)
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    p2.space_before = Pt(20)
    rsub = p2.add_run()
    _set_font(rsub, 16, color=TEXT_DARK)
    rsub.text = (
        "ZPD\u00b7\uc2a4\uce90\ud3f0\ub529\u00b7\ud53c\ub4dc\ubc31\u00b7\uc790\uae30\uc870\uc808\ud559\uc2b5\uc744 \ud1b5\ud569\ud55c\n"
        "\uac00\uc774\ub4dc\ub808\uc77c \uc788\ub294 AI \ud559\uc2b5\uc9c0\uc6d0 \uc571 \u2014 \uc9c0\ub3c4\uc640 \uc870\uc5b8\uc744 \ubd80\ud0c1\ub4dc\ub9bd\ub2c8\ub2e4."
    )
    _add_footer(slide, page)


def _content_slide(prs: Presentation, spec: dict, page: int):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _apply_bg(slide)
    _add_top_bar(slide, spec["title"])
    img = spec.get("image")
    if img:
        _add_bullets(slide, spec["bullets"], width=6.1, size=16)
        _add_image(slide, img, 6.65, 1.05, 6.1)
    else:
        _add_bullets(slide, spec["bullets"])
    _add_footer(slide, page)


def build_presentation() -> Presentation:
    slides_data = json.loads("""[
  {
    \"type\": \"agenda\"
  },
  {
    \"title\": \"연구 한 줄 소개\",
    \"bullets\": [
      \"특성화고 자동차과 '자동차 전기·전자 제어' 실습에서 고장진단 능력과 자기주도 학습을 동시에 지원하는 생성형 AI 웹앱 설계·개발·검증\",
      \"교사 1명이 다수 학생을 지도할 때 발생하는 '피드백 병목'을 AI로 보완하되, 정답 대행이 아닌 학습 설계\",
      \"NCS 수행준거 → 4단계 미션 → AI 피드백 → 수행평가·세특 환류의 전체 흐름형 학습지원 (v3)\"
    ]
  },
  {
    \"title\": \"왜 이 연구인가 — 실습 현장\",
    \"bullets\": [
      \"회로도 해석 → 계측 → 기준값 비교 → 판정의 단계적 논리·추상적 신호·고전압 안전이 동시에 요구됨\",
      \"교사 1 : 학생 다수 — 안전 관리와 개별 지도를 동시에 수행하기 어려움\",
      \"막힘 구간에서 즉각적·맞춤형 피드백 공급 한계\",
      \"2022 개정 교육과정·AX 특성화고 등 디지털·AI 직업교육 정책과 정합\"
    ]
  },
  {
    \"title\": \"피드백 병목 (Feedback Bottleneck)\",
    \"bullets\": [
      \"실습 시간·인력 제약으로 '과정 피드백'이 병목\",
      \"학습자는 막혔을 때 다음 행동을 정하기 어려움\",
      \"본 연구의 출발점: 병목 완화 + 학습 주체성 유지\"
    ],
    \"image\": \"figures/fig_01.png\"
  },
  {
    \"title\": \"생성형 AI — 기회와 주의\",
    \"bullets\": [
      \"Bastani 등(2025): 정답 제공 GPT → 연습 향상, AI 차단 시험에서 성적 하락('목발 효과')\",
      \"Gerlich(2025): AI 과의존과 비판적 사고 저하\",
      \"León-Domínguez(2024): 완성 해법 제공으로 인지적 오프로딩 증폭\",
      \"필요: 가이드레일이 내장된 AI 학습지원 — AI 찬스·정답 비제시 설계\"
    ]
  },
  {
    \"title\": \"연구 목적\",
    \"bullets\": [
      \"고장진단 능력과 자기주도 학습 태도를 지원하는 생성형 AI 학습지원 앱을 설계·개발\",
      \"NCS 기반 수행평가·기록 환류형 고장진단 학습지원 (v3 포지셔닝)\",
      \"피드백 병목 완화(실용)와 AI가 학습을 대신하지 않게 설계(학술)를 동시 추구\"
    ]
  },
  {
    \"title\": \"통합 이론적 틀\",
    \"bullets\": [
      \"비고츠키 ZPD — '언제' AI·교사가 개입하는가\",
      \"Wood 등 스캐폴딩 — '어떻게' 단계·자유도를 조절하는가\",
      \"Hattie & Timperley — '무엇을' 피드백하는가 (목표·현재·다음)\",
      \"Zimmerman SRL — 학습자가 '스스로' 계획·수행·성찰·재수행하는가\"
    ]
  },
  {
    \"title\": \"① 비고츠키 — 근접발달영역(ZPD)\",
    \"bullets\": [
      \"혼자 가능한 수준과 도움 시 가능한 잠재 수준 사이가 최적 학습 구간\",
      \"AI는 ZPD 안의 임시적 '능숙한 조력자'\",
      \"정답 대행 시 의존 → 정답 비제시·단계적 발문 설계\"
    ]
  },
  {
    \"title\": \"② Wood 등 — 스캐폴딩(비계)\",
    \"bullets\": [
      \"일시적 지원 — 익숙해지면 비계 거두기(fading)\",
      \"자유도 축소: 4단계 미션 카드\",
      \"좌절 통제·거두기: AI 찬스 1회, 감점 및 사용 로그\"
    ]
  },
  {
    \"title\": \"③ Hattie — 피드백 모형\",
    \"bullets\": [
      \"Feed Up: 목표·기준\",
      \"Feed Back: 사실 + NCS 기준 + 통과/보완\",
      \"Feed Forward: 보완 제안, 다음 측정 방향\",
      \"자기 수준(칭찬만) 피드백 차단\"
    ],
    \"image\": \"figures/fig_03.png\"
  },
  {
    \"title\": \"④ Zimmerman — 자기조절학습(SRL)\",
    \"bullets\": [
      \"계획: 구조화 입력(부품·상태·학습 질문)\",
      \"수행: 4단계 미션 메모·사진·완료 체크\",
      \"성찰: AI 평가, 실습 소감, '다시 평가 받기'\"
    ],
    \"image\": \"figures/fig_06.png\"
  },
  {
    \"title\": \"Bastani·가이드레일 — AI 찬스\",
    \"bullets\": [
      \"막힌 단계에서 추가 도움 1회 — 감점·로그 가시화\",
      \"정답·원인 단정 금지 — 측정·관찰·비교 절차만 발문\",
      \"'선택과 책임'으로 AI 의존 통제\",
      \"직업교육·안전·계측·판정 도메인으로 가이드레일 확장\"
    ]
  },
  {
    \"title\": \"핵심 설계 ① — NCS 절차적 스캐폴딩\",
    \"bullets\": [
      \"NCS 자동차 전기·전자장치 정비(15060303) 6개 능력단위\",
      \"고장진단 4단계 강제 분절 및 순차 진행\",
      \"수행준거 키워드 코드·프롬프트 내장\",
      \"수행평가·세특 기록 환류 연계\"
    ]
  },
  {
    \"title\": \"핵심 설계 ② — 정답을 주지 않는 AI 튜터\",
    \"bullets\": [
      \"Gemini 멀티모달 — Streamlit 웹앱\",
      \"Hattie 구조의 NCS 루브릭 자동 평가\",
      \"신명은(2025) 연구를 특성화고·NCS·실습으로 확장\",
      \"교사 모드·포트폴리오 PDF·학습 분석 대시보드\"
    ]
  },
  {
    \"title\": \"프로젝트 모형 — 핵심 루프\",
    \"bullets\": [
      \"입력 → 가이드 → 4단계 수행 → 평가 → 환류\",
      \"폭포수 모형 기반 개발\",
      \"v3: core loop 중심 재구성\"
    ],
    \"image\": \"figures/fig_05.png\"
  },
  {
    \"title\": \"개발 환경 및 산출물\",
    \"bullets\": [
      \"Python, Streamlit, Google Gemini API, Google Sheets\",
      \"시스템 프롬프트: 학습·평가·AI 찬스·세특 분리\",
      \"산출물: 웹앱, 루브릭·설문·형성평가 도구, 학습 기록\"
    ]
  },
  {
    \"title\": \"효과성 검증 계획\",
    \"bullets\": [
      \"대상: 특성화고 자동차과 2학년\",
      \"사전·사후 형성평가 (NCS, 80점 만점)\",
      \"교사 인터뷰 6문항, 학생 설문 15문항\",
      \"고장진단 향상 및 AI 찬스 의존 통제 검증\"
    ]
  },
  {
    \"title\": \"기대 기여·한계\",
    \"bullets\": [
      \"피드백 병목 완화 + AI 목발 회피를 동시에 다룬 직업교육 사례\",
      \"이론 통합의 UI·시스템 수준 구현\",
      \"한계: 단일 학교·표본, AI 찬스 감점값 1차 설계\",
      \"향후: 다학교 확장, 감점·도움 횟수 실증 조정\"
    ]
  },
  {
    \"type\": \"thanks\"
  }
]""")
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    pg = 1
    _slide_title(prs)
    pg += 1
    for spec in slides_data:
        if spec.get("type") == "agenda":
            _slide_agenda(prs, pg)
        elif spec.get("type") == "thanks":
            _slide_thanks(prs, pg)
        else:
            _content_slide(prs, spec, pg)
        pg += 1
    return prs


def main():
    prs = build_presentation()
    prs.save(OUT_MAIN)
    shutil.copy2(OUT_MAIN, OUT_COPY)
    for p in (OUT_MAIN, OUT_COPY):
        print(f"Created: {p.name} ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
