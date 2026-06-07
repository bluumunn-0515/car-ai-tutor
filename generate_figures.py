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
    6: "학습자 활동 중심 프로젝트 모형",
    7: "폭포수 모형",
    8: "프로젝트 개발 도구 모형 매칭 시각화",
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
    7: "폭포수_모형",
    8: "개발도구_매칭",
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


def save(fig, num: int):
    OUT_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    slug = FIGURE_SLUGS.get(num, f"fig_{num:02d}")
    fig.subplots_adjust(left=0.06, right=0.94, top=0.90, bottom=0.08)
    for ext in ("png", "jpg"):
        kw = dict(facecolor="white", bbox_inches="tight", pad_inches=0.35)
        if ext == "jpg":
            kw["dpi"] = 200
        p1 = OUT_DIR / f"fig_{num:02d}.{ext}"
        p2 = DOWNLOAD_DIR / f"그림_{num:02d}_{slug}.{ext}"
        fig.savefig(p1, **kw)
        fig.savefig(p2, **kw)
    plt.close(fig)
    print(f"  [OK] fig_{num:02d}.png/jpg + download/그림_{num:02d}_{slug}")


def _box(ax, x, y, w, h, text, fc="#E8F4FD", ec="#2E86AB", fs=9, zorder=2):
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=1.5, zorder=zorder,
    )
    ax.add_patch(rect)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=fs, zorder=zorder + 1,
        linespacing=1.35,
    )


def _arrow(ax, x1, y1, x2, y2, color="#555", zorder=1):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1), zorder=zorder,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8,
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


# ── [그림 5] 프로젝트 모형 ────────────────────────────────────────
def fig05():
    fig, ax = plt.subplots(figsize=(7, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 13)
    ax.axis("off")
    _title(ax, "자동차 고장진단 학습지원 앱 프로젝트 모형")

    steps = [
        "① 접속·로그인",
        "② NCS 단원 선택",
        "③ 진단 입력 (3요소+사진)",
        "④ 4단계 미션 카드 (메모·사진·완료)",
        "⑤ AI 찬스 (선택·감점)",
        "⑥ AI 평가 (NCS 루브릭)",
        "⑦ 재수행 (다시 평가)",
        "⑧ 기록 누적 (Google Sheets)",
        "⑨ 교사 모드·포트폴리오 PDF",
    ]
    box_h, gap = 0.85, 0.45
    y_top = 11.5
    for i, s in enumerate(steps):
        y = y_top - i * (box_h + gap)
        _box(ax, 1.5, y, 7.0, box_h, s, fc="#E8F4FD" if i % 2 == 0 else "#E8F5E9", fs=10)
        if i < len(steps) - 1:
            _arrow(ax, 5.0, y, 5.0, y - gap)
    save(fig, 5)


# ── [그림 6] 학습자 활동 중심 모형 ────────────────────────────────
def fig06():
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6)
    ax.axis("off")
    _title(ax, "학습자 활동 중심 프로젝트 모형")

    ax.text(6.5, 5.0, "학습자 활동 흐름", ha="center", fontsize=11, fontweight="bold", color="#1565C0")
    labels = ["로그인", "단원·증상\n입력", "4단계\n수행", "AI 평가\n확인", "보완·\n재수행", "PDF\n출력"]
    n = len(labels)
    bw, gap = 1.6, 0.35
    total_w = n * bw + (n - 1) * gap
    x0 = (13 - total_w) / 2
    y_learn = 3.2
    centers = []
    for i, t in enumerate(labels):
        x = x0 + i * (bw + gap)
        _box(ax, x, y_learn, bw, 1.2, t, fc="#E3F2FD", ec="#1565C0", fs=9)
        centers.append(x + bw / 2)
        if i < n - 1:
            nx = x + bw + gap
            _arrow(ax, x + bw, y_learn + 0.6, nx, y_learn + 0.6)

    ax.text(6.5, 1.3, "시스템 지원 요소", ha="center", fontsize=11, fontweight="bold", color="#E65100")
    systems = [
        (centers[1], "Gemini AI"),
        (centers[2], "NCS 루브릭"),
        (centers[3], "Google Sheets"),
        (centers[4], "Plotly 대시보드"),
    ]
    for cx, name in systems:
        _box(ax, cx - 1.0, 0.35, 2.0, 0.75, name, fc="#FFF3E0", ec="#E65100", fs=8)
        _arrow(ax, cx, 1.1, cx, y_learn, color="#E65100")
    save(fig, 6)


# ── [그림 7] 폭포수 모형 ──────────────────────────────────────────
def fig07():
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
    save(fig, 7)


# ── [그림 8] 개발 도구 매칭 ───────────────────────────────────────
def fig08():
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.axis("off")
    _title(ax, "프로젝트 개발 도구 모형 매칭 시각화")

    phases = ["요구사항", "설계", "구현", "테스트", "배포"]
    rows = [
        ("개발 도구", [
            "Google Docs\n한글·Canva", "화면 흐름 설계",
            "Cursor IDE\nPython·Streamlit", "기능·UI 테스트",
            "GitHub\nStreamlit Cloud",
        ]),
        ("AI 도구", [
            "—", "—", "Gemini API\nNCS 프롬프트", "멀티모달 검증", "—",
        ]),
        ("데이터 도구", [
            "—", "Sheets 스키마", "sheets_backend",
            "동시편집 안전패턴", "Plotly·fpdf2",
        ]),
    ]
    table_data = [r[1] for r in rows]
    row_names = [r[0] for r in rows]
    tbl = ax.table(
        cellText=table_data,
        rowLabels=row_names,
        colLabels=phases,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1.0, 2.6)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#455A64")
        if row == 0:
            cell.set_facecolor("#E8EEF7")
            cell.set_text_props(fontweight="bold")
        elif col == -1:
            cell.set_facecolor("#F5F5F5")
            cell.set_text_props(fontweight="bold")
        elif row == 1:
            cell.set_facecolor("#E8F5E9")
        elif row == 2:
            cell.set_facecolor("#FFF3E0")
        elif row == 3:
            cell.set_facecolor("#F3E5F5")
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
