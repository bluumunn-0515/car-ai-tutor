"""
연구계획서용 그림 자동 생성.

기본 생성: [그림 1]~[그림 11] (개념도·모형도 + 앱 UI 목업)
추가 생성: [그림 23]~[그림 28] (효과성 검증 차트, --all 옵션)

출력:
  figures/fig_NN.png, fig_NN.jpg
  figures/download/그림_NN_제목.png, .jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle
import numpy as np

OUT_DIR = Path(__file__).parent / "figures"
DOWNLOAD_DIR = OUT_DIR / "download"

# [그림 12]~[그림 22] — 실제 앱 캡처 권장 (미생성)
APP_SCREENSHOT_FIGS = set(range(12, 23))

FIGURE_TITLES = {
    1: "자동차 전기·전자 제어 실기 교육 '피드백 병목' 개념도",
    2: "비고츠키의 근접발달영역(ZPD) 개념도",
    3: "Hattie & Timperley(2007)의 피드백 모형",
    4: "Zimmerman(2002)의 자기조절학습 3단계 순환 모형",
    5: "자동차 고장진단 학습지원 앱 프로젝트 모형",
    6: "학습자 활동 중심 고장진단 학습지원 앱 프로젝트 모형",
    7: "프로젝트 개발 도구 모형 매칭 시각화",
    8: "폭포수 모형",
    9: "폭포수 모형을 기반으로 한 프로젝트 개발 절차",
    10: "시작·로그인 화면",
    11: "NCS 능력단위 선택 화면",
    23: "사전·사후 형성평가 평균 점수 변화",
    24: "학생 설문조사 — 진단 능력 향상 영역 응답 결과",
    25: "학생 설문조사 — 피드백 만족도 영역 응답 결과",
    26: "학생 설문조사 — 자기 주도적 학습 경험 영역 응답 결과",
    27: "학생 설문조사 — 사용 편의성 영역 응답 결과",
    28: "학생 설문조사 — 전반적 만족도 영역 응답 결과",
}

FIGURE_SLUGS = {
    1: "피드백_병목_개념도",
    2: "ZPD_개념도",
    3: "Hattie_피드백_모형",
    4: "Zimmerman_SRL_모형",
    5: "프로젝트_모형",
    6: "학습자_활동_모형",
    7: "개발도구_매칭",
    8: "폭포수_모형",
    9: "개발_절차",
    10: "시작_로그인_화면",
    11: "NCS_능력단위_선택",
    23: "형성평가_점수변화",
    24: "설문_진단능력",
    25: "설문_피드백만족",
    26: "설문_자기주도학습",
    27: "설문_사용편의성",
    28: "설문_전반만족",
}

DEFAULT_FIGS = list(range(1, 12))
RESULT_FIGS = list(range(23, 29))


def setup():
    plt.rcParams.update({
        "font.family": "Malgun Gothic",
        "axes.unicode_minus": False,
        "figure.dpi": 150,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    })


def save(fig, num: int, dpi: int | None = None, pad: float | None = None):
    OUT_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    slug = FIGURE_SLUGS.get(num, f"fig_{num:02d}")
    fig.subplots_adjust(left=0.04, right=0.96, top=0.96, bottom=0.04)
    pad_inches = 0.35 if pad is None else pad
    for ext in ("png", "jpg"):
        kw = dict(facecolor="white", bbox_inches="tight", pad_inches=pad_inches, dpi=dpi or 200)
        p1 = OUT_DIR / f"fig_{num:02d}.{ext}"
        p2 = DOWNLOAD_DIR / f"그림_{num:02d}_{slug}.{ext}"
        fig.savefig(p1, **kw)
        fig.savefig(p2, **kw)
    plt.close(fig)
    print(f"  [OK] fig_{num:02d}.png/jpg + download/그림_{num:02d}_{slug}")


def _box(ax, x, y, w, h, text, fc="#E8F4FD", ec="#2E86AB", fs=9, zorder=2, label=None):
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=1.5, zorder=zorder,
    )
    ax.add_patch(rect)
    if label:
        ax.text(
            x + w / 2, y + h - 0.18, label,
            ha="center", va="top", fontsize=fs + 0.5, fontweight="bold",
            zorder=zorder + 1, linespacing=1.2,
        )
        text_y = y + h / 2 - 0.12
    else:
        text_y = y + h / 2
    ax.text(
        x + w / 2, text_y, text,
        ha="center", va="center", fontsize=fs, zorder=zorder + 1,
        linespacing=1.08 if fs >= 40 else (1.15 if fs >= 24 else 1.35),
    )


def _arrow(ax, x1, y1, x2, y2, color="#555", zorder=1, lw=1.8):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1), zorder=zorder,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                        shrinkA=4, shrinkB=4, mutation_scale=12),
    )


def _title(ax, text: str, size: int = 12):
    ax.set_title(text, fontsize=size, fontweight="bold", pad=18, y=1.02)


# ── [그림 1] 피드백 병목 ──────────────────────────────────────────
def fig01():
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 7)
    ax.axis("off")
    _title(ax, "자동차 전기·전자 제어 실기 교육 '피드백 병목' 개념도")

    # 학생 N명 (상단)
    students = ["학생 A", "학생 B", "학생 C", "학생 D", "…", "학생 N"]
    for i, label in enumerate(students):
        _box(ax, 0.6 + i * 1.65, 5.6, 1.35, 0.75, label, fc="#E3F2FD", ec="#1565C0", fs=8)
    ax.text(5.5, 6.55, "실습 참여 학생 N명", ha="center", fontsize=9, color="#1565C0", fontweight="bold")

    # 4단계 (중단 — 가로 배치)
    stages = ["① 준비/안전", "② 점검/회로도", "③ 측정/전압", "④ 판정/조치"]
    for i, s in enumerate(stages):
        _box(ax, 0.8 + i * 2.55, 3.5, 2.1, 0.9, s, fc="#F3E5F5", ec="#7B1FA2", fs=8)
        # 각 단계에서 학생들로 피드백 요구 (단순화: 위쪽 화살표 1개 + 라벨)
        cx = 0.8 + i * 2.55 + 1.05
        _arrow(ax, cx, 4.4, cx, 5.55, color="#C62828")
    ax.text(5.5, 4.95, "단계별 즉각 피드백 요구", ha="center",
            fontsize=9, color="#C62828", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="#FFEBEE", ec="#C62828", alpha=0.9))

    # 교사 1인 (하단 중앙)
    _box(ax, 4.0, 1.5, 3.0, 1.0, "교사 1인", fc="#FFE0B2", ec="#E65100", fs=11)
    _arrow(ax, 5.5, 2.5, 5.5, 3.45, color="#E65100")

    # 병목 설명
    _box(ax, 0.6, 0.3, 9.8, 0.95,
         "병목: 교사 1인 × 학생 N명 × 4단계 = 동시 다발적 피드백 요구 → 즉각 대응 한계",
         fc="#FFEBEE", ec="#C62828", fs=10)
    save(fig, 1)


# ── [그림 2] ZPD ──────────────────────────────────────────────────
def fig02():
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.5)
    ax.axis("off")
    _title(ax, "비고츠키의 근접발달영역(ZPD) 개념도")

    layers = [
        (4.8, 1.0, "잠재적 발달 수준", "#E0E0E0", "#616161", 10, False),
        (3.0, 1.5, "근접발달영역 (ZPD)\n도움을 받으면 해결 가능", "#C8E6C9", "#2E7D32", 11, True),
        (1.2, 1.0, "실제 발달 수준\n(혼자 해결 가능)", "#BBDEFB", "#1565C0", 10, False),
    ]
    for y, h, text, fc, ec, fs, bold in layers:
        ax.add_patch(mpatches.FancyBboxPatch(
            (1.5, y), 6.5, h, boxstyle="round,pad=0.02",
            facecolor=fc, edgecolor=ec, linewidth=2,
        ))
        ax.text(4.75, y + h / 2, text, ha="center", va="center",
                fontsize=fs, fontweight="bold" if bold else "normal")

    ax.annotate(
        "스캐폴딩\n(교사·동료·AI)",
        xy=(4.75, 4.0), xytext=(8.3, 4.0),
        fontsize=10, color="#2E7D32", fontweight="bold",
        ha="center", va="center",
        arrowprops=dict(arrowstyle="-|>", color="#2E7D32", lw=2, connectionstyle="arc3,rad=0"),
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#2E7D32"),
    )
    ax.annotate("", xy=(4.75, 2.2), xytext=(4.75, 3.15),
                arrowprops=dict(arrowstyle="-|>", color="#455A64", lw=1.5))
    ax.text(5.3, 2.65, "발달", fontsize=9, color="#455A64")
    save(fig, 2)


# ── [그림 3] Hattie 피드백 모형 ───────────────────────────────────
def fig03():
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.axis("off")
    _title(ax, "Hattie & Timperley(2007)의 피드백 모형")

    col_labels = [
        "Feed Up\n(Where am I going?)",
        "Feed Back\n(How am I going?)",
        "Feed Forward\n(Where to next?)",
    ]
    row_labels = [
        "과제 수준 (FT)",
        "과정 수준 (FP)",
        "자기조절 (FR)",
        "자기 수준 (FS)",
    ]
    cells = [
        ["4단계 미션 카드", "사실 + NCS기준", "보완 제안"],
        ["측정값 정확성", "절차 비교", "재수행 유도"],
        ["다시 평가 받기", "통과/보완 라벨", "AI 찬스 결정"],
        ["(의도적 차단)", "(의도적 차단)", "(의도적 차단)"],
    ]
    header = [""] + col_labels
    table_data = [[row_labels[r]] + cells[r] for r in range(4)]

    tbl = ax.table(
        cellText=table_data,
        colLabels=header,
        loc="center",
        cellLoc="center",
        colWidths=[0.18, 0.27, 0.27, 0.27],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.0, 2.4)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#455A64")
        cell.set_linewidth(1)
        if row == 0:
            cell.set_facecolor("#E8EEF7")
            cell.set_text_props(fontweight="bold", color="#1565C0")
        elif col == 0:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(fontweight="bold")
        else:
            colors = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#FFEBEE"]
            cell.set_facecolor(colors[row - 1])
    save(fig, 3)


# ── [그림 4] Zimmerman SRL ────────────────────────────────────────
def fig04():
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis("off")
    _title(ax, "Zimmerman(2002)의 자기조절학습 3단계 순환 모형")

    nodes = [
        (5.0, 6.5, 3.0, 1.4, "계획 (Forethought)",
         "목표 설정 · 전략 계획 · 자기효능감", "#E3F2FD", "#1565C0"),
        (2.2, 2.8, 3.0, 1.4, "자기 성찰\n(Self-reflection)",
         "자기 평가 · 적응적 반응 · 다시 평가", "#FFF3E0", "#E65100"),
        (7.8, 2.8, 3.0, 1.4, "수행 (Performance)",
         "자기 통제 · 자기 관찰 · 메모·사진", "#E8F5E9", "#2E7D32"),
    ]
    for x, y, w, h, title, sub, fc, ec in nodes:
        _box(ax, x - w / 2, y - h / 2, w, h, f"{title}\n\n{sub}", fc=fc, ec=ec, fs=9)

    style = "Simple,tail_width=0.6,head_width=5,head_length=7"
    kw = dict(arrowstyle=style, color="#455A64", lw=2, zorder=0)
    ax.add_patch(FancyArrowPatch((6.8, 5.6), (7.8, 3.8), connectionstyle="arc3,rad=-0.2", **kw))
    ax.add_patch(FancyArrowPatch((6.3, 2.8), (3.7, 2.8), connectionstyle="arc3,rad=0", **kw))
    ax.add_patch(FancyArrowPatch((2.7, 3.8), (4.0, 5.6), connectionstyle="arc3,rad=-0.2", **kw))

    ax.text(8.5, 4.6, "수행", fontsize=9, color="#455A64", fontweight="bold")
    ax.text(5.0, 2.0, "성찰", fontsize=9, color="#455A64", fontweight="bold")
    ax.text(2.5, 4.6, "계획", fontsize=9, color="#455A64", fontweight="bold")
    ax.text(5.0, 0.6, "← 순환 환류 (직전 학습 성찰 → 다음 학습 계획) →",
            ha="center", fontsize=10, color="#455A64")
    save(fig, 4)


def _flow_rect(ax, cx, cy, w, h, text, fc="#FFFFFF", ec="#333333", fs=8.5):
    x, y = cx - w / 2, cy - h / 2
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.06",
        facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=2,
    )
    ax.add_patch(rect)
    ls = 1.08 if fs >= 30 else 1.15
    txt = ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=3, linespacing=ls)
    txt.set_clip_path(rect)


def _flow_start_end(ax, cx, cy, w, h, text, fs=9):
    x, y = cx - w / 2, cy - h / 2
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.35",
        facecolor="#FFFFFF", edgecolor="#333333", linewidth=1.8, zorder=2,
    )
    ax.add_patch(rect)
    ls = 1.08 if fs >= 30 else 1.15
    txt = ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=3, linespacing=ls)
    txt.set_clip_path(rect)


def _flow_diamond(ax, cx, cy, w, h, text, fs=8):
    pts = np.array([
        [cx, cy + h / 2],
        [cx + w / 2, cy],
        [cx, cy - h / 2],
        [cx - w / 2, cy],
    ])
    poly = mpatches.Polygon(
        pts, closed=True, facecolor="#FFFFFF", edgecolor="#333333", linewidth=1.8, zorder=2,
    )
    ax.add_patch(poly)
    ls = 1.08 if fs >= 30 else 1.12
    txt = ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=3, linespacing=ls)
    txt.set_clip_path(poly)


def _flow_line(ax, x1, y1, x2, y2, color="#333333", lw=1.2):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1), zorder=1,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, shrinkA=2, shrinkB=2, mutation_scale=16),
    )


def _flow_label(ax, x, y, text, fs=7.5, ha="center", va="center"):
    ax.text(
        x, y, text, ha=ha, va=va, fontsize=fs, color="#222222", zorder=10,
        bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=1.0),
    )


def _label_on_arrow(ax, x1, y1, x2, y2, text, fs, orient="v-right", pad=1.0):
    """화살표 중간 지점에 분기 라벨을 붙인다."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if abs(x2 - x1) >= abs(y2 - y1):
        _flow_label(ax, mx, my + pad * 0.55, text, fs=fs, ha="center", va="bottom")
    elif orient == "v-right":
        _flow_label(ax, mx + pad, my, text, fs=fs, ha="left", va="center")
    else:
        _flow_label(ax, mx - pad, my, text, fs=fs, ha="right", va="center")


def _label_down_branch(ax, cx, y_from, y_to, text, fs, side="right", frac=0.34):
    """마름모 바로 아래 화살표 상단 구간, 세로 흐름선 옆에 라벨 배치."""
    gap = y_from - y_to
    y = y_from - frac * gap
    if side == "right":
        _flow_label(ax, cx + 0.68, y, text, fs=fs, ha="left", va="center")
    else:
        _flow_label(ax, cx - 0.68, y, text, fs=fs, ha="right", va="center")


# ── [그림 5] 프로젝트 모형 (신명은 2025 플로우차트 형식) ─────────────
def fig05():
    fig, ax = plt.subplots(figsize=(18, 32))
    ax.axis("off")

    cx = 9.2
    rx = 17.2
    fs, fs_lbl = 34, 30
    edge_gap = 1.05  # 분기 라벨(아니오·종료)이 들어갈 세로 화살표 길이 확보

    # 15칸 -> 10칸: 덜 중요한 직사각형 단계 병합, '추가 선택' 제거
    nodes = [
        ("start", "시스템\n시작"),
        ("rect", "NCS 단원 선택"),
        (
            "rect",
            "[학습자] 진단 입력 (3요소·메인 사진)\n"
            "[Gemini] 4단계 미션·소크라테스 발문 생성",
        ),
        ("rect", "[학습자] 4단계 실습 수행\n(메모·사진·완료·AI 찬스)"),
        (
            "rect",
            "[Gemini] NCS 루브릭 평가·피드백\n"
            "[학습자] 평가 결과 검토",
        ),
        ("diamond", "재수행\n여부"),
        ("rect", "Google Sheets·Plotly\n학습 데이터 집계·시각화·결과 출력"),
        ("rect", "PDF 생성"),
        ("diamond", "시스템\n선택"),
        ("start", "시스템\n종료"),
    ]

    def node_size(kind, text):
        lines = text.count("\n") + 1
        if kind == "start":
            return 7.0, 1.55 + 0.48 * (lines - 1)
        if kind == "diamond":
            return 7.4, 2.55 + 0.52 * (lines - 1)
        return 13.8, 1.30 + 0.68 * lines

    sizes = [node_size(k, t) for k, t in nodes]

    def half_h(i):
        return sizes[i][1] / 2

    ys = [0.0] * len(nodes)
    total_h = sum(h for _, h in sizes) + edge_gap * (len(nodes) - 1)
    ys[0] = total_h - sizes[0][1] / 2
    for i in range(1, len(nodes)):
        ys[i] = ys[i - 1] - sizes[i - 1][1] / 2 - edge_gap - sizes[i][1] / 2

    y_min = ys[-1] - half_h(-1) - 0.35
    y_max = ys[0] + half_h(0) + 0.35
    ax.set_xlim(0, 20)
    ax.set_ylim(y_min, y_max)

    for i, ((kind, text), cy) in enumerate(zip(nodes, ys)):
        w, h = sizes[i]
        if kind == "start":
            _flow_start_end(ax, cx, cy, w, h, text, fs=fs)
        elif kind == "rect":
            _flow_rect(ax, cx, cy, w, h, text, fs=fs)
        elif kind == "diamond":
            _flow_diamond(ax, cx, cy, w, h, text, fs=fs)

    def top_y(i):
        return ys[i] + half_h(i)

    def bot_y(i):
        return ys[i] - half_h(i)

    for i in range(len(nodes) - 1):
        _flow_line(ax, cx, bot_y(i), cx, top_y(i + 1), lw=2.4)

    i_redo, i_practice, i_data = 5, 3, 6
    y_redo = ys[i_redo]
    x_dia_r = cx + sizes[i_redo][0] / 2
    _flow_line(ax, x_dia_r, y_redo, rx, y_redo, lw=2.4)
    _flow_line(ax, rx, y_redo, rx, ys[i_practice], lw=2.4)
    _flow_line(ax, rx, ys[i_practice], cx + sizes[i_practice][0] / 2, ys[i_practice], lw=2.4)
    _label_on_arrow(ax, x_dia_r, y_redo, rx, y_redo, "예", fs_lbl, orient="h-above", pad=0.45)
    _label_down_branch(ax, cx, bot_y(i_redo), top_y(i_data), "아니오", fs_lbl, side="left", frac=0.34)

    # PDF 생성 후 시스템 선택: 재시작(우측 루프) / 종료(아래)
    i_sys, i_ncs = 8, 1
    y_sys = ys[i_sys]
    x_dia_r_sys = cx + sizes[i_sys][0] / 2
    _flow_line(ax, x_dia_r_sys, y_sys, rx, y_sys, lw=2.4)
    _flow_line(ax, rx, y_sys, rx, ys[i_ncs], lw=2.4)
    _flow_line(ax, rx, ys[i_ncs], cx + sizes[i_ncs][0] / 2, ys[i_ncs], lw=2.4)
    _label_on_arrow(ax, x_dia_r_sys, y_sys, rx, y_sys, "재시작", fs_lbl, orient="h-above", pad=0.45)
    _label_down_branch(ax, cx, bot_y(i_sys), top_y(len(nodes) - 1), "종료", fs_lbl, side="right", frac=0.34)

    save(fig, 5, dpi=300, pad=0.12)


# ── [그림 6] 학습자 활동 중심 모형 (신명은 2025 학습자 측면 세부 흐름) ──
def fig06():
    fig, ax = plt.subplots(figsize=(18, 34))
    ax.axis("off")

    cx = 9.2
    rx = 17.2
    lx = 1.8
    fs, fs_lbl = 32, 28
    edge_gap = 0.88

    # 14칸 → 11칸: 시작·로그인, 평가·검토, 저장·포트폴리오 병합
    nodes = [
        ("start", "고장진단 학습 시작\n(로그인·학습 시작)"),
        ("diamond", "NCS\n단원 선택"),
        ("rect", "진단 입력 화면\n(3요소·메인 사진)"),
        ("rect", "[학습자 활동] 4단계 실습 수행\n(메모·사진·완료·AI 찬스)"),
        (
            "rect",
            "AI 평가 요청·결과 검토\n(제출하기 → [학습자 활동] 검토)",
        ),
        ("diamond", "재수행\n여부"),
        (
            "rect",
            "학습 기록 저장·결과 페이지\n(이대로 저장 · NCS 점수·누적 차트)",
        ),
        ("diamond", "다음 행동\n선택"),
        ("rect", "PDF 내보내기"),
        ("diamond", "PDF 내보내기\n후 선택"),
        ("start", "완료"),
    ]

    branch_extra = 1.55  # NCS 3분기 행 높이

    def node_size(kind, text):
        lines = text.count("\n") + 1
        if kind == "start":
            return 7.0, 1.55 + 0.48 * (lines - 1)
        if kind == "diamond":
            return 7.4, 2.55 + 0.52 * (lines - 1)
        return 13.8, 1.30 + 0.68 * lines

    sizes = [node_size(k, t) for k, t in nodes]

    def half_h(i):
        return sizes[i][1] / 2

    ys = [0.0] * len(nodes)
    total_h = sum(h for _, h in sizes) + edge_gap * (len(nodes) - 1) + branch_extra
    ys[0] = total_h - sizes[0][1] / 2
    for i in range(1, len(nodes)):
        extra = branch_extra if i == 2 else 0.0
        ys[i] = ys[i - 1] - sizes[i - 1][1] / 2 - edge_gap - extra - sizes[i][1] / 2

    y_min = ys[-1] - half_h(-1) - 0.28
    y_max = ys[0] + half_h(0) + 0.28
    ax.set_xlim(0, 20)
    ax.set_ylim(y_min, y_max)

    for i, ((kind, text), cy) in enumerate(zip(nodes, ys)):
        w, h = sizes[i]
        if kind == "start":
            _flow_start_end(ax, cx, cy, w, h, text, fs=fs)
        elif kind == "rect":
            _flow_rect(ax, cx, cy, w, h, text, fs=fs)
        elif kind == "diamond":
            _flow_diamond(ax, cx, cy, w, h, text, fs=fs)

    def top_y(i):
        return ys[i] + half_h(i)

    def bot_y(i):
        return ys[i] - half_h(i)

    for i in range(len(nodes) - 1):
        if i == 1:
            continue
        if i == 2:
            continue
        _flow_line(ax, cx, bot_y(i), cx, top_y(i + 1), lw=2.4)

    # NCS 단원 선택 → 3분기 → 진단 입력
    y_dia_bot = bot_y(1)
    y_branch = y_dia_bot - edge_gap - 0.38
    y_merge = y_branch - 0.72
    y_input_top = top_y(2)
    branch_labels = [
        "고장진단·\n배터리 점검",
        "시동·충전·\n조명 장치",
        "편의·\n네트워크 장치",
    ]
    bx = [cx - 5.2, cx, cx + 5.2]
    bw_b, bh_b = 4.9, 1.42
    for x, lbl in zip(bx, branch_labels):
        _flow_rect(ax, x, y_branch, bw_b, bh_b, lbl, fs=fs - 2)
        _flow_line(ax, cx, y_dia_bot, x, y_branch + bh_b / 2, lw=2.2)
        _flow_line(ax, x, y_branch - bh_b / 2, cx, y_merge, lw=2.2)
    _flow_line(ax, cx, y_merge, cx, y_input_top, lw=2.4)

    # 재수행: 예 → 보완·재수행 → 4단계 실습
    i_practice, i_redo = 3, 5
    y_redo = ys[i_redo]
    x_dia_r = cx + sizes[i_redo][0] / 2
    y_redo_box = ys[i_practice]
    _flow_rect(
        ax, rx - 0.15, y_redo_box, 5.8, 1.38,
        "[학습자 활동]\n4단계 보완·재수행", fs=fs - 2,
    )
    _flow_line(ax, x_dia_r, y_redo, rx, y_redo, lw=2.4)
    _flow_line(ax, rx, y_redo, rx, y_redo_box, lw=2.4)
    _flow_line(ax, rx, y_redo_box, cx + sizes[i_practice][0] / 2, ys[i_practice], lw=2.4)
    _label_on_arrow(ax, x_dia_r, y_redo, rx, y_redo, "예", fs_lbl, orient="h-above", pad=0.42)
    _label_down_branch(ax, cx, bot_y(i_redo), top_y(6), "아니오", fs_lbl, side="left", frac=0.34)

    # 다음 행동 선택: 처음으로 / PDF / 종료
    i_next, i_ncs, i_pdf, i_pdf_after = 7, 1, 8, 9
    y_next = ys[i_next]
    x_dia_r_next = cx + sizes[i_next][0] / 2
    x_dia_l_next = cx - sizes[i_next][0] / 2
    _flow_line(ax, x_dia_r_next, y_next, rx, y_next, lw=2.4)
    _flow_line(ax, rx, y_next, rx, ys[i_ncs], lw=2.4)
    _flow_line(ax, rx, ys[i_ncs], cx + sizes[i_ncs][0] / 2, ys[i_ncs], lw=2.4)
    _label_on_arrow(
        ax, x_dia_r_next, y_next, rx, y_next,
        "처음으로", fs_lbl, orient="h-above", pad=0.42,
    )
    _flow_line(ax, x_dia_l_next, y_next, lx, y_next, lw=2.4)
    _flow_line(ax, lx, y_next, lx, ys[-1], lw=2.4)
    _flow_line(ax, lx, ys[-1], cx - sizes[-1][0] / 2, ys[-1], lw=2.4)
    _label_on_arrow(ax, x_dia_l_next, y_next, lx, y_next, "종료", fs_lbl, orient="h-above", pad=0.42)
    _label_down_branch(ax, cx, bot_y(i_next), top_y(i_pdf), "PDF", fs_lbl, side="right", frac=0.34)

    # PDF 후 선택: 처음으로 / 완료
    y_pdf_after = ys[i_pdf_after]
    x_dia_r_pdf = cx + sizes[i_pdf_after][0] / 2
    _flow_line(ax, x_dia_r_pdf, y_pdf_after, rx, y_pdf_after, lw=2.4)
    _flow_line(ax, rx, y_pdf_after, rx, ys[i_ncs], lw=2.4)
    _label_on_arrow(
        ax, x_dia_r_pdf, y_pdf_after, rx, y_pdf_after,
        "처음으로", fs_lbl, orient="h-above", pad=0.42,
    )
    _label_down_branch(ax, cx, bot_y(i_pdf_after), top_y(len(nodes) - 1), "종료", fs_lbl, side="right", frac=0.34)

    save(fig, 6, dpi=300, pad=0.12)


# 개발 도구 색상 팔레트 (그림 7 범례·태그 공통)
TOOL_PALETTE = {
    "streamlit": ("Streamlit", "#FFF59D", "#F9A825"),
    "html": ("HTML·CSS", "#FFF176", "#F9A825"),
    "gemini": ("Gemini 2.5 Flash", "#A5D6A7", "#2E7D32"),
    "ncs": ("NCS_RUBRIC", "#DCEDC8", "#558B2F"),
    "pillow": ("Pillow", "#FFCC80", "#E65100"),
    "sheets": ("Google Sheets", "#90CAF9", "#1565C0"),
    "plotly": ("Plotly·pandas", "#80DEEA", "#00838F"),
    "fpdf": ("fpdf2·malgun", "#CE93D8", "#7B1FA2"),
}


def _tool_strip_height(n_tools: int, row_h: float = 0.78) -> float:
    if n_tools <= 0:
        return 0.0
    rows = 1 if n_tools <= 2 else 2
    return rows * row_h + 0.12


def _draw_tool_strip(ax, cx, cy, w, tool_keys, fs_tool=22, row_h=0.78):
    """노드 하단에 개발 도구 색상 태그를 가로·2열 배치."""
    if not tool_keys:
        return
    n = len(tool_keys)
    cols = n if n <= 2 else 2
    rows = int(np.ceil(n / cols))
    strip_h = rows * row_h + 0.08
    y0 = cy - strip_h / 2
    x0 = cx - w / 2
    cell_w = w / cols

    for idx, key in enumerate(tool_keys):
        label, fc, ec = TOOL_PALETTE[key]
        r, c = divmod(idx, cols)
        px = x0 + c * cell_w + 0.03
        py = y0 + strip_h - (r + 1) * row_h + 0.03
        pw, ph = cell_w - 0.06, row_h - 0.06
        cell = FancyBboxPatch(
            (px, py), pw, ph, boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor=fc, edgecolor=ec, linewidth=1.4, zorder=3,
        )
        ax.add_patch(cell)
        txt = ax.text(
            px + pw / 2, py + ph / 2, label,
            ha="center", va="center", fontsize=fs_tool, zorder=4, linespacing=1.05,
        )
        txt.set_clip_path(cell)


def _flow_rect_with_tools(ax, cx, cy, w, h_body, text, tool_keys, fs=34, fs_tool=22):
    strip_h = _tool_strip_height(len(tool_keys))
    total_h = h_body + strip_h
    x0 = cx - w / 2
    y0 = cy - total_h / 2

    outer = FancyBboxPatch(
        (x0, y0), w, total_h, boxstyle="round,pad=0.03,rounding_size=0.06",
        facecolor="#FFFFFF", edgecolor="#333333", linewidth=1.8, zorder=2,
    )
    ax.add_patch(outer)

    if strip_h > 0:
        ax.plot([x0 + 0.06, x0 + w - 0.06], [y0 + strip_h, y0 + strip_h], color="#333333", lw=1.2, zorder=3)

    body_cy = y0 + strip_h + h_body / 2
    ls = 1.08 if fs >= 30 else 1.15
    txt = ax.text(cx, body_cy, text, ha="center", va="center", fontsize=fs, zorder=4, linespacing=ls)
    txt.set_clip_path(outer)

    if tool_keys:
        strip_cy = y0 + strip_h / 2
        _draw_tool_strip(ax, cx, strip_cy, w - 0.14, tool_keys, fs_tool=fs_tool)


ROLE_LABEL = {
    "streamlit": "Streamlit",
    "html": "HTML·CSS",
    "gemini": "Gemini",
    "ncs": "NCS_RUBRIC",
    "pillow": "Pillow",
    "sheets": "Google Sheets",
    "plotly": "Plotly·pandas",
    "fpdf": "fpdf2·malgun",
}


def _role_entries(role_lines):
    """도구별 '주제: 간략한 설명' 한 줄 형식 (줄바꿈 없음)."""
    return [
        (key, f"{ROLE_LABEL[key]}: {desc}")
        for key, desc in role_lines
    ]


def _draw_step_roles(ax, cx, cy, w, h, role_lines, fs_max=30):
    """모형 오른쪽 — 왼쪽 노드와 동일 크기, 도구당 한 줄 설명."""
    if not role_lines:
        return
    pad_x, pad_y = 0.38, 0.36
    x0, y0 = cx - w / 2, cy - h / 2
    patch = FancyBboxPatch(
        (x0, y0), w, h, boxstyle="round,pad=0.03,rounding_size=0.06",
        facecolor="#F5F5F5", edgecolor="#78909C", linewidth=1.8, zorder=3,
    )
    ax.add_patch(patch)

    entries = _role_entries(role_lines)
    fs = fs_max
    while fs >= 20:
        n = len(entries)
        line_step = (h - 2 * pad_y) / max(n, 1)
        if line_step >= fs * 0.021:
            break
        fs -= 2

    n = len(entries)
    line_step = (h - 2 * pad_y) / max(n, 1)
    top = cy + h / 2 - pad_y
    for i, (key, line) in enumerate(entries):
        y = top - (i + 0.5) * line_step
        _, _, ec = TOOL_PALETTE[key]
        txt = ax.text(
            x0 + pad_x, y, line,
            ha="left", va="center", fontsize=fs, color=ec, fontweight="bold", zorder=4,
        )
        txt.set_clip_path(patch)


# ── [그림 7] 개발 도구 모형 매칭 (그림 5 + 단계별 도구 색상 태그) ──
def fig07():
    fig, ax = plt.subplots(figsize=(38, 42))
    ax.axis("off")

    cx = 9.2
    box_gap = 3.6
    flow_w = 13.8
    note_cx = cx + flow_w + box_gap
    rx = note_cx + flow_w / 2 + 2.2
    fs, fs_lbl, fs_tool, fs_role = 34, 28, 24, 30
    edge_gap = 1.05

    # (kind, text, tool_keys, role_lines: [(tool_key, 설명), ...])
    nodes = [
        ("start", "시스템\n시작", [], None),
        (
            "rect", "NCS 단원 선택", ["streamlit", "html"],
            [("streamlit", "NCS 단원 UI"), ("html", "반응형 스타일")],
        ),
        (
            "rect",
            "[학습자] 진단 입력 (3요소·메인 사진)\n"
            "[Gemini] 4단계 미션·소크라테스 발문 생성",
            ["streamlit", "pillow", "gemini", "ncs"],
            [
                ("streamlit", "3요소·사진 입력"),
                ("pillow", "이미지 압축"),
                ("gemini", "미션·소크라테스 발문"),
                ("ncs", "PeDK 수행준거 주입"),
            ],
        ),
        (
            "rect", "[학습자] 4단계 실습 수행\n(메모·사진·완료·AI 찬스)", ["streamlit"],
            [
                ("streamlit", "메모·사진·완료 UI"),
                ("streamlit", "AI 찬스·감점 표시"),
            ],
        ),
        (
            "rect",
            "[Gemini] NCS 루브릭 평가·피드백\n"
            "[학습자] 평가 결과 검토",
            ["gemini", "streamlit"],
            [
                ("gemini", "NCS 루브릭 평가"),
                ("streamlit", "검토·저장·재수행"),
            ],
        ),
        ("diamond", "재수행\n여부", [], None),
        (
            "rect",
            "Google Sheets·Plotly\n학습 데이터 집계·시각화·결과 출력",
            ["sheets", "plotly"],
            [
                ("sheets", "학습 기록 저장"),
                ("plotly", "NCS·카테고리 차트"),
            ],
        ),
        (
            "rect", "PDF 생성", ["fpdf"],
            [("fpdf", "포트폴리오 PDF 출력")],
        ),
        ("diamond", "시스템\n선택", [], None),
        ("start", "시스템\n종료", [], None),
    ]

    def node_body_size(kind, text):
        lines = text.count("\n") + 1
        if kind == "start":
            return 7.0, 1.55 + 0.48 * (lines - 1)
        if kind == "diamond":
            return 7.4, 2.55 + 0.52 * (lines - 1)
        return 13.8, 1.30 + 0.68 * lines

    body_sizes = [node_body_size(k, t) for k, t, _, _ in nodes]
    sizes = [
        (w, h + _tool_strip_height(len(tools)))
        for (w, h), (_, _, tools, _) in zip(body_sizes, nodes)
    ]

    def half_h(i):
        return sizes[i][1] / 2

    ys = [0.0] * len(nodes)
    total_h = sum(h for _, h in sizes) + edge_gap * (len(nodes) - 1)
    ys[0] = total_h - sizes[0][1] / 2
    for i in range(1, len(nodes)):
        ys[i] = ys[i - 1] - sizes[i - 1][1] / 2 - edge_gap - sizes[i][1] / 2

    y_min = ys[-1] - half_h(-1) - 0.45
    y_max = ys[0] + half_h(0) + 0.35
    ax.set_xlim(0, 38)
    ax.set_ylim(y_min, y_max)

    for i, ((kind, text, tools, roles), cy) in enumerate(zip(nodes, ys)):
        w, h_body = body_sizes[i]
        box_w, box_h = sizes[i]
        if kind == "start":
            _flow_start_end(ax, cx, cy, w, h_body, text, fs=fs)
        elif kind == "diamond":
            _flow_diamond(ax, cx, cy, w, h_body, text, fs=fs)
        else:
            _flow_rect_with_tools(ax, cx, cy, w, h_body, text, tools, fs=fs, fs_tool=fs_tool)

        if roles:
            _draw_step_roles(ax, note_cx, cy, box_w, box_h, roles, fs_max=fs_role)
            fx = cx + box_w / 2
            nx = note_cx - box_w / 2
            ax.plot([fx + 0.1, nx - 0.08], [cy, cy], linestyle=(0, (4, 3)), color="#78909C", lw=1.4, zorder=1)

    def top_y(i):
        return ys[i] + half_h(i)

    def bot_y(i):
        return ys[i] - half_h(i)

    for i in range(len(nodes) - 1):
        _flow_line(ax, cx, bot_y(i), cx, top_y(i + 1), lw=2.4)

    i_redo, i_practice, i_data = 5, 3, 6
    y_redo = ys[i_redo]
    x_dia_r = cx + body_sizes[i_redo][0] / 2
    _flow_line(ax, x_dia_r, y_redo, rx, y_redo, lw=2.4)
    _flow_line(ax, rx, y_redo, rx, ys[i_practice], lw=2.4)
    _flow_line(ax, rx, ys[i_practice], cx + body_sizes[i_practice][0] / 2, ys[i_practice], lw=2.4)
    _label_on_arrow(ax, x_dia_r, y_redo, rx, y_redo, "예", fs_lbl, orient="h-above", pad=0.45)
    _label_down_branch(ax, cx, bot_y(i_redo), top_y(i_data), "아니오", fs_lbl, side="left", frac=0.34)

    i_sys, i_ncs = 8, 1
    y_sys = ys[i_sys]
    x_dia_r_sys = cx + body_sizes[i_sys][0] / 2
    _flow_line(ax, x_dia_r_sys, y_sys, rx, y_sys, lw=2.4)
    _flow_line(ax, rx, y_sys, rx, ys[i_ncs], lw=2.4)
    _flow_line(ax, rx, ys[i_ncs], cx + body_sizes[i_ncs][0] / 2, ys[i_ncs], lw=2.4)
    _label_on_arrow(ax, x_dia_r_sys, y_sys, rx, y_sys, "재시작", fs_lbl, orient="h-above", pad=0.45)
    _label_down_branch(ax, cx, bot_y(i_sys), top_y(len(nodes) - 1), "종료", fs_lbl, side="right", frac=0.34)

    save(fig, 7, dpi=300, pad=0.12)


# ── [그림 8] 폭포수 모형 ──────────────────────────────────────────
def fig08():
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis("off")
    _title(ax, "폭포수 모형 (Waterfall Model)")

    phases = ["요구사항 분석", "설계", "구현", "테스트", "운영·유지보수"]
    colors = ["#E3F2FD", "#BBDEFB", "#90CAF9", "#64B5F6", "#42A5F5"]
    x_start, base_w, h, gap, step = 1.0, 6.5, 1.0, 0.25, 0.55
    for i, (p, c) in enumerate(zip(phases, colors)):
        y = 7.0 - i * (h + gap)
        width = base_w - i * step
        ax.add_patch(mpatches.FancyBboxPatch(
            (x_start, y), width, h, boxstyle="round,pad=0.02",
            facecolor=c, edgecolor="#1565C0", linewidth=2,
        ))
        ax.text(x_start + width / 2, y + h / 2, p, ha="center", va="center", fontsize=11)
        if i < len(phases) - 1:
            x_right = x_start + width
            y_next_top = y - gap
            ax.plot([x_right, x_right - step], [y, y], color="#1565C0", lw=2)
            ax.plot([x_right - step, x_right - step], [y, y_next_top - h], color="#1565C0", lw=2)

    ax.text(8.5, 4.0, "순차적\n단방향\n진행", ha="center", va="center", fontsize=10,
            color="#455A64", bbox=dict(boxstyle="round,pad=0.4", fc="#F5F5F5", ec="#BDBDBD"))
    save(fig, 8)


# ── [그림 9] 폭포수 기반 개발 절차 ────────────────────────────────
def fig09():
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axis("off")
    _title(ax, "폭포수 모형을 기반으로 한 프로젝트 개발 절차")

    details = [
        ("요구사항 분석", "NCS 6단원 · 4단계 미션 · AI 찬스 · 평가 루브릭"),
        ("설계", "화면 흐름 · 역할 분리 · 프롬프트 4종"),
        ("구현", "app.py · sheets_backend.py · Gemini 연동"),
        ("테스트", "UI · 멀티모달 · 감점 · PDF · Sheets 안정성"),
        ("운영·유지보수", "Streamlit Cloud 배포 · GitHub 이슈 추적"),
    ]
    tbl = ax.table(
        cellText=[[d[1]] for d in details],
        rowLabels=[d[0] for d in details],
        colLabels=["세부 내용"],
        loc="center",
        cellLoc="left",
        colWidths=[0.72],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 2.2)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#455A64")
        cell.PAD = 0.08
        if row == 0:
            cell.set_facecolor("#E8EEF7")
            cell.set_text_props(fontweight="bold")
        elif col == -1:
            cell.set_facecolor("#BBDEFB")
            cell.set_text_props(fontweight="bold")
        else:
            cell.set_facecolor("#FAFAFA")
    save(fig, 9)


def _draw_browser_frame(ax, x0, y0, w, h, url="localhost:8501"):
    """앱 UI 목업용 브라우저 프레임."""
    ax.add_patch(Rectangle((x0, y0), w, h, facecolor="#F8FAFC", edgecolor="#CBD5E1", lw=2))
    ax.add_patch(Rectangle((x0, y0 + h - 0.35), w, 0.35, facecolor="#E2E8F0", edgecolor="#CBD5E1", lw=1))
    ax.add_patch(Circle((x0 + 0.18, y0 + h - 0.175), 0.06, facecolor="#FCA5A5", edgecolor="none"))
    ax.add_patch(Circle((x0 + 0.32, y0 + h - 0.175), 0.06, facecolor="#FDE68A", edgecolor="none"))
    ax.add_patch(Circle((x0 + 0.46, y0 + h - 0.175), 0.06, facecolor="#86EFAC", edgecolor="none"))
    ax.add_patch(FancyBboxPatch(
        (x0 + 0.7, y0 + h - 0.28), w - 1.0, 0.2,
        boxstyle="round,pad=0.01", facecolor="#FFFFFF", edgecolor="#94A3B8", lw=1,
    ))
    ax.text(x0 + w / 2, y0 + h - 0.18, url, ha="center", va="center", fontsize=7, color="#64748B")


def _draw_button(ax, x, y, w, h, label, fc="#2563EB", tc="white", fs=9):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02",
        facecolor=fc, edgecolor=fc, linewidth=1,
    ))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fs, color=tc, fontweight="bold")


def _draw_input(ax, x, y, w, h, label, placeholder=""):
    ax.text(x, y + h + 0.05, label, fontsize=8, fontweight="bold", color="#334155")
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.01",
        facecolor="#FFFFFF", edgecolor="#94A3B8", linewidth=1.2,
    ))
    if placeholder:
        ax.text(x + 0.12, y + h / 2, placeholder, va="center", fontsize=8, color="#94A3B8")


# ── [그림 10] 시작·로그인 화면 (앱 UI 목업) ───────────────────────
def fig10():
    fig, axes = plt.subplots(1, 2, figsize=(15, 8))
    fig.suptitle("[그림 10] 시작·로그인 화면", fontsize=14, fontweight="bold", y=1.0)

    # ── 좌: 시작(랜딩) 화면 ──
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("① 시작 화면 (역할 선택)", fontsize=11, fontweight="bold", pad=14)
    _draw_browser_frame(ax, 0.4, 0.5, 9.2, 8.5)

    ax.text(5, 7.6, "자동차 고장진단 AI tutor", ha="center", fontsize=13,
            fontweight="bold", color="#1E3A8A")
    ax.text(5, 7.0, "자동차 전기전자제어 · NCS 수행준거 기반 학습 도우미",
            ha="center", fontsize=8.5, color="#475569")
    ax.text(5, 6.45, "아래 카드를 클릭해 역할을 선택해 주세요.",
            ha="center", fontsize=8, color="#64748B")

    _box(ax, 0.9, 3.6, 3.6, 2.2, "교사 모드\n\n학생 실습 기록 확인\n피드백 작성",
         fc="#FFF59D", ec="#F9A825", fs=10)
    _box(ax, 5.5, 3.6, 3.6, 2.2, "학생 모드\n\n고장진단 실습 진행\n포트폴리오 작성",
         fc="#90CAF9", ec="#1565C0", fs=10)

    ax.text(5, 1.3, "NCS 수행준거 기반 · 소크라테스식 AI 학습 지원",
            ha="center", fontsize=7.5, color="#94A3B8")

    # ── 우: 학생 로그인 화면 ──
    ax = axes[1]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("② 학생 로그인 화면", fontsize=11, fontweight="bold", pad=14)
    _draw_browser_frame(ax, 0.4, 0.5, 9.2, 8.5)

    ax.text(5, 7.5, "학생 로그인", ha="center", fontsize=12, fontweight="bold", color="#1E293B")
    _draw_input(ax, 2.2, 6.0, 5.6, 0.5, "학번", "예: 20240101")
    _draw_input(ax, 2.2, 4.85, 5.6, 0.5, "이름", "예: 홍길동")
    _draw_input(ax, 2.2, 3.7, 5.6, 0.5, "비밀번호", "******")
    _draw_button(ax, 2.2, 2.6, 5.6, 0.6, "로그인")

    _box(ax, 1.8, 1.2, 6.4, 0.9,
         "로그인 후 NCS 능력단위 선택 → 진단 실습 시작",
         fc="#EFF6FF", ec="#93C5FD", fs=8)

    fig.subplots_adjust(wspace=0.25, top=0.88)
    save(fig, 10)


# ── [그림 11] NCS 능력단위 선택 화면 (앱 UI 목업) ─────────────────
def fig11():
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 10.5)
    ax.axis("off")
    _title(ax, "[그림 11] NCS 능력단위 선택 화면", size=14)
    _draw_browser_frame(ax, 0.5, 0.8, 11.0, 8.8, "자동차 고장진단 AI tutor")

    ax.text(6, 8.7, "NCS 능력단위 선택", ha="center", fontsize=12, fontweight="bold", color="#1E3A8A")
    ax.text(6, 8.2, "이번 차시에 학습할 단원을 선택하세요. (자동차 전기전자제어)",
            ha="center", fontsize=9, color="#475569")

    units = [
        ("자동차 전기전자장치\n고장진단", "#DBEAFE", "#2563EB"),
        ("배터리 점검", "#D1FAE5", "#059669"),
        ("시동·충전장치 점검", "#E0E7FF", "#4F46E5"),
        ("조명장치 점검", "#FEF3C7", "#D97706"),
        ("편의장치 점검", "#FCE7F3", "#DB2777"),
        ("네트워크 장치 점검", "#E0F2FE", "#0284C7"),
    ]
    cw, ch, gx, gy = 3.2, 1.8, 0.4, 0.5
    x0, y_row1, y_row2 = 1.0, 5.5, 3.2
    xs = [x0, x0 + cw + gx, x0 + 2 * (cw + gx)]
    positions = [(xs[0], y_row1), (xs[1], y_row1), (xs[2], y_row1),
                   (xs[0], y_row2), (xs[1], y_row2), (xs[2], y_row2)]

    for (name, bg, border), (x, y) in zip(units, positions):
        _box(ax, x, y, cw, ch, name, fc=bg, ec=border, fs=9)

    # 선택 강조 (배터리 점검)
    sel_x, sel_y = xs[1], y_row1
    ax.add_patch(FancyBboxPatch(
        (sel_x - 0.08, sel_y - 0.08), cw + 0.16, ch + 0.16,
        boxstyle="round,pad=0.02", facecolor="none",
        edgecolor="#DC2626", linewidth=2.5, linestyle="--", zorder=5,
    ))
    ax.text(sel_x + cw / 2, sel_y + ch + 0.25, "▲ 선택됨",
            ha="center", fontsize=8, color="#DC2626", fontweight="bold")

    _draw_button(ax, 4.5, 1.5, 3.0, 0.65, "다음 →", fc="#2563EB")
    ax.text(6, 0.95, "6개 NCS 능력단위 중 1개 선택 → 진단 입력 화면으로 이동",
            ha="center", fontsize=8, color="#64748B")
    save(fig, 11)


# ── [그림 23] 사전·사후 형성평가 ──────────────────────────────────
def fig23():
    fig, ax = plt.subplots(figsize=(6, 4.5))
    labels = ["사전 평가", "사후 평가"]
    # 예상 결과 틀용 샘플 값 (실험 후 교체)
    means = [42.5, 58.3]
    stds = [8.2, 7.5]
    x = np.arange(len(labels))
    bars = ax.bar(x, means, yerr=stds, capsize=6, color=["#90CAF9", "#66BB6A"],
                  edgecolor="#37474F", width=0.5)
    ax.set_ylabel("평균 점수 (80점 만점)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 80)
    ax.set_title("사전·사후 형성평가 평균 점수 변화\n(예상 결과 틀 — 실험 후 데이터로 교체)",
                 fontsize=10, fontweight="bold")
    for bar, m in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 10,
                f"{m:.1f}점", ha="center", fontsize=10, fontweight="bold")
    ax.axhline(y=40, color="#E53935", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.text(1.4, 41, "저점수 구간(40점)", fontsize=7, color="#E53935")
    save(fig, 23)


# ── 설문 영역별 차트 (24~28) ──────────────────────────────────────
SURVEY_DOMAINS = {
    24: ("진단 능력 향상", ["Q1 절차 구분", "Q2 회로·측정", "Q3 판정 능력"]),
    25: ("피드백 만족도", ["Q4 명확·친절", "Q5 보완 인식", "Q6 실질 도움"]),
    26: ("자기 주도적 학습", ["Q7 자기 인식", "Q8 재수행", "Q9 AI 찬스 결정"]),
    27: ("사용 편의성", ["Q10 입력·업로드", "Q11 미션 카드", "Q12 모바일"]),
    28: ("전반적 만족도", ["Q13 자신감", "Q14 지속 활용", "Q15 추천 의향"]),
}

LIKERT_LABELS = ["매우\n그렇다", "그렇다", "보통", "그렇지\n않다", "전혀\n아님"]
LIKERT_COLORS = ["#1B5E20", "#66BB6A", "#FFCA28", "#FFA726", "#EF5350"]

# 예상 분포 샘플 (%) — 실험 후 교체
SAMPLE_DIST = [
    [35, 40, 18, 5, 2],
    [30, 45, 20, 3, 2],
    [28, 42, 22, 6, 2],
]


def _survey_fig(num: int, domain: str, questions: list[str]):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.8), sharey=True)
    fig.suptitle(f"학생 설문조사 — {domain} 영역 응답 결과\n(예상 결과 틀 — 실험 후 데이터로 교체)",
                 fontsize=10, fontweight="bold")

    for ax, q, dist in zip(axes, questions, SAMPLE_DIST):
        bottom = 0
        for pct, label, color in zip(dist, LIKERT_LABELS, LIKERT_COLORS):
            ax.bar(0, pct, bottom=bottom, color=color, width=0.6, edgecolor="white")
            if pct >= 8:
                ax.text(0, bottom + pct / 2, f"{pct}%", ha="center", va="center",
                        fontsize=7, color="white", fontweight="bold")
            bottom += pct
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(0, 100)
        ax.set_xticks([])
        ax.set_title(q, fontsize=8)
        ax.set_ylabel("응답 비율 (%)" if ax == axes[0] else "")

    handles = [mpatches.Patch(color=c, label=l.replace("\n", " "))
               for c, l in zip(LIKERT_COLORS, LIKERT_LABELS)]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=7,
               bbox_to_anchor=(0.5, -0.02))
    save(fig, num)


def fig24():
    d, qs = SURVEY_DOMAINS[24]
    _survey_fig(24, d, qs)


def fig25():
    d, qs = SURVEY_DOMAINS[25]
    _survey_fig(25, d, qs)


def fig26():
    d, qs = SURVEY_DOMAINS[26]
    _survey_fig(26, d, qs)


def fig27():
    d, qs = SURVEY_DOMAINS[27]
    _survey_fig(27, d, qs)


def fig28():
    d, qs = SURVEY_DOMAINS[28]
    _survey_fig(28, d, qs)


GENERATORS = {
    1: fig01, 2: fig02, 3: fig03, 4: fig04, 5: fig05,
    6: fig06, 7: fig07, 8: fig08, 9: fig09,
    10: fig10, 11: fig11,
    23: fig23, 24: fig24, 25: fig25, 26: fig26, 27: fig27, 28: fig28,
}


def main(fig_nums: list[int] | None = None):
    setup()
    OUT_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    targets = fig_nums or DEFAULT_FIGS
    print(f"Generating figures -> {OUT_DIR}")
    print(f"Download copies -> {DOWNLOAD_DIR}\n")
    for n in targets:
        if n not in GENERATORS:
            print(f"  [SKIP] fig_{n:02d} (no generator)")
            continue
        GENERATORS[n]()
    if not fig_nums:
        skipped = ", ".join(f"fig_{n:02d}" for n in sorted(APP_SCREENSHOT_FIGS))
        print(f"\nNot generated (use real app capture): {skipped}")
    print(f"\nDone - {len(targets)} figure(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="연구계획서 그림 생성")
    parser.add_argument("--all", action="store_true", help="그림 1~11 + 23~28 전체 생성")
    parser.add_argument("--fig", type=int, nargs="+", help="특정 그림 번호만 생성")
    args = parser.parse_args()
    if args.fig:
        main(args.fig)
    elif args.all:
        main(DEFAULT_FIGS + RESULT_FIGS)
    else:
        main(DEFAULT_FIGS)
