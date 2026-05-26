import base64
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
import streamlit as st

import sheets_backend as shb

logger = logging.getLogger(__name__)
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
try:
    import plotly.graph_objects as go
except ImportError:
    go = None
try:
    from fpdf import FPDF  # pyright: ignore[reportMissingModuleSource]
except ImportError:
    FPDF = None
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

# ───────────────────────────────────────────────────────────────────────────
# 상수 및 설정
# ───────────────────────────────────────────────────────────────────────────
NCS_UNITS = [
    "자동차 전기전자장치 고장진단",
    "배터리 점검",
    "시동·충전장치 점검",
    "조명장치 점검",
    "편의장치 점검",
    "네트워크 장치 점검",
]
CURRICULUM = {"자동차 전기전자제어": list(NCS_UNITS)}
UNIT_ICONS = {
    "자동차 전기전자장치 고장진단": "🔧",
    "배터리 점검": "🔋",
    "시동·충전장치 점검": "🚗",
    "조명장치 점검": "💡",
    "편의장치 점검": "🪑",
    "네트워크 장치 점검": "🛰️",
}

NCS_RUBRIC = {
    "자동차 전기전자장치 고장진단": [
        ("안전·전원 차단 확인", ["안전", "전원 차단", "감전", "단락", "보호구", "규정 토크", "정비지침서"]),
        ("회로도/기호 분석", ["회로도", "전장 회로도", "커넥터", "하네스", "배선 색", "기호", "조인트", "DLC"]),
        ("회로시험기 측정 절차", ["멀티미터", "회로시험기", "0점 조정", "전압", "저항", "통전", "리드선", "COM", "VΩ"]),
        ("진단장비(스캐너) 활용", ["스캐너", "OBD-II", "OBD-Ⅱ", "DTC", "고장코드", "센서 데이터", "강제구동", "오실로스코프"]),
    ],
    "배터리 점검": [
        ("배터리 외관/상태 확인", ["배터리", "축전지", "단자", "비중", "전해액", "부식", "AGM", "EFB", "MF", "라벨"]),
        ("개방회로 전압(OCV) 측정", ["OCV", "개방회로", "정지 전압", "12.3", "12.9", "단자 전압", "DC V", "20℃"]),
        ("부하/CCA·SOC 판정", ["CCA", "RC", "부하 시험", "SOC", "충전 상태", "방전", "교체", "판정", "크랭킹 전압"]),
        ("암전류/배터리 센서 점검", ["암전류", "50mA", "배터리 센서", "퓨즈", "릴레이", "PWM"]),
    ],
    "시동·충전장치 점검": [
        ("시동회로 점검", ["시동 전동기", "스타터", "솔레노이드", "B단자", "ST단자", "M단자", "시동 릴레이", "인히비터", "크랭킹", "피니언", "오버러닝 클러치"]),
        ("발전기 출력 점검", ["발전기", "알터네이터", "충전 전압", "13.8", "14.9", "리플", "FR단자", "C단자", "레귤레이터", "OAD"]),
        ("회로 전압강하 측정", ["전압강하", "0.2V", "케이블", "B+", "접지", "굵기", "배선"]),
        ("점검 절차/예비점검", ["예비점검", "단계", "순서", "점프 스타트", "벨트장력", "정비지침서", "P/N", "관능검사"]),
    ],
    "조명장치 점검": [
        ("등화회로 분석", ["전조등", "미등", "방향지시등", "정지등", "번호판등", "퓨즈", "라이트 스위치", "플래셔", "다기능 스위치"]),
        ("광원/전구 점검", ["전구", "LED", "필라멘트", "단선", "소켓", "분당", "60~120회", "하이빔", "로우빔"]),
        ("회로 전압/접지 측정", ["입력 전압", "접지", "도통", "1Ω", "1MΩ", "1㏁", "단락", "어스", "릴레이"]),
        ("BCM/CAN 등화 제어", ["BCM", "IPS", "B-CAN", "C-CAN", "MICOM", "스캐너", "DTC", "Failsafe"]),
    ],
    "편의장치 점검": [
        ("편의장치 유형/회로 식별", ["BCM", "ETACS", "다기능 스위치", "와이퍼", "워셔", "도어록", "파워윈도우", "레인센서", "썬루프", "열선"]),
        ("모듈 전원·접지 점검", ["IGN2", "공급전압", "선간 전압", "0.3V", "접지", "0.2V", "탐침봉", "정상 전압"]),
        ("액추에이터/릴레이 점검", ["액추에이터", "모터", "릴레이", "85", "86", "30", "87", "와이퍼 25A", "85~110Ω", "구동"]),
        ("스캐너 자기진단/강제구동", ["스캐너", "DLC", "DTC", "고장코드", "센서 데이터", "강제구동", "VCU", "IMS", "자기진단"]),
    ],
    "네트워크 장치 점검": [
        ("통신 프로토콜 이해", ["CAN", "LIN", "K-LIN", "KWP2000", "프로토콜", "C-CAN", "B-CAN", "CRC", "트랜시버"]),
        ("종단저항/배선 점검", ["종단저항", "120Ω", "60Ω", "주선", "트위스트 페어", "조인트 커넥터", "배선"]),
        ("통신 신호/파형 측정", ["오실로스코프", "파형", "high", "low", "신호", "전압 레벨", "스코프"]),
        ("게이트웨이/모듈 진단", ["게이트웨이", "GW", "ECU", "DLC", "DTC", "bus-off", "time-out", "스캐너", "통신 가능"]),
    ],
}

MODE_RUBRIC_WEIGHTS = {
    "학습 모드": {
        "안전·전원 차단 확인": 1.3, "회로도/기호 분석": 1.2, "회로시험기 측정 절차": 1.1, "진단장비(스캐너) 활용": 1.0,
        "배터리 외관/상태 확인": 1.1, "개방회로 전압(OCV) 측정": 1.1, "부하/CCA·SOC 판정": 1.0, "암전류/배터리 센서 점검": 1.0,
        "시동회로 점검": 1.1, "발전기 출력 점검": 1.0, "회로 전압강하 측정": 1.0, "점검 절차/예비점검": 1.2,
        "등화회로 분석": 1.1, "광원/전구 점검": 1.0, "회로 전압/접지 측정": 1.0, "BCM/CAN 등화 제어": 1.0,
        "편의장치 유형/회로 식별": 1.0, "모듈 전원·접지 점검": 1.1, "액추에이터/릴레이 점검": 1.0, "스캐너 자기진단/강제구동": 1.1,
        "통신 프로토콜 이해": 1.2, "종단저항/배선 점검": 1.1, "통신 신호/파형 측정": 1.0, "게이트웨이/모듈 진단": 1.0,
    }
}

UNIT_INPUT_HINTS = {
    "자동차 전기전자장치 고장진단": {"target": "예: 운전석 도어 커넥터 E12", "state": "예: 멀티미터 전압 0V", "question": "예: 단선 위치 점검 순서"},
    "배터리 점검": {"target": "예: 12V 납축전지(MF)", "state": "예: OCV 12.0V 측정", "question": "예: CCA와 SOC 판정 순서"},
    "시동·충전장치 점검": {"target": "예: 알터네이터 B단자", "state": "예: 충전 전압 13.2V", "question": "예: 전압강하 문제 구분법"},
    "조명장치 점검": {"target": "예: 좌측 전조등(로우빔)", "state": "예: 퓨즈 도통되나 부점등", "question": "예: 접지 불량 확인법"},
    "편의장치 점검": {"target": "예: 파워윈도우 모터", "state": "예: 수동은 되나 AUTO 안됨", "question": "예: 강제구동 활용법"},
    "네트워크 장치 점검": {"target": "예: C-CAN 주선", "state": "예: ABS 모듈 통신불가", "question": "예: 종단저항 측정 포인트"},
}

UNIT_PHOTO_CHECKLISTS = {
    "자동차 전기전자장치 고장진단": ["회로도 분석용 커넥터 핀 번호가 보이나요?", "멀티미터 모드(DC V/Ω)가 보이나요?"],
    "배터리 점검": ["터미널 부식 상태가 보이나요?", "배터리 라벨(CCA/AGM 등)이 보이나요?"],
    "시동·충전장치 점검": ["솔레노이드 단자 위치가 보이나요?", "벨트 장력 상태가 보이나요?"],
}

GEMINI_MODEL_CANDIDATES = ["gemini-2.0-flash", "gemini-1.5-flash"]
GEMINI_RETRY_DELAYS_SECONDS = [2.0, 4.0]
GEMINI_IMAGE_MAX_SIZE = (1024, 1024)
GEMINI_IMAGE_JPEG_QUALITY = 85
TEACHER_PASSWORD_DEFAULT = "0000"

# ───────────────────────────────────────────────────────────────────────────
# 유틸리티 함수
# ───────────────────────────────────────────────────────────────────────────
def now_kst_display() -> str:
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        dt = datetime.now(timezone.utc) + timedelta(hours=9)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _normalize_sid(student_id: Any) -> str:
    return str(student_id or "").strip()

def reset_student_session_soft() -> None:
    st.session_state.student_logged_in = False
    st.session_state.student_id = ""
    st.session_state.student_display_name = ""
    st.session_state["my_history_records"] = None
    reset_diagnosis_flow()

def reset_diagnosis_flow() -> None:
    st.session_state.diag_step = "input"
    st.session_state.latest_guidance = ""
    st.session_state.latest_evaluation = ""
    st.session_state.latest_execution_result = ""
    st.session_state.latest_result = ""
    st.session_state.latest_symptom = ""
    st.session_state.latest_reflection = ""
    st.session_state.latest_image_b64 = ""

def compose_structured_symptom(target_part: str, current_state: str, learning_question: str) -> str:
    target = (target_part or "").strip()
    state = (current_state or "").strip()
    question = (learning_question or "").strip()
    if not (target or state or question): return ""
    return f"[대상 부품]\n{target or '(미입력)'}\n[현재 상태]\n{state or '(미입력)'}\n[학습 질문]\n{question or '(미입력)'}"

def make_thumbnail_b64(image_file: Any) -> str:
    if image_file is None or PILImage is None: return ""
    try:
        raw = image_file.getvalue()
        with PILImage.open(BytesIO(raw)) as im:
            im.load()
            if im.mode != "RGB": im = im.convert("RGB")
            im.thumbnail((480, 480), PILImage.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=60)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception: return ""

def thumbnail_b64_to_bytes(b64: str) -> Optional[bytes]:
    if not b64: return None
    try: return base64.b64decode(str(b64).strip())
    except: return None

# ───────────────────────────────────────────────────────────────────────────
# AI 및 비즈니스 로직
# ───────────────────────────────────────────────────────────────────────────
STANDARD_PROCEDURE_BLOCK = """
[표준 절차 기준]
가. 멀티미터 사용 전 안전 점검 (전원 차단 확인, 레인지 선택)
나. 회로도 분석 (전원→퓨즈→스위치→부하→접지 흐름 추적)
다. 진단장비(스캐너) 사용 (DTC 확인, 센서 데이터 분석)
""".strip()

def build_learning_prompt(user_symptom: str, selected_unit: str) -> str:
    return f"""
너는 '자동차 전기전자제어' AI 튜터다. 학생에게 정답을 주지 말고 '미션'과 '측정 방법'만 제시해라.
[단원] {selected_unit}
[입력 증상] {user_symptom}
{STANDARD_PROCEDURE_BLOCK}
## 🎯 미션 요약: ...
## 📋 NCS 기반 수행 순서:
### 🛡️ 준비 / 안전
• ...
### 🔍 점검 / 회로도
• ...
### ⚡ 측정 / 전압
• ...
### 🛠️ 판정 / 조치
• ...
"""

def build_evaluation_prompt(user_symptom: str, student_reasoning: str, selected_unit: str, guidance_text: str) -> str:
    return f"""
너는 평가 코치다. 학생의 실습 결과를 가이드와 비교해 평가해라.
[단원] {selected_unit}
[가이드] {guidance_text}
[학생 결과] {student_reasoning}
## 📋 평가 한줄 요약: ...
## 🏷 카테고리 요약:
• 🛡️ 준비 / 안전 — [✅ 통과/⚠ 보완] | ...
• 🔍 점검 / 회로도 — [✅ 통과/⚠ 보완] | ...
• ⚡ 측정 / 전압 — [✅ 통과/⚠ 보완] | ...
• 🛠️ 판정 / 조치 — [✅ 통과/⚠ 보완] | ...
"""

def ask_gemini(user_symptom: str, student_reasoning: str, image_file: Any, key: str, selected_unit: str, step: str, guidance_text: str = "") -> str:
    client = genai.Client(api_key=key)
    prompt = build_evaluation_prompt(user_symptom, student_reasoning, selected_unit, guidance_text) if step == "evaluation" else build_learning_prompt(user_symptom, selected_unit)
    
    parts = [types.Part.from_text(text=prompt)]
    if image_file:
        parts.append(types.Part.from_bytes(data=image_file.getvalue(), mime_type="image/jpeg"))
        
    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(model=model_name, contents=[types.Content(role="user", parts=parts)])
            return response.text
        except Exception as e:
            logger.error(f"AI 호출 에러 ({model_name}): {e}")
            continue
    return "AI 응답을 가져오지 못했습니다."

# ───────────────────────────────────────────────────────────────────────────
# PDF 생성 로직 (수평 공간 부족 오류 해결 버전)
# ───────────────────────────────────────────────────────────────────────────
_CATEGORY_LABELS = [
    ("🛡️", "준비 / 안전"),
    ("🔍", "점검 / 회로도"),
    ("⚡", "측정 / 전압"),
    ("🛠️", "판정 / 조치"),
]

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _parse_category_scores(result_text: str) -> dict[str, int]:
    """평가 결과 텍스트에서 카테고리별 통과/보완 여부를 파싱해 점수(100/60/0)로 환산."""
    scores: dict[str, int] = {}
    text = result_text or ""
    for _icon, label in _CATEGORY_LABELS:
        # 라벨 뒤의 첫 ✅ 또는 ⚠ 한 줄 안에서만 탐색
        pattern = rf"{re.escape(label)}[^\n]{{0,80}}?(✅|⚠)"
        m = re.search(pattern, text)
        if m:
            scores[label] = 100 if m.group(1) == "✅" else 60
        else:
            scores[label] = 0
    return scores

def _score_color(score: float) -> str:
    if score >= 85: return "#10B981"   # green
    if score >= 70: return "#3B82F6"   # blue
    if score >= 55: return "#F59E0B"   # amber
    return "#EF4444"                   # red

def _score_band(score: float) -> str:
    if score >= 85: return "우수"
    if score >= 70: return "양호"
    if score >= 55: return "보통"
    return "보완 필요"

def _aggregate_unit_scores(records: list[dict]) -> list[tuple[str, float, int]]:
    """단원별 평균 NCS 점수와 건수를 반환."""
    totals: dict[str, list[float]] = {}
    for r in records:
        unit = (r.get("unit") or "").strip()
        if not unit:
            continue
        totals.setdefault(unit, []).append(_safe_float(r.get("ncs_score"), 0))
    rows: list[tuple[str, float, int]] = []
    for unit in NCS_UNITS:
        if unit in totals:
            vs = totals[unit]
            rows.append((unit, sum(vs) / len(vs), len(vs)))
    # NCS_UNITS에 없는 단원도 뒤에 붙임
    for unit, vs in totals.items():
        if unit not in NCS_UNITS:
            rows.append((unit, sum(vs) / len(vs), len(vs)))
    return rows

def _aggregate_category_scores(records: list[dict]) -> dict[str, float]:
    """전체 기록의 카테고리별 평균 점수."""
    buckets: dict[str, list[int]] = {label: [] for _i, label in _CATEGORY_LABELS}
    for r in records:
        cs = _parse_category_scores(r.get("result", ""))
        for label, sc in cs.items():
            if sc > 0:
                buckets[label].append(sc)
    return {label: (sum(v) / len(v) if v else 0.0) for label, v in buckets.items()}

def _plotly_to_png_bytes(fig) -> Optional[bytes]:
    """Plotly 그래프를 PNG로 변환(가능할 때만). kaleido가 없으면 None."""
    if fig is None:
        return None
    try:
        return fig.to_image(format="png", width=900, height=420, scale=2)
    except Exception:
        return None

# fpdf2는 폰트에 없는 글자(이모지 등)를 만나면 글자 폭을 계산하지 못해
# "Not enough horizontal space to render a single character" 예외를 던진다.
# Malgun Gothic은 한글/한자/기호는 지원하지만 대부분의 컬러 이모지는 지원하지 않으므로
# PDF에 넣기 전에 미리 안전한 텍스트로 정리한다.
_EMOJI_REPLACEMENTS = {
    "🛡️": "[안전]", "🔍": "[점검]", "⚡": "[측정]", "🛠️": "[판정]",
    "🔧": "", "🔋": "", "🚗": "", "💡": "", "🪑": "", "🛰️": "",
    "📓": "", "📚": "", "📊": "", "📅": "", "📝": "", "📬": "", "📌": "",
    "🎯": "", "🎓": "", "🚀": "", "🤖": "", "🧭": "", "🧪": "",
    "✅": "[O]", "⚠": "[!]", "⚠️": "[!]", "❓": "?", "❗": "!",
    "🏷": "", "🏷️": "", "·": "·",
}

def _sanitize_pdf_text(text: Any) -> str:
    """PDF 출력 전에 폰트가 지원하지 않는 이모지/변형 선택자를 제거하거나 치환한다."""
    if text is None:
        return ""
    s = str(text)
    for emo, rep in _EMOJI_REPLACEMENTS.items():
        if emo in s:
            s = s.replace(emo, rep)
    # 변형 선택자(U+FE0E/U+FE0F), 0폭 결합자(U+200D), 영역 표시(U+20E3) 제거
    s = re.sub(r"[\ufe00-\ufe0f\u200d\u20e3]", "", s)
    # BMP 밖(서플리먼터리 평면)의 모든 코드포인트 = 거의 모든 이모지/픽토그램 제거
    s = "".join(ch for ch in s if ord(ch) <= 0xFFFF)
    # BMP 내 이모지/픽토그램 영역도 제거
    s = re.sub(
        r"[\u2300-\u23FF\u2460-\u24FF\u25A0-\u25FF\u2600-\u27BF\u2B00-\u2BFF]",
        "",
        s,
    )
    return s.strip()

def _pdf_safe_multicell(pdf, text: str, line_height: float = 7.0, width: float = 0.0) -> None:
    """fpdf2에서 폭 부족으로 인한 예외가 나도 PDF 생성이 중단되지 않도록 보호."""
    cleaned = _sanitize_pdf_text(text)
    if not cleaned:
        return
    # 좌측 마진으로 복귀하여 충분한 폭 확보
    try:
        pdf.set_x(pdf.l_margin)
    except Exception:
        pass
    try:
        pdf.multi_cell(width, line_height, cleaned)
    except Exception as e:
        logger.warning("PDF multi_cell 실패, 안전 모드로 재시도: %s", e)
        # 한 글자도 못 그릴 정도면 안전한 ASCII로 재시도
        ascii_safe = re.sub(r"[^\x20-\x7E\r\n\t]", "?", cleaned)
        try:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(width, line_height, ascii_safe)
        except Exception as e2:
            logger.error("PDF multi_cell 최종 실패: %s", e2)

def build_comprehensive_portfolio_pdf(student_id: str, student_name: str, records: list[dict]) -> bytes:
    """학기말 포트폴리오 PDF 생성. 어떤 예외가 발생해도 빈 bytes를 반환하여 UI 충돌을 방지한다."""
    if FPDF is None:
        return b""
    try:
        return _build_portfolio_pdf_inner(student_id, student_name, records)
    except Exception as e:
        logger.exception("학기말 포트폴리오 PDF 생성 중 예외: %s", e)
        return b""

def _build_portfolio_pdf_inner(student_id: str, student_name: str, records: list[dict]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=15, top=15, right=15)

    font_path = Path(__file__).resolve().parent / "malgun.ttf"
    bold_path = Path(__file__).resolve().parent / "malgunbd.ttf"
    has_font = font_path.exists()
    if has_font:
        pdf.add_font("Malgun", "", str(font_path))
        if bold_path.exists():
            pdf.add_font("Malgun", "B", str(bold_path))
        base_font = "Malgun"
    else:
        base_font = "Helvetica"
    has_bold = has_font and bold_path.exists()
    pdf.set_font(base_font, size=11)

    student_id = _sanitize_pdf_text(student_id) or "-"
    student_name = _sanitize_pdf_text(student_name) or "학생"

    # ── 표지 ─────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(30, 58, 138)
    pdf.rect(0, 0, 210, 40, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(base_font, "B" if has_bold else "", 22)
    pdf.set_xy(0, 12)
    pdf.cell(210, 12, _sanitize_pdf_text("나의 자동차 실습 성장 일지"), align="C")
    pdf.set_font(base_font, size=12)
    pdf.set_xy(0, 26)
    pdf.cell(210, 8, _sanitize_pdf_text(f"{student_name}  ·  학번 {student_id}"), align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(15, 50)

    # ── 요약 카드 ────────────────────────────────────────
    pdf.set_font(base_font, size=11)
    avg_score = (sum(_safe_float(r.get("ncs_score")) for r in records) / len(records)) if records else 0
    fb_count = sum(1 for r in records if (r.get("teacher_feedback") or "").strip())
    unit_count = len({(r.get("unit") or "").strip() for r in records if r.get("unit")})
    pdf.set_fill_color(243, 244, 246)
    pdf.set_draw_color(229, 231, 235)
    pdf.rect(15, pdf.get_y(), 180, 22, "DF")
    y0 = pdf.get_y()
    pdf.set_xy(20, y0 + 3); pdf.cell(55, 7, _sanitize_pdf_text("총 실습 건수"))
    pdf.set_xy(20, y0 + 11); pdf.set_font_size(14); pdf.cell(55, 7, f"{len(records)} 건"); pdf.set_font_size(11)
    pdf.set_xy(80, y0 + 3); pdf.cell(55, 7, _sanitize_pdf_text("평균 성취도"))
    pdf.set_xy(80, y0 + 11); pdf.set_font_size(14); pdf.cell(55, 7, f"{avg_score:.1f} 점"); pdf.set_font_size(11)
    pdf.set_xy(140, y0 + 3); pdf.cell(50, 7, _sanitize_pdf_text("참여 단원 / 피드백"))
    pdf.set_xy(140, y0 + 11); pdf.set_font_size(14); pdf.cell(50, 7, f"{unit_count}단원 · {fb_count}건"); pdf.set_font_size(11)
    pdf.set_xy(15, y0 + 28)

    # ── 교사 피드백 상단 강조 ────────────────────────────
    feedback_recs = [r for r in records if (r.get("teacher_feedback") or "").strip()]
    if feedback_recs:
        pdf.set_font_size(14); pdf.set_text_color(202, 138, 4)
        pdf.set_x(15)
        pdf.cell(0, 10, _sanitize_pdf_text("[ 선생님의 피드백 ]"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(11)
        for r in feedback_recs:
            if pdf.get_y() > 250: pdf.add_page()
            pdf.set_fill_color(255, 247, 230)
            pdf.set_draw_color(250, 140, 22)
            head = f"  {r.get('unit', '')}  ({(r.get('submitted_at') or '')[:10]})"
            pdf.set_x(15); pdf.cell(180, 6, _sanitize_pdf_text(head), fill=True)
            pdf.ln(6)
            _pdf_safe_multicell(pdf, f"  {r.get('teacher_feedback', '')}", line_height=7, width=180)
            pdf.ln(3)
        pdf.ln(2)

    # ── 단원별 성취도 그래프 ─────────────────────────────
    if go is not None and records:
        try:
            unit_rows = _aggregate_unit_scores(records)
            if unit_rows:
                units = [u for u, _s, _n in unit_rows]
                scores = [s for _u, s, _n in unit_rows]
                colors = [_score_color(s) for s in scores]
                fig = go.Figure(data=[go.Bar(
                    x=units, y=scores, marker_color=colors,
                    text=[f"{s:.0f}" for s in scores], textposition="outside"
                )])
                fig.update_layout(
                    title="단원별 평균 성취도",
                    yaxis=dict(range=[0, 110]),
                    plot_bgcolor="white", paper_bgcolor="white",
                    margin=dict(l=40, r=20, t=40, b=80),
                )
                png = _plotly_to_png_bytes(fig)
                if png:
                    if pdf.get_y() > 200: pdf.add_page()
                    pdf.image(BytesIO(png), x=15, w=180)
                    pdf.ln(4)

            cat_avgs = _aggregate_category_scores(records)
            if any(cat_avgs.values()):
                labels = [lab for _ico, lab in _CATEGORY_LABELS]
                vals = [cat_avgs.get(lab, 0.0) for lab in labels]
                fig2 = go.Figure(data=go.Scatterpolar(
                    r=vals + [vals[0]], theta=labels + [labels[0]],
                    fill="toself", line_color="#1E40AF", fillcolor="rgba(59,130,246,0.35)"
                ))
                fig2.update_layout(
                    title="NCS 카테고리별 평균",
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    paper_bgcolor="white", margin=dict(l=40, r=40, t=40, b=20),
                )
                png2 = _plotly_to_png_bytes(fig2)
                if png2:
                    if pdf.get_y() > 200: pdf.add_page()
                    pdf.image(BytesIO(png2), x=30, w=150)
                    pdf.ln(4)
        except Exception as e:
            logger.warning("그래프 PDF 임베드 실패(텍스트 본문은 계속 진행): %s", e)

    # ── 실습 기록 상세 ────────────────────────────────────
    pdf.add_page()
    pdf.set_font_size(14); pdf.set_text_color(30, 58, 138)
    pdf.set_x(15)
    pdf.cell(0, 10, _sanitize_pdf_text("실습 기록"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0); pdf.set_font_size(11)

    for idx, rec in enumerate(sorted(records, key=lambda x: x.get('submitted_at', '')), 1):
        if pdf.get_y() > 240: pdf.add_page()
        score = _safe_float(rec.get("ncs_score"))
        col = _score_color(score)
        r_, g_, b_ = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        y = pdf.get_y()
        pdf.set_fill_color(r_, g_, b_); pdf.rect(15, y, 4, 22, "F")
        pdf.set_xy(22, y + 2)
        pdf.set_font_size(13)
        title = f"{idx}. {rec.get('unit', '')}  ({(rec.get('submitted_at') or '')[:10]})"
        pdf.cell(0, 7, _sanitize_pdf_text(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font_size(10); pdf.set_text_color(107, 114, 128)
        pdf.set_x(22)
        pdf.cell(0, 6, _sanitize_pdf_text(f"성취도 {score:.0f}점  ·  {_score_band(score)}"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(11)
        pdf.ln(2)

        _pdf_safe_multicell(pdf, f"[수행 내용]\n{rec.get('symptom', '(없음)')}")
        pdf.ln(1)
        _pdf_safe_multicell(pdf, f"[나의 소감]\n{rec.get('reflection', '(없음)')}")
        pdf.ln(2)

        img_bytes = thumbnail_b64_to_bytes(rec.get("image_b64", ""))
        if img_bytes:
            try:
                pdf.set_x(15)
                pdf.image(BytesIO(img_bytes), w=55)
                pdf.ln(3)
            except Exception:
                pass

        pdf.set_draw_color(229, 231, 235)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(4)

    return bytes(pdf.output(dest="S"))

# ───────────────────────────────────────────────────────────────────────────
# UI 렌더링 함수
# ───────────────────────────────────────────────────────────────────────────
def render_mission_card(text: str):
    with st.container(border=True):
        st.markdown("### 🧭 AI 진단 가이드")
        st.markdown(text)

def render_evaluation_card(text: str):
    with st.container(border=True):
        st.markdown("### 📝 실습 수행 평가")
        st.markdown(text)

def render_ncs_achievement(result_text: str, unit_name: str):
    st.subheader(f"📊 {unit_name} 성취도 분석")
    # 정규표현식이나 키워드 매칭을 통해 당일 단원의 점수만 계산하여 표시하는 로직
    score = 85 # 예시 점수
    st.progress(score / 100, text=f"오늘의 성취도: {score}점")

def _render_diagnosis_input_tab(selected_unit: str, api_key: str):
    diag_step = st.session_state.get("diag_step", "input")
    
    if diag_step == "input":
        # AI 가이드 받기 버튼을 크고 눈에 띄게 만드는 전용 스타일
        st.markdown(
            """
<style>
div.stButton > button[kind="primary"] {
    font-size: 1.35rem !important;
    font-weight: 800 !important;
    padding: 18px 28px !important;
    border-radius: 14px !important;
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    color: #ffffff !important;
    border: none !important;
    box-shadow: 0 10px 24px rgba(37, 99, 235, 0.30) !important;
    transition: transform .18s ease, box-shadow .18s ease, filter .18s ease !important;
    letter-spacing: 0.5px;
}
div.stButton > button[kind="primary"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 16px 32px rgba(37, 99, 235, 0.40) !important;
    filter: brightness(1.05);
}
div.stButton > button[kind="primary"]:active { transform: translateY(-1px); }
</style>
""",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown(f"### 📝 오늘의 과제: {selected_unit}")
            hints = UNIT_INPUT_HINTS.get(selected_unit, {})
            t = st.text_input(
                "🔍 대상 부품",
                key="diag_target_part",
                placeholder=hints.get("target", "예: 운전석 도어 커넥터 E12"),
                help="오늘 실습할 부품 또는 장치의 이름을 정확히 적어주세요.",
            )
            s = st.text_area(
                "⚡ 현재 상태  —  오늘 실습하고자 하는 부품이나 장치의 상태를 작성하세요",
                key="diag_current_state",
                placeholder=hints.get("state", "예: 멀티미터 전압 0V, 점등되지 않음"),
                help="오늘 실습하고자 하는 부품이나 장치의 상태를 작성하세요.",
                height=110,
            )
            q = st.text_area(
                "❓ 학습 질문  —  오늘 실습하는 부품이나 장치의 고장 및 진단, 정비 방법에 대해 자유롭게 질문하세요",
                key="diag_learning_question",
                placeholder=hints.get("question", "예: 단선 위치는 어떻게 점검하면 되나요?"),
                help="오늘 실습하는 부품이나 장치의 고장 및 진단, 정비 방법에 대해 자유롭게 질문하세요.",
                height=110,
            )
            img = st.file_uploader("📸 사진 업로드", type=["jpg", "png"])

            st.markdown("")
            if st.button("🚀 AI 가이드 받기", type="primary", use_container_width=True):
                symptom = compose_structured_symptom(t, s, q)
                with st.spinner("가이드 생성 중..."):
                    guide = ask_gemini(symptom, "", img, api_key, selected_unit, "guidance")
                    st.session_state.latest_guidance = guide
                    st.session_state.latest_symptom = symptom
                    st.session_state.latest_image_b64 = make_thumbnail_b64(img)
                    st.session_state.diag_step = "guidance"
                    st.rerun()

    elif diag_step == "guidance":
        render_mission_card(st.session_state.latest_guidance)
        st.markdown("---")
        res = st.text_area("🧪 실습 수행 결과 입력", height=200)
        refl = st.text_area("📝 오늘의 실습 소감", placeholder="실습을 통해 느낀 점을 적어주세요.")
        
        if st.button("✅ 결과 제출 및 평가받기"):
            with st.spinner("평가 분석 중..."):
                eval_res = ask_gemini(st.session_state.latest_symptom, res, None, api_key, selected_unit, "evaluation", st.session_state.latest_guidance)
                
                record = {
                    "record_id": str(uuid.uuid4()),
                    "submitted_at": now_kst_display(),
                    "student_id": st.session_state.student_id,
                    "student_display_name": st.session_state.student_display_name,
                    "subject": "자동차 전기전자제어",
                    "unit": selected_unit,
                    "mode": "학습 모드",
                    "symptom": st.session_state.latest_symptom,
                    "reasoning": res,
                    "result": shb.compose_combined_result(st.session_state.latest_guidance, eval_res),
                    "reflection": refl,
                    "image_b64": st.session_state.latest_image_b64,
                    "teacher_feedback": "",
                    "teacher_feedback_updated_at": ""
                }
                shb.append_history_from_record(record, 80.0) # 80.0은 임시 점수
                st.session_state.latest_evaluation = eval_res
                st.session_state.diag_step = "result"
                shb.invalidate_all_sheet_caches()
                st.session_state["my_history_records"] = shb.filter_history_records_by_student(st.session_state.student_id)
                st.rerun()

    elif diag_step == "result":
        st.success("🎉 실습이 완료되었습니다!")
        render_evaluation_card(st.session_state.latest_evaluation)
        if st.button("🔄 새 진단 시작"):
            reset_diagnosis_flow()
            st.rerun()

_PORTFOLIO_CSS = """
<style>
.pf-hero {
    background: linear-gradient(135deg,#1E3A8A 0%,#3B82F6 100%);
    color:#fff; padding:18px 22px; border-radius:14px; margin-bottom:16px;
    box-shadow:0 4px 14px rgba(30,58,138,0.18);
}
.pf-hero h2 { margin:0; font-size:22px; }
.pf-hero p { margin:4px 0 0 0; opacity:0.92; font-size:14px; }
.pf-stats { display:flex; gap:10px; margin-top:14px; flex-wrap:wrap; }
.pf-stat {
    background:rgba(255,255,255,0.15); padding:8px 14px; border-radius:10px;
    backdrop-filter:blur(4px);
}
.pf-stat b { font-size:18px; display:block; }
.pf-stat span { font-size:11px; opacity:0.85; }

.pf-fb-card {
    background:#FFF7E6; border-left:6px solid #FA8C16;
    border-radius:10px; padding:14px 18px; margin:8px 0;
    box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.pf-fb-head { display:flex; justify-content:space-between; align-items:center;
    color:#92400E; font-weight:600; margin-bottom:6px; font-size:14px; }
.pf-fb-body { color:#5C3300; line-height:1.65; font-size:15px; white-space:pre-wrap; }
.pf-fb-empty {
    background:#F3F4F6; border:1px dashed #D1D5DB; color:#6B7280;
    padding:14px; border-radius:10px; text-align:center;
}

.pf-record {
    border:1px solid #E5E7EB; border-radius:12px;
    padding:14px 16px; margin-bottom:12px; background:#fff;
    box-shadow:0 1px 2px rgba(0,0,0,0.03);
}
.pf-rec-head { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.pf-rec-title { font-size:16px; font-weight:700; color:#111827; }
.pf-rec-date { font-size:12px; color:#6B7280; }
.pf-chip { display:inline-block; padding:4px 10px; border-radius:999px;
    font-size:12px; font-weight:600; margin-left:4px; }
.pf-chip-fb { background:#DBEAFE; color:#1D4ED8; }
.pf-chip-wait { background:#F3F4F6; color:#6B7280; }
.pf-score {
    display:inline-block; padding:4px 12px; border-radius:8px;
    font-weight:700; font-size:13px; color:#fff;
}
</style>
"""

def _render_teacher_feedback_section(records: list[dict]) -> None:
    st.markdown("### 📬 선생님의 피드백")
    feedback_recs = [r for r in records if (r.get("teacher_feedback") or "").strip()]
    if not feedback_recs:
        st.markdown(
            '<div class="pf-fb-empty">아직 도착한 피드백이 없습니다. '
            '실습 기록을 보고 선생님께서 피드백을 남기시면 이곳에 가장 먼저 표시돼요.</div>',
            unsafe_allow_html=True,
        )
        return
    feedback_recs.sort(
        key=lambda r: (r.get("teacher_feedback_updated_at") or r.get("submitted_at") or ""),
        reverse=True,
    )
    for r in feedback_recs[:5]:
        unit = r.get("unit", "")
        icon = UNIT_ICONS.get(unit, "📘")
        when = (r.get("teacher_feedback_updated_at") or r.get("submitted_at") or "")[:16]
        fb = (r.get("teacher_feedback") or "").strip()
        st.markdown(
            f"""
<div class="pf-fb-card">
  <div class="pf-fb-head">
    <span>{icon} {unit}</span>
    <span style="font-weight:400;font-size:12px;color:#9A6B00;">📅 {when}</span>
  </div>
  <div class="pf-fb-body">{fb}</div>
</div>""",
            unsafe_allow_html=True,
        )
    if len(feedback_recs) > 5:
        st.caption(f"…외 {len(feedback_recs) - 5}건의 피드백이 더 있어요. 아래 실습 기록에서 확인하세요.")

def _render_achievement_charts(records: list[dict]) -> None:
    st.markdown("### 📊 분야별 성취도")
    if go is None:
        st.caption("그래프를 표시하려면 `plotly` 패키지가 필요합니다.")
        return

    unit_rows = _aggregate_unit_scores(records)
    cat_avgs = _aggregate_category_scores(records)

    col1, col2 = st.columns(2)
    with col1:
        if unit_rows:
            units = [u for u, _s, _n in unit_rows]
            scores = [s for _u, s, _n in unit_rows]
            counts = [n for _u, _s, n in unit_rows]
            colors = [_score_color(s) for s in scores]
            fig = go.Figure(data=[go.Bar(
                x=scores, y=units, orientation="h",
                marker_color=colors,
                text=[f"{s:.0f}점 · {n}회" for s, n in zip(scores, counts)],
                textposition="outside",
                hovertemplate="%{y}<br>평균 %{x:.1f}점<extra></extra>",
            )])
            fig.update_layout(
                title="단원별 평균 성취도",
                xaxis=dict(range=[0, 110], title="평균 점수"),
                yaxis=dict(autorange="reversed"),
                height=320, margin=dict(l=10, r=20, t=40, b=20),
                plot_bgcolor="#FAFAFA", paper_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("아직 단원별 점수 데이터가 부족해요.")

    with col2:
        if any(cat_avgs.values()):
            labels = [f"{ico} {lab}" for ico, lab in _CATEGORY_LABELS]
            vals = [cat_avgs[lab] for _ico, lab in _CATEGORY_LABELS]
            fig2 = go.Figure(data=go.Scatterpolar(
                r=vals + [vals[0]],
                theta=labels + [labels[0]],
                fill="toself",
                line_color="#1E40AF",
                fillcolor="rgba(59,130,246,0.35)",
                hovertemplate="%{theta}<br>%{r:.0f}점<extra></extra>",
            ))
            fig2.update_layout(
                title="NCS 카테고리별 평균",
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                height=320, margin=dict(l=40, r=40, t=40, b=20),
                paper_bgcolor="white",
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("AI 평가 결과에 카테고리 정보가 누적되면 레이더 차트가 표시돼요.")

def _render_record_card(rec: dict) -> None:
    unit = rec.get("unit", "")
    icon = UNIT_ICONS.get(unit, "📘")
    date = (rec.get("submitted_at") or "")[:10]
    score = _safe_float(rec.get("ncs_score"))
    color = _score_color(score)
    band = _score_band(score)
    has_fb = bool((rec.get("teacher_feedback") or "").strip())
    fb_chip = ('<span class="pf-chip pf-chip-fb">📬 피드백 도착</span>'
               if has_fb else
               '<span class="pf-chip pf-chip-wait">⏳ 피드백 대기</span>')

    with st.container():
        st.markdown(
            f"""
<div class="pf-record">
  <div class="pf-rec-head">
    <div>
      <div class="pf-rec-title">{icon} {unit}</div>
      <div class="pf-rec-date">📅 {date}</div>
    </div>
    <div style="text-align:right;">
      <div class="pf-score" style="background:{color};">{score:.0f}점 · {band}</div>
      <div style="margin-top:6px;">{fb_chip}</div>
    </div>
  </div>
</div>""",
            unsafe_allow_html=True,
        )
        with st.expander("상세 보기"):
            if has_fb:
                st.markdown(
                    f"""
<div class="pf-fb-card">
  <div class="pf-fb-head"><span>🎯 선생님 피드백</span></div>
  <div class="pf-fb-body">{(rec.get('teacher_feedback') or '').strip()}</div>
</div>""",
                    unsafe_allow_html=True,
                )

            cat_scores = _parse_category_scores(rec.get("result", ""))
            if any(cat_scores.values()):
                cols = st.columns(len(_CATEGORY_LABELS))
                for (ico, label), c in zip(_CATEGORY_LABELS, cols):
                    sc = cat_scores.get(label, 0)
                    with c:
                        st.markdown(
                            f"""
<div style="background:{_score_color(sc) if sc else '#F3F4F6'}; color:{'#fff' if sc else '#9CA3AF'};
            padding:10px; border-radius:10px; text-align:center;">
  <div style="font-size:18px;">{ico}</div>
  <div style="font-size:11px; opacity:0.9;">{label}</div>
  <div style="font-weight:700; font-size:14px; margin-top:2px;">
    {'통과' if sc >= 100 else ('보완' if sc >= 60 else '미평가')}
  </div>
</div>""",
                            unsafe_allow_html=True,
                        )
                st.markdown("")

            tab1, tab2, tab3 = st.tabs(["🔍 수행 내용", "📝 나의 소감", "🤖 AI 평가"])
            with tab1:
                if rec.get("symptom"):
                    st.markdown(f"```\n{rec.get('symptom')}\n```")
                if rec.get("reasoning"):
                    st.markdown(f"**내가 작성한 진단**")
                    st.write(rec.get("reasoning"))
                img_bytes = thumbnail_b64_to_bytes(rec.get("image_b64"))
                if img_bytes:
                    st.image(img_bytes, width=280)
            with tab2:
                refl = rec.get("reflection") or "(소감 없음)"
                st.info(refl)
            with tab3:
                res = rec.get("result") or "(AI 평가 없음)"
                st.markdown(res)

def _render_final_portfolio_section(records: list[dict]) -> None:
    """학기말 최종 포트폴리오 다운로드 영역. 6개 단원을 모두 완료해야 활성화된다."""
    st.markdown("### 🎓 학기말 최종 포트폴리오")

    completed_units = {(r.get("unit") or "").strip() for r in records if r.get("unit")}
    required_units = list(NCS_UNITS)
    done_units = [u for u in required_units if u in completed_units]
    missing_units = [u for u in required_units if u not in completed_units]
    progress = len(done_units) / len(required_units) if required_units else 0.0

    if missing_units:
        st.warning(
            f"📌 학기말 최종 포트폴리오는 **6개 단원 모두 최소 1개씩 수행평가를 완료**해야 생성할 수 있어요. "
            f"현재 **{len(done_units)} / {len(required_units)} 단원** 완료했어요!"
        )
        st.progress(progress, text=f"단원 완료율 {progress * 100:.0f}%")

        with st.container(border=True):
            st.markdown("**단원별 완료 현황**")
            cols = st.columns(2)
            for i, unit in enumerate(required_units):
                icon = UNIT_ICONS.get(unit, "📘")
                with cols[i % 2]:
                    if unit in completed_units:
                        st.markdown(
                            f"<div style='padding:6px 10px;margin:3px 0;border-radius:8px;"
                            f"background:#ECFDF5;color:#065F46;'>✅ {icon} {unit}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='padding:6px 10px;margin:3px 0;border-radius:8px;"
                            f"background:#FEF2F2;color:#991B1B;'>⬜ {icon} {unit} <span style='font-size:11px;opacity:0.8;'>(아직 미완료)</span></div>",
                            unsafe_allow_html=True,
                        )
            st.caption(f"남은 단원 {len(missing_units)}개를 완료하면 PDF 다운로드 버튼이 활성화돼요.")

        st.button(
            "🎓 학기말 최종 포트폴리오 생성 (PDF)",
            type="primary", disabled=True, use_container_width=True,
            help="6개 단원의 수행평가를 모두 완료해야 활성화됩니다.",
        )
        return

    # 6개 단원을 모두 완료한 경우
    st.success("🎉 6개 단원의 수행평가를 모두 완료했어요! 이제 학기말 최종 포트폴리오를 생성할 수 있어요.")
    if st.button("🎓 학기말 최종 포트폴리오 생성 (PDF)", type="primary", use_container_width=True):
        with st.spinner("PDF를 생성하고 있어요..."):
            pdf_bytes = build_comprehensive_portfolio_pdf(
                st.session_state.student_id, st.session_state.student_display_name, records
            )
        if pdf_bytes:
            st.session_state["_final_pdf_bytes"] = pdf_bytes
        else:
            st.info(
                "잠시 후 다시 시도해 주세요. 일부 기록에 PDF가 지원하지 않는 문자가 포함되어 있을 수 있어요. "
                "문제가 계속되면 선생님께 문의하세요."
            )
    pdf_cached = st.session_state.get("_final_pdf_bytes")
    if pdf_cached:
        st.download_button(
            "💾 PDF 다운로드", data=pdf_cached,
            file_name=f"Final_Portfolio_{st.session_state.student_id}.pdf",
            mime="application/pdf", use_container_width=True,
        )

def _render_portfolio_view():
    st.markdown(_PORTFOLIO_CSS, unsafe_allow_html=True)

    records = st.session_state.get("my_history_records", []) or []

    # ── 헤더 (요약 카드) ─────────────────────────────────
    if records:
        avg_score = sum(_safe_float(r.get("ncs_score")) for r in records) / len(records)
        fb_count = sum(1 for r in records if (r.get("teacher_feedback") or "").strip())
        unit_count = len({(r.get("unit") or "").strip() for r in records if r.get("unit")})
    else:
        avg_score, fb_count, unit_count = 0.0, 0, 0

    name = st.session_state.get("student_display_name", "학생")
    st.markdown(
        f"""
<div class="pf-hero">
  <h2>📓 {name} 학생의 성장 일지</h2>
  <p>그동안의 자동차 전기전자제어 실습 기록을 한눈에 확인해 보세요.</p>
  <div class="pf-stats">
    <div class="pf-stat"><b>{len(records)}</b><span>총 실습 건수</span></div>
    <div class="pf-stat"><b>{avg_score:.1f}</b><span>평균 성취도</span></div>
    <div class="pf-stat"><b>{unit_count}</b><span>참여 단원 수</span></div>
    <div class="pf-stat"><b>{fb_count}</b><span>받은 피드백</span></div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    if not records:
        st.info("아직 누적된 기록이 없습니다. 첫 실습을 완료해 보세요!")
        return

    # ── ① 교사 피드백 (최상단) ─────────────────────────
    _render_teacher_feedback_section(records)

    st.markdown("")
    # ── ② 분야별 성취도 그래프 ────────────────────────
    _render_achievement_charts(records)

    st.markdown("---")
    # ── ③ 실습 기록 카드 목록 ─────────────────────────
    st.markdown("### 📚 실습 기록")
    sort_opt = st.radio(
        "정렬", ["최신순", "성취도 높은 순", "단원별"],
        horizontal=True, label_visibility="collapsed", key="pf_sort",
    )
    if sort_opt == "성취도 높은 순":
        sorted_recs = sorted(records, key=lambda r: _safe_float(r.get("ncs_score")), reverse=True)
    elif sort_opt == "단원별":
        sorted_recs = sorted(records, key=lambda r: (r.get("unit", ""), r.get("submitted_at", "")), reverse=False)
    else:
        sorted_recs = sorted(records, key=lambda r: r.get("submitted_at", ""), reverse=True)

    for rec in sorted_recs:
        _render_record_card(rec)

    st.markdown("---")
    # ── ④ 최종 PDF 다운로드 (6개 단원 모두 완료 시에만 활성화) ─────
    _render_final_portfolio_section(records)

def render_student_mode():
    st.sidebar.title("메뉴")
    view = st.sidebar.radio("이동", ["🧑‍🏫 학습 모드", "📓 나의 포트폴리오"])

    api_key = st.secrets.get("GEMINI_API_KEY", "")

    if view == "🧑‍🏫 학습 모드":
        unit = st.selectbox("단원 선택", NCS_UNITS)
        _render_diagnosis_input_tab(unit, api_key)
    else:
        _render_portfolio_view()

# ───────────────────────────────────────────────────────────────────────────
# 교사 모드 (학생별 기록 보기 + 피드백 작성)
# ───────────────────────────────────────────────────────────────────────────
def _get_teacher_password() -> str:
    try:
        return str(st.secrets.get("TEACHER_PASSWORD") or TEACHER_PASSWORD_DEFAULT)
    except Exception:
        return TEACHER_PASSWORD_DEFAULT

def render_teacher_login() -> None:
    st.markdown("### 🧑‍🏫 교사 로그인")
    with st.form("teacher_login_form"):
        pw = st.text_input("교사 비밀번호", type="password",
                           help="기본값은 0000이며, secrets의 TEACHER_PASSWORD로 변경 가능합니다.")
        ok = st.form_submit_button("로그인", type="primary")
    if ok:
        if pw == _get_teacher_password():
            st.session_state["teacher_logged_in"] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

def render_teacher_mode() -> None:
    st.header("🧑‍🏫 교사 대시보드")
    st.caption("학생들의 실습 기록을 확인하고 피드백을 남길 수 있습니다.")

    try:
        df = shb.force_refresh_history()
    except Exception as e:
        logger.exception("history 시트 로드 실패: %s", e)
        st.error("학습 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    if df is None or df.empty:
        st.info("아직 누적된 학생 실습 기록이 없습니다.")
        return

    records = shb.history_df_to_records(df)

    # 학생 목록 구성
    students: dict[str, str] = {}
    for r in records:
        sid = (r.get("student_id") or "").strip()
        if not sid:
            continue
        name = (r.get("student_display_name") or "").strip()
        students[sid] = name or students.get(sid, "")

    if not students:
        st.info("학생 정보가 포함된 기록을 찾지 못했습니다.")
        return

    # 통계 요약
    col1, col2, col3 = st.columns(3)
    col1.metric("등록된 학생 수", f"{len(students)} 명")
    col2.metric("총 실습 기록", f"{len(records)} 건")
    fb_done = sum(1 for r in records if (r.get("teacher_feedback") or "").strip())
    col3.metric("피드백 완료", f"{fb_done} / {len(records)} 건")

    st.markdown("---")

    options = sorted(students.keys())
    labels = {sid: f"{students[sid] or '(이름 미상)'}  ·  {sid}" for sid in options}
    sel_sid = st.selectbox(
        "학생 선택", options=options,
        format_func=lambda s: labels.get(s, s),
    )
    if not sel_sid:
        return

    student_records = [r for r in records if (r.get("student_id") or "").strip() == sel_sid]
    student_records.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
    st.markdown(f"#### 📒 {students[sel_sid] or '(이름 미상)'} 학생의 실습 기록 ({len(student_records)}건)")

    for rec in student_records:
        rid = (rec.get("record_id") or "").strip()
        unit = rec.get("unit", "")
        icon = UNIT_ICONS.get(unit, "📘")
        when = (rec.get("submitted_at") or "")[:16]
        score = _safe_float(rec.get("ncs_score"))
        has_fb = bool((rec.get("teacher_feedback") or "").strip())
        title = f"{icon} {unit} · {when} · {score:.0f}점 {'✅ 피드백 완료' if has_fb else '⏳ 피드백 필요'}"
        with st.expander(title, expanded=False):
            st.markdown(f"**🔍 수행 내용**")
            st.code(rec.get("symptom") or "(없음)")
            if rec.get("reasoning"):
                st.markdown("**🧪 학생이 작성한 진단**")
                st.write(rec.get("reasoning"))
            if rec.get("reflection"):
                st.markdown("**📝 학생 소감**")
                st.info(rec.get("reflection"))
            img_bytes = thumbnail_b64_to_bytes(rec.get("image_b64"))
            if img_bytes:
                st.image(img_bytes, width=280)
            with st.expander("🤖 AI 평가 보기", expanded=False):
                st.markdown(rec.get("result") or "(AI 평가 없음)")

            st.markdown("---")
            st.markdown("**💬 교사 피드백 작성**")
            if not rid:
                st.warning("이 기록은 record_id가 없어 피드백 저장이 불가합니다.")
                continue
            current_fb = rec.get("teacher_feedback") or ""
            new_fb = st.text_area(
                "피드백 내용", value=current_fb, key=f"fb_{rid}", height=120,
                placeholder="예: 멀티미터 측정 절차를 정확히 따랐어요. 다음에는 접지 측정도 추가해 보세요.",
            )
            save_col, info_col = st.columns([1, 3])
            with save_col:
                if st.button("💾 피드백 저장", key=f"save_{rid}", type="primary"):
                    try:
                        shb.update_teacher_feedback_in_sheet(
                            rid, new_fb.strip(), now_kst_display()
                        )
                        shb.invalidate_all_sheet_caches()
                        st.success("피드백이 저장되었습니다.")
                        st.rerun()
                    except Exception as e:
                        logger.exception("피드백 저장 실패: %s", e)
                        st.error(f"저장 실패: {e}")
            with info_col:
                updated = rec.get("teacher_feedback_updated_at") or ""
                if updated:
                    st.caption(f"최근 저장: {updated}")

# ───────────────────────────────────────────────────────────────────────────
# 랜딩(역할 선택) 페이지
# ───────────────────────────────────────────────────────────────────────────
def render_landing() -> None:
    st.markdown(
        """
<style>
.landing-wrap { max-width: 1000px; margin: 1.2rem auto 0 auto; text-align: center; }
.landing-hero { padding: 18px 0 10px 0; }
.landing-title {
    font-size: 2.8rem; font-weight: 800; color: #1e3a8a; margin: 0;
    letter-spacing: -0.5px;
}
.landing-sub { color:#475569; font-size: 1.15rem; margin: 10px 0 0 0; }
.landing-hint { color:#64748b; font-size: 1.05rem; margin: 24px 0 18px 0; line-height: 1.6; }

.mode-cards {
    display: flex; gap: 32px; justify-content: center; margin: 28px auto 0 auto;
    max-width: 920px; flex-wrap: wrap;
}
.mode-card {
    flex: 1 1 380px; min-width: 320px; max-width: 440px;
    padding: 56px 32px;
    border-radius: 24px; text-decoration: none !important;
    box-shadow: 0 10px 28px rgba(15,23,42,0.12);
    border: 3px solid transparent;
    display: block; text-align: center;
    transition: transform .22s ease, box-shadow .22s ease, filter .22s ease;
    cursor: pointer;
}
.mode-card:hover {
    transform: translateY(-6px) scale(1.02);
    box-shadow: 0 22px 44px rgba(15,23,42,0.20);
    filter: brightness(1.04);
}
.mode-card:active { transform: translateY(-2px) scale(1.01); }

.mode-card-teacher {
    background: linear-gradient(160deg,#fffde7 0%,#fff59d 40%,#fdd835 100%);
    border-color: #f9a825; color: #3e2723 !important;
}
.mode-card-student {
    background: linear-gradient(160deg,#e3f2fd 0%,#90caf9 45%,#42a5f5 100%);
    border-color: #1565c0; color: #0d47a1 !important;
}

.mode-card-icon { font-size: 4.5rem; line-height: 1; display: block; margin-bottom: 14px; }
.mode-card-label { font-size: 2.0rem; font-weight: 800; display: block; margin-bottom: 12px; }
.mode-card-desc { font-size: 1.1rem; opacity: 0.95; line-height: 1.55; display: block; }

.landing-foot { color:#94a3b8; font-size: 0.9rem; margin-top: 36px; }
</style>
<div class="landing-wrap">
  <div class="landing-hero">
    <h1 class="landing-title">🚗 자동차 고장진단 AI tutor</h1>
    <p class="landing-sub">자동차 전기전자제어 · NCS 수행준거 기반 학습 도우미</p>
  </div>
  <p class="landing-hint">
    아래 카드를 클릭해 역할을 선택해 주세요.<br/>
    선택한 역할은 세션 동안 유지되며, 사이드바에서 언제든 다시 바꿀 수 있어요.
  </p>

  <div class="mode-cards">
    <a class="mode-card mode-card-teacher" href="?role=teacher" target="_self">
      <span class="mode-card-icon">🧑‍🏫</span>
      <span class="mode-card-label">교사 모드</span>
      <span class="mode-card-desc">학생 실습 기록 확인<br/>· 피드백 작성 ·</span>
    </a>
    <a class="mode-card mode-card-student" href="?role=student" target="_self">
      <span class="mode-card-icon">🧑‍🎓</span>
      <span class="mode-card-label">학생 모드</span>
      <span class="mode-card-desc">고장진단 실습 진행<br/>· 포트폴리오 작성 ·</span>
    </a>
  </div>

  <p class="landing-foot">NCS 수행준거 기반 · 소크라테스식 AI 학습 지원</p>
</div>
""",
        unsafe_allow_html=True,
    )

# ───────────────────────────────────────────────────────────────────────────
# 메인 진입점
# ───────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="자동차 고장진단 AI tutor", page_icon="🚗", layout="wide")

# ── 전역 글자 크기 1.5배 업스케일 (사이드바 포함) ─────────────────
st.markdown(
    """
<style>
/* 본문 기본 폰트 1.5배 */
html, body, [class*="st-emotion"], .stApp { font-size: 1.5rem !important; line-height: 1.65; }

/* 헤딩 비례 확대 */
.stApp h1 { font-size: 2.8rem !important; }
.stApp h2 { font-size: 2.25rem !important; }
.stApp h3 { font-size: 1.85rem !important; }
.stApp h4 { font-size: 1.55rem !important; }
.stApp h5 { font-size: 1.35rem !important; }
.stApp h6 { font-size: 1.2rem !important; }

/* 본문 단락·리스트 */
.stMarkdown p, .stMarkdown li, .stMarkdown span,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span { font-size: 1.15rem !important; line-height: 1.7; }

/* 입력 위젯 (텍스트·텍스트영역·셀렉트·숫자·날짜) */
.stTextInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"] *,
.stNumberInput input, .stDateInput input,
.stMultiSelect div[data-baseweb="select"] * { font-size: 1.15rem !important; }

/* 위젯 라벨 */
.stTextInput label, .stTextArea label, .stSelectbox label,
.stNumberInput label, .stDateInput label, .stMultiSelect label,
.stRadio label, .stCheckbox label, .stFileUploader label,
.stSlider label, .stColorPicker label
{ font-size: 1.2rem !important; font-weight: 600 !important; }

/* 라디오 옵션 라벨 */
.stRadio div[role="radiogroup"] label p { font-size: 1.15rem !important; }

/* 버튼 */
.stButton button, .stDownloadButton button, .stFormSubmitButton button,
.stLinkButton button { font-size: 1.2rem !important; font-weight: 600; padding: 0.6rem 1.1rem !important; }

/* 탭 */
.stTabs [data-baseweb="tab"] { font-size: 1.25rem !important; font-weight: 600; }

/* 메트릭/캡션/얼럿 */
[data-testid="stMetricValue"] { font-size: 2.4rem !important; }
[data-testid="stMetricLabel"] { font-size: 1.15rem !important; }
[data-testid="stMetricDelta"] { font-size: 1.05rem !important; }
[data-testid="stCaptionContainer"], .stCaption, small { font-size: 1.0rem !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { font-size: 1.15rem !important; }
[data-testid="stExpander"] summary p { font-size: 1.2rem !important; font-weight: 600; }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { font-size: 1.15rem !important; }
.stDataFrame, .stTable { font-size: 1.05rem !important; }
.stCode, pre, code { font-size: 1.05rem !important; }

/* 사이드바 너비 확대 (메뉴 항목이 한 줄에 표시되도록) */
section[data-testid="stSidebar"] { width: 340px !important; min-width: 340px !important; }
section[data-testid="stSidebar"] > div:first-child { width: 340px !important; min-width: 340px !important; }
section[data-testid="stSidebar"] .stButton button,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
    white-space: nowrap !important;
}

/* 사이드바 전체 1.5배 확대 */
section[data-testid="stSidebar"] * { font-size: 1.15rem !important; }
section[data-testid="stSidebar"] h1 { font-size: 1.9rem !important; }
section[data-testid="stSidebar"] h2 { font-size: 1.6rem !important; }
section[data-testid="stSidebar"] h3 { font-size: 1.4rem !important; }
section[data-testid="stSidebar"] h4 { font-size: 1.25rem !important; }
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stCheckbox label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stButton button { font-size: 1.2rem !important; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] small { font-size: 1.0rem !important; }

/* 진행 바 두께도 비례 확대 */
.stProgress > div > div > div { height: 18px !important; }
</style>
""",
    unsafe_allow_html=True,
)

shb.gsheets_available()

# 세션 상태 초기화
if "app_role" not in st.session_state:
    st.session_state["app_role"] = None
if "student_logged_in" not in st.session_state:
    st.session_state["student_logged_in"] = False
if "teacher_logged_in" not in st.session_state:
    st.session_state["teacher_logged_in"] = False

# 랜딩 카드 클릭(?role=teacher / ?role=student) → 세션에 반영 후 쿼리 정리
try:
    _qp_role = st.query_params.get("role")
    if _qp_role in ("teacher", "student") and st.session_state["app_role"] is None:
        st.session_state["app_role"] = _qp_role
        try:
            del st.query_params["role"]
        except Exception:
            pass
        st.rerun()
except Exception:
    pass

# ── 역할 미선택 → 랜딩 페이지 표시 ──────────────────────
if st.session_state["app_role"] is None:
    render_landing()
    st.stop()

# ── 사이드바: 현재 역할 표시 + 역할 재선택 ────────────
with st.sidebar:
    role = st.session_state["app_role"]
    role_label = "🧑‍🏫 교사" if role == "teacher" else "🧑‍🎓 학생"
    st.markdown(f"### {role_label} 모드")
    if st.button("🔄 역할 다시 선택", use_container_width=True):
        st.session_state["app_role"] = None
        st.session_state["teacher_logged_in"] = False
        reset_student_session_soft()
        st.rerun()
    st.markdown("---")

# ── 역할에 따른 화면 분기 ─────────────────────────────
if st.session_state["app_role"] == "teacher":
    if not st.session_state.get("teacher_logged_in"):
        render_teacher_login()
    else:
        render_teacher_mode()
else:
    if not st.session_state.get("student_logged_in"):
        st.markdown("### 🧑‍🎓 학생 로그인")
        with st.form("login"):
            sid = st.text_input("학번")
            name = st.text_input("이름")
            pw = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", type="primary"):
                st.session_state.student_id = sid
                st.session_state.student_display_name = name
                st.session_state.student_logged_in = True
                st.session_state["my_history_records"] = shb.filter_history_records_by_student(sid)
                st.rerun()
    else:
        render_student_mode()