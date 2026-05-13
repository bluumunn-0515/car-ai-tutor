import base64
import logging
import re
import time
import json
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
# '자동차 전기전자제어' 교과 NCS 능력단위(세부 단원)
NCS_UNITS = [
    "자동차 전기전자장치 고장진단",
    "배터리 점검",
    "시동·충전장치 점검",
    "조명장치 점검",
    "편의장치 점검",
    "네트워크 장치 점검",
]
# 교과 → 단원(능력단위) 매핑 — '자동차 전기전자제어' 단일 교과
CURRICULUM = {
    "자동차 전기전자제어": list(NCS_UNITS),
}
# 단원별 직관 아이콘 — 카드/배지/라디오 라벨에 활용
UNIT_ICONS = {
    "자동차 전기전자장치 고장진단": "🔧",
    "배터리 점검": "🔋",
    "시동·충전장치 점검": "🚗",
    "조명장치 점검": "💡",
    "편의장치 점검": "🪑",
    "네트워크 장치 점검": "🛰️",
}
# NCS 학습모듈(LM1506030101/102/104/105/106/108) 및 '자동차 전기·전자 제어 2022(보안)'
# 교과서의 수행준거·핵심 용어를 추출하여 단원별 루브릭 키워드로 구성
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
        "안전·전원 차단 확인": 1.3,
        "회로도/기호 분석": 1.2,
        "회로시험기 측정 절차": 1.1,
        "진단장비(스캐너) 활용": 1.0,
        "배터리 외관/상태 확인": 1.1,
        "개방회로 전압(OCV) 측정": 1.1,
        "부하/CCA·SOC 판정": 1.0,
        "암전류/배터리 센서 점검": 1.0,
        "시동회로 점검": 1.1,
        "발전기 출력 점검": 1.0,
        "회로 전압강하 측정": 1.0,
        "점검 절차/예비점검": 1.2,
        "등화회로 분석": 1.1,
        "광원/전구 점검": 1.0,
        "회로 전압/접지 측정": 1.0,
        "BCM/CAN 등화 제어": 1.0,
        "편의장치 유형/회로 식별": 1.0,
        "모듈 전원·접지 점검": 1.1,
        "액추에이터/릴레이 점검": 1.0,
        "스캐너 자기진단/강제구동": 1.1,
        "통신 프로토콜 이해": 1.2,
        "종단저항/배선 점검": 1.1,
        "통신 신호/파형 측정": 1.0,
        "게이트웨이/모듈 진단": 1.0,
    },
    "평가 모드": {
        "안전·전원 차단 확인": 1.1,
        "회로도/기호 분석": 1.2,
        "회로시험기 측정 절차": 1.3,
        "진단장비(스캐너) 활용": 1.2,
        "배터리 외관/상태 확인": 1.0,
        "개방회로 전압(OCV) 측정": 1.3,
        "부하/CCA·SOC 판정": 1.2,
        "암전류/배터리 센서 점검": 1.1,
        "시동회로 점검": 1.2,
        "발전기 출력 점검": 1.3,
        "회로 전압강하 측정": 1.3,
        "점검 절차/예비점검": 1.0,
        "등화회로 분석": 1.0,
        "광원/전구 점검": 1.0,
        "회로 전압/접지 측정": 1.3,
        "BCM/CAN 등화 제어": 1.1,
        "편의장치 유형/회로 식별": 1.0,
        "모듈 전원·접지 점검": 1.2,
        "액추에이터/릴레이 점검": 1.1,
        "스캐너 자기진단/강제구동": 1.3,
        "통신 프로토콜 이해": 1.1,
        "종단저항/배선 점검": 1.3,
        "통신 신호/파형 측정": 1.3,
        "게이트웨이/모듈 진단": 1.2,
    },
}
# 단원별 촬영 전 체크리스트 — PDF 실습 지침에서 학생들이 자주 놓치는 포인트를 발췌하여 구어체로 재작성
UNIT_PHOTO_CHECKLISTS = {
    "자동차 전기전자장치 고장진단": [
        "회로도 분석에 필요한 커넥터 핀 번호 라벨이 사진에 잘 보이나요?",
        "측정 중인 멀티미터 모드(DC V / Ω / 통전)가 화면에 또렷이 찍혔나요?",
        "리드봉이 점검 단자(VΩmA / COM)에 정확히 닿아 있는 모습이 보이나요?",
        "단선·단락·접지가 의심되는 배선 구간이 한 컷에 같이 담겼나요?",
    ],
    "배터리 점검": [
        "(＋)/(－) 터미널 부식·황화 상태가 잘 보이게 찍었나요?",
        "배터리 라벨(CCA, RC, AGM/EFB/MF 표기)이 또렷이 찍혔나요?",
        "배터리 표시창(매직아이)의 색상이 선명하게 나오나요?",
        "DC V 측정 시 단자 양쪽에 리드봉이 닿은 모습과 측정 전압이 함께 보이나요?",
    ],
    "시동·충전장치 점검": [
        "솔레노이드 B/ST/M 단자 위치가 한 컷에 모두 보이나요?",
        "발전기 B단자·FR단자·C단자 커넥터와 케이블 굵기를 알 수 있게 찍었나요?",
        "시동 ON 또는 크랭킹 시점의 측정값(전압/전류)이 화면에 함께 나오나요?",
        "벨트장력·풀리(OAD 포함) 상태가 잘 드러나는 각도인가요?",
    ],
    "조명장치 점검": [
        "전조등/미등/방향지시등 등 점검 중인 등화의 종류를 알 수 있는 사진인가요?",
        "회로도 상의 배선 색상과 실제 배선 색상이 일치하게 보이나요?",
        "멀티미터 리드봉이 커넥터 핀(또는 소켓 단자)에 정확히 닿아 있나요?",
        "퓨즈/릴레이 박스의 해당 칸 표기와 부품 위치가 함께 찍혔나요?",
    ],
    "편의장치 점검": [
        "BCM/ETACS 모듈 또는 다기능 스위치의 커넥터 핀 번호가 잘 보이나요?",
        "릴레이 30/87/85/86 단자 식별이 가능한 각도로 촬영했나요?",
        "스캐너 화면에 DTC 코드와 차량 모델 정보가 함께 캡처됐나요?",
        "와이퍼·도어록·파워윈도우 등 점검 대상 액추에이터의 위치가 식별되나요?",
    ],
    "네트워크 장치 점검": [
        "DLC 커넥터에 스캐너 케이블이 연결된 모습이 보이나요?",
        "C-CAN/B-CAN 주선의 트위스트 페어 배선과 종단저항 위치가 함께 찍혔나요?",
        "오실로스코프 파형의 시간축·전압축 설정이 화면에 또렷이 나오나요?",
        "스캐너의 통신 가능/불가 ECU 목록 또는 bus-off/time-out 메시지가 보이나요?",
    ],
}
# 단원별 [대상 부품/현재 상태/학습 질문] 입력 예시 — placeholder 가이드용
UNIT_INPUT_HINTS = {
    "자동차 전기전자장치 고장진단": {
        "target": "예: 운전석 도어 커넥터 E12, 미등 회로 퓨즈",
        "state": "예: 멀티미터로 단자 전압을 측정하니 0V가 나옴, 통전 부저가 울리지 않음",
        "question": "예: 단선 위치를 어떻게 좁혀가야 하는지 점검 순서가 헷갈려요",
    },
    "배터리 점검": {
        "target": "예: 12V 납축전지(MF), 배터리 센서, B+ 케이블",
        "state": "예: OCV 12.0V 측정, 시동 시 크랭킹 약함, 매직아이 색이 어두움",
        "question": "예: OCV 12.0V는 정상인가요? CCA·SOC 중 무엇을 먼저 확인해야 하나요?",
    },
    "시동·충전장치 점검": {
        "target": "예: 알터네이터 B단자, 시동 솔레노이드, 시동 릴레이",
        "state": "예: 공회전 시 충전 전압 13.2V로 낮음, 크랭킹은 되는데 잘 안 걸림",
        "question": "예: 13.2V면 발전기 불량인지 전압강하 문제인지 어떻게 구분하나요?",
    },
    "조명장치 점검": {
        "target": "예: 좌측 전조등(로우빔), 방향지시등 플래셔, 미등 릴레이",
        "state": "예: 좌측 로우빔만 점등 안 됨, 우측은 정상, 퓨즈는 도통됨",
        "question": "예: 전구·소켓·접지 중 무엇부터 점검해야 효율적인가요?",
    },
    "편의장치 점검": {
        "target": "예: 운전석 파워윈도우 모터, 와이퍼 릴레이, BCM",
        "state": "예: AUTO 작동 안 됨, 수동 UP은 됨, 스캐너에 B1234 DTC 표시",
        "question": "예: 강제구동으로 단품을 먼저 봐야 할지, 입력 신호부터 봐야 할지 모르겠어요",
    },
    "네트워크 장치 점검": {
        "target": "예: C-CAN 주선, ABS 모듈, 게이트웨이",
        "state": "예: 스캐너에서 ABS 모듈만 통신 불가, 다른 ECU는 정상",
        "question": "예: 종단저항·주선 단선 중 어디부터 측정해야 하나요? 120Ω 기준은요?",
    },
}
# Google AI Studio가 2024~2025년 사이 1.5 라인을 v1beta에서 단계적으로 디프리케이션하면서
# `gemini-1.5-flash`/`gemini-1.5-pro` 가 신규 키에서 404(NOT_FOUND)로 막히는 사례가 늘었다.
# 그래서 현재 시점 가장 안정적인 2.x flash 라인을 1순위로 두고, 계정/리전 상황에 따라
# 라우팅이 다를 수 있는 alias 들을 폴백으로 함께 제공한다. 404가 나면 즉시 다음 후보로 넘어간다.
GEMINI_MODEL_CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
]
GEMINI_RETRY_DELAYS_SECONDS = [2.0, 4.0]
GEMINI_IMAGE_MAX_SIZE = (1024, 1024)
GEMINI_IMAGE_JPEG_QUALITY = 85

# --- 교사 인증(세션 전용; DB 미연동 시 재시작·새로고침 시 초기화) ---
TEACHER_PASSWORD_DEFAULT = "0000"
MISSION_PHOTOS_JSON_MAX_CHARS = 48_000  # Google Sheet 셀 한도(~50k자) 전에 자르기


def now_kst_display() -> str:
    """접속 로그용 한국 표준시 문자열."""
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        dt = datetime.now(timezone.utc) + timedelta(hours=9)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " KST"


def reset_teacher_session_soft() -> None:
    """역할 전환 등으로 교사 로그인 상태만 해제한다."""
    st.session_state.teacher_logged_in = False
    st.session_state.teacher_display_name = ""


def normalize_student_name(s: str) -> str:
    return " ".join((s or "").strip().split())


def reset_student_auth_form() -> None:
    """학생 로그인/가입 단계 입력만 초기화한다."""
    st.session_state.student_auth_stage = "idle"
    st.session_state.student_pending_id = ""
    st.session_state.student_pending_name = ""


def reset_student_session_soft() -> None:
    """학생 로그아웃·역할 전환 시 로그인 상태 및 임시 입력을 해제한다."""
    st.session_state.student_logged_in = False
    reset_student_auth_form()
    st.session_state.student_id = ""
    st.session_state.student_display_name = ""
    # 사이드바 메뉴(학습 모드 / 나의 포트폴리오) 선택도 초기화
    for k in ("student_view_pick",):
        if k in st.session_state:
            try:
                del st.session_state[k]
            except Exception:
                pass
    # 다른 학생이 같은 브라우저로 로그인할 때 이전 학생의 누적 캐시가 새지 않도록 비운다.
    st.session_state["my_history_records"] = None
    try:
        shb.invalidate_all_sheet_caches()
    except Exception:
        pass
    reset_diagnosis_flow()


def reset_diagnosis_flow() -> None:
    """2단계 진단 플로우 상태를 초기화한다(새 진단 시작 / 로그아웃 시 사용)."""
    st.session_state.diag_step = "input"
    st.session_state.latest_guidance = ""
    st.session_state.latest_evaluation = ""
    st.session_state.latest_execution_result = ""
    st.session_state.latest_result = ""
    st.session_state.latest_symptom = ""
    st.session_state.latest_generated_at = ""
    st.session_state.latest_reflection = ""
    st.session_state.latest_image_b64 = ""
    st.session_state.mission_step_photos = {}
    st.session_state.diag_photo_nonce = uuid.uuid4().hex[:12]
    for widget_key in (
        "diag_target_part",
        "diag_current_state",
        "diag_learning_question",
        "diag_uploaded_image",
        "diag_execution_result",
        "diag_reflection",
    ):
        if widget_key in st.session_state:
            try:
                del st.session_state[widget_key]
            except Exception:
                st.session_state[widget_key] = "" if widget_key != "diag_uploaded_image" else None
def compose_structured_symptom(target_part: str, current_state: str, learning_question: str) -> str:
    """학생의 [대상 부품/현재 상태/학습 질문] 입력을 AI가 인지 가능한 구조화된 블록으로 합친다.

    - 모든 필드가 비어 있으면 빈 문자열을 반환한다(기존 호출부의 '사진만 업로드' 대응 유지).
    - 학습 질문은 비어 있더라도 라벨은 남겨 AI가 우선 응답할 영역을 명확히 인지하도록 한다.
    """
    target = (target_part or "").strip()
    state = (current_state or "").strip()
    question = (learning_question or "").strip()
    if not (target or state or question):
        return ""
    return (
        "[대상 부품]\n"
        f"{target or '(미입력)'}\n"
        "[현재 상태]\n"
        f"{state or '(미입력)'}\n"
        "[학습 질문 — 우선 응답 요청]\n"
        f"{question or '(미입력)'}"
    )


def _rubric_lines_for_unit(unit: str) -> str:
    lines = NCS_RUBRIC.get(unit, [])
    if not lines:
        return "(해당 단원 수행준거 정보 없음)"
    return "\n".join(f"- {label}: 키워드 예시 {', '.join(kws)}" for label, kws in lines)


# NCS 학습모듈(LM1506030104 등) 및 '자동차 전기·전자 제어 2022(보안)' 교과서에서 추출한 표준 절차.
# 모든 단원에 공통으로 적용되는 안전·계측·진단 흐름을 AI 튜터가 항상 인지하도록 프롬프트에 주입한다.
STANDARD_PROCEDURE_BLOCK = """
[표준 절차 — NCS 학습모듈 + '자동차 전기·전자 제어 2022(보안)' 교과서 기준]
가. 멀티미터(회로시험기) 사용 전 안전 점검
   1) 정비지침서·작업 순서·장비를 사전 검토하고 인화성 물질을 별도 보관한다.
   2) 전기·전자 회로 작업 전 전원(배터리(－) 또는 IG) 차단 여부를 먼저 확인한다.
   3) 측정 종류(DC V / AC V / Ω / A)에 맞는 레인지·단자(VΩmA / COM / 10A)를 선택한다.
   4) 저항 측정은 반드시 무전원 상태에서 수행하며 아날로그는 0점 조정 후 측정한다.
   5) 반도체(ECM·BCM 등) 회로는 시험등(테스트 램프) 대신 고임피던스 디지털 회로시험기를 사용한다.
   6) 측정 종료 시 선택 스위치를 OFF로 돌려 건전지 방전·오측정을 예방한다.
나. 회로도 분석 순서
   1) 정비지침서에서 해당 차종 전장 회로도를 찾고 구성 부품 기호·접지 표시를 확인한다.
   2) 배선 색상(B/Br/G/Gr/L/Lg/O/P/R/W/Y 등) 및 하네스 기호(E/M/A/R/D/C/F/S)를 식별한다.
   3) 전원(상시·IG·ACC)→퓨즈→스위치/릴레이→부하(액추에이터)→접지 흐름을 차례로 추적한다.
   4) 커넥터 식별도와 핀 번호로 측정 포인트(체크 포인트)를 결정한 뒤 측정에 들어간다.
다. 시험등 vs 디지털 멀티미터 사용 기준
   - 시험등(test lamp): 단순 회로의 전압 유무·통전 개략 확인용. ECM/BCM 등 반도체 회로에는 사용 금지.
   - 디지털 멀티미터: 정밀 측정·반도체 회로·전압강하·소비전류 측정에 사용. 변화 추세는 그래프/스코프 병행.
라. 진단장비(스캐너) 사용 절차
   1) DLC 커넥터에 케이블을 연결하고 IG ON 상태에서 차종·시스템(ECM/BCM 등)을 선택한다.
   2) 고장코드(DTC) 확인 → 진단 가이드로 부품 위치·규정값 점검.
   3) 센서 데이터/그래프로 입출력 경향을 분석한다.
   4) 필요 시 강제구동으로 액추에이터 단품을 구동해 단품 불량을 확인한다.
   5) 네트워크 점검 시 통신 가능/불가 ECU 분류 → 종단저항·주선 단선/단락·bus-off/time-out을 함께 확인한다.
""".strip()
def build_learning_prompt(
    user_symptom: str,
    selected_subject: str,
    selected_unit: str,
    mode: str = "학습 모드",
) -> str:
    """[단계 1] AI 가이드(미션) 프롬프트.

    - 정답을 직접 알려주지 않고 '진단 방향'과 '측정/점검 방법'만 미션 형태로 제시한다.
    - 출력은 불렛(•)과 표(Table)를 적극 사용해 가독성을 높인다.
    """
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    rubric_block = _rubric_lines_for_unit(selected_unit)
    tone_block = (
        "[톤] 친근하고 교육적인 코치 톤. 학생이 스스로 답을 찾도록 힌트와 소크라테스식 질문을 활용한다."
        if mode == "학습 모드"
        else "[톤] 단정적 정답 노출 없이, NCS 평가 기준에 부합하도록 객관적이고 절차 중심으로 안내한다."
    )
    return f"""
너는 특성화고 '자동차 전기전자제어' 교과 실습 수업의 AI 튜터이며,
자동차 전장(電裝) 시스템 — 배터리/시동·충전/조명/편의/네트워크 통신 — 분야 전문가다.
지금은 **[단계 1] 진단 가이드(미션) 단계**다. 절대 정답(예: "이 배터리는 방전 상태이다", "이 IPS가 고장이다")을
단정하여 알려주지 말고, **학생이 직접 측정·확인할 수 있는 '진단 방향'과 '측정/점검 방법'만** 제시한다.
답변은 NCS 학습모듈(LM1506030101/102/104/105/106/108)과 '자동차 전기·전자 제어 2022(보안)' 교과서에 명시된 절차·용어를 기준으로 한다.

[선택 교과] {selected_subject}
[선택 단원(능력단위)] {selected_unit}
[이 단원의 수행준거 요약]
{rubric_block}
{STANDARD_PROCEDURE_BLOCK}
[학생 입력 증상]
{symptom_block}

{tone_block}

[작성 원칙 — 반드시 준수]
- ❌ 결론·정답 단정 금지(예: "원인은 ~다", "~를 교체하면 됩니다" 등 직접적 답).
- ❌ **"## 📋 NCS 기반 수행 순서" 섹션에서는 표(Markdown table)를 절대 사용하지 말 것.**
- ✅ 진단 방향과 측정/점검 절차를 **'미션' 형태**로 제시.
- ✅ "수행 순서" 섹션은 4개의 ### 소제목(🛡️/🔍/⚡/🛠️)으로 분류한다.
- ✅ **각 단계는 다음 4줄 구조로 반드시 작성한다** — 학생이 단계 2(실습 수행 결과 제출)에서 그대로 따라 할 수 있게 한다:
    1) 상위 불릿 = 핵심 행동 타이틀: `• [핵심 행동] **[규정값]**` (20자 이내, 규정값 제외)
    2) 서브 불릿 #1: `    - 🛠 방법: [측정/관찰/조작 절차, 40자 이내]`
    3) 서브 불릿 #2: `    - 📚 NCS 준거: [본 단원의 [이 단원의 수행준거 요약]에 적힌 라벨 중 한 개를 정확히 인용]`
    4) 서브 불릿 #3: `    - 📝 기록 예: "[학생이 단계 2 [실습 수행 결과] 입력란에 그대로 붙여 넣을 한 줄 예시, 따옴표 포함, 40자 이내]"`
- ✅ 규정값(예: 12.6V, 0.2V 이하, 120Ω 등)은 반드시 Markdown **굵게** 표기(`**12.6V**`). 타이틀과 기록 예 안의 측정값도 굵게.
- ✅ 한 카테고리(### 소제목)당 단계 수는 **최소 2개, 권장 3~4개**. 너무 적게 쳐내지 말고, 본 단원의 수행준거([이 단원의 수행준거 요약])가 골고루 매핑되도록 단계를 구성한다.
- ✅ "수행 순서" 외 섹션(권장 측정 도구 등)에서는 표 사용 가능. 다른 섹션도 가능하면 짧은 불릿(•)으로.
- ✅ 단원 핵심 키워드(예: OCV 12.3~12.9V, 발전기 13.8~14.9V, 전압강하 0.2V, 종단저항 120Ω, 솔레노이드 B/ST/M, 릴레이 30/87/85/86, BCM/IPS/B-CAN, bus-off/time-out 등)를 자연스럽게 포함.
- ✅ [표준 절차]의 (가) 안전 점검 → (나) 회로도 분석(전원→퓨즈→스위치/릴레이→부하→접지) → (다) 시험등 vs DMM 사용 기준 → (라) 스캐너 절차(DTC→센서데이터→강제구동) 흐름을 미션에 녹인다.
- ✅ [학생 입력 증상]에 [학습 질문]이 비어 있지 않다면, **`💡 학습 질문 힌트` 섹션에서 그 질문을 우선적으로 다룬다**(정답은 X, 소크라테스식 힌트만).
- ✅ 부품 식별 신뢰도가 낮으면 `📷 추가 촬영 가이드` 섹션에서 각도/거리/초점을 구체적으로 안내.

[출력 형식 — 아래 마크다운 구조를 그대로 따른다]

## 🎯 미션 요약
• (한 문장으로 학생이 이번 실습에서 수행할 핵심 미션)

## 📍 점검 대상
• 추정 부품 명칭(신뢰도): …
• 회로 내 위치/역할: …
• 단원과의 연관성: …

## 🛠 권장 측정 도구
| 도구 | 측정 모드/레인지 | 사용 목적 |
| --- | --- | --- |
| 디지털 멀티미터 | DC V / Ω / 통전 | … |
| (필요 시) 스캐너 | DTC·센서데이터·강제구동 | … |
| (필요 시) 시험등/오실로스코프 | … | … |

## 📋 NCS 기반 수행 순서 (Mission Steps)
> ⚠ 이 섹션은 **반드시 아래 4개의 ### 소제목**으로만 작성한다. **표 사용 금지**. 각 단계는 **상위 불릿(타이틀, 20자 이내) + 들여쓴 서브 불릿 3줄(🛠 방법 / 📚 NCS 준거 / 📝 기록 예)** 구조를 그대로 따른다.

### 🛡️ 준비 / 안전
• 점화스위치 OFF 확인
    - 🛠 방법: 키 OFF · 계기판 소등 확인
    - 📚 NCS 준거: 안전·전원 차단 확인
    - 📝 기록 예: "점화 OFF, 계기판 소등 확인 (양호)"
• 절연장갑 착용
    - 🛠 방법: 양손 절연장갑 + 보안경 착용
    - 📚 NCS 준거: 안전·전원 차단 확인
    - 📝 기록 예: "절연장갑·보안경 착용 완료"

### 🔍 점검 / 회로도
• 회로도 퓨즈 위치 식별
    - 🛠 방법: 정비지침서 회로도에서 30A 퓨즈 위치 확인
    - 📚 NCS 준거: 회로도/기호 분석
    - 📝 기록 예: "F12 30A 퓨즈 도통 양호 (회로도 일치)"
• 커넥터 핀 번호 확인
    - 🛠 방법: 커넥터 식별도로 측정 포인트 핀 번호 매칭
    - 📚 NCS 준거: 회로도/기호 분석
    - 📝 기록 예: "E12 커넥터 3번 핀 = (+) 입력 확인"

### ⚡ 측정 / 전압
• OCV 측정 **12.3~12.9V**
    - 🛠 방법: DC V 레인지, (+)/(-) 단자에 리드 접촉 후 측정
    - 📚 NCS 준거: 개방회로 전압(OCV) 측정
    - 📝 기록 예: "OCV **12.45V** 측정 (규정 범위 내, 양호)"
• 전압강하 측정 **0.2V 이하**
    - 🛠 방법: 부하 인가 상태에서 B+ 케이블 양단 전압 측정
    - 📚 NCS 준거: 회로 전압강하 측정
    - 📝 기록 예: "B+ 전압강하 **0.12V** (규정 0.2V 이하, 양호)"

### 🛠️ 판정 / 조치
• SOC 75% 이상 양호
    - 🛠 방법: OCV→SOC 환산표 또는 배터리 테스터로 SOC 판정
    - 📚 NCS 준거: 부하/CCA·SOC 판정
    - 📝 기록 예: "SOC **82%** (양호) — 충전 추가 불필요"
• 규정 외 시 단품 점검
    - 🛠 방법: CCA 부하시험으로 단품 노후/방전 여부 추가 확인
    - 📚 NCS 준거: 부하/CCA·SOC 판정
    - 📝 기록 예: "CCA 측정값 vs 규격 비교 → 단품 교체 권고 검토"

## ⚠ 안전 주의
• …
• …

## 💡 학습 질문 힌트
• (학생의 [학습 질문]을 그대로 인용한 뒤, 답이 아니라 **다음에 어떤 측정/관찰을 해보면 단서가 잡힐지** 힌트만 제시)
• 소크라테스식 되묻기 1~2개

## 📷 추가 촬영 가이드 (신뢰도 낮은 경우만)
• 각도/거리/초점 …

[중요]
- 위 7개 H2 섹션 헤더(##)를 정확히 그대로 사용한다.
- "수행 순서" 섹션 안의 4개 H3 소제목(🛡️ 준비 / 안전, 🔍 점검 / 회로도, ⚡ 측정 / 전압, 🛠️ 판정 / 조치)을 정확히 그대로 사용한다. 표 금지.
- **각 단계는 위 예시처럼 반드시 4줄(타이틀 + 🛠 방법 + 📚 NCS 준거 + 📝 기록 예) 구조로 작성**한다. 한 줄도 빠뜨리지 않는다.
- 📚 NCS 준거 값은 [이 단원의 수행준거 요약]에 명시된 라벨에서 골라 정확히 인용한다.
- 📝 기록 예는 "" 따옴표로 감싸 학생이 그대로 복사·붙여넣을 수 있는 형태로 작성한다(40자 이내).
- 규정값/측정값은 반드시 **굵게**.
""".strip()
def build_evaluation_prompt(
    user_symptom: str,
    student_reasoning: str,
    selected_subject: str,
    selected_unit: str,
    guidance_text: str = "",
    mode: str = "평가 모드",
) -> str:
    """[단계 2] 실습 수행 결과 평가 프롬프트.

    - [단계 1]에서 AI가 제시한 가이드(미션) 대비 학생 수행 결과의 충실도를 표 형태로 정리한다.
    - 정답 단정은 피하되, 가이드 미이행 항목은 명확히 짚어 보완 방향을 제시한다.
    """
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    reasoning_block = student_reasoning if student_reasoning.strip() else "(학생이 실습 수행 결과를 입력하지 않음)"
    guidance_block = guidance_text.strip() if guidance_text and guidance_text.strip() else "(이전 단계 가이드가 비어 있음)"
    rubric_block = _rubric_lines_for_unit(selected_unit)
    tone_block = (
        "[톤] 학생을 격려하면서도 NCS 수행준거에 비춰 객관적으로 짚는 코치 톤."
        if mode == "학습 모드"
        else "[톤] 객관적·절차 중심. 합격/불합격 표현은 금지하되 보완 항목은 분명히 명시한다."
    )
    return f"""
너는 특성화고 '자동차 전기전자제어' 교과 실습의 평가 코치다.
지금은 **[단계 2] 학생의 실습 수행 결과 평가 단계**이며, [단계 1]에서 너 자신이 제시한 가이드(미션)와
학생이 실제로 측정·관찰·판단한 결과를 비교해 **충실도(faithfulness)** 와 **NCS 수행준거 정렬도**를 평가한다.
평가 기준은 NCS 학습모듈(LM1506030101/102/104/105/106/108)과 '자동차 전기·전자 제어 2022(보안)' 교과서의 표준 절차를 따른다.

[선택 교과] {selected_subject}
[선택 단원(능력단위)] {selected_unit}
[이 단원의 수행준거 요약]
{rubric_block}
{STANDARD_PROCEDURE_BLOCK}

[학생 입력 증상]
{symptom_block}

[단계 1 AI 가이드(미션)]
{guidance_block}

[학생 실습 수행 결과 / 측정 해석]
{reasoning_block}

{tone_block}

[작성 원칙 — 반드시 준수]
- ❌ '합격/불합격' 표현 금지.
- ❌ 정답을 단정하여 노출하지 말 것(필요 시 "권장 진단 방향" 정도로 표현).
- ❌ **"## ✅ 가이드 대비 수행 충실도" 섹션에서는 표(Markdown table)를 절대 사용하지 말 것.**
- ✅ **"## 🏷 카테고리 요약" 섹션은 반드시 4줄(4개 카테고리 각 1줄)로 작성한다.** 각 줄은 `• [카테고리] — [✅ 통과 | ⚠ 보완] | [코멘트 25자 이내]` 형식으로, 학생이 한눈에 '무엇을 잘했고 무엇을 놓쳤는지' 알 수 있게 한다.
- ✅ "가이드 대비 수행 충실도"는 4개의 ### 소제목(🛡️/🔍/⚡/🛠️)으로 구분하고, **각 단계는 상위 불릿 1줄 + 들여쓴 서브 불릿 2줄(💬 코멘트 / 🛠 보완)** 구조로 작성한다:
    1) 상위 불릿: `• [핵심 행동] **[측정값]** — [별점]` (별점 ★★★/★★☆/★☆☆/☆☆☆)
    2) 서브 불릿 #1: `    - 💬 코멘트: [학생 수행에서 확인된 점, 35자 이내]`
    3) 서브 불릿 #2: `    - 🛠 보완: [다음 실습에서 보완할 점, 35자 이내 또는 '-']`
- ✅ [단계 1 AI 가이드(미션)]에 포함된 각 단계에 대해 1:1로 평가한다(가이드의 단계를 모두 짚을 것).
- ✅ 규정값(예: 12.6V, 0.2V 이하, 120Ω 등)은 반드시 Markdown **굵게** 표기.
- ✅ "NCS 기준 4축 분석" 등 다른 섹션은 표(Table) 사용 가능.
- ✅ 표준 절차 (가)안전 점검 / (나)회로도 분석 / (다)시험등 vs DMM / (라)스캐너 절차(DTC→센서데이터→강제구동) 네 측면에서 강·약점을 짚는다.
- ✅ 단원 핵심 키워드(OCV 12.3~12.9V, 발전기 13.8~14.9V, 전압강하 0.2V, 종단저항 120Ω, 솔레노이드 B/ST/M, 릴레이 30/87/85/86, BCM/IPS/B-CAN, bus-off/time-out 등)를 인용해 구체화.
- ✅ [학생 입력 증상]에 [학습 질문]이 있다면, `다음 학습 미션` 섹션에서 그 질문에 직접적으로 도움이 되는 후속 실습을 제안한다.

[출력 형식 — 아래 마크다운 구조를 그대로 따른다]

## 📋 평가 한줄 요약
• (이번 실습 수행을 한 줄로 평가, 35자 이내)

## 🏷 카테고리 요약
> ⚠ 반드시 아래 4줄(4개 카테고리 각 1줄)만 작성한다. 각 줄 형식: `• [카테고리 이름] — [✅ 통과 | ⚠ 보완] | [한줄 코멘트, 25자 이내]`
> 통과 기준: 학생 수행이 가이드와 NCS 수행준거에 큰 누락 없이 부합. 보완: 누락·근거 부족·규정값 미인용 중 하나라도 해당.

• 🛡️ 준비 / 안전 — ✅ 통과 | 점화 OFF·보호구 모두 확인
• 🔍 점검 / 회로도 — ⚠ 보완 | 커넥터 핀 번호 누락
• ⚡ 측정 / 전압 — ✅ 통과 | OCV **12.45V** 규정 범위 내
• 🛠️ 판정 / 조치 — ⚠ 보완 | SOC 환산 근거 부족

## ✅ 가이드 대비 수행 충실도
> ⚠ 표 금지. 아래 4개 ### 소제목으로만 작성한다. 각 단계는 **상위 불릿 1줄 + 들여쓴 서브 불릿 2줄(💬 코멘트 / 🛠 보완)** 구조.
> 상위 불릿 형식: `• [핵심 행동] **[측정값]** — [별점]` (별점은 ★★★ / ★★☆ / ★☆☆ / ☆☆☆ 중 하나)

### 🛡️ 준비 / 안전
• 점화 OFF 확인 — ★★☆
    - 💬 코멘트: 점화 OFF 언급은 있으나 계기판 소등 확인 누락
    - 🛠 보완: 다음 실습에서 계기판 소등 시점까지 함께 기록할 것
• 절연장갑 착용 — ☆☆☆
    - 💬 코멘트: 보호구 착용 관련 기록이 전혀 없음
    - 🛠 보완: 안전 점검 단계 첫 줄에 보호구 착용 여부를 명시

### 🔍 점검 / 회로도
• 회로도 분석 — ★★★
    - 💬 코멘트: 전원→퓨즈→스위치→부하→접지 흐름이 정확히 기술됨
    - 🛠 보완: 다음 단계에서 커넥터 핀 번호까지 함께 인용하면 더 좋음
• 커넥터 핀 식별 — ★☆☆
    - 💬 코멘트: 커넥터 위치는 언급되었으나 핀 번호 매칭 부족
    - 🛠 보완: 식별도 기준 핀 번호(예: E12-3번)를 명시할 것

### ⚡ 측정 / 전압
• OCV 측정 **12.45V** — ★★★
    - 💬 코멘트: DC V 레인지 사용·규정 범위 비교 모두 충실
    - 🛠 보완: -
• 전압강하 측정 — ☆☆☆
    - 💬 코멘트: B+ 케이블 전압강하 측정이 수행 결과에 없음
    - 🛠 보완: 부하 인가 상태에서 **0.2V 이하** 여부 추가 측정 권장

### 🛠️ 판정 / 조치
• SOC 양호 판정 — ★★☆
    - 💬 코멘트: SOC 수치는 적혔으나 환산 근거(OCV→SOC) 설명 부족
    - 🛠 보완: 환산표 또는 테스터 화면 캡처와 함께 근거를 남길 것
• 단품 점검 제안 — ★★★
    - 💬 코멘트: 다음 점검 동선(CCA 부하시험) 제안이 구체적
    - 🛠 보완: -

## 🔍 NCS 기준 4축 분석
| 분석 축 | 학생 수행에서 확인된 점 | 보완 필요 |
| --- | --- | --- |
| (가) 안전 점검 | … | … |
| (나) 회로도 분석 순서 | … | … |
| (다) 계측 절차/규정값 | … | … |
| (라) 진단장비 활용(DTC→센서데이터→강제구동) | … | … |

## 🛠 보완이 필요한 능력 단위 요소
• (해당 단원의 핵심 수행준거 기준으로, 누락된 표준 절차 단계 또는 규정값 인용 부족 항목 나열)

## 🚀 다음 학습 미션
• 다음에 학생이 수행할 구체적인 측정/진단 과제(규정값·측정 포인트 포함)
• [학습 질문]에 대한 후속 실습 동선 제안

[중요]
- 위 5개 H2 섹션 헤더(##)를 정확히 그대로 사용한다(평가 한줄 요약, 🏷 카테고리 요약, ✅ 가이드 대비 수행 충실도, 🔍 NCS 기준 4축 분석, 🛠 보완이 필요한 능력 단위 요소, 🚀 다음 학습 미션).
- "🏷 카테고리 요약" 섹션은 정확히 4줄 — 🛡️ 준비 / 안전, 🔍 점검 / 회로도, ⚡ 측정 / 전압, 🛠️ 판정 / 조치 — 각 1줄씩 작성한다. 상태는 ✅ 통과 또는 ⚠ 보완 중 하나.
- "가이드 대비 수행 충실도" 섹션 안의 4개 H3 소제목(🛡️ 준비 / 안전, 🔍 점검 / 회로도, ⚡ 측정 / 전압, 🛠️ 판정 / 조치)을 정확히 그대로 사용한다. 표 금지.
- 각 단계는 위 예시처럼 반드시 3줄(타이틀 + 💬 코멘트 + 🛠 보완) 구조로 작성한다. 한 줄도 빠뜨리지 않는다.
- 규정값은 **굵게**(Markdown bold) 표기.
""".strip()


def make_thumbnail_b64(image_file: Any) -> str:
    """업로드된 사진을 작은 썸네일(JPEG, base64)로 변환해 포트폴리오 저장용으로 압축한다.

    - Google Sheets 단일 셀 한계(약 50,000자)를 넘기지 않도록 480×480 / quality 60 으로 강하게 압축.
    - PIL 사용 불가 또는 디코딩 실패 시 빈 문자열을 반환해 호출자가 안전하게 처리한다.
    """
    if image_file is None or PILImage is None:
        return ""
    try:
        raw = image_file.getvalue() if hasattr(image_file, "getvalue") else b""
        if not raw:
            return ""
        with PILImage.open(BytesIO(raw)) as im:
            im.load()
            if im.mode != "RGB":
                im = im.convert("RGB")
            im.thumbnail((480, 480), PILImage.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=60, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logger.warning("포트폴리오 썸네일 생성 실패: %s", exc)
        return ""


def thumbnail_b64_to_bytes(b64: str) -> Optional[bytes]:
    """포트폴리오 카드/PDF 임베딩용으로 base64 썸네일을 원본 바이트로 되돌린다."""
    if not b64 or not str(b64).strip():
        return None
    try:
        return base64.b64decode(str(b64).strip())
    except Exception as exc:
        logger.warning("썸네일 base64 디코딩 실패: %s", exc)
        return None




def make_step_photo_b64(image_file: Any) -> str:
    """미션 단계별 인증 사진용 초소형 JPEG base64."""
    if image_file is None or PILImage is None:
        return ""
    try:
        raw = image_file.getvalue()
        with PILImage.open(BytesIO(raw)) as im:
            im.load()
            if im.mode != "RGB":
                im = im.convert("RGB")
            im.thumbnail((360, 360), PILImage.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=50, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logger.warning("미션 단계 사진 썸네일 생성 실패: %s", exc)
        return ""


def parse_mission_step_photos(rec: dict) -> list[dict]:
    raw = (rec.get("mission_step_photos_json") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def collect_mission_step_photos_json() -> str:
    store = st.session_state.get("mission_step_photos") or {}
    items: list[dict] = []
    for slot_key in sorted(store.keys()):
        meta = store.get(slot_key) or {}
        if not isinstance(meta, dict):
            continue
        b64 = (meta.get("b64") or "").strip()
        if not b64:
            continue
        items.append(
            {
                "slot": str(slot_key)[:64],
                "category": str(meta.get("category", ""))[:32],
                "step": int(meta.get("step") or 0),
                "title": str(meta.get("title", ""))[:200],
                "b64": b64,
            }
        )
    if not items:
        return ""
    while items:
        out = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        if len(out) <= MISSION_PHOTOS_JSON_MAX_CHARS:
            return out
        items.pop()
        logger.warning(
            "mission_step_photos_json 초과 — 항목을 줄여 %d장만 저장합니다.", len(items)
        )
    return ""


def render_mission_step_photos_gallery(rec: dict) -> None:
    photos = parse_mission_step_photos(rec)
    if not photos:
        return
    st.markdown("**📷 미션 단계별 수행 사진**")
    n = min(3, len(photos))
    cols = st.columns(n if n > 0 else 1)
    for i, p in enumerate(photos):
        title = (p.get("title") or "").strip() or f"단계 {p.get('step') or i + 1}"
        cat = (p.get("category") or "").strip()
        cap = f"{cat} · {title}" if cat else title
        raw = thumbnail_b64_to_bytes((p.get("b64") or "").strip())
        with cols[i % len(cols)]:
            if raw:
                st.image(raw, caption=cap[:80], use_container_width=True)

def _prepare_image_for_gemini(image_file: Any) -> tuple[bytes, str]:
    """Gemini 호출 전 이미지를 안전한 크기로 리사이징한다.

    - 학생이 스마트폰으로 촬영한 고해상도 사진(수 MB)을 그대로 보내면 업로드/추론 단계에서
      Timeout·503 에러가 자주 발생하므로, PIL을 사용해 최대 ``GEMINI_IMAGE_MAX_SIZE`` 안으로
      축소하고 JPEG로 재인코딩해 페이로드를 줄인다.
    - PIL이 없거나 이미지 디코딩 실패 시 원본 바이트를 그대로 반환해 호출은 계속 시도한다.
    """
    raw_bytes = image_file.getvalue() if hasattr(image_file, "getvalue") else b""
    fallback_mime = getattr(image_file, "type", None) or "image/jpeg"
    if not raw_bytes:
        return b"", fallback_mime
    if PILImage is None:
        return raw_bytes, fallback_mime
    try:
        from io import BytesIO

        with PILImage.open(BytesIO(raw_bytes)) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGB")
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im.thumbnail(GEMINI_IMAGE_MAX_SIZE, PILImage.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=GEMINI_IMAGE_JPEG_QUALITY, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("이미지 리사이징 실패 — 원본 바이트로 폴백: %s", exc)
        return raw_bytes, fallback_mime


def ask_gemini(
    mode: str,
    user_symptom: str,
    student_reasoning: str,
    image_file: Optional[Any],
    key: str,
    selected_subject: str,
    selected_unit: str,
    step: str = "guidance",
    guidance_text: str = "",
) -> str:
    """Gemini 호출 진입점.

    - step="guidance" → [단계 1] AI 미션/가이드 생성 (build_learning_prompt)
    - step="evaluation" → [단계 2] 실습 수행 결과 평가 (build_evaluation_prompt)
      · guidance_text 인자로 [단계 1]의 가이드를 함께 전달해야 충실도 비교가 가능하다.
    """
    client = genai.Client(api_key=key)
    if step == "evaluation":
        prompt = build_evaluation_prompt(
            user_symptom=user_symptom,
            student_reasoning=student_reasoning,
            selected_subject=selected_subject,
            selected_unit=selected_unit,
            guidance_text=guidance_text,
            mode=mode,
        )
    else:
        prompt = build_learning_prompt(
            user_symptom=user_symptom,
            selected_subject=selected_subject,
            selected_unit=selected_unit,
            mode=mode,
        )
    parts = [types.Part.from_text(text=prompt)]
    if image_file is not None:
        image_bytes, image_mime_type = _prepare_image_for_gemini(image_file)
        if image_bytes:
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type))
    contents = [types.Content(role="user", parts=parts)]
    last_error = None
    unavailable_error_seen = False
    for model_name in GEMINI_MODEL_CANDIDATES:
        for retry_idx in range(len(GEMINI_RETRY_DELAYS_SECONDS) + 1):
            try:
                response = client.models.generate_content(model=model_name, contents=contents)
                return response.text if response and response.text else "응답을 받지 못했습니다. 다시 시도해 주세요."
            except TimeoutError as exc:
                raise RuntimeError(
                    "Gemini 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 잠시 후 다시 시도해 주세요."
                ) from exc
            except Exception as exc:
                last_error = exc
                error_text = str(exc).lower()
                if "timeout" in error_text or "timed out" in error_text or "deadline" in error_text:
                    raise RuntimeError(
                        "Gemini API 호출 중 타임아웃이 발생했습니다. 입력을 간단히 하거나 잠시 후 다시 시도해 주세요."
                    ) from exc
                if "404" in error_text or "not_found" in error_text or "is not found" in error_text:
                    break
                if "503" in error_text or "unavailable" in error_text:
                    unavailable_error_seen = True
                    if retry_idx < len(GEMINI_RETRY_DELAYS_SECONDS):
                        time.sleep(GEMINI_RETRY_DELAYS_SECONDS[retry_idx])
                        continue
                    break
                raise RuntimeError(f"Gemini API 호출 중 오류가 발생했습니다: {exc}") from exc
    if unavailable_error_seen:
        raise RuntimeError(
            "Gemini 서버가 일시적으로 혼잡합니다(503). 잠시 후 다시 시도해 주세요. "
            "무료 API의 일시적 제한일 수 있으니 1분 후 다시 시도해 주세요. "
            "문제가 반복되면 입력을 조금 줄이거나 다른 시간대에 재시도해 주세요."
        )
    raise RuntimeError(
        "현재 API 키로 사용 가능한 Gemini 모델을 찾지 못했습니다. "
        "Google AI Studio(https://aistudio.google.com/)에서 키가 활성화돼 있고 "
        "`gemini-2.0-flash` 또는 `gemini-2.5-flash` 모델 사용 권한이 있는지 확인해 주세요. "
        "1.5 라인은 단계적으로 디프리케이션되어 신규 키에서는 404가 날 수 있습니다. "
        f"(마지막 오류: {last_error})"
    )
def split_sections(result_text: str) -> dict:
    """[Legacy] 0)~5) 번호로 나뉜 옛 포맷 결과를 섹션별로 쪼갠다.

    신규 2단계 미션/평가 포맷에는 사용되지 않으며, 옛 이력(history) 데이터 호환용으로만 남긴다.
    """
    pattern = r"(?:^|\n)\s*(0\)|1\)|2\)|3\)|4\)|5\))\s*"
    parts = re.split(pattern, result_text)
    sections = {
        "0)": "영역 0",
        "1)": "영역 1",
        "2)": "영역 2",
        "3)": "영역 3",
        "4)": "영역 4",
        "5)": "영역 5",
    }
    parsed = {title: "" for title in sections.values()}
    if len(parts) < 3:
        parsed["영역 5"] = result_text.strip()
        return parsed
    for idx in range(1, len(parts), 2):
        key = parts[idx].strip()
        value = parts[idx + 1].strip() if idx + 1 < len(parts) else ""
        if key in sections:
            parsed[sections[key]] = value
    return parsed


_GUIDANCE_HEADER = "[단계 1 AI 가이드]"
_EVALUATION_HEADER = "[단계 2 실습 수행 평가]"


def compose_combined_result(guidance_text: str, evaluation_text: str) -> str:
    """history 시트에 저장할 단일 result 필드 형태로 두 단계 결과를 합친다."""
    parts: list[str] = []
    if guidance_text and guidance_text.strip():
        parts.append(f"{_GUIDANCE_HEADER}\n{guidance_text.strip()}")
    if evaluation_text and evaluation_text.strip():
        parts.append(f"{_EVALUATION_HEADER}\n{evaluation_text.strip()}")
    return "\n\n---\n\n".join(parts)


def split_combined_result(combined_text: str) -> tuple[str, str]:
    """compose_combined_result로 합쳐진 결과를 (guidance, evaluation)로 분리한다.

    옛 포맷(헤더 없음) 데이터의 경우 evaluation 한쪽으로 모아서 반환한다.
    """
    text = combined_text or ""
    if _GUIDANCE_HEADER not in text and _EVALUATION_HEADER not in text:
        return "", text.strip()
    guidance = ""
    evaluation = ""
    if _GUIDANCE_HEADER in text:
        after_g = text.split(_GUIDANCE_HEADER, 1)[1]
        if _EVALUATION_HEADER in after_g:
            guidance, _, rest = after_g.partition(_EVALUATION_HEADER)
            evaluation = rest
        else:
            guidance = after_g
    elif _EVALUATION_HEADER in text:
        evaluation = text.split(_EVALUATION_HEADER, 1)[1]
    guidance = guidance.strip().lstrip("-").strip()
    evaluation = evaluation.strip().lstrip("-").strip()
    return guidance, evaluation


def extract_evidence_snippet(text: str, keyword: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if keyword.lower() in line.lower():
            return line
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return "근거 문장을 찾지 못했습니다."
    start = max(0, idx - 35)
    end = min(len(text), idx + len(keyword) + 35)
    return text[start:end].replace("\n", " ")
def _is_legacy_numbered_format(text: str) -> bool:
    """옛 0)~5) 번호 섹션 포맷인지 확인."""
    if not text:
        return False
    if "## 🎯" in text or "## 📋" in text or "## ✅" in text:
        return False
    return bool(re.search(r"(?:^|\n)\s*[1-5]\)\s", text))


def _render_legacy_feedback(result_text: str, mode: str) -> None:
    """옛 0)~5) 포맷 이력 데이터 렌더링(과거 history 호환)."""
    parsed = split_sections(result_text)
    if mode == "학습 모드":
        titles = [
            "학습 시작 질문", "부품 명칭 추정", "고장 증상 연결",
            "우선 측정 작업", "멀티미터 측정 위치", "질문/핵심 정리",
        ]
        keys = ["영역 0", "영역 1", "영역 2", "영역 3", "영역 4", "영역 5"]
    else:
        titles = [
            "부품 명칭 추정/증상 연결", "NCS 기준 진단 분석",
            "보완이 필요한 능력 단위 요소", "우선 측정 작업",
            "멀티미터 위치/다음 실습 과제",
        ]
        keys = ["영역 1", "영역 2", "영역 3", "영역 4", "영역 5"]
    for title, key in zip(titles, keys):
        body = parsed.get(key, "") or "응답 내용 없음"
        with st.container(border=True):
            st.markdown(f"#### {title}")
            st.markdown(body)


# ─────────────────── 마크다운 가이드/평가 파서 ───────────────────
# [단계 1] AI 가이드와 [단계 2] 평가 결과는 ## H2 + ### H3 구조로 작성되므로
# 정규표현식으로 섹션과 불릿을 추출해 인터랙티브 탭/Expander UI로 재구성한다.
_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"(?m)^###\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[•\-\*])\s*(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _split_by_heading(text: str, regex: re.Pattern) -> list[tuple[str, str]]:
    matches = list(regex.finditer(text))
    if not matches:
        return []
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        out.append((header, body))
    return out


def _extract_bullets(body: str) -> list[str]:
    """기존 flat 불릿 추출 — 다른 H2 섹션(안전 주의·학습 힌트 등) 호환용으로 남겨둔다."""
    bullets: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            content = m.group(1).strip()
            if content:
                bullets.append(content)
    return bullets


# 상위 불릿(공백 0~1칸 시작) vs 서브 불릿(공백 2칸 이상 시작) 구분
_TOP_BULLET_RE = re.compile(r"^\s{0,1}[•\-\*]\s+(.*)$")
_SUB_BULLET_RE = re.compile(r"^\s{2,}[-•\*]\s+(.*)$")


def _extract_step_blocks(body: str) -> list[dict]:
    """수행 순서 / 충실도 섹션을 '상위 불릿 = 단계 타이틀' + '들여쓴 서브 불릿 = 단계 내용'으로 파싱.

    Returns: list of dicts {"title": str, "body_md": str (raw sub-bullet markdown lines), "sub": list[str]}
    """
    items: list[dict] = []
    current: Optional[dict] = None
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if current is not None:
                current["body_lines"].append("")
            continue
        top_m = _TOP_BULLET_RE.match(line)
        sub_m = _SUB_BULLET_RE.match(line)
        if top_m and not sub_m:
            current = {"title": top_m.group(1).strip(), "body_lines": [], "sub": []}
            items.append(current)
        elif current is not None:
            if sub_m:
                current["sub"].append(sub_m.group(1).strip())
            # 들여쓰기 정도와 무관하게 raw line은 body_md 원문에 보존(재현용)
            current["body_lines"].append(line.lstrip())
    return [
        {
            "title": it["title"],
            "body_md": "\n".join(f"- {s}" for s in it["sub"]).strip(),
            "sub": it["sub"],
        }
        for it in items
    ]


_CATEGORY_DEFS = [
    ("safety", "🛡️", "준비 / 안전", ["준비", "안전", "🛡"]),
    ("inspect", "🔍", "점검 / 회로도", ["점검", "회로도", "🔍"]),
    ("measure", "⚡", "측정 / 전압", ["측정", "전압", "⚡"]),
    ("judge", "🛠️", "판정 / 조치", ["판정", "조치", "🛠"]),
]


def _parse_category_summary(body: str) -> list[dict]:
    """평가 결과의 '## 🏷 카테고리 요약' 섹션 body 를 4개 카테고리 카드로 파싱.

    각 줄 형식: `• [카테고리] — [✅ 통과 | ⚠ 보완] | [코멘트]`
    """
    parsed: dict[str, dict] = {}
    if not (body or "").strip():
        return []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(">"):
            continue
        # 불릿 제거
        m = re.match(r"^[•\-\*]\s*(.+)$", line)
        if not m:
            continue
        content = m.group(1).strip()
        # `카테고리 — 상태 | 코멘트` 분해 — 'ㅡ', '—', '-' 등 다양한 대시 허용
        parts = re.split(r"\s*[—–―ㅡ-]\s*", content, maxsplit=1)
        if len(parts) < 2:
            continue
        cat_raw, rest = parts[0].strip(), parts[1].strip()
        # 상태 | 코멘트 분리
        if "|" in rest:
            status_raw, comment = [p.strip() for p in rest.split("|", 1)]
        else:
            status_raw, comment = rest, ""

        # 카테고리 식별
        cat_l = cat_raw.replace("*", "")
        key = ""
        icon = "📌"
        label = cat_raw
        for k, ic, lab, kws in _CATEGORY_DEFS:
            if any(kw in cat_l for kw in kws):
                key, icon, label = k, ic, lab
                break
        if not key:
            continue

        # 상태 판정 — ✅/통과/PASS vs ⚠/보완/FIX
        s_low = status_raw.lower()
        if "✅" in status_raw or "통과" in status_raw or "pass" in s_low or "ok" in s_low:
            status = "pass"
        elif "⚠" in status_raw or "보완" in status_raw or "fix" in s_low:
            status = "fix"
        else:
            status = "other"

        # 같은 카테고리가 중복 등장 시 가장 마지막 줄을 사용
        parsed[key] = {
            "key": key,
            "icon": icon,
            "label": label,
            "status": status,
            "comment": comment,
        }
    # 정의된 4개 카테고리 순서로 정렬해 반환
    return [parsed[k] for k, *_ in _CATEGORY_DEFS if k in parsed]


def _classify_sub_bullet(sub: str) -> tuple[str, str]:
    """서브 불릿 한 줄을 (kind, value) 로 분류.

    kind in {"method", "ncs", "record", "comment", "fix", "other"}
    """
    text = sub.strip()
    # 선두의 이모지/장식 문자를 제거하고 'key: value' 패턴을 검사한다.
    # 키워드 매칭은 한국어 라벨 기준으로 한다 (방법/NCS 준거/기록 예/코멘트/보완).
    head_strip = re.sub(r"^[\s🛠📚📝💬✅⚠⚡🔍🛡️🪛🧭🚀]+", "", text)
    m = re.match(r"^(?P<key>[^:：]{1,30})\s*[:：]\s*(?P<val>.*)$", head_strip)
    if not m:
        return ("other", text)
    key_raw = m.group("key").strip().lower()
    val = m.group("val").strip()
    if "방법" in key_raw or "how" in key_raw:
        return ("method", val)
    if "ncs" in key_raw or "준거" in key_raw:
        return ("ncs", val)
    if "기록" in key_raw or "예" == key_raw or "예시" in key_raw or "record" in key_raw:
        return ("record", val)
    if "코멘트" in key_raw or "평가" in key_raw or "comment" in key_raw:
        return ("comment", val)
    if "보완" in key_raw or "개선" in key_raw or "tip" in key_raw or "fix" in key_raw:
        return ("fix", val)
    return ("other", text)


def _classify_step_category(header: str) -> Optional[str]:
    """### 소제목을 4개 미션 카테고리(safety/inspect/measure/judge)로 분류."""
    h = header.replace("*", "")
    if "🛡" in h or "준비" in h or "안전" in h:
        return "safety"
    if "🔍" in h or "점검" in h or "회로도" in h:
        return "inspect"
    if "⚡" in h or "측정" in h or "전압" in h:
        return "measure"
    if "🛠" in h or "판정" in h or "조치" in h:
        return "judge"
    return None


def _parse_structured_markdown(text: str, steps_h2_keyword: str) -> dict:
    """공통 파서: build_learning_prompt / build_evaluation_prompt 출력 구조를 동일하게 파싱한다.

    Args:
        text: 원본 마크다운
        steps_h2_keyword: ### 단계 그룹을 가진 H2 섹션을 식별할 키워드
            (가이드는 "수행 순서", 평가는 "충실도")

    Returns dict:
        h2_sections: list[(header, body)] 원본 H2 섹션 그대로
        steps_groups: dict[category] -> list[bullet]
        has_new_format: 4개 카테고리 중 1개 이상 불릿이 있으면 True (탭 UI 사용 가능)
    """
    result = {
        "h2_sections": [],
        "steps_groups": {"safety": [], "inspect": [], "measure": [], "judge": []},
        "steps_h2_body": "",
        "has_new_format": False,
    }
    if not (text or "").strip():
        return result
    h2_sections = _split_by_heading(text, _H2_RE)
    if not h2_sections:
        return result
    result["h2_sections"] = h2_sections
    for header, body in h2_sections:
        if steps_h2_keyword in header.replace("*", ""):
            result["steps_h2_body"] = body
            for sub_header, sub_body in _split_by_heading(body, _H3_RE):
                cat = _classify_step_category(sub_header)
                if cat is None:
                    continue
                # 새 포맷: 상위 불릿 + 서브 불릿 블록을 함께 캡처
                result["steps_groups"][cat].extend(_extract_step_blocks(sub_body))
            break
    result["has_new_format"] = any(result["steps_groups"].values())
    return result


def _find_h2_body(h2_sections: list[tuple[str, str]], *keywords: str) -> str:
    for header, body in h2_sections:
        h = header.replace("*", "")
        if any(k in h for k in keywords):
            return body
    return ""


def _strip_bold(text: str) -> str:
    return _BOLD_RE.sub(r"\1", text)


def _render_regulation_badges(values: list[str]) -> None:
    if not values:
        return
    badges = " ".join(
        f'<span style="background:#fef3c7;border:1px solid #f59e0b;color:#92400e;'
        f'padding:0.28rem 0.75rem;border-radius:10px;font-weight:700;margin:0.15rem 0.3rem 0.15rem 0;'
        f'display:inline-block;font-size:1.0rem;">📐 {v}</span>'
        for v in values
    )
    st.markdown(
        f'<div style="margin:0.25rem 0 0.6rem 0;font-size:1.0rem;"><b>규정값/기준:</b> {badges}</div>',
        unsafe_allow_html=True,
    )


def _render_ncs_badge(ncs_label: str) -> None:
    """NCS 수행준거 라벨을 보라색 배지로 렌더링한다."""
    if not ncs_label:
        return
    st.markdown(
        f'<div style="margin:0.2rem 0 0.6rem 0;">'
        f'<span style="background:#ede9fe;border:1px solid #8b5cf6;color:#5b21b6;'
        f'padding:0.3rem 0.8rem;border-radius:10px;font-weight:700;font-size:1.0rem;'
        f'display:inline-block;">📚 NCS 수행준거 · {ncs_label}</span></div>',
        unsafe_allow_html=True,
    )


def _render_step_cards(steps: list[dict], icon: str, empty_msg: str = "", *, category_id: str = "step", enable_step_photos: bool = True) -> None:
    """[단계 1 미션] 진행형 Expander 카드.

    각 카드는 학생이 단계 2(실습 수행 결과 제출)를 작성하는 데 직접 도움이 되도록 다음 정보를 포함한다.
      - 🛠 측정/관찰 방법 (어떻게 수행하는가)
      - 📚 NCS 수행준거 (이 단계가 매핑되는 능력단위 요소 — 보라색 배지)
      - 📐 규정값/기준 (타이틀의 굵게 표시 값 — 노란 배지)
      - 📷 단계 수행 사진 업로드(선택)
      - 📝 기록 예 (단계 2에 그대로 붙여 넣을 한 줄 — st.code 로 복사 가능)
    """
    if not steps:
        if empty_msg:
            st.caption(empty_msg)
        return
    if enable_step_photos:
        nonce = str(st.session_state.get("diag_photo_nonce") or "run")
        st.session_state.setdefault("mission_step_photos", {})
        photos = st.session_state["mission_step_photos"]
    else:
        nonce = ""
        photos = {}
    for idx, item in enumerate(steps):
        # 새 포맷(dict) / 옛 포맷(str) 모두 호환
        if isinstance(item, str):
            title_raw, sub_lines = item, []
        else:
            title_raw = item.get("title", "")
            sub_lines = item.get("sub", []) or []

        bold_values = _BOLD_RE.findall(title_raw)
        title_clean = _strip_bold(title_raw)

        method = ncs = record = ""
        other_md_lines: list[str] = []
        for sub in sub_lines:
            kind, value = _classify_sub_bullet(sub)
            if kind == "method":
                method = value
            elif kind == "ncs":
                ncs = value
            elif kind == "record":
                record = value
            else:
                other_md_lines.append(f"- {value}")

        with st.expander(f"{icon} 단계 {idx + 1} · {title_clean}", expanded=(idx == 0)):
            _render_regulation_badges(bold_values)
            _render_ncs_badge(ncs)

            if method:
                st.markdown(f"**🛠 측정 / 관찰 방법**")
                st.markdown(f"> {method}")
            if other_md_lines:
                st.markdown("\n".join(other_md_lines))

            if record:
                st.markdown("**📝 단계 2 기록 가이드** — 아래 줄을 복사해 [실습 수행 결과] 입력란에 붙여 넣으세요:")
                # 따옴표 제거(시각상 깔끔하게)하되 측정값 굵게는 마크다운이 안 먹는 st.code 에 맞춰
                # 그대로 두는 게 학생에게는 더 직관적이다.
                copy_text = record.strip().strip('"').strip("'")
                st.code(copy_text, language="text")

            # 가이드가 비정상적으로 짧을 때(서브 불릿이 비어 있을 때)도 빈 카드는 피한다.
            if not (method or ncs or record or other_md_lines or bold_values):
                st.caption("이 단계의 상세 가이드가 비어 있어요. 다음 단계 카드를 펼쳐 진행하세요.")

            if enable_step_photos:
                slot_key = f"{category_id}_{idx}"
                st.caption(
                    "📷 이 단계에서 실제로 수행한 모습을 사진으로 남기면 포트폴리오·교사 화면·시트에 함께 저장됩니다."
                )
                up = st.file_uploader(
                    "단계 수행 사진 (선택)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"mup_{nonce}_{category_id}_{idx}",
                    label_visibility="collapsed",
                )
                if up is not None:
                    b64 = make_step_photo_b64(up)
                    if b64:
                        photos[slot_key] = {
                            "category": category_id,
                            "step": idx + 1,
                            "title": title_clean,
                            "b64": b64,
                        }
                existing = photos.get(slot_key, {}).get("b64", "")
                if existing:
                    prev = thumbnail_b64_to_bytes(existing)
                    if prev:
                        st.image(prev, width=220, caption=f"저장 예정 · {title_clean[:40]}")
                if slot_key in photos and st.button("이 단계 사진 지우기", key=f"mdel_{nonce}_{category_id}_{idx}"):
                    photos.pop(slot_key, None)
                    st.rerun()
            else:
                st.caption("📷 단계별 인증 사진은 **[📝 실습 수행]** 탭의 미션 카드에서만 등록할 수 있습니다.")


def _render_eval_step_cards(steps: list[dict], icon: str, empty_msg: str = "") -> None:
    """[단계 2 평가] 진행형 Expander 카드.

    상위 불릿 `행동 — ★★☆` + 서브 불릿(💬 코멘트 / 🛠 보완) 구조를 렌더링한다.
    """
    if not steps:
        if empty_msg:
            st.caption(empty_msg)
        return
    for idx, item in enumerate(steps):
        if isinstance(item, str):
            title_raw, sub_lines = item, []
        else:
            title_raw = item.get("title", "")
            sub_lines = item.get("sub", []) or []

        # 타이틀의 ' — ★★☆ ' 형식 분해
        parts = [p.strip() for p in title_raw.split("—")]
        action = parts[0] if parts else title_raw
        stars = parts[1] if len(parts) >= 2 else ""
        title_tail_comment = " — ".join(parts[2:]) if len(parts) >= 3 else ""

        bold_values = _BOLD_RE.findall(action)
        action_clean = _strip_bold(action)

        comment = fix = ""
        other_md_lines: list[str] = []
        for sub in sub_lines:
            kind, value = _classify_sub_bullet(sub)
            if kind == "comment":
                comment = value
            elif kind == "fix":
                fix = value
            else:
                other_md_lines.append(f"- {value}")

        header = f"{icon} {action_clean}"
        if stars:
            header += f"  ·  {stars}"
        with st.expander(header, expanded=(idx == 0)):
            _render_regulation_badges(bold_values)
            if title_tail_comment:
                st.markdown(f"💬 {title_tail_comment}")
            if comment:
                st.markdown("**💬 평가 코멘트**")
                st.markdown(f"> {comment}")
            if fix and fix != "-":
                st.markdown("**🛠 다음 실습 보완 포인트**")
                st.markdown(f"> {fix}")
            if other_md_lines:
                st.markdown("\n".join(other_md_lines))
            if not (comment or fix or other_md_lines or bold_values or title_tail_comment):
                st.caption("이 단계의 상세 평가가 비어 있어요.")


def render_mission_card(guidance_text: str, *, enable_step_photos: bool = True) -> None:
    """[단계 1] AI 미션 카드 — 3 tabs(준비/안전 · 측정 미션 · 고장 판정) + 진행형 Expander.

    레거시(H2만 있고 H3 4카테고리가 없는) 가이드는 원문 마크다운으로 폴백한다.
    """
    if not guidance_text or not guidance_text.strip():
        st.caption("아직 생성된 가이드가 없습니다.")
        return

    parsed = _parse_structured_markdown(guidance_text, steps_h2_keyword="수행 순서")
    h2_sections = parsed["h2_sections"]
    groups = parsed["steps_groups"]

    summary = _find_h2_body(h2_sections, "미션 요약")
    target = _find_h2_body(h2_sections, "점검 대상")
    tools = _find_h2_body(h2_sections, "측정 도구", "권장 측정")
    safety_notes = _find_h2_body(h2_sections, "안전 주의")
    hint = _find_h2_body(h2_sections, "학습 질문 힌트")
    photo = _find_h2_body(h2_sections, "추가 촬영")

    # ─── 미션 브리핑 배너 ───
    with st.chat_message("assistant", avatar="🧭"):
        st.markdown(
            '<div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);'
            'color:#fef3c7;padding:0.7rem 1rem;border-radius:10px;font-weight:700;'
            'letter-spacing:0.02em;margin-bottom:0.6rem;font-size:1.12rem;'
            'box-shadow:0 2px 8px rgba(15,23,42,0.25);">'
            '🤫 AI 튜터의 비밀 지령 — Mission Briefing</div>',
            unsafe_allow_html=True,
        )
        st.caption("정답은 없어. 너만의 진단 미션이지! 아래 3개 탭을 순서대로 클릭해 보자.")
        if summary:
            with st.container(border=True):
                st.markdown("#### 🎯 미션 요약")
                st.markdown(summary)

    # ─── 레거시 폴백: 새 포맷(H3 4카테고리)이 없으면 원문 마크다운 그대로 ───
    if not parsed["has_new_format"]:
        with st.container(border=True):
            st.markdown("##### 📜 가이드 원문 (이전 포맷)")
            st.markdown(guidance_text)
        return

    # ─── 3 탭 인터랙티브 UI ───
    tab_safety, tab_measure, tab_judge = st.tabs(
        ["🛡️ 준비 / 안전", "⚡ 측정 미션", "🛠️ 고장 판정"]
    )

    with tab_safety:
        if target:
            with st.container(border=True):
                st.markdown("#### 📍 점검 대상")
                st.markdown(target)
        if safety_notes:
            with st.container(border=True):
                st.markdown("#### ⚠ 안전 주의")
                st.markdown(safety_notes)
        st.markdown("##### 🛡️ 준비 / 안전 단계")
        _render_step_cards(
            groups["safety"], "🛡️",
            empty_msg="준비/안전 단계가 비어 있어요. 점화 OFF · 절연장갑 등 기본 점검을 먼저 확인하세요.",
            category_id="safety",
            enable_step_photos=enable_step_photos,
        )

    with tab_measure:
        if tools:
            with st.container(border=True):
                st.markdown("#### 🛠 권장 측정 도구")
                st.markdown(tools)
        if groups["inspect"]:
            st.markdown("##### 🔍 점검 / 회로도 단계")
            _render_step_cards(groups["inspect"], "🔍", category_id="inspect", enable_step_photos=enable_step_photos)
            st.markdown("")
        st.markdown("##### ⚡ 측정 / 전압 단계")
        _render_step_cards(
            groups["measure"], "⚡",
            empty_msg="측정 단계가 비어 있어요. 멀티미터 모드와 측정 포인트를 먼저 확인하세요.",
            category_id="measure",
            enable_step_photos=enable_step_photos,
        )

    with tab_judge:
        st.markdown("##### 🛠️ 판정 / 조치 단계")
        _render_step_cards(
            groups["judge"], "🛠️",
            empty_msg="판정 단계가 비어 있어요. 측정값을 규정값과 비교해 판정해 보세요.",
            category_id="judge",
            enable_step_photos=enable_step_photos,
        )
        if hint:
            with st.container(border=True):
                st.markdown("#### 💡 학습 질문 힌트")
                st.markdown(hint)
        if photo:
            with st.expander("📷 추가 촬영 가이드", expanded=False):
                st.markdown(photo)


def _render_category_card(item: dict) -> None:
    """카테고리 요약 한 칸 — ✅통과 / ⚠보완 + 1줄 코멘트."""
    if item["status"] == "pass":
        bg = "linear-gradient(135deg,#dcfce7 0%,#86efac 100%)"
        border = "#16a34a"
        title_color = "#14532d"
        badge_bg = "#16a34a"
        badge_text = "#ffffff"
        badge_label = "✅ 통과"
    elif item["status"] == "fix":
        bg = "linear-gradient(135deg,#fee2e2 0%,#fca5a5 100%)"
        border = "#ef4444"
        title_color = "#7f1d1d"
        badge_bg = "#ef4444"
        badge_text = "#ffffff"
        badge_label = "⚠ 보완"
    else:
        bg = "linear-gradient(135deg,#f1f5f9 0%,#cbd5e1 100%)"
        border = "#64748b"
        title_color = "#334155"
        badge_bg = "#64748b"
        badge_text = "#ffffff"
        badge_label = "ℹ 확인"

    comment_html = (item.get("comment") or "").strip() or "코멘트 없음"
    # ** ** (Markdown bold) → <b> 치환으로 카드 안에서도 굵게 보이게
    comment_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", comment_html)

    html = (
        f'<div style="background:{bg};border:2px solid {border};border-radius:14px;'
        f'padding:1rem 1.1rem;min-height:155px;display:flex;flex-direction:column;'
        f'justify-content:space-between;box-shadow:0 3px 10px rgba(15,23,42,0.08);">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:1.05rem;font-weight:800;color:{title_color};">'
        f'{item["icon"]} {item["label"]}</span>'
        f'<span style="background:{badge_bg};color:{badge_text};font-weight:800;'
        f'padding:0.35rem 0.85rem;border-radius:14px;font-size:0.95rem;letter-spacing:0.02em;">'
        f'{badge_label}</span>'
        f'</div>'
        f'<div style="margin-top:0.7rem;font-size:1.02rem;line-height:1.55;color:#0f172a;">'
        f'{comment_html}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_evaluation_card(evaluation_text: str) -> None:
    """[단계 2] 실습 수행 평가 카드 — 4개 카테고리 시각 카드 중심으로 압축.

    텍스트를 대폭 줄이고 ✅통과/⚠보완 + 1줄 코멘트만 빠르게 보이도록 한다.
    상세 충실도/4축 분석/보완 항목/다음 미션은 보조 expander로 숨긴다.
    """
    if not evaluation_text or not evaluation_text.strip():
        st.caption("아직 생성된 평가가 없습니다.")
        return

    parsed = _parse_structured_markdown(evaluation_text, steps_h2_keyword="충실도")
    h2_sections = parsed["h2_sections"]
    groups = parsed["steps_groups"]

    one_liner = _find_h2_body(h2_sections, "한줄 요약", "평가 한줄")
    cat_summary_body = _find_h2_body(h2_sections, "카테고리 요약", "🏷")
    axis_analysis = _find_h2_body(h2_sections, "4축 분석", "기준 4축")
    weak_units = _find_h2_body(h2_sections, "보완이 필요한", "보완 필요")
    next_mission = _find_h2_body(h2_sections, "다음 학습 미션", "다음 학습")

    category_items = _parse_category_summary(cat_summary_body)

    # ─── 결과 배너 + 한줄 요약 ───
    with st.chat_message("assistant", avatar="📝"):
        st.markdown(
            '<div style="background:linear-gradient(135deg,#065f46 0%,#10b981 100%);'
            'color:#ecfdf5;padding:0.7rem 1rem;border-radius:10px;font-weight:700;'
            'letter-spacing:0.02em;margin-bottom:0.6rem;font-size:1.12rem;'
            'box-shadow:0 2px 8px rgba(6,95,70,0.25);">'
            '🏆 미션 수행 평가 — 한눈에 보는 결과</div>',
            unsafe_allow_html=True,
        )
        if one_liner:
            one_liner_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", one_liner.strip())
            st.markdown(
                f'<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:10px;'
                f'padding:0.8rem 1rem;color:#064e3b;font-size:1.08rem;line-height:1.55;">'
                f'📋 <b>한줄 요약</b> — {one_liner_html}</div>',
                unsafe_allow_html=True,
            )

    # ─── 레거시 폴백 ───
    if not parsed["has_new_format"] and not category_items:
        with st.container(border=True):
            st.markdown("##### 📜 평가 원문 (이전 포맷)")
            st.markdown(evaluation_text)
        return

    # ─── 4 카테고리 시각 카드 (2x2 그리드) ───
    st.markdown("#### 🏷 카테고리별 평가 — 한눈에 보기")
    if not category_items:
        st.caption(
            "AI 응답에 '🏷 카테고리 요약' 섹션이 포함되지 않았습니다. "
            "아래 상세 충실도 섹션을 참고해 주세요."
        )
    else:
        # 통과/보완 집계 메트릭 (상단에 큼직하게)
        pass_count = sum(1 for it in category_items if it["status"] == "pass")
        fix_count = sum(1 for it in category_items if it["status"] == "fix")
        m1, m2, m3 = st.columns(3)
        m1.metric("🎯 평가 카테고리", f"{len(category_items)}개")
        m2.metric("✅ 통과", f"{pass_count}개")
        m3.metric("⚠ 보완 필요", f"{fix_count}개", delta=None)

        # 2x2 그리드 카드 배치
        rows = [category_items[i:i + 2] for i in range(0, len(category_items), 2)]
        for row in rows:
            cols = st.columns(len(row))
            for col, item in zip(cols, row):
                with col:
                    _render_category_card(item)
            st.markdown("")  # 행 사이 간격

    # ─── 상세 정보는 expander 로 숨김 ───
    has_detail = bool(
        groups["safety"] or groups["inspect"] or groups["measure"] or groups["judge"]
        or axis_analysis or weak_units or next_mission
    )
    if not has_detail:
        return

    with st.expander("🔍 상세 평가 — 단계별 충실도 / 4축 분석 / 다음 미션", expanded=False):
        if any(groups.values()):
            st.markdown("##### ✅ 가이드 대비 수행 충실도")
            cat_safety, cat_measure, cat_judge = st.tabs(
                ["🛡️ 준비 / 안전", "⚡ 측정 미션", "🛠️ 고장 판정"]
            )
            with cat_safety:
                _render_eval_step_cards(groups["safety"], "🛡️", empty_msg="해당 카테고리 평가가 없어요.")
            with cat_measure:
                if groups["inspect"]:
                    st.markdown("**🔍 점검 / 회로도**")
                    _render_eval_step_cards(groups["inspect"], "🔍")
                    st.markdown("")
                st.markdown("**⚡ 측정 / 전압**")
                _render_eval_step_cards(groups["measure"], "⚡", empty_msg="해당 카테고리 평가가 없어요.")
            with cat_judge:
                _render_eval_step_cards(groups["judge"], "🛠️", empty_msg="해당 카테고리 평가가 없어요.")
        if axis_analysis:
            with st.container(border=True):
                st.markdown("**🔍 NCS 기준 4축 분석**")
                st.markdown(axis_analysis)
        if weak_units:
            with st.container(border=True):
                st.markdown("**🛠 보완이 필요한 능력 단위 요소**")
                st.markdown(weak_units)
        if next_mission:
            with st.container(border=True):
                st.markdown("**🚀 다음 학습 미션**")
                st.markdown(next_mission)


def render_feedback_cards(result_text: str, mode: str) -> None:
    """이력/현재 결과 모두를 처리하는 통합 피드백 렌더러.

    - 신규 포맷: compose_combined_result로 합쳐진 (가이드 + 평가) 텍스트.
    - 옛 포맷: 0)~5) 번호 섹션. 이전 학생 이력 호환을 위해 레거시 렌더로 fallback.
    """
    if not result_text or not result_text.strip():
        st.caption("응답 내용 없음")
        return
    if _is_legacy_numbered_format(result_text):
        _render_legacy_feedback(result_text, mode)
        return
    guidance_text, evaluation_text = split_combined_result(result_text)
    if guidance_text:
        render_mission_card(guidance_text, enable_step_photos=False)
    if evaluation_text:
        render_evaluation_card(evaluation_text)
    if not guidance_text and not evaluation_text:
        with st.container(border=True):
            st.markdown(result_text)
def render_photo_retake_notice(result_text: str) -> None:
    lowered = result_text.lower()
    trigger_keywords = ["신뢰도 낮음", "추가 사진", "추가 촬영", "재촬영", "식별 어려움"]
    if any(keyword in lowered for keyword in trigger_keywords):
        st.info(
            "사진 식별 신뢰도가 낮은 것으로 판단되었습니다. "
            "정면/측면/후면, 근접/중간 거리, 커넥터/라벨/배선이 보이도록 다시 촬영해 업로드해 주세요."
        )
def render_photo_upload_checklist(selected_unit: Optional[str] = None) -> None:
    common_items = [
        "정면, 측면, 후면 사진을 각각 1장 이상 촬영했나요?",
        "부품 전체가 보이는 중간 거리 사진과 커넥터/라벨이 보이는 근접 사진이 있나요?",
        "그림자/역광이 심하지 않고, 손떨림 없이 초점이 맞았나요?",
        "가능하면 부품 주변 위치(엔진룸 내 상대 위치)도 함께 보이게 촬영했나요?",
    ]
    unit_items = UNIT_PHOTO_CHECKLISTS.get(selected_unit or "", [])
    with st.expander("촬영 전 체크리스트 (권장)", expanded=False):
        st.markdown("**공통 체크리스트**")
        st.markdown("\n".join(f"- {item}" for item in common_items))
        if unit_items:
            st.markdown(f"**[{selected_unit}] 단원별 체크리스트**")
            st.markdown("\n".join(f"- {item}" for item in unit_items))
        st.caption("체크리스트를 만족할수록 부품 식별 신뢰도와 측정 안내 정확도가 올라갑니다.")
def calculate_ncs_scores(
    result_text: str,
    mode: str,
    guidance_text: str = "",
    active_unit: Optional[str] = None,
) -> dict:
    """NCS 수행준거 기반 성취도 계산.

    신 포맷에서는 ``result_text``는 학생의 [단계 2] 실습 수행 결과(+ AI 평가)를 합친 텍스트이고,
    ``guidance_text``는 [단계 1]에서 AI가 제시한 가이드(미션)이다.

    가이드가 주어진 경우, '학생이 가이드를 얼마나 충실히 따라 수행했는지(faithfulness)'를 점수에 반영한다.

    - 가이드에 포함 + 학생 결과에도 포함 → 만점 가중(가이드 충실 이행)
    - 가이드에 포함 + 학생 결과 누락 → 0점(가이드 미이행, 보완 항목으로 표기)
    - 가이드 미포함 + 학생 결과에 포함 → 70% 가중(가이드 외 자율 수행 부분 인정)
    - 둘 다 미포함 → 0점

    가이드가 없는 경우(옛 포맷, 단일 단계)는 기존 키워드 매칭 방식을 유지한다.

    ``active_unit``이 ``NCS_UNITS`` 중 하나면 해당 단원만 루브릭 채점을 하고,
    나머지 단원은 완성도 0으로 둔다(한 회차 수행평가는 선택 단원에만 반영).
    비어 있거나 목록에 없으면 옛 데이터 호환을 위해 전체 단원을 채점한다.
    """
    weights = MODE_RUBRIC_WEIGHTS.get(mode, {})
    has_guidance = bool(guidance_text and guidance_text.strip())
    result_lower = (result_text or "").lower()
    guidance_lower = (guidance_text or "").lower()

    focus = (active_unit or "").strip()
    if focus not in NCS_RUBRIC:
        focus = ""

    unit_scores = []
    total_weighted_score = 0.0
    total_weighted_items = 0.0
    for unit in NCS_UNITS:
        if focus and unit != focus:
            unit_scores.append(
                {
                    "unit": unit,
                    "completion": 0.0,
                    "missing_labels": [],
                }
            )
            continue

        criteria = NCS_RUBRIC[unit]
        missing_labels: list[str] = []
        unit_weighted_score = 0.0
        unit_weight_total = 0.0
        for label, keywords in criteria:
            criterion_weight = weights.get(label, 1.0)
            unit_weight_total += criterion_weight
            in_result = any(keyword.lower() in result_lower for keyword in keywords)
            if has_guidance:
                in_guidance = any(keyword.lower() in guidance_lower for keyword in keywords)
                if in_guidance and in_result:
                    unit_weighted_score += criterion_weight
                elif in_guidance and not in_result:
                    missing_labels.append(f"{label} (가이드 미이행)")
                elif in_result:
                    unit_weighted_score += criterion_weight * 0.7
                else:
                    missing_labels.append(label)
            else:
                if in_result:
                    unit_weighted_score += criterion_weight
                else:
                    missing_labels.append(label)
        completion = unit_weighted_score / unit_weight_total if unit_weight_total else 0.0
        completion = max(0.0, min(1.0, completion))
        unit_scores.append(
            {
                "unit": unit,
                "completion": completion,
                "missing_labels": missing_labels,
            }
        )
        total_weighted_score += unit_weighted_score
        total_weighted_items += unit_weight_total
    overall_rate = (total_weighted_score / total_weighted_items) * 100 if total_weighted_items else 0.0
    overall_rate = max(0.0, min(100.0, overall_rate))
    return {
        "overall_rate": overall_rate,
        "unit_scores": unit_scores,
        "guidance_aware": has_guidance,
    }
def build_pdf_bytes(
    generated_at: str,
    mode: str,
    symptom: str,
    result_text: str,
    ncs_score: float,
    subject: str,
    unit: str,
    student_id: str,
    execution_result: str = "",
) -> bytes:
    if FPDF is None:
        raise RuntimeError("fpdf2 라이브러리가 필요합니다.")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    font_path = Path(__file__).resolve().parent / "malgun.ttf"
    try:
        if font_path.exists():
            pdf.add_font("Malgun", "", str(font_path))
            pdf.set_font("Malgun", size=12)
        else:
            pdf.set_font("Helvetica", size=12)
    except Exception:
        pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "자동차 전기전자제어 진단 결과 리포트 (학생 포트폴리오)")
    pdf.ln(2)
    pdf.multi_cell(0, 8, f"학생 ID/이름: {student_id}")
    pdf.multi_cell(0, 8, f"교과: {subject}")
    pdf.multi_cell(0, 8, f"단원: {unit}")
    pdf.multi_cell(0, 8, f"진단 일시: {generated_at}")
    pdf.multi_cell(0, 8, f"선택 모드: {mode}")
    pdf.multi_cell(0, 8, f"NCS 성취도 점수: {ncs_score:.1f}%")
    pdf.ln(2)
    pdf.multi_cell(0, 8, "[입력 증상]")
    pdf.multi_cell(0, 8, symptom if symptom else "사진 기반 진단(텍스트 입력 없음)")
    pdf.ln(2)
    guidance_text, evaluation_text = split_combined_result(result_text)
    if not guidance_text and not evaluation_text and result_text:
        evaluation_text = result_text
    if guidance_text:
        pdf.multi_cell(0, 8, "[단계 1 — AI 진단 가이드(미션)]")
        pdf.multi_cell(0, 8, guidance_text)
        pdf.ln(2)
    if execution_result and execution_result.strip():
        pdf.multi_cell(0, 8, "[단계 2 — 학생 실습 수행 결과]")
        pdf.multi_cell(0, 8, execution_result.strip())
        pdf.ln(2)
    if evaluation_text:
        pdf.multi_cell(0, 8, "[단계 2 — 실습 수행 평가]")
        pdf.multi_cell(0, 8, evaluation_text)
        pdf.ln(2)
    return bytes(pdf.output(dest="S"))


def build_comprehensive_portfolio_pdf(
    student_id: str,
    student_name: str,
    records: list[dict],
) -> bytes:
    """학기 전체 실습 기록을 한 권의 '나의 성장 일지' PDF로 묶는다.

    - 표지: 따뜻한 타이틀(나의 성장 일지) + 학생 정보 + 누적 실습 건수
    - 본문: 실습별로 ① 메타정보 → ② 수행 내용(입력) → ③ AI 코칭 요약 → ④ 나의 소감 → ⑤ 첨부 사진
    - 실습 사이에는 가로 구분선을 그어 '기록의 흐름'이 보이도록 한다.
    - 한글 출력을 위해 같은 폴더의 ``malgun.ttf`` 폰트를 사용한다.
    """
    if FPDF is None:
        raise RuntimeError("fpdf2 라이브러리가 필요합니다.")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    font_path = Path(__file__).resolve().parent / "malgun.ttf"
    has_korean_font = False
    try:
        if font_path.exists():
            pdf.add_font("Malgun", "", str(font_path))
            has_korean_font = True
    except Exception:
        has_korean_font = False

    def _set_font(size: int, bold: bool = False) -> None:
        # fpdf2 의 한글 TTF 는 굵게 흉내가 어렵기 때문에 크기로 위계를 표현한다.
        if has_korean_font:
            pdf.set_font("Malgun", size=size)
        else:
            pdf.set_font("Helvetica", style="B" if bold else "", size=size)

    def _safe_text(s: str) -> str:
        """Malgun TTF 가 처리하지 못하는 일부 이모지/기타 BMP 외 문자를 안전한 기호로 치환.

        - 'Not enough horizontal space' 류의 오류가 폰트 글리프 결손에서 비롯되는 경우를
          미리 방지한다. (▶ 등 ASCII/한자 권역의 안전한 대체 문자로 변환)
        """
        if not s:
            return ""
        replacements = {
            "📓": "[일지]", "📅": "[날짜]", "🔍": "[수행]", "🧭": "[가이드]",
            "🧪": "[측정]", "📝": "[소감]", "📷": "[사진]", "🏆": "[평가]",
            "🗒": "[피드백]", "🎯": "[성취]", "🛡️": "[안전]", "📐": "[회로]",
            "⚡": "[전기]", "🛠️": "[조치]", "📡": "[진단장비]", "📶": "[통신]",
            "🔋": "[배터리]", "💡": "[조명]", "🚗": "[차량]",
        }
        out = s
        for k, v in replacements.items():
            out = out.replace(k, v)
        # Malgun 등 TTF 에 글리프가 없는 서로게이트 평면 문자 제거(남은 이모지 등)
        out = "".join(ch for ch in out if ord(ch) < 0x10000)
        return out

    def _section_label(label: str) -> None:
        """섹션 라벨을 컬러 배지처럼 강조한다.

        ``cell()`` 은 한 줄 너비 초과 시 'Not enough horizontal space' 를 던질 수 있어
        반드시 ``multi_cell()`` 로 자동 줄바꿈을 보장한다.
        """
        pdf.set_x(pdf.l_margin)
        _set_font(12, bold=True)
        pdf.set_fill_color(241, 245, 249)  # slate-100
        pdf.set_text_color(15, 23, 42)      # slate-900
        pdf.multi_cell(0, 8, _safe_text(label), fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_x(pdf.l_margin)
        pdf.ln(1)

    def _write_block(label: str, body: str, *, allow_empty_caption: bool = True) -> None:
        body_text = _safe_text((body or "").strip())
        _section_label(label)
        pdf.set_x(pdf.l_margin)
        _set_font(11)
        if body_text:
            # 폭 0 = 우측 마진까지 사용 → 페이지 너비에 맞춰 자동 줄바꿈
            pdf.multi_cell(0, 8, body_text)
        elif allow_empty_caption:
            pdf.set_text_color(120, 120, 120)
            pdf.multi_cell(0, 8, "(내용 없음)")
            pdf.set_text_color(0, 0, 0)
        pdf.set_x(pdf.l_margin)
        pdf.ln(2)

    def _draw_divider() -> None:
        """실습 기록 사이의 구분선 — '기록의 흐름'이 보이도록."""
        pdf.ln(3)
        pdf.set_draw_color(203, 213, 225)  # slate-300
        y = pdf.get_y()
        # 좌/우 마진을 고려해 페이지 폭에 맞게 그린다.
        left_x = pdf.l_margin
        right_x = pdf.w - pdf.r_margin
        pdf.line(left_x, y, right_x, y)
        pdf.set_draw_color(0, 0, 0)
        pdf.ln(4)

    def _embed_image_from_b64(b64: str) -> None:
        """썸네일 base64 를 PDF 에 이미지로 임베딩한다 (페이지 폭 안전).

        - fpdf2 는 image() 후 커서 x 가 이미지 오른쪽에 머물 수 있어, 다음 multi_cell(0)의
          '사용 가능 폭'이 0에 가까워지며 Not enough horizontal space 오류가 난다.
        - 항상 왼쪽 여백에서 그린 뒤 x 를 l_margin 으로 되돌린다.
        """
        img_bytes = thumbnail_b64_to_bytes(b64)
        if not img_bytes or PILImage is None:
            return
        try:
            pdf.set_x(pdf.l_margin)
            with PILImage.open(BytesIO(img_bytes)) as im:
                im.load()
                if im.mode != "RGB":
                    im = im.convert("RGB")
                content_w = pdf.w - pdf.l_margin - pdf.r_margin
                target_w = min(90.0, max(24.0, content_w * 0.72))
                pdf.image(im, x=pdf.l_margin, w=target_w)
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)
        except Exception as exc:
            logger.warning("PDF 이미지 임베딩 실패: %s", exc)

    # ─────────── 표지 ───────────
    pdf.add_page()
    pdf.ln(22)
    _set_font(22, bold=True)
    pdf.set_text_color(7, 89, 133)  # sky-800
    pdf.multi_cell(0, 14, "나의 성장 일지")
    pdf.set_text_color(0, 0, 0)
    _set_font(13)
    pdf.multi_cell(0, 9, "Growth Journal — 자동차 전기전자제어 실습 포트폴리오")
    pdf.ln(8)
    _set_font(13)
    pdf.multi_cell(0, 9, f"학생 성명: {student_name or '-'}")
    pdf.multi_cell(0, 9, f"학번: {student_id or '-'}")
    pdf.multi_cell(0, 9, f"누적 실습 건수: {len(records)}건")
    pdf.multi_cell(0, 9, f"발행일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(8)
    _set_font(11)
    pdf.set_text_color(71, 85, 105)  # slate-600
    pdf.multi_cell(
        0,
        7,
        "본 일지는 NCS '자동차 전기전자제어' 능력단위 기반 실습 기록을 시간 순으로 묶은 학습 결과물입니다. "
        "각 실습 단원의 수행 내용·AI 코칭 요약·실습 소감·첨부 사진을 한 권에 모아 학기 동안의 성장을 보여 줍니다.",
    )
    pdf.set_text_color(0, 0, 0)

    # ─────────── 본문: 실습별 페이지 ───────────
    if not records:
        pdf.add_page()
        _set_font(12)
        pdf.multi_cell(0, 8, "아직 등록된 실습 기록이 없습니다.")
        return bytes(pdf.output(dest="S"))

    sorted_records = sorted(records, key=lambda r: r.get("submitted_at") or "")
    total = len(sorted_records)
    for idx, rec in enumerate(sorted_records, start=1):
        pdf.add_page()
        guidance_text, evaluation_text = split_combined_result(rec.get("result") or "")

        # NCS 성취도(이 회차 단일) 계산 — PDF 헤더에 노출
        try:
            ncs_data = calculate_ncs_scores(
                evaluation_text or rec.get("reasoning") or "",
                rec.get("mode") or "학습 모드",
                guidance_text=guidance_text,
                active_unit=rec.get("unit") or None,
            )
            overall_rate = float(ncs_data.get("overall_rate") or 0.0)
        except Exception:
            overall_rate = 0.0

        # 실습 #N — 진한 컬러 헤더
        _set_font(16, bold=True)
        pdf.set_text_color(124, 45, 18)  # orange-900
        pdf.multi_cell(0, 11, _safe_text(f"📓 실습 #{idx} / {total}"))
        pdf.set_text_color(0, 0, 0)
        _set_font(11)
        # 메타 정보 — 모두 multi_cell 로 안전하게 출력
        pdf.multi_cell(0, 8, _safe_text(f"진단 일시: {rec.get('submitted_at') or '-'}"))
        pdf.multi_cell(
            0, 8,
            _safe_text(f"교과 · 단원: {rec.get('subject') or '-'}  >  {rec.get('unit') or '-'}"),
        )
        pdf.multi_cell(0, 8, _safe_text(f"학습 모드: {rec.get('mode') or '학습 모드'}"))
        pdf.multi_cell(0, 8, _safe_text(f"NCS 성취도(이 회차): {overall_rate:.0f} / 100"))
        pdf.ln(2)
        pdf.set_x(pdf.l_margin)

        # ① 수행 내용 — 학생 입력
        _write_block("🔍 수행 내용 (대상 / 상태 / 학습 질문)", rec.get("symptom") or "")

        # ② AI 코칭 — 가이드 요약
        guide_short = (guidance_text or "").strip()
        if guide_short and len(guide_short) > 1500:
            guide_short = guide_short[:1500] + " …"
        _write_block(
            "🧭 AI 코칭 — 미션 가이드 요약",
            guide_short or "(AI 가이드 텍스트가 저장되지 않았습니다.)",
        )

        # ③ 수행 결과 — 학생이 직접 입력한 측정/판정 요약
        _write_block("🧪 실습 수행 결과", rec.get("reasoning") or "")

        # ④ AI 평가 — 회차별 평가 카드 텍스트 요약
        eval_short = (evaluation_text or "").strip()
        if eval_short and len(eval_short) > 1500:
            eval_short = eval_short[:1500] + " …"
        _write_block(
            "🏆 AI 평가 — 수행 평가 요약",
            eval_short or "(AI 평가 텍스트가 저장되지 않았습니다.)",
        )

        # ⑤ 나의 소감
        _write_block(
            "📝 나의 소감",
            rec.get("reflection") or "",
        )

        # ⑥ 첨부 사진 (있을 때만)
        image_b64 = (rec.get("image_b64") or "").strip()
        if image_b64:
            _section_label("📷 1단계 입력 시 첨부 사진")
            _embed_image_from_b64(image_b64)

        mphotos = parse_mission_step_photos(rec)
        if mphotos:
            _section_label("📷 미션 단계별 수행 사진")
            for mp in mphotos:
                cap = (mp.get("title") or "").strip() or f"단계 {mp.get('step')}"
                cat = (mp.get("category") or "").strip()
                pdf.set_x(pdf.l_margin)
                if cat:
                    _set_font(10)
                    pdf.multi_cell(0, 6, _safe_text(f"· [{cat}] {cap}"))
                bb = (mp.get("b64") or "").strip()
                if bb:
                    _embed_image_from_b64(bb)

        # 교사 피드백 (있을 때만)
        tf = (rec.get("teacher_feedback") or "").strip()
        if tf:
            _write_block("🗒 교사 피드백", tf)

        # 다음 실습과 시각적으로 분리
        if idx < total:
            _draw_divider()

    return bytes(pdf.output(dest="S"))


def _criterion_icon(idx: int, label: str) -> str:
    """단원 내 수행준거 라벨에 어울리는 직관적인 이모지를 자동 매핑한다."""
    L = label
    if any(k in L for k in ("안전", "전원", "차단", "보호")):
        return "🛡️"
    if any(k in L for k in ("회로도", "기호", "분석")):
        return "📐"
    if any(k in L for k in ("측정", "OCV", "전압", "강하", "파형", "신호")):
        return "⚡"
    if any(k in L for k in ("판정", "교체", "조치", "SOC", "CCA", "교환")):
        return "🛠️"
    if any(k in L for k in ("외관", "확인", "예비")):
        return "🔍"
    if any(k in L for k in ("스캐너", "DTC", "강제구동", "진단장비")):
        return "📡"
    if any(k in L for k in ("통신", "CAN", "LIN", "게이트웨이", "종단", "프로토콜")):
        return "📶"
    if "암전류" in L:
        return "🔋"
    return ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][idx % 4]


def calculate_single_unit_criteria(
    unit_name: str,
    result_text: str,
    guidance_text: str = "",
    mode: str = "학습 모드",
) -> list[dict]:
    """단일 단원의 4개 수행준거별 달성률(0~1)과 매칭 키워드를 계산한다.

    - 가이드(미션)에 키워드가 있고 학생 결과에도 있으면 100% (가이드 이행)
    - 가이드에는 있으나 학생 결과 누락이면 0% (보완 필요)
    - 가이드 외 학생이 자율 언급이면 70% (자율 수행 인정)
    - 둘 다 없으면 0%
    """
    criteria = NCS_RUBRIC.get(unit_name, [])
    weights = MODE_RUBRIC_WEIGHTS.get(mode, {})
    has_guidance = bool(guidance_text and guidance_text.strip())
    result_lower = (result_text or "").lower()
    guidance_lower = (guidance_text or "").lower()

    rows: list[dict] = []
    for label, keywords in criteria:
        weight = weights.get(label, 1.0)
        matched_in_result = [kw for kw in keywords if kw.lower() in result_lower]
        matched_in_guidance = [kw for kw in keywords if kw.lower() in guidance_lower]
        if has_guidance:
            in_g = bool(matched_in_guidance)
            in_r = bool(matched_in_result)
            if in_g and in_r:
                completion, status = 1.0, "good"
            elif in_g and not in_r:
                completion, status = 0.0, "guide-missed"
            elif in_r:
                completion, status = 0.7, "self"
            else:
                completion, status = 0.0, "absent"
        else:
            in_r = bool(matched_in_result)
            completion = 1.0 if in_r else 0.0
            status = "good" if in_r else "absent"
        rows.append(
            {
                "label": label,
                "completion": completion,
                "weight": weight,
                "matched_keywords": matched_in_result[:3],
                "example_keywords": keywords[:4],
                "status": status,
            }
        )
    return rows


def _render_criterion_progress(idx: int, row: dict) -> None:
    """단일 수행준거의 큰 진행 카드 — 아이콘 + 라벨 + 상태 배지 + 굵은 progress bar."""
    icon = _criterion_icon(idx, row["label"])
    comp = float(row["completion"])
    pct = int(round(comp * 100))
    if comp >= 0.8:
        badge_bg = "#16a34a"
        badge_text = "#ffffff"
        badge_label = "✅ 충족"
    elif comp >= 0.4:
        badge_bg = "#f59e0b"
        badge_text = "#7c2d12"
        badge_label = "🟡 부분 충족"
    else:
        badge_bg = "#ef4444"
        badge_text = "#ffffff"
        badge_label = "⚠️ 보완 필요"

    with st.container(border=True):
        head_html = (
            '<div style="display:flex;align-items:center;justify-content:space-between;'
            'margin-bottom:0.4rem;">'
            f'<span style="font-size:1.18rem;font-weight:800;color:#0f172a;">'
            f'{icon} 준거 {idx + 1}. {row["label"]}</span>'
            f'<span style="background:{badge_bg};color:{badge_text};font-weight:800;'
            f'padding:0.35rem 0.85rem;border-radius:14px;font-size:0.95rem;">{badge_label}</span>'
            '</div>'
        )
        st.markdown(head_html, unsafe_allow_html=True)
        st.progress(comp, text=f"{pct}% 달성")
        if row["matched_keywords"]:
            kws = ", ".join(f"`{k}`" for k in row["matched_keywords"])
            st.markdown(
                f'<div style="color:#14532d;font-size:0.98rem;margin-top:0.35rem;">'
                f'✅ 내 결과에서 확인된 키워드 — {kws}</div>',
                unsafe_allow_html=True,
            )
        else:
            examples = ", ".join(f"`{k}`" for k in row["example_keywords"])
            st.markdown(
                f'<div style="color:#7f1d1d;font-size:0.98rem;margin-top:0.35rem;">'
                f'⚠️ 관련 키워드를 찾지 못했어요. 다음 실습에서는 {examples} 같은 표현을 결과에 포함해 보세요.</div>',
                unsafe_allow_html=True,
            )


def render_ncs_achievement(
    result_text: str,
    mode: str,
    guidance_text: str = "",
    unit_name: str = "",
) -> None:
    """오늘 수행한 단일 단원에 집중한 성취도 화면.

    기존의 '모든 단원 평균 + 레이더 차트' UI 대신, 학생이 방금 끝낸 단원의
    4가지 세부 수행준거를 개별 progress 카드로 큼직하게 노출한다.
    """
    if not result_text or not result_text.strip():
        st.caption("아직 분석할 결과가 없습니다. 먼저 [단계 2] 실습 수행 결과를 제출해 주세요.")
        return

    unit_name = (unit_name or st.session_state.get("latest_unit") or "").strip()
    if not unit_name or unit_name not in NCS_RUBRIC:
        st.warning("최근 수행한 단원 정보를 찾을 수 없어 분석할 수 없습니다.")
        return

    icon = UNIT_ICONS.get(unit_name, "📘")
    rows = calculate_single_unit_criteria(unit_name, result_text, guidance_text, mode)
    if not rows:
        st.warning(f"'{unit_name}' 단원의 수행준거 정보가 없어 분석할 수 없습니다.")
        return

    # 가중 합산 성취율
    total_weight = sum(r["weight"] for r in rows) or 1.0
    overall = sum(r["completion"] * r["weight"] for r in rows) / total_weight * 100
    good_count = sum(1 for r in rows if r["completion"] >= 0.8)
    fix_count = sum(1 for r in rows if r["completion"] < 0.4)

    # ─── 헤더 ───
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#1e3a8a 0%,#3b82f6 100%);'
        f'color:#eff6ff;padding:1.1rem 1.3rem;border-radius:14px;'
        f'box-shadow:0 4px 14px rgba(30,58,138,0.25);margin-bottom:1rem;">'
        f'<div style="font-size:1.45rem;font-weight:800;letter-spacing:-0.01em;">'
        f'{icon} 오늘의 단원 · {unit_name}</div>'
        f'<div style="font-size:1.0rem;color:#dbeafe;margin-top:0.35rem;">'
        f'오늘 진행한 실습에서 이 단원의 세부 수행준거를 얼마나 충족했는지 한눈에 확인하세요.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ─── 한눈에 보이는 핵심 메트릭 ───
    m1, m2, m3 = st.columns(3)
    m1.metric("🎯 오늘의 단원 성취율", f"{overall:.0f}%")
    m2.metric("✅ 충족한 준거", f"{good_count} / {len(rows)}")
    m3.metric("⚠ 보완 필요", f"{fix_count}개")

    if guidance_text and guidance_text.strip():
        st.caption("ℹ️ 가이드 충실도 가중치가 반영된 성취율입니다 (가이드 이행=100%, 자율 수행=70%).")

    # ─── 4개 수행준거별 진행 카드 ───
    st.markdown(f"#### 📋 세부 수행준거 4가지 — {unit_name}")
    for idx, row in enumerate(rows):
        _render_criterion_progress(idx, row)

    # ─── 가벼운 학습 동선 안내 ───
    weak_rows = [r for r in rows if r["completion"] < 0.4]
    if weak_rows:
        with st.container(border=True):
            st.markdown("##### 🚀 다음 실습 동선 제안")
            for r in weak_rows[:2]:
                examples = ", ".join(f"`{k}`" for k in r["example_keywords"][:3])
                st.markdown(f"- **{r['label']}** — 결과에 {examples} 등의 표현을 포함해 보세요.")
    elif good_count == len(rows):
        st.success("🎉 오늘 실습의 핵심 수행준거가 모두 잘 반영되었습니다. 멋진 하루였어요!")
def gs_app_sheets_ready() -> bool:
    """Secrets 에 [connections.gsheets] 섹션이 있는지 + 실제 연결이 생성되는지 확인한다.

    - 실패해도 사용자에게는 부드러운 안내만 하고, 구체적 원인(시트 URL / `type='service_account'` 등)은
      `st.warning` 및 로그로 함께 남겨 운영자가 바로 원인 파악할 수 있도록 한다.
    - 상세 경고 메시지는 세션 내 한 번만 표시되도록 중복 출력을 피한다.
    """

    def _warn_once(msg: str) -> None:
        logger.warning("gs_app_sheets_ready: %s", msg)
        shown = st.session_state.setdefault("_gsheets_warned_msgs", set())
        if msg in shown:
            return
        shown.add(msg)
        st.warning(msg)

    if not shb.gsheets_available():
        _warn_once(
            "Google Sheets 연동 라이브러리(`st-gsheets-connection`) 가 아직 로드되지 않았습니다. "
            "`requirements.txt` 에 해당 패키지가 포함되어 있는지, Streamlit Cloud 에서 앱이 Reboot 되었는지 확인해 주세요."
        )
        return False

    try:
        gs_secrets = st.secrets["connections"]["gsheets"]
    except Exception:
        _warn_once(
            "Secrets 에 `[connections.gsheets]` 섹션이 보이지 않습니다. "
            "Streamlit Cloud **Manage app → Settings → Secrets** 에 해당 섹션을 추가해 주세요. "
            "(시트 URL(`spreadsheet`) 과 `type = \"service_account\"` 를 포함한 서비스 계정 JSON 필드가 필요합니다.)"
        )
        return False

    def _get(k: str) -> str:
        try:
            v = gs_secrets.get(k) if hasattr(gs_secrets, "get") else gs_secrets[k]
        except Exception:
            v = None
        return str(v or "").strip()

    spreadsheet = _get("spreadsheet")
    sec_type = _get("type")
    if not spreadsheet:
        _warn_once(
            "`[connections.gsheets]` 의 `spreadsheet` 값이 비어 있습니다. "
            "대상 Google Sheets 의 전체 URL을 넣어주세요. "
            "(예: `spreadsheet = \"https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit\"`)"
        )
    if sec_type != "service_account":
        _warn_once(
            "`[connections.gsheets].type` 이 `\"service_account\"` 가 아닙니다. "
            "현재 값: "
            + (f"`{sec_type}`" if sec_type else "(없음)")
            + ". 서비스 계정 JSON 을 사용하려면 `type = \"service_account\"` 로 설정해야 합니다."
        )

    try:
        shb.get_gsheets_connection()
    except Exception as exc:
        logger.exception("get_gsheets_connection() raised")
        _warn_once(
            f"Google Sheets 연결 초기화 실패: {exc}. "
            "시트 URL이 올바른지, 서비스 계정 이메일(`client_email`) 에 편집자 권한으로 공유했는지, "
            "`private_key` 가 여러 줄 그대로 보존됐는지(`\"\"\"...\"\"\"` 권장) 확인해 주세요."
        )
        return False

    return True


def get_diagnostic_records() -> list[dict]:
    """history 시트 기준 진단 기록 (세션 캐시 TTL 내 재사용)."""
    if not gs_app_sheets_ready():
        return []
    try:
        return shb.history_df_to_records(shb.read_history_df())
    except Exception as exc:
        st.session_state["_gsheets_read_error"] = str(exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 학생 누적 이력(History) 영속성 보장 헬퍼
#
# 핵심 원칙:
#   1) 학생이 로그인하면 즉시 `force_fetch_student_history` 로 시트를 강제 재읽기
#      → `_gs_history_df` 세션 캐시를 무효화하고 최신 상태를 가져온다.
#   2) 학번 비교는 항상 `str(...).strip()` 으로 정규화하여 int/str 추론 차이로
#      필터가 누락되는 사고를 막는다.
#   3) 조회 결과는 `st.session_state["my_history_records"]` 에 보관해 포트폴리오,
#      대시보드, 사이드바 카운트가 동일한 단일 출처(single source of truth)를 본다.
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_sid(student_id: Any) -> str:
    """학번 비교용 표준화: 항상 trim 된 문자열로 통일."""
    return str(student_id or "").strip()


def force_fetch_student_history(student_id: Any) -> list[dict]:
    """시트 캐시를 무효화하고 해당 student_id 의 모든 누적 기록을 다시 읽어 반환.

    실패 시에도 예외를 위로 던지지 않고 빈 리스트를 반환해 UI 흐름을 끊지 않는다.
    상세 원인은 logger.exception 으로 콘솔에 남긴다.
    """
    sid = _normalize_sid(student_id)
    if not sid:
        return []
    if not gs_app_sheets_ready():
        logger.warning("force_fetch_student_history: Google Sheets 미연결 → 빈 결과 반환 (sid=%s)", sid)
        return []
    try:
        records = shb.filter_history_records_by_student(sid)
    except Exception as exc:
        logger.exception("force_fetch_student_history 실패 (sid=%s): %s", sid, exc)
        st.session_state["_gsheets_read_error"] = str(exc)
        return []
    return records


def refresh_my_history_cache() -> list[dict]:
    """현재 로그인 학생의 누적 기록을 강제로 새로 읽어 세션 캐시에 반영."""
    sid = _normalize_sid(st.session_state.get("student_id"))
    if not sid:
        st.session_state["my_history_records"] = []
        return []
    records = force_fetch_student_history(sid)
    st.session_state["my_history_records"] = records
    return records


def _get_gsheets_secrets_summary() -> dict:
    """Secrets 의 [connections.gsheets] 섹션 상태를 비밀번호 노출 없이 요약 반환."""
    summary = {
        "has_section": False,
        "type": "(없음)",
        "spreadsheet": "(없음)",
        "client_email": "(없음)",
    }
    try:
        gs = st.secrets["connections"]["gsheets"]
    except Exception:
        return summary
    summary["has_section"] = True

    def _g(k: str) -> str:
        try:
            v = gs.get(k) if hasattr(gs, "get") else gs[k]
        except Exception:
            v = None
        return str(v or "").strip() or "(없음)"

    summary["type"] = _g("type")
    sp = _g("spreadsheet")
    # URL 은 너무 길어 우측 끝 일부만 노출
    if sp != "(없음)" and len(sp) > 64:
        summary["spreadsheet"] = sp[:24] + "…" + sp[-24:]
    else:
        summary["spreadsheet"] = sp
    summary["client_email"] = _g("client_email")
    return summary


def run_sheet_write_smoke_test() -> dict:
    """history 시트에 'heartbeat' 행을 1줄 써 보고 즉시 다시 읽어 검증한다.

    UI 에서 '🧪 시트 쓰기 테스트' 버튼을 누르면 호출된다. 실제 학습 데이터는 건들지
    않고, ``student_id="__diag__"``, ``mode="diagnostic"`` 으로 식별 가능한 더미 행만
    추가해 누적 통계에 영향이 없도록 한다.

    Returns
    -------
    dict { "ok": bool, "error": str|None, "round_trip_seconds": float, "row": dict }
    """
    started = time.time()
    test_record_id = str(uuid.uuid4())
    heartbeat_record = {
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "student_id": "__diag__",
        "student_display_name": "diag-bot",
        "subject": "자동차 전기전자제어",
        "unit": "(쓰기 테스트)",
        "result": "[diag] heartbeat OK",
        "mode": "diagnostic",
        "record_id": test_record_id,
        "symptom": "(쓰기 테스트)",
        "reasoning": "(쓰기 테스트)",
        "reflection": "(쓰기 테스트)",
        "image_b64": "",
        "mission_step_photos_json": "",
    }
    try:
        shb.append_history_from_record(heartbeat_record, 0.0)
    except Exception as exc:
        logger.exception("[DIAG] 시트 쓰기 테스트 실패: %s", exc)
        return {"ok": False, "error": str(exc), "round_trip_seconds": time.time() - started, "row": {}}

    # 캐시 무효화 후 즉시 다시 읽어 round-trip 검증
    try:
        shb.invalidate_all_sheet_caches()
        df = shb.force_refresh_history()
        rows = df[df["record_id"].astype(str).str.strip() == test_record_id].to_dict("records")
        if not rows:
            return {
                "ok": False,
                "error": "쓰기는 성공했으나 다시 읽기에서 해당 record_id 를 찾지 못했습니다. (캐시/권한 문제 가능)",
                "round_trip_seconds": time.time() - started,
                "row": {},
            }
        return {"ok": True, "error": None, "round_trip_seconds": time.time() - started, "row": rows[0]}
    except Exception as exc:
        logger.exception("[DIAG] 시트 쓰기 테스트 검증 단계 실패: %s", exc)
        return {"ok": False, "error": f"쓰기 후 검증 실패: {exc}", "round_trip_seconds": time.time() - started, "row": {}}


def render_db_diagnostic_panel() -> None:
    """사이드바에 노출되는 '🔧 DB 저장 상태' 진단 패널.

    학생/교사 누구나 클릭해서:
      - 현재 Google Sheets 연결 모드(service_account 여부)
      - 직전 저장 시도 결과(성공/실패/오류 메시지)
      - '🧪 시트 쓰기 테스트' 로 즉시 round-trip 검증
    을 확인할 수 있다.
    """
    with st.expander("🔧 DB 저장 상태", expanded=False):
        ready = gs_app_sheets_ready()
        summary = _get_gsheets_secrets_summary()
        if ready and summary["type"] == "service_account":
            st.markdown(
                '<div style="background:#dcfce7;border:1px solid #22c55e;color:#14532d;'
                'padding:0.45rem 0.7rem;border-radius:8px;font-size:0.85rem;">'
                '✅ 쓰기 가능 모드 — service_account 자격증명이 적용되어 있습니다.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="background:#fee2e2;border:1px solid #ef4444;color:#7f1d1d;'
                'padding:0.45rem 0.7rem;border-radius:8px;font-size:0.85rem;">'
                '⚠ 쓰기 불가 모드 — Secrets 의 <code>type</code> 가 '
                "<b>service_account</b> 가 아닙니다. 이 상태에서는 학습 결과가 "
                "시트에 저장되지 않습니다.</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            f"🔑 type: `{summary['type']}` · 📄 spreadsheet: `{summary['spreadsheet']}` · "
            f"✉ client_email: `{summary['client_email']}`"
        )

        last = st.session_state.get("_last_save_status")
        st.markdown("**직전 저장 결과**")
        if not last:
            st.caption("아직 저장 시도가 없습니다.")
        elif last.get("ok"):
            st.success(
                f"✅ 성공 — {last.get('at')} · 단원 [{last.get('unit')}] · "
                f"NCS {last.get('ncs_score')} (sid={last.get('sid')})"
            )
        else:
            st.error(
                f"❌ 실패 — {last.get('at')} · 단원 [{last.get('unit')}]\n\n"
                f"오류: `{last.get('error')}`"
            )

        if st.button("🧪 시트 쓰기 테스트 실행", key="db_diag_smoke_test_btn",
                      help="더미 'heartbeat' 행을 1줄 쓰고 즉시 다시 읽어 round-trip 을 확인합니다."):
            with st.spinner("시트에 더미 행을 써 보고 다시 읽는 중…"):
                result = run_sheet_write_smoke_test()
            if result["ok"]:
                st.success(
                    f"✅ 쓰기/읽기 모두 OK ({result['round_trip_seconds']:.2f}초). "
                    "현재 시트 연결은 정상입니다."
                )
                st.caption(
                    "더미 행은 student_id='__diag__' · mode='diagnostic' 으로 표시되어 "
                    "학생 누적 통계에는 포함되지 않습니다. (필요 시 시트에서 수동 삭제)"
                )
            else:
                st.error(
                    f"❌ 시트 쓰기 테스트 실패 — {result['error']}\n\n"
                    "→ Secrets 의 `type='service_account'`, `private_key`(여러 줄 따옴표), "
                    "그리고 `client_email` 이 대상 스프레드시트에 **편집자**로 공유되어 있는지 "
                    "확인해 주세요."
                )


def get_my_history_records() -> list[dict]:
    """포트폴리오/사이드바 등에서 사용하는 표준 진입점.

    세션 캐시(`my_history_records`)가 있으면 그대로 사용하고, 비어 있으면
    시트에서 1회 강제 재동기화한다. 학번 타입 차이로 인한 누락을 방지하기 위해
    캐시된 결과도 학번을 한 번 더 정규화 비교해 안전하게 필터링한다.

    또한 시트 쓰기 진단용 더미 행(``student_id='__diag__'`` 또는
    ``mode='diagnostic'``)은 학생 통계/포트폴리오에서 자동 제외한다.
    """
    sid = _normalize_sid(st.session_state.get("student_id"))
    if not sid:
        return []
    cached = st.session_state.get("my_history_records")
    if cached is None:
        cached = force_fetch_student_history(sid)
        st.session_state["my_history_records"] = cached

    def _keep(rec: dict) -> bool:
        if _normalize_sid(rec.get("student_id")) != sid:
            return False
        if (rec.get("mode") or "").strip().lower() == "diagnostic":
            return False
        if _normalize_sid(rec.get("student_id")) == "__diag__":
            return False
        return True

    return [r for r in cached if _keep(r)]


def append_diagnostic_record(record: dict) -> None:
    """진단 완료 시 history 시트에 append.

    저장되는 핵심 필드 (모두 누락 없이 시트에 들어가는지 매번 점검):
      - ``record_id``      : 회차 고유 UUID
      - ``submitted_at``   : 제출 일시
      - ``student_id`` / ``student_display_name``
      - ``subject`` / ``unit`` / ``mode``
      - ``symptom``        : 학생이 입력한 [대상/상태/질문]
      - ``reasoning``      : 학생의 실습 수행 결과
      - ``result``         : compose_combined_result(guidance, evaluation) 합본
                             → split_combined_result 로 가이드/평가를 다시 분리해 사용
      - ``reflection``     : 오늘의 실습 소감
      - ``image_b64``      : 첨부 사진 썸네일(base64 JPEG)
      - ``mission_step_photos_json`` : 미션 단계별 수행 사진(JSON 배열, base64 JPEG 포함)

    저장 결과(성공/실패)는 ``st.session_state["_last_save_status"]`` 에 영구 기록되어
    st.rerun() 후에도 사이드바·메인 화면에서 사용자가 확인할 수 있다.
    """
    sid = _normalize_sid(record.get("student_id"))

    if not gs_app_sheets_ready():
        st.session_state["_last_save_status"] = {
            "ok": False,
            "at": now_kst_display() if "now_kst_display" in globals() else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sid": sid,
            "unit": record.get("unit") or "-",
            "error": "Google Sheets에 연결할 수 없습니다. (Secrets [connections.gsheets] 미설정)",
        }
        raise RuntimeError(
            "Google Sheets에 연결할 수 없습니다. "
            "secrets.toml [connections.gsheets] 섹션과 service_account 자격 증명을 확인해 주세요."
        )

    combined = record.get("result") or ""
    guidance_text, evaluation_text = split_combined_result(combined)

    # 디버그용: 어떤 필드가 비어 들어가는지 콘솔에 명시. 누락 사고를 즉시 탐지한다.
    logger.info(
        "[APPEND] sid=%s unit=%s | reasoning=%dchar guidance=%dchar evaluation=%dchar reflection=%dchar image_b64=%s",
        sid,
        record.get("unit") or "-",
        len(record.get("reasoning") or ""),
        len(guidance_text or ""),
        len(evaluation_text or ""),
        len(record.get("reflection") or ""),
        "있음" if (record.get("image_b64") or "").strip() else "없음",
    )
    logger.info("[APPEND] mission_step_photos_json=%d자", len((record.get("mission_step_photos_json") or "").strip()))

    score_input_text = evaluation_text or combined
    ncs = calculate_ncs_scores(
        score_input_text,
        record.get("mode") or "학습 모드",
        guidance_text=guidance_text,
        active_unit=record.get("unit") or None,
    )["overall_rate"]

    try:
        shb.append_history_from_record(record, ncs)
    except Exception as exc:
        # 실패 사유를 영구 기록해 st.rerun() 이후에도 보이도록 한다.
        logger.exception("[APPEND] 시트 쓰기 실패 (sid=%s): %s", sid, exc)
        st.session_state["_last_save_status"] = {
            "ok": False,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sid": sid,
            "unit": record.get("unit") or "-",
            "error": str(exc),
        }
        raise

    # 성공 — 무엇이 저장됐는지 영구 기록
    st.session_state["_last_save_status"] = {
        "ok": True,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sid": sid,
        "unit": record.get("unit") or "-",
        "record_id": record.get("record_id") or "",
        "ncs_score": round(float(ncs), 2),
    }
    logger.info("[APPEND] 시트 쓰기 성공 — sid=%s unit=%s ncs=%.1f",
                sid, record.get("unit") or "-", ncs)

    # Streamlit 의 모든 @st.cache_data 결과를 무효화하여 포트폴리오 탭이
    # 즉시 새 기록을 반영하도록 한다 (st-gsheets-connection 의 내부 캐시 포함).
    try:
        st.cache_data.clear()
    except Exception as exc:
        logger.warning("[APPEND] st.cache_data.clear() 실패 (무시): %s", exc)
def compute_class_average_unit_scores(records: list[dict]) -> tuple[list[str], list[float]]:
    if not records:
        return [], []
    sums = {u: 0.0 for u in NCS_UNITS}
    counts = {u: 0 for u in NCS_UNITS}
    for rec in records:
        result = rec.get("result") or ""
        mode = rec.get("mode") or "학습 모드"
        if not result.strip():
            continue
        guidance_text, evaluation_text = split_combined_result(result)
        score_input_text = evaluation_text or result
        score_data = calculate_ncs_scores(
            score_input_text,
            mode,
            guidance_text=guidance_text,
            active_unit=rec.get("unit") or None,
        )
        for us in score_data["unit_scores"]:
            sums[us["unit"]] += us["completion"] * 100.0
            counts[us["unit"]] += 1
    radar_labels = []
    radar_values = []
    for unit in NCS_UNITS:
        c = counts[unit]
        if c == 0:
            continue
        short = unit.replace("자동차 ", "").replace(" 점검", "").replace(" 고장진단", "")
        radar_labels.append(short)
        radar_values.append(round(sums[unit] / c, 1))
    return radar_labels, radar_values

def _teacher_real_submission(rec: dict) -> bool:
    """교사 대시보드 분석·피드백용: 시트 진단/더미 행 제외."""
    if _normalize_sid(rec.get("student_id")) == "__diag__":
        return False
    if (rec.get("mode") or "").strip().lower() == "diagnostic":
        return False
    return True


def _ncs_unit_short_label(unit: str) -> str:
    u = str(unit or "")
    return u.replace("자동차 ", "").replace(" 점검", "").replace(" 고장진단", "")


def _unique_student_options(records: list[dict]) -> list[tuple[str, str, str]]:
    """(student_id, select_label, display_name) 리스트, 학번 정렬."""
    best_name: dict[str, str] = {}
    for rec in records:
        if not _teacher_real_submission(rec):
            continue
        sid = _normalize_sid(rec.get("student_id"))
        if not sid:
            continue
        nm = (rec.get("student_display_name") or "").strip() or sid
        best_name[sid] = nm
    out: list[tuple[str, str, str]] = []
    for sid in sorted(best_name.keys()):
        nm = best_name[sid]
        out.append((sid, f"{sid} {nm}", nm))
    return out


def compute_student_unit_radar_values(records: list[dict], student_id: str) -> tuple[list[str], list[float]]:
    """선택 학생만: 루브릭 기반 6개 단원 평균 성취도(%). 미수행 단원 0%."""
    sid = _normalize_sid(student_id)
    sums = {u: 0.0 for u in NCS_UNITS}
    counts = {u: 0 for u in NCS_UNITS}
    for rec in records:
        if _normalize_sid(rec.get("student_id")) != sid:
            continue
        if not _teacher_real_submission(rec):
            continue
        result = rec.get("result") or ""
        mode = rec.get("mode") or "학습 모드"
        if not str(result).strip():
            continue
        guidance_text, evaluation_text = split_combined_result(result)
        score_input_text = evaluation_text or result
        score_data = calculate_ncs_scores(
            score_input_text,
            mode,
            guidance_text=guidance_text,
            active_unit=rec.get("unit") or None,
        )
        for us in score_data["unit_scores"]:
            u = us["unit"]
            if u in sums:
                sums[u] += float(us["completion"]) * 100.0
                counts[u] += 1
    labels = [_ncs_unit_short_label(u) for u in NCS_UNITS]
    values = [round(sums[u] / counts[u], 1) if counts[u] else 0.0 for u in NCS_UNITS]
    return labels, values


def _student_unit_attempt_counts(records: list[dict], student_id: str) -> dict[str, int]:
    """실제 제출된 단원별 학생 실습 완료 횟수."""
    sid = _normalize_sid(student_id)
    cnt = {u: 0 for u in NCS_UNITS}
    for rec in records:
        if _normalize_sid(rec.get("student_id")) != sid:
            continue
        if not _teacher_real_submission(rec):
            continue
        u = (rec.get("unit") or "").strip()
        if u in cnt:
            cnt[u] += 1
    return cnt


def _squish_teacher_display_text(text: str, max_chars: int = 240) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1].rstrip() + "…"


def _symptom_bullets_for_teacher(symptom: str) -> list[str]:
    raw = (symptom or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for title, key in (
        ("대상", "대상 부품"),
        ("상태", "현재 상태"),
        ("질문", "학습 질문"),
    ):
        m = re.search(rf"\[{re.escape(key)}\]\s*([^\n]+)", raw)
        if m:
            val = m.group(1).strip()
            if val and val != "(미입력)":
                out.append(f"**{title}** · {_squish_teacher_display_text(val, 180)}")
    if out:
        return out
    return [_squish_teacher_display_text(raw, 320)]


def _ai_evaluation_teacher_bullets(
    evaluation_text: str, max_items: int = 5, max_each: int = 130
) -> list[str]:
    body = (evaluation_text or "").strip()
    if not body:
        return []
    bullets: list[str] = []
    m = re.search(r"한줄\s*요약[：:]\s*\*?\*?(.+?)\*?\*?(?:\n|$)", body)
    if m:
        bullets.append(_squish_teacher_display_text(m.group(1), max_each))
    in_cat = False
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if "카테고리 요약" in s or "🏷" in s:
            in_cat = True
            continue
        if in_cat and (s.startswith("•") or s.startswith("-")):
            piece = s.lstrip("•-").strip()
            if piece and piece not in bullets:
                bullets.append(_squish_teacher_display_text(piece, max_each))
        if len(bullets) >= max_items:
            break
    if not bullets:
        flat = re.sub(r"^#+\s*.+$", "", body, flags=re.MULTILINE)
        flat = _squish_teacher_display_text(flat, max_each * max_items)
        if flat:
            bullets.append(flat)
    dedup: list[str] = []
    for b in bullets:
        if b not in dedup:
            dedup.append(b)
    return dedup[:max_items]


def _build_teacher_ai_digest_rows(
    student_records: list[dict], max_sessions: int = 3
) -> list[dict[str, str]]:
    """최근 회차별 AI 평가를 교사용 짧은 카드 row로 변환."""

    def _sort_ts(r: dict) -> str:
        return str(r.get("submitted_at") or "")

    recs = sorted(
        [r for r in student_records if _teacher_real_submission(r)],
        key=_sort_ts,
        reverse=True,
    )[:max_sessions]
    rows: list[dict[str, str]] = []
    for rec in recs:
        _, evaluation_text = split_combined_result(rec.get("result") or "")
        bl = _ai_evaluation_teacher_bullets(evaluation_text, max_items=3, max_each=150)
        if not bl:
            continue
        ts = rec.get("submitted_at") or "-"
        unit = rec.get("unit") or "-"
        rows.append(
            {
                "meta": f"{ts} · {unit}",
                "summary": bl[0],
                "extra": " · ".join(bl[1:]),
            }
        )
    return rows


def _render_teacher_submission_preview(current: dict) -> None:
    """교사용: 학생 입력·AI 평가를 압축 요약 + 원문은 접기."""
    st.markdown(
        f"**{current.get('student_display_name') or '-'}** (`{current.get('student_id') or '-'}`) · "
        f"{current.get('submitted_at') or '-'} · **{current.get('unit') or '-'}**"
    )
    st.markdown("##### 학생 입력 요약")
    sb = _symptom_bullets_for_teacher(current.get("symptom") or "")
    if sb:
        for line in sb:
            st.markdown(f"- {line}")
    else:
        st.caption("구조화된 증상 입력이 없습니다.")
    reasoning = (current.get("reasoning") or "").strip()
    if reasoning:
        st.markdown("##### 수행 결과 (압축)")
        st.markdown(f"> {_squish_teacher_display_text(reasoning, 360)}")
    refl = (current.get("reflection") or "").strip()
    if refl:
        st.caption(f"소감: {_squish_teacher_display_text(refl, 200)}")
    _, e_text = split_combined_result(current.get("result") or "")
    st.markdown("##### AI 평가 · 교사용 요약")
    ev_b = _ai_evaluation_teacher_bullets(e_text, max_items=6, max_each=120)
    if ev_b:
        for b in ev_b:
            st.markdown(f"- {b}")
    else:
        st.caption("AI 평가 문단을 요약할 수 없습니다.")
    render_mission_step_photos_gallery(current)
    with st.expander("원문 전체 보기 (학생 입력·AI 리포트)", expanded=False):
        st.text_area(
            "원문 증상·질문",
            value=(current.get("symptom") or "(없음)")[:8000],
            height=120,
            disabled=True,
            key=f"teacher_prev_sym_{current.get('record_id', '')}",
        )
        if reasoning:
            st.text_area(
                "원문 수행 결과",
                value=reasoning[:8000],
                height=120,
                disabled=True,
                key=f"teacher_prev_reas_{current.get('record_id', '')}",
            )
        st.text_area(
            "AI 리포트 전체",
            value=(current.get("result") or "")[:12000],
            height=220,
            disabled=True,
            key=f"teacher_prev_res_{current.get('record_id', '')}",
        )


def render_teacher_login() -> None:
    """교사 모드 선택 직후: 성함·비밀번호 검증 후 대시보드 진입."""
    st.markdown("## 교사 로그인")
    st.caption("교사 대시보드는 성함과 비밀번호 확인 후에만 이용할 수 있습니다.")
    st.caption(
        "※ 비밀번호·접속 기록은 브라우저 세션에만 저장됩니다. "
        "페이지를 새로고침하거나 서버가 재시작되면 비밀번호는 초기값(0000)으로 돌아갑니다. (추후 DB 연동 예정)"
    )
    with st.form("teacher_login_form", clear_on_submit=False):
        name_in = st.text_input("성함", placeholder="홍길동", key="teacher_login_name")
        pw_in = st.text_input("비밀번호", type="password", key="teacher_login_pw")
        submitted = st.form_submit_button("로그인", type="primary")
    if submitted:
        if not (name_in or "").strip():
            st.error("성함을 입력해 주세요.")
        elif pw_in != st.session_state.teacher_password:
            st.error("비밀번호가 올바르지 않습니다. 다시 확인해 주세요.")
        else:
            st.session_state.teacher_logged_in = True
            st.session_state.teacher_display_name = (name_in or "").strip()
            st.session_state.teacher_login_logs.append(
                {
                    "teacher_name": st.session_state.teacher_display_name,
                    "logged_in_at_kst": now_kst_display(),
                }
            )
            st.rerun()


def render_teacher_password_sidebar() -> None:
    """로그인한 교사만: 사이드바에서 비밀번호 변경."""
    st.markdown("---")
    st.markdown("#### 교사 비밀번호 변경")
    st.caption("저장 후 다음 로그인부터 새 비밀번호가 적용됩니다.")
    with st.form("teacher_pw_change_form"):
        new_pw = st.text_input("새 비밀번호", type="password", key="teacher_pw_new")
        new_pw2 = st.text_input("새 비밀번호 확인", type="password", key="teacher_pw_new2")
        change_submitted = st.form_submit_button("비밀번호 저장")
    if change_submitted:
        if not (new_pw or "").strip():
            st.error("새 비밀번호를 입력해 주세요.")
        elif new_pw != new_pw2:
            st.error("새 비밀번호가 서로 일치하지 않습니다.")
        else:
            st.session_state.teacher_password = new_pw.strip()
            st.success("비밀번호가 변경되었습니다.")
            st.rerun()


def render_teacher_mode() -> None:
    tname = (st.session_state.get("teacher_display_name") or "").strip() or "선생님"
    st.success(f"{tname} 선생님, 환영합니다!")
    st.header("교사 대시보드")
    st.caption("제출된 진단 기록을 한눈에 보고, 성취도를 분석하며 피드백을 남길 수 있습니다.")
    if not gs_app_sheets_ready():
        st.info(
            "Google Sheets 연결이 아직 준비되지 않았습니다. 위 안내를 확인한 뒤 "
            "Secrets 설정이 반영되면 다시 이 페이지를 열어 주세요."
        )
        return
    prev_err = st.session_state.pop("_gsheets_read_error", None)
    if prev_err:
        st.warning(f"이전 시트 읽기 오류: {prev_err}")
    c_ref, _ = st.columns([1, 4])
    with c_ref:
        if st.button("시트 새로고침", help="캐시를 비우고 history를 다시 읽습니다.", key="teacher_gs_refresh"):
            shb.invalidate_all_sheet_caches()
            st.rerun()
    records_raw = get_diagnostic_records()
    records = [r for r in records_raw if _teacher_real_submission(r)]
    st.subheader("학생 실황 — 진단 제출 현황")
    if not records_raw:
        st.info("아직 제출된 진단 기록이 없습니다. 학생 모드에서 진단을 실행하면 여기에 표시됩니다.")
    else:
        rows = []
        for rec in reversed(records_raw):
            rows.append(
                {
                    "진단 일시": rec.get("submitted_at") or "-",
                    "학생 ID": rec.get("student_id") or "-",
                    "표시 이름": rec.get("student_display_name") or "-",
                    "교과": rec.get("subject") or "-",
                    "선택 단원": rec.get("unit") or "-",
                    "모드": rec.get("mode") or "-",
                    "교사 피드백 유무": "있음" if (rec.get("teacher_feedback") or "").strip() else "없음",
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("👩‍🎓 학생별 성취도 및 진도 분석")
    sel_sid = None
    stud_recs_for_fb: list[dict] = []
    if not records:
        st.caption("실습 제출이 있는 학생을 선택하면 개인별 진도·성취도를 확인할 수 있습니다.")
    else:
        stud_opts = _unique_student_options(records)
        labels_for_box = [t[1] for t in stud_opts]
        sid_by_label = {t[1]: t[0] for t in stud_opts}
        pick = st.selectbox(
            "분석할 학생 선택",
            labels_for_box,
            key="teacher_student_analysis_pick",
            help="학번·이름 기준으로 선택합니다. 아래 차트·AI 요약·피드백 목록이 이 학생에 맞춰집니다.",
        )
        sel_sid = sid_by_label.get(pick)
        stud_recs_for_fb = [
            r for r in records if _normalize_sid(r.get("student_id")) == _normalize_sid(sel_sid)
        ] if sel_sid else []

        col_prog, col_radar = st.columns([1, 1])
        with col_prog:
            st.markdown("##### 📋 단원별 진도 (실습 제출 횟수)")
            attempts = _student_unit_attempt_counts(records, str(sel_sid))
            for u in NCS_UNITS:
                n = attempts.get(u, 0)
                if n > 0:
                    st.markdown(f"✅ **{u}** ({n}회)")
                else:
                    st.markdown(f"⬜ **{u}** (미수행)")
        with col_radar:
            st.markdown("##### 📊 능력단위별 성취도 (루브릭 추정 %)")
            if go is None:
                st.info("레이더 차트를 보려면 `pip install plotly`로 Plotly를 설치해 주세요.")
            else:
                r_labels, r_vals = compute_student_unit_radar_values(records, str(sel_sid))
                r_lbl_closed = r_labels + [r_labels[0]]
                r_val_closed = r_vals + [r_vals[0]]
                fig_s = go.Figure(
                    data=[
                        go.Scatterpolar(
                            r=r_val_closed,
                            theta=r_lbl_closed,
                            fill="toself",
                            name="선택 학생 성취도(%)",
                        )
                    ]
                )
                pick_nm = next((t[2] for t in stud_opts if t[0] == sel_sid), "")
                fig_s.update_layout(
                    polar={"radialaxis": {"visible": True, "range": [0, 100]}},
                    showlegend=False,
                    margin={"l": 30, "r": 30, "t": 40, "b": 30},
                    title=f"{sel_sid} {pick_nm} — NCS 능력단위 평균 (미수행 0%)",
                )
                st.plotly_chart(fig_s, use_container_width=True)

        st.subheader("🤖 AI 튜터의 학생 종합 평가 코멘트")
        digest_rows = _build_teacher_ai_digest_rows(stud_recs_for_fb, max_sessions=3)
        if not digest_rows:
            st.caption(
                "최근 AI 평가 문단이 없거나 요약할 수 없습니다. 아래 제출물의 'AI 평가 · 교사용 요약'을 참고하세요."
            )
        else:
            for dr in digest_rows:
                with st.container(border=True):
                    st.caption(dr["meta"])
                    st.markdown(f"**핵심** — {dr['summary']}")
                    if (dr.get("extra") or "").strip():
                        st.caption(dr["extra"])

    st.subheader("과제 관리 — 진단 리포트별 상세 피드백 (초안)")
    if not records or not stud_recs_for_fb:
        st.caption(
            "피드백을 남길 제출물이 없습니다. 위에서 학생을 선택했는지 확인해 주세요."
            if records and not stud_recs_for_fb
            else "피드백을 남길 제출물이 없습니다."
        )
        current = None
        picked_id = None
    else:
        options: list[tuple[str, str]] = []
        for rec in reversed(stud_recs_for_fb):
            sid = rec.get("student_id", "")
            ts = rec.get("submitted_at", "")
            unit = rec.get("unit", "")
            rid = rec["record_id"][:8]
            label = f"{ts} | {sid} | {unit} | #{rid}"
            options.append((label, rec["record_id"]))
        labels_only = [o[0] for o in options]
        id_by_label = dict(options)
        picked_label = st.selectbox(
            "피드백할 제출 선택 (선택한 학생만)",
            labels_only,
            index=0,
            key="teacher_fb_pick_filtered",
        )
        picked_id = id_by_label.get(picked_label)
        rec_by_id = {r["record_id"]: r for r in stud_recs_for_fb}
        current = rec_by_id.get(picked_id) if picked_id else None
        if current:
            with st.expander("선택한 제출의 요약 / 리포트 미리보기", expanded=True):
                _render_teacher_submission_preview(current)
            fb_key = f"teacher_fb_draft_{current['record_id']}"
            if fb_key not in st.session_state:
                st.session_state[fb_key] = current.get("teacher_feedback") or ""
            feedback_text = st.text_area(
                "교사 상세 피드백",
                key=fb_key,
                height=200,
                placeholder="예: 측정 포인트 선택은 좋았으나, 접지 경로를 먼저 확인하는 절차를 추가해 보세요.",
            )
            if st.button("피드백 저장", type="primary", key="teacher_fb_save_btn"):
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    shb.update_teacher_feedback_in_sheet(
                        str(current["record_id"]),
                        feedback_text.strip(),
                        now,
                    )
                    st.success("피드백이 Google Sheets에 저장되었습니다.")
                except Exception as exc:
                    st.error(f"시트 저장 실패: {exc}")
                st.rerun()
            if (current.get("teacher_feedback") or "").strip():
                st.caption(f"마지막 저장: {current.get('teacher_feedback_updated_at') or '-'}")
    st.markdown("---")
    st.subheader("최근 접속 기록")
    st.caption("로그인 성공 시점 기준 · KST")
    logs = list(reversed(st.session_state.get("teacher_login_logs") or []))
    if not logs:
        st.caption("저장된 접속 기록이 없습니다.")
    else:
        st.dataframe(
            [{"교사 성함": e["teacher_name"], "접속 시각 (KST)": e["logged_in_at_kst"]} for e in logs[:30]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("최근 30건만 표시합니다. 세션 종료 시 기록이 사라질 수 있습니다.")
    st.caption(
        "※ DB 미연결: 새로고침·서버 재시작 시 비밀번호는 0000으로 초기화될 수 있습니다."
    )
    st.markdown("---")
    if records_raw and st.button("모든 진단 기록 초기화 (데모용)", key="teacher_clear_history_demo"):
        try:
            shb.clear_history_worksheet()
            st.success("history 시트를 비웠습니다.")
        except Exception as exc:
            st.error(f"시트 초기화 실패: {exc}")
        st.rerun()


def complete_student_login(student_no: str, name: str) -> None:
    """가입/로그인 성공 후 세션에 반영한다.

    추가 책임:
      - Google Sheets 캐시(`_gs_history_df`, `_gs_users_df`)를 모두 무효화.
      - `history` 탭에서 해당 학번의 누적 기록을 즉시 강제 동기화하여
        `st.session_state["my_history_records"]` 에 캐싱.
      - 로그인 직후 누적 실습 건수를 콘솔(logger.info)에 기록해
        DB 동기화 상태를 운영자가 즉시 확인할 수 있도록 한다.
    """
    reset_student_auth_form()
    sid_norm = _normalize_sid(student_no)
    st.session_state.student_logged_in = True
    st.session_state.student_id = sid_norm
    st.session_state.student_display_name = name

    # 시트 캐시를 강제로 비우고 최신 데이터로 다시 채운다.
    try:
        shb.invalidate_all_sheet_caches()
        # Streamlit 의 @st.cache_data 전역 캐시도 함께 비워 다른 컴포넌트의
        # 옛 캐시(예: 학생 이름 룩업)가 새 학생 정보로 갱신되도록 한다.
        st.cache_data.clear()
    except Exception as exc:
        logger.warning("[LOGIN] 시트 캐시 무효화 실패 (무시): %s", exc)

    try:
        my_records = force_fetch_student_history(sid_norm)
    except Exception as exc:
        logger.exception("[LOGIN] 학생 %s 누적 이력 동기화 실패: %s", sid_norm, exc)
        my_records = []

    st.session_state["my_history_records"] = my_records
    logger.info(
        "[LOGIN] 학생 %s (%s) 누적 실습 이력 %d건을 시트에서 동기화 완료.",
        sid_norm, name, len(my_records),
    )

    st.rerun()


def render_student_login() -> None:
    """학생 모드: users 시트 기준 신규 가입 또는 기존 로그인."""
    st.markdown("## 학생 로그인 / 회원가입")
    st.caption("이름과 학번을 입력한 뒤 안내에 따라 비밀번호를 설정하거나 입력해 주세요.")
    st.caption(
        "※ 학생 계정은 **Google Sheets `users` 탭**에 저장됩니다. 비밀번호는 **해시**만 저장되며 시트에 평문으로 남지 않습니다."
    )
    if not gs_app_sheets_ready():
        st.info(
            "서버 설정 업데이트 중입니다. 잠시 후 다시 시도해 주세요. "
            "문제가 지속되면 담당 선생님께 알려 주세요."
        )
        return

    stage = st.session_state.get("student_auth_stage", "idle")

    if stage == "idle":
        with st.form("student_step_id_name"):
            name_in = st.text_input("이름", placeholder="홍길동", key="stu_login_name")
            sid_in = st.text_input("학번", placeholder="숫자만 입력 (예: 20250101)", key="stu_login_sid")
            next_clicked = st.form_submit_button("다음", type="primary")
        if next_clicked:
            raw_sid = (sid_in or "").strip()
            nm = normalize_student_name(name_in or "")
            if not nm:
                st.error("이름을 입력해 주세요.")
            elif not raw_sid:
                st.error("학번을 입력해 주세요.")
            elif not raw_sid.isdigit():
                st.error("학번은 숫자만 입력할 수 있습니다. 문자는 사용할 수 없습니다.")
            else:
                sid = raw_sid
                try:
                    shb.force_refresh_users()
                    row = shb.get_user_row(sid)
                except Exception as exc:
                    st.error(f"시트를 읽는 중 오류가 발생했습니다: {exc}")
                    return
                if row is None:
                    st.session_state.student_auth_stage = "register"
                    st.session_state.student_pending_id = sid
                    st.session_state.student_pending_name = nm
                    st.rerun()
                else:
                    stored_name = normalize_student_name(row.get("name", ""))
                    if stored_name != nm:
                        st.warning(
                            "입력하신 이름이 시트에 등록된 이름과 다릅니다. "
                            "비밀번호 로그인은 계속 진행되며, 표시되는 이름은 시트 기준입니다."
                        )
                    st.session_state.student_auth_stage = "login"
                    st.session_state.student_pending_id = sid
                    st.session_state.student_pending_name = row.get("name") or nm
                    st.rerun()

    elif stage == "register":
        pid = st.session_state.get("student_pending_id") or ""
        pname = st.session_state.get("student_pending_name") or ""
        st.success("첫 접속을 환영합니다! 사용할 비밀번호를 설정해 주세요.")
        st.info(f"**이름:** {pname} · **학번:** {pid}")
        with st.form("student_register_pw"):
            pw1 = st.text_input("비밀번호", type="password", key="stu_reg_pw1")
            pw2 = st.text_input("비밀번호 확인", type="password", key="stu_reg_pw2")
            reg_submit = st.form_submit_button("비밀번호 설정 및 시작", type="primary")
        if reg_submit:
            if not (pw1 or "").strip():
                st.error("비밀번호를 입력해 주세요.")
            elif pw1 != pw2:
                st.error("비밀번호가 서로 일치하지 않습니다.")
            else:
                try:
                    shb.force_refresh_users()
                    if shb.get_user_row(pid) is not None:
                        st.error("이미 등록된 학번입니다. 처음부터 다시 시도해 주세요.")
                    else:
                        shb.append_user_row(pid, pname, pw1.strip())
                        complete_student_login(pid, pname)
                except Exception as exc:
                    st.error(f"회원 등록 저장 실패: {exc}")
        if st.button("처음부터 다시 입력", key="stu_back_from_register"):
            reset_student_auth_form()
            st.rerun()

    elif stage == "login":
        pid = st.session_state.get("student_pending_id") or ""
        pname = st.session_state.get("student_pending_name") or ""
        st.info(f"학번 **{pid}** ({pname})으로 로그인합니다. 비밀번호를 입력해 주세요.")
        with st.form("student_login_pw"):
            pw_in = st.text_input("비밀번호", type="password", key="stu_login_pw_only")
            login_submit = st.form_submit_button("로그인", type="primary")
        if login_submit:
            try:
                rec = shb.get_user_row(pid)
            except Exception as exc:
                st.error(f"시트를 읽는 중 오류가 발생했습니다: {exc}")
                rec = None
            if not rec:
                st.error("등록 정보를 찾을 수 없습니다. 처음부터 다시 시도해 주세요.")
            elif not shb.verify_student_password(pid, pw_in or "", rec.get("password_hash") or ""):
                st.error("비밀번호가 올바르지 않습니다. 다시 확인해 주세요.")
            else:
                try:
                    shb.maybe_upgrade_plaintext_password(pid, pw_in or "", rec.get("password_hash") or "")
                except Exception:
                    pass
                complete_student_login(pid, rec.get("name") or pname)
        if st.button("처음부터 다시 입력", key="stu_back_from_login"):
            reset_student_auth_form()
            st.rerun()


_DIAG_STEPS = [
    ("input", "📝 입력", "부품·증상·학습 질문"),
    ("guidance", "🎯 미션 수행", "AI 미션 따라 실측·기록"),
    ("result", "🏆 완료", "성취도 분석 & 피드백"),
]


def _diag_step_index(step: str) -> int:
    for idx, (key, _label, _desc) in enumerate(_DIAG_STEPS):
        if key == step:
            return idx
    return 0


def _render_diagnosis_progress(step: str) -> None:
    """게임 퀘스트 스타일 스테이트 배지 + 진행 바."""
    idx = _diag_step_index(step)
    total = len(_DIAG_STEPS)
    progress_value = (idx + 1) / total
    st.progress(progress_value, text=f"퀘스트 진행률 · {int(progress_value*100)}%  ({idx+1}/{total} 단계)")

    cols = st.columns(total)
    for col_idx, (_key, label, desc) in enumerate(_DIAG_STEPS):
        with cols[col_idx]:
            if col_idx < idx:
                bg = "linear-gradient(135deg,#dcfce7 0%,#86efac 100%)"
                border = "#16a34a"
                text_color = "#14532d"
                state_icon = "✅"
                state_text = "Cleared"
                glow = "box-shadow:0 2px 6px rgba(22,163,74,0.18);"
                opacity = "1"
            elif col_idx == idx:
                bg = "linear-gradient(135deg,#fef9c3 0%,#fde68a 50%,#fbbf24 100%)"
                border = "#f59e0b"
                text_color = "#7c2d12"
                state_icon = "🔥"
                state_text = "진행 중"
                glow = "box-shadow:0 0 0 4px rgba(251,191,36,0.25),0 4px 14px rgba(245,158,11,0.45);"
                opacity = "1"
            else:
                bg = "#f1f5f9"
                border = "#cbd5e1"
                text_color = "#94a3b8"
                state_icon = "🔒"
                state_text = "Locked"
                glow = ""
                opacity = "0.65"
            # NOTE: HTML은 한 줄로 작성한다. 멀티라인 + 들여쓰기는 Streamlit 마크다운에서
            # 코드 블록으로 잘못 파싱되어 style 속성 일부가 그대로 텍스트로 노출되는 문제가 있다.
            badge_html = (
                f'<div style="background:{bg};border:2px solid {border};border-radius:16px;'
                f'padding:1rem 0.7rem;text-align:center;{glow}opacity:{opacity};'
                f'min-height:150px;display:flex;flex-direction:column;justify-content:center;">'
                f'<div style="font-size:1.9rem;line-height:1;">{state_icon}</div>'
                f'<div style="font-weight:800;color:{text_color};font-size:1.25rem;margin-top:0.45rem;letter-spacing:-0.01em;">{label}</div>'
                f'<div style="font-size:1.0rem;color:{text_color};margin-top:0.3rem;opacity:0.95;line-height:1.4;">{desc}</div>'
                f'<div style="font-size:0.92rem;color:{text_color};margin-top:0.5rem;font-weight:700;letter-spacing:0.06em;">{state_text}</div>'
                f'</div>'
            )
            st.markdown(badge_html, unsafe_allow_html=True)
    st.markdown("")


def _render_diagnosis_input_tab(
    mode: str,
    api_key: str,
    selected_subject: str,
    selected_unit: str,
) -> None:
    """[단계 1] 입력 → AI 가이드 호출, [단계 2] 가이드 표시 + 실습 결과 입력 → 평가 호출."""
    diag_step = st.session_state.get("diag_step", "input")

    # ──────────────────── [단계 1] 입력 폼 ────────────────────
    if diag_step == "input":
        hints = UNIT_INPUT_HINTS.get(
            selected_unit,
            {
                "target": "예: 점검 중인 부품 이름을 적어 주세요",
                "state": "예: 측정값/관찰한 증상을 적어 주세요",
                "question": "예: 가장 헷갈리는 부분을 적어 주세요",
            },
        )

        # ─── 오늘의 수행 과제 카드 ───
        with st.container(border=True):
            st.markdown(f"### 📝 오늘의 수행 과제  ·  {UNIT_ICONS.get(selected_unit, '📘')} {selected_unit}")
            st.caption("아래 3가지만 짧게 적어 주세요. 자세한 가이드는 ❓ 도움말 아이콘을 눌러 확인할 수 있어요.")

            st.markdown("**🔍 [대상]  어디를 점검하나요?**")
            target_part = st.text_input(
                "대상 부품",
                placeholder=hints["target"],
                key="diag_target_part",
                label_visibility="collapsed",
                help="회로도 상의 부품 이름이나 커넥터 번호(예: E12)를 함께 적으면 더 정확한 안내가 가능합니다.",
            )

            st.markdown("**⚡ [상태]  지금 증상이 어떤가요?**")
            current_state = st.text_area(
                "현재 상태",
                placeholder=hints["state"],
                height=110,
                key="diag_current_state",
                label_visibility="collapsed",
                help="멀티미터/스캐너로 측정한 값, 작동·미작동 상황, DTC 코드 등을 구체적으로 적어 주세요.",
            )

            st.markdown("**❓ [질문]  무엇이 궁금한가요?**")
            learning_question = st.text_area(
                "학습 질문",
                placeholder=hints["question"],
                height=90,
                key="diag_learning_question",
                label_visibility="collapsed",
                help="AI 튜터가 이 질문을 우선 다뤄 힌트를 줍니다(정답을 바로 알려주지는 않아요).",
            )

        symptom_text = compose_structured_symptom(target_part, current_state, learning_question)

        # ─── 사진 업로드 (선택, 평소엔 접힘) ───
        with st.expander("📸 부품/측정 사진 업로드 (선택)", expanded=False):
            uploaded_image = st.file_uploader(
                "사진 첨부",
                type=["png", "jpg", "jpeg", "webp"],
                key="diag_uploaded_image",
                label_visibility="collapsed",
            )
            if uploaded_image is not None:
                st.image(uploaded_image, caption="업로드된 사진", use_container_width=True)
            render_photo_upload_checklist(selected_unit)

        run_step1 = st.button("🚀 1단계: AI 가이드 받기", type="primary", use_container_width=True)
        if run_step1:
            if genai is None:
                st.error("Gemini 라이브러리가 설치되지 않았습니다. `pip install google-genai` 후 다시 실행해 주세요.")
                return
            if not api_key:
                st.warning("Gemini API 키를 먼저 설정해 주세요. (배포: Streamlit Secrets / 로컬: 사이드바 입력)")
                return
            if not symptom_text.strip() and uploaded_image is None:
                st.warning(
                    "①대상 부품 / ②현재 상태 / ③학습 질문 중 하나 이상을 적거나, 부품 사진을 업로드해 주세요."
                )
                return
            with st.spinner("AI 튜터가 NCS 기반 진단 미션을 작성 중입니다..."):
                try:
                    guidance_text = ask_gemini(
                        mode=mode,
                        user_symptom=symptom_text.strip(),
                        student_reasoning="",
                        image_file=uploaded_image,
                        key=api_key,
                        selected_subject=selected_subject,
                        selected_unit=selected_unit,
                        step="guidance",
                    )
                except Exception as exc:
                    st.error(f"진단 가이드 요청 중 오류가 발생했습니다: {exc}")
                    return
            st.session_state.latest_guidance = guidance_text
            st.session_state.latest_mode = mode
            st.session_state.latest_symptom = symptom_text.strip()
            st.session_state.latest_subject = selected_subject
            st.session_state.latest_unit = selected_unit
            st.session_state.latest_evaluation = ""
            st.session_state.latest_execution_result = ""
            st.session_state.latest_result = ""
            # 포트폴리오 저장용 썸네일: 단계 2 제출 시 record 에 함께 기록한다.
            st.session_state.latest_image_b64 = (
                make_thumbnail_b64(uploaded_image) if uploaded_image is not None else ""
            )
            st.session_state.mission_step_photos = {}
            st.session_state.diag_photo_nonce = uuid.uuid4().hex[:12]
            st.session_state.diag_step = "guidance"
            st.rerun()
        return

    # ──────────────────── [단계 2] 가이드 표시 + 실습 결과 입력 ────────────────────
    if diag_step == "guidance":
        st.subheader("② AI 가이드 확인 → 실습 수행")
        st.success("✅ 1단계 완료! 아래 미션을 따라 실측한 뒤 결과를 입력하면, AI가 충실도와 NCS 정렬을 평가합니다.")
        with st.expander("내가 입력한 증상 다시 보기", expanded=False):
            st.code(st.session_state.get("latest_symptom") or "(미입력)")
        st.markdown("---")
        render_mission_card(st.session_state.get("latest_guidance", ""))
        st.markdown("---")
        st.markdown("#### 🧪 실습 수행 결과 입력")
        st.markdown(
            # 글자색을 어두운 슬레이트(#1e293b)로 명시해 라이트/다크 테마 어디서도 명확히 보이게 한다.
            '<div style="background:#fffbeb;border:1px solid #fde68a;border-left:5px solid #f59e0b;'
            'padding:0.85rem 1rem;border-radius:10px;margin-bottom:0.7rem;font-size:1.05rem;'
            'line-height:1.6;color:#1e293b;">'
            '<span style="color:#b45309;font-weight:800;font-size:1.1rem;">💡 작성 팁</span> '
            '<span style="color:#1e293b;">— 위 미션 카드의 </span>'
            '<b style="color:#0f172a;">📝 단계 2 기록 가이드</b>'
            '<span style="color:#1e293b;"> 줄을 그대로 복사해 </span>'
            '<b style="color:#0f172a;">4개 카테고리</b>'
            '<span style="color:#1e293b;">(🛡️ 준비·안전 / 🔍 점검·회로도 / ⚡ 측정·전압 / 🛠️ 판정·조치)별로 '
            '정리하면 AI 평가에서 충실도(★★★)가 잘 매칭됩니다.</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        execution_result = st.text_area(
            "실습 수행 결과",
            placeholder=(
                "### 🛡️ 준비 / 안전\n"
                "- 점화 OFF, 계기판 소등 확인 (양호)\n"
                "- 절연장갑·보안경 착용 완료\n\n"
                "### 🔍 점검 / 회로도\n"
                "- F12 30A 퓨즈 도통 양호 (회로도 일치)\n"
                "- E12 커넥터 3번 핀 = (+) 입력 확인\n\n"
                "### ⚡ 측정 / 전압\n"
                "- OCV 12.45V 측정 (규정 12.3~12.9V 범위 내, 양호)\n"
                "- B+ 전압강하 0.12V (규정 0.2V 이하, 양호)\n\n"
                "### 🛠️ 판정 / 조치\n"
                "- SOC 82% 양호 — 충전 추가 불필요\n"
                "- 시동 불량은 솔레노이드 ST단자 전압강하 의심 → 추가 점검 권고"
            ),
            height=320,
            key="diag_execution_result",
            help="미션 카드의 '📝 기록 가이드' 줄을 복사해 4개 카테고리 아래에 붙여 넣고, 실제 측정값으로 숫자를 교체하세요.",
        )

        # ─── 📝 오늘의 실습 소감 ───
        with st.container(border=True):
            st.markdown("### 📝 오늘의 실습 소감")
            st.caption(
                "오늘 실습에서 어려웠던 점, 새롭게 알게 된 점, 다음 실습에서 더 잘하고 싶은 점을 자유롭게 적어 주세요. "
                "여기에 적은 소감은 [나의 포트폴리오 — 성장 일지]에 그대로 보관됩니다."
            )
            reflection = st.text_area(
                "실습 소감",
                placeholder=(
                    "예시) 처음에는 OCV 측정 시 리드봉 접촉 위치가 헷갈렸지만, 회로도에서 단자 위치를 먼저 확인하고 측정하니 "
                    "값이 안정적으로 나왔다. 다음에는 부하 인가 상태에서의 전압강하 측정도 함께 해 보고 싶다."
                ),
                height=160,
                key="diag_reflection",
                label_visibility="collapsed",
            )

        col_back, col_submit = st.columns([1, 2])
        with col_back:
            if st.button("← 1단계로 돌아가기"):
                st.session_state.diag_step = "input"
                st.rerun()
        with col_submit:
            run_step2 = st.button("✅ 2단계: 실습 결과 제출 & 평가받기", type="primary", use_container_width=True)
        if run_step2:
            if not execution_result.strip():
                st.warning("실습 수행 결과를 한 줄 이상 입력해 주세요.")
                return
            if not api_key:
                st.warning("Gemini API 키를 먼저 설정해 주세요.")
                return
            with st.spinner("AI 코치가 가이드 충실도와 NCS 정렬을 평가 중입니다..."):
                try:
                    evaluation_text = ask_gemini(
                        mode=mode,
                        user_symptom=st.session_state.get("latest_symptom") or "",
                        student_reasoning=execution_result.strip(),
                        image_file=None,
                        key=api_key,
                        selected_subject=st.session_state.get("latest_subject") or selected_subject,
                        selected_unit=st.session_state.get("latest_unit") or selected_unit,
                        step="evaluation",
                        guidance_text=st.session_state.get("latest_guidance", ""),
                    )
                except Exception as exc:
                    st.error(f"평가 요청 중 오류가 발생했습니다: {exc}")
                    return
            generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            combined_result = compose_combined_result(
                st.session_state.get("latest_guidance", ""),
                evaluation_text,
            )
            st.session_state.latest_evaluation = evaluation_text
            st.session_state.latest_execution_result = execution_result.strip()
            st.session_state.latest_result = combined_result
            st.session_state.latest_mode = mode
            st.session_state.latest_generated_at = generated_at
            # ⚠ diag_step 은 시트 저장이 성공한 뒤에만 'result' 로 전환한다.
            # 실패 시 학생이 다시 제출을 시도할 수 있도록 단계 2 화면을 유지한다.
            record = {
                "record_id": str(uuid.uuid4()),
                "submitted_at": generated_at,
                "student_id": st.session_state.student_id,
                "student_display_name": st.session_state.get("student_display_name")
                or st.session_state.student_id,
                "subject": st.session_state.get("latest_subject") or selected_subject,
                "unit": st.session_state.get("latest_unit") or selected_unit,
                "mode": mode,
                "symptom": st.session_state.get("latest_symptom") or "",
                "reasoning": execution_result.strip(),
                "result": combined_result,
                "teacher_feedback": "",
                "teacher_feedback_updated_at": "",
                "reflection": (reflection or "").strip(),
                "image_b64": st.session_state.get("latest_image_b64", "") or "",
                "mission_step_photos_json": collect_mission_step_photos_json(),
            }
            # 단계 3 표시용으로 소감을 세션에도 남긴다.
            st.session_state.latest_reflection = (reflection or "").strip()
            try:
                append_diagnostic_record(record)
                # 저장이 성공해야만 단계 3 으로 진행한다.
                st.session_state.diag_step = "result"
                # ① 시트 측 캐시를 비우고 ② 학생 누적 이력을 즉시 다시 끌어와
                # 포트폴리오/사이드바 카운트가 새 기록을 바로 반영하도록 한다.
                shb.invalidate_all_sheet_caches()
                refreshed = refresh_my_history_cache()
                logger.info(
                    "[APPEND] 학생 %s 새 기록 저장 후 누적 이력 %d건으로 재동기화 완료.",
                    _normalize_sid(st.session_state.get("student_id")),
                    len(refreshed),
                )
                st.session_state["_just_completed_step2"] = True
                st.session_state["_save_banner_msg"] = (
                    f"✅ 시트 저장 완료 — 단원 [{record.get('unit')}] · 누적 {len(refreshed)}건"
                )
                st.toast("📈 성취도 분석 결과가 준비됐어요! 상단 [📈 성취도 분석] 탭을 확인해 주세요.", icon="🎉")
                st.balloons()
                # 성공 시에만 rerun → 단계 3 화면으로 전환
                st.rerun()
            except Exception as sheet_exc:
                # 실패: rerun 하지 않고 화면에 오류를 영구 표시한다.
                # diag_step 은 'guidance' 로 유지하여 학생이 다시 제출을 시도하거나
                # 사이드바의 'DB 저장 상태'에서 사유를 확인할 수 있게 한다.
                st.session_state.diag_step = "guidance"
                st.session_state["_save_banner_msg"] = (
                    f"❌ 시트 저장 실패: {sheet_exc}"
                )
                st.error(
                    "구글 시트 저장에 실패했습니다. 사이드바의 **🔧 DB 저장 상태** 패널에서 "
                    "원인을 확인하고, 같은 화면 하단의 **🧪 시트 쓰기 테스트** 버튼으로 "
                    "연결 상태를 즉시 재진단해 주세요.\n\n"
                    f"**오류 메시지:** `{sheet_exc}`"
                )
        return

    # ──────────────────── [단계 3] 결과 표시 / 새 진단 ────────────────────
    st.subheader("③ 학습 성찰 단계")
    st.success(
        "🎉 **모든 학습 활동이 완료되었습니다!**\n\n"
        "👉 상단의 **[📈 성취도 분석]** 탭으로 이동해 NCS 성취도와 가이드 충실도를 확인하세요.\n"
        "👉 **[🔍 AI 코칭]** 탭에서는 AI 진단 가이드와 평가 카드를 한 번에 다시 볼 수 있어요."
    )
    if st.session_state.pop("_just_completed_step2", False):
        st.info(
            "📌 **다음 단계 안내** — 위쪽 탭 가운데 **📈 성취도 분석**을 눌러 결과 레이더 차트를 확인해 보세요. "
            "잘한 영역과 보완이 필요한 능력단위를 한눈에 점검할 수 있습니다."
        )
    with st.expander("이번 진단 입력 요약", expanded=False):
        st.code(st.session_state.get("latest_symptom") or "(미입력)")
        if st.session_state.get("latest_execution_result"):
            st.markdown("**실습 수행 결과**")
            st.code(st.session_state.get("latest_execution_result", ""))
    if st.button("🔄 새 진단 시작하기", type="primary", use_container_width=True):
        reset_diagnosis_flow()
        st.rerun()


def _render_diagnosis_feedback_tab() -> None:
    """🔍 AI 코칭 탭: 단계별 가이드/평가 카드를 보여 준다.

    회차별 PDF 다운로드 기능은 제거되었다. 모든 학기 누적 PDF 출력은
    사이드바 메뉴의 **📓 나의 포트폴리오** 에서 한 번에 생성한다.
    """
    st.subheader("🔍 AI 코칭 — 진단 가이드 & 수행 평가")
    diag_step = st.session_state.get("diag_step", "input")
    guidance_text = st.session_state.get("latest_guidance", "")
    evaluation_text = st.session_state.get("latest_evaluation", "")
    if diag_step == "input" and not guidance_text:
        st.caption("아직 생성된 코칭 카드가 없습니다. [📝 실습 수행] 탭에서 1단계를 먼저 진행해 주세요.")
        return
    st.caption(
        f"교과: {st.session_state.get('latest_subject', '')} | 단원: {st.session_state.get('latest_unit', '')} | 모드: {st.session_state.get('latest_mode', '')}"
    )
    if guidance_text:
        render_photo_retake_notice(guidance_text)
        render_mission_card(guidance_text, enable_step_photos=False)
    if diag_step == "guidance" and not evaluation_text:
        st.info("📌 [단계 2] 실습 수행 결과를 [📝 실습 수행] 탭에서 제출하면 평가 카드가 이 아래에 추가됩니다.")
    if evaluation_text:
        st.markdown("---")
        render_evaluation_card(evaluation_text)
        # 회차별 PDF 다운로드는 제거. 학기말 통합 PDF 안내만 남긴다.
        st.markdown("---")
        st.markdown(
            '<div style="background:linear-gradient(135deg,#ecfeff 0%,#cffafe 100%);'
            'padding:1rem 1.2rem;border-radius:12px;border:1px solid #06b6d4;'
            'margin-top:0.5rem;">'
            '<div style="font-size:1.1rem;font-weight:700;color:#0e7490;">'
            '💾 이번 실습 기록이 자동으로 저장되었습니다.</div>'
            '<div style="font-size:0.98rem;color:#0e7490;margin-top:0.35rem;line-height:1.55;">'
            '회차별 PDF 저장은 더 이상 제공되지 않습니다. '
            '학기 동안 누적된 모든 실습은 사이드바의 '
            '<b>📓 나의 포트폴리오</b> 메뉴에서 한 권의 PDF로 다운로드할 수 있습니다.</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_diagnosis_ncs_tab() -> None:
    """📈 성취도 분석 탭: [단계 2] 결과 입력 후, 오늘 수행한 단원 1개에만 집중해 분석한다."""
    st.subheader("📈 성취도 분석 — 오늘 수행한 단원에 집중")
    diag_step = st.session_state.get("diag_step", "input")
    if diag_step != "result":
        st.info(
            "📊 성취도 분석은 **[단계 2] 실습 수행 결과** 제출이 끝난 뒤에 생성됩니다.\n\n"
            "• 1단계: 부품·증상 입력 → AI 가이드 받기\n"
            "• 2단계: 가이드를 따라 측정·판단 → 결과 입력 후 제출\n"
            "• 3단계: 여기에서 오늘 단원의 세부 수행준거 4가지 달성 현황을 확인할 수 있어요."
        )
        return
    if st.session_state.get("_just_completed_step2"):
        st.success(
            "🎯 방금 제출한 실습 결과의 성취도 분석이 도착했어요. "
            "아래에서 오늘 수행한 단원의 무엇을 잘했고 무엇을 놓쳤는지 확인해 봅시다!"
        )
    render_ncs_achievement(
        st.session_state.get("latest_evaluation", "") or st.session_state.get("latest_execution_result", ""),
        st.session_state.get("latest_mode", "학습 모드"),
        guidance_text=st.session_state.get("latest_guidance", ""),
        unit_name=st.session_state.get("latest_unit") or "",
    )


def _format_week_key(submitted_at: str) -> tuple[str, str]:
    """제출 일시(YYYY-MM-DD HH:MM:SS) → (week_key, sort_key) 변환.

    - week_key: "2026년 19주차 (5/4 ~ 5/10)" 형태의 한국어 라벨 (UI 표시용)
    - sort_key: "2026-W19" — 그룹 정렬용
    """
    try:
        dt = datetime.strptime((submitted_at or "")[:10], "%Y-%m-%d")
    except Exception:
        return ("기타", "9999-W99")
    year, week, _ = dt.isocalendar()
    # 해당 ISO 주의 월요일(시작일) 계산
    try:
        monday = datetime.fromisocalendar(year, week, 1)
        sunday = datetime.fromisocalendar(year, week, 7)
        label = f"{year}년 {week}주차 ({monday.month}/{monday.day} ~ {sunday.month}/{sunday.day})"
    except Exception:
        label = f"{year}년 {week}주차"
    return (label, f"{year}-W{week:02d}")


def _compute_record_achievement(rec: dict) -> tuple[float, list[dict]]:
    """단일 record 의 NCS 성취도(overall, 단원별 세부)를 계산해 반환.

    Returns
    -------
    overall_rate : float (0~100)
    unit_scores  : 해당 record 의 단원 점수 리스트 (calculate_ncs_scores 결과)
    """
    combined = rec.get("result") or ""
    guidance_text, evaluation_text = split_combined_result(combined)
    score_input_text = evaluation_text or combined or (rec.get("reasoning") or "")
    if not score_input_text.strip():
        return 0.0, []
    try:
        data = calculate_ncs_scores(
            score_input_text,
            rec.get("mode") or "학습 모드",
            guidance_text=guidance_text,
            active_unit=rec.get("unit") or None,
        )
    except Exception:
        return 0.0, []
    return float(data.get("overall_rate") or 0.0), list(data.get("unit_scores") or [])


def _render_portfolio_card(rec: dict) -> None:
    """포트폴리오 한 건의 expander 카드 — 날짜·단원·수행·AI 코칭·소감·사진을 깔끔하게 흐름 정리."""
    submitted_at = rec.get("submitted_at") or "-"
    date_part = submitted_at[:10] if submitted_at != "-" else "-"
    time_part = submitted_at[11:16] if len(submitted_at) >= 16 else ""
    unit_name = rec.get("unit") or "-"
    icon = UNIT_ICONS.get(unit_name, "📘")

    overall_rate, unit_scores = _compute_record_achievement(rec)
    title = (
        f"📅 {date_part} {time_part} · {icon} {unit_name}"
        f" · 🎯 성취도 {overall_rate:.0f}점"
    )

    with st.expander(title, expanded=False):
        # ── 성취도 요약 (상단 메트릭 3종) ─────────────────────────────
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("🎯 NCS 종합", f"{overall_rate:.0f} / 100")
        with col_b:
            unit_match = next(
                (u for u in unit_scores if u.get("unit") == unit_name),
                None,
            )
            unit_pct = float(unit_match.get("completion") or 0.0) * 100 if unit_match else overall_rate
            st.metric("📘 단원 달성률", f"{unit_pct:.0f}%")
        with col_c:
            reflection_len = len((rec.get("reflection") or "").strip())
            st.metric("📝 소감 분량", f"{reflection_len}자")

        # 수행 내용 — 학생이 입력한 [대상/상태/질문] 요약
        symptom = (rec.get("symptom") or "").strip()
        if symptom:
            st.markdown("**🔍 수행 내용 — 대상 / 상태 / 학습 질문**")
            st.code(symptom, language="text")

        # 실습 수행 결과 — 학생이 직접 적은 측정/판정
        reasoning = (rec.get("reasoning") or "").strip()
        if reasoning:
            st.markdown("**🧪 나의 실습 수행 결과**")
            st.code(reasoning, language="text")

        # AI 코칭 — 가이드 텍스트의 앞부분(미션 요약 + 첫 카테고리)을 요약 노출
        combined = rec.get("result") or ""
        guidance_text, evaluation_text = split_combined_result(combined)
        if guidance_text.strip():
            st.markdown("**🧭 AI 코칭 — 미션 가이드 요약**")
            preview = guidance_text.strip()
            preview = preview[:600] + (" …" if len(preview) > 600 else "")
            with st.container(border=True):
                st.markdown(preview)

        # AI 평가 — 평가 카드(있을 때만 미리보기)
        if evaluation_text.strip():
            st.markdown("**🏆 AI 평가 — 수행 평가 요약**")
            eval_preview = evaluation_text.strip()
            eval_preview = eval_preview[:600] + (" …" if len(eval_preview) > 600 else "")
            with st.container(border=True):
                st.markdown(eval_preview)

        # 나의 소감 — 노란 하이라이트 카드
        reflection = (rec.get("reflection") or "").strip()
        st.markdown("**📝 나의 소감**")
        if reflection:
            st.markdown(
                '<div style="background:#fefce8;border-left:5px solid #facc15;'
                'padding:0.8rem 1rem;border-radius:8px;font-size:1.02rem;line-height:1.6;">'
                f'{reflection}'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("(소감이 기록되어 있지 않습니다.)")

        # 첨부 사진 — 썸네일 base64 복원
        image_b64 = (rec.get("image_b64") or "").strip()
        if image_b64:
            img_bytes = thumbnail_b64_to_bytes(image_b64)
            if img_bytes:
                st.markdown("**📷 1단계 입력 시 첨부 사진**")
                st.image(img_bytes, width=360)

        render_mission_step_photos_gallery(rec)

        # 교사 피드백 (있을 때만)
        tf = (rec.get("teacher_feedback") or "").strip()
        if tf:
            st.markdown("**🗒 교사 피드백**")
            st.success(tf)


def _render_portfolio_view() -> None:
    """📓 나의 포트폴리오 — 누적 실습 기록을 '성장 일지'처럼 주차별 카드로 보여준다.

    UI 다이어트 방침에 따라 메트릭/레이더 차트는 보여 주지 않고,
    날짜 → 단원 → 수행 → AI 코칭 → 소감 → 사진의 '기록 흐름'만 깔끔하게 노출한다.
    """
    student_id = st.session_state.get("student_id") or ""
    student_name = (st.session_state.get("student_display_name") or "").strip() or student_id

    st.markdown(
        f'<div style="background:linear-gradient(135deg,#fef3c7 0%,#fde68a 50%,#fbbf24 100%);'
        f'padding:1.2rem 1.4rem;border-radius:14px;border:1px solid #f59e0b;'
        f'box-shadow:0 4px 14px rgba(245,158,11,0.2);margin-bottom:1.2rem;">'
        f'<div style="font-size:1.65rem;font-weight:800;color:#7c2d12;letter-spacing:-0.01em;">'
        f'📓 나의 성장 일지 — Growth Journal</div>'
        f'<div style="font-size:1.05rem;color:#78350f;margin-top:0.35rem;">'
        f'{student_name} 학생의 자동차 전기전자제어 실습 기록을 주차별로 모아 보여줍니다.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not gs_app_sheets_ready():
        st.info("Google Sheets 연결 준비 중입니다. 잠시 후 다시 시도해 주세요.")
        return

    # 학번 타입 차이로 인한 누락을 방지하기 위해 정규화된 비교 + 강제 동기화 헬퍼 사용.
    # 사용자가 "🔄 시트에서 새로 불러오기" 버튼을 누르면 캐시를 무시하고 다시 읽는다.
    col_refresh, col_meta = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 시트에서 새로 불러오기", key="portfolio_force_refresh",
                     help="구글 시트 history 탭을 강제로 다시 읽어 누적 기록을 새로고침합니다."):
            refreshed = refresh_my_history_cache()
            st.success(f"새로 불러온 누적 실습 이력: {len(refreshed)}건")
    with col_meta:
        st.caption(
            f"🔗 연결된 학생: **{student_name}** · 학번 `{_normalize_sid(student_id)}`"
        )

    all_records = get_my_history_records()
    if not all_records:
        st.info(
            "아직 저장된 실습 기록이 없습니다. 사이드바의 **[🧑‍🏫 학습 모드]**에서 첫 실습을 시작해 보세요!"
        )
        return

    # 오래된 → 최신 순으로 정렬 후 주차별 그룹화
    sorted_records = sorted(all_records, key=lambda r: r.get("submitted_at") or "")

    from collections import OrderedDict
    weekly: "OrderedDict[str, list[dict]]" = OrderedDict()
    sort_keys: dict[str, str] = {}
    for rec in sorted_records:
        label, sort_key = _format_week_key(rec.get("submitted_at") or "")
        weekly.setdefault(label, []).append(rec)
        sort_keys[label] = sort_key
    # 최신 주차가 위로 오도록 재정렬
    weekly = OrderedDict(
        sorted(weekly.items(), key=lambda kv: sort_keys.get(kv[0], "9999-W99"), reverse=True)
    )

    # 상단 요약 캡션 (수치 없이 흐름 위주)
    st.caption(
        f"✨ 누적 실습 **{len(sorted_records)}건** · 시작 {sorted_records[0].get('submitted_at', '')[:10]} "
        f"~ 최근 {sorted_records[-1].get('submitted_at', '')[:10]}"
    )

    for week_label, week_records in weekly.items():
        st.markdown(
            f'<div style="margin-top:1.4rem;margin-bottom:0.5rem;padding:0.55rem 1rem;'
            f'background:#eff6ff;border-left:5px solid #2563eb;border-radius:8px;'
            f'font-weight:700;font-size:1.18rem;color:#1e3a8a;">'
            f'📅 {week_label} — 실습 {len(week_records)}건</div>',
            unsafe_allow_html=True,
        )
        # 같은 주차 안에서는 최신이 위로 오게
        for rec in sorted(week_records, key=lambda r: r.get("submitted_at") or "", reverse=True):
            _render_portfolio_card(rec)

    # ─── 학기말 최종 포트폴리오 PDF ───
    st.markdown("---")
    st.markdown(
        '<div style="background:linear-gradient(135deg,#dcfce7 0%,#86efac 100%);'
        'padding:1rem 1.2rem;border-radius:12px;border:1px solid #22c55e;'
        'margin:1rem 0 0.8rem 0;">'
        '<div style="font-size:1.35rem;font-weight:800;color:#14532d;">🎓 학기말 최종 포트폴리오</div>'
        '<div style="font-size:1.0rem;color:#166534;margin-top:0.35rem;">'
        '지금까지의 모든 실습·소감·첨부 사진을 한 권의 PDF 성장 일지로 묶어 내려받을 수 있어요.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if FPDF is None:
        st.info("PDF 저장 기능을 사용하려면 `pip install fpdf2`를 실행해 주세요.")
        return
    try:
        portfolio_bytes = build_comprehensive_portfolio_pdf(
            student_id=student_id,
            student_name=student_name,
            records=sorted_records,
        )
        st.download_button(
            "🎓 학기말 최종 포트폴리오 생성 & 다운로드",
            data=portfolio_bytes,
            file_name=(
                f"growth_journal_{student_id or 'student'}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            ),
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    except Exception as exc:
        st.error(f"학기말 포트폴리오 PDF 생성 중 오류가 발생했습니다: {exc}")


def render_student_mode() -> None:
    sname = (st.session_state.get("student_display_name") or "").strip() or "학생"
    with st.sidebar:
        st.header("학생 설정")
        st.caption(
            f"로그인: **{st.session_state.get('student_display_name') or '-'}** · 학번 `{st.session_state.get('student_id') or '-'}`"
        )
        st.caption("※ 브라우저 세션만 초기화됩니다. 학생 계정·진단 이력은 Google Sheets에 저장됩니다.")
        secret_api_key = st.secrets.get("GEMINI_API_KEY", "")
        if secret_api_key:
            api_key = secret_api_key
            st.success("Streamlit Secrets에서 API 키를 불러왔습니다.")
        else:
            api_key = st.text_input("API 키 입력 (로컬 테스트용)", type="password").strip()

        # ── 메뉴(view) — 학습 모드 / 나의 포트폴리오 ──
        view = st.radio(
            "메뉴",
            ["🧑‍🏫 학습 모드", "📓 나의 포트폴리오"],
            index=0,
            key="student_view_pick",
            help="학습 모드: 단원을 골라 새로운 실습을 진행합니다. 나의 포트폴리오: 누적 실습 기록을 성장 일지처럼 모아보고 학기말 PDF로 저장합니다.",
        )
        if not api_key:
            st.info("Gemini API 키를 입력해 주세요.")
        st.markdown("#### 반영 NCS 능력단위 (참고)")
        for unit in NCS_UNITS:
            st.markdown(f"- {unit}")

    # ── '평가 모드'는 메뉴에서 제거되었지만 AI 호출 인자는 그대로 살려 학습 톤을 적용한다. ──
    mode = "학습 모드"

    # ── 저장 결과 영구 배너 (st.rerun() 으로 메시지가 사라지는 사고 방지) ──
    save_banner = st.session_state.get("_save_banner_msg")
    if save_banner:
        if save_banner.startswith("✅"):
            st.success(save_banner)
        else:
            st.error(save_banner)
        if st.button("배너 닫기", key="dismiss_save_banner_btn"):
            st.session_state.pop("_save_banner_msg", None)
            st.rerun()

    # ── 사이드바 메뉴 분기 ──
    if "포트폴리오" in view:
        _render_portfolio_view()
        return

    st.success(f"안녕하세요, {sname} 학생! 오늘도 즐겁게 실습해봅시다.")
    st.header("학생 학습 경로")
    st.caption("교과·단원을 고른 뒤 AI 튜터와 실습하고, 누적 기록은 [📓 나의 포트폴리오] 메뉴에서 확인할 수 있어요.")

    selected_subject = "자동차 전기전자제어"
    unit_choices = CURRICULUM[selected_subject]
    st.markdown("#### 🎯 오늘 어떤 실습을 할까요?")
    st.caption("아래에서 단원 카드를 선택하세요. 선택한 단원에 맞춰 입력 예시와 미션이 달라집니다.")
    unit_labels = [f"{UNIT_ICONS.get(u, '📘')} {u}" for u in unit_choices]
    picked_label = st.radio(
        "단원 선택",
        unit_labels,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="unit_radio_pick",
    )
    selected_unit = unit_choices[unit_labels.index(picked_label)]
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%);
            border:1px solid #93c5fd; border-radius:12px;
            padding:0.65rem 1rem; margin:0.25rem 0 1rem 0;
            font-size:0.95rem; color:#1e3a8a;">
            <b>{UNIT_ICONS.get(selected_unit, '📘')} 선택된 단원:</b>
            {selected_unit} <span style="color:#475569;">· {selected_subject}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_diagnosis_progress(st.session_state.get("diag_step", "input"))
    tab_input, tab_feedback, tab_ncs = st.tabs(["📝 실습 수행", "🔍 AI 코칭", "📈 성취도 분석"])
    with tab_input:
        _render_diagnosis_input_tab(
            mode=mode,
            api_key=api_key,
            selected_subject=selected_subject,
            selected_unit=selected_unit,
        )
    with tab_feedback:
        _render_diagnosis_feedback_tab()
    with tab_ncs:
        _render_diagnosis_ncs_tab()
    st.caption("📌 누적 실습 기록은 사이드바의 [📓 나의 포트폴리오] 메뉴에서 주차별 성장 일지 형태로 모아볼 수 있어요.")


def init_session_state() -> None:
    defaults = {
        "app_role": None,
        "latest_result": "",
        "latest_mode": "학습 모드",
        "latest_symptom": "",
        "latest_generated_at": "",
        "latest_subject": "",
        "latest_unit": "",
        "student_id": "",
        "student_display_name": "",
        "diag_step": "input",
        "latest_guidance": "",
        "latest_evaluation": "",
        "latest_execution_result": "",
        "latest_reflection": "",
        "latest_image_b64": "",
        "mission_step_photos": {},
        "diag_photo_nonce": "",
        # 누적 history 캐시 — 로그인 직후 force_fetch_student_history 로 채워진다.
        # None = 아직 동기화 전, [] = 동기화 완료(0건)
        "my_history_records": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    if "teacher_password" not in st.session_state:
        st.session_state.teacher_password = TEACHER_PASSWORD_DEFAULT
    if "teacher_login_logs" not in st.session_state:
        st.session_state.teacher_login_logs = []
    if "teacher_logged_in" not in st.session_state:
        st.session_state.teacher_logged_in = False
    if "teacher_display_name" not in st.session_state:
        st.session_state.teacher_display_name = ""
    if "student_logged_in" not in st.session_state:
        st.session_state.student_logged_in = False
    if "student_auth_stage" not in st.session_state:
        st.session_state.student_auth_stage = "idle"
    if "student_pending_id" not in st.session_state:
        st.session_state.student_pending_id = ""
    if "student_pending_name" not in st.session_state:
        st.session_state.student_pending_name = ""


def _consume_role_query_param() -> None:
    """랜딩 페이지의 카드 링크(?role=)로 진입 시 역할을 반영한다."""
    qp = st.query_params
    if "role" not in qp:
        return
    raw = qp.get("role")
    val = raw[0] if isinstance(raw, list) else raw
    try:
        del st.query_params["role"]
    except Exception:
        try:
            qp.pop("role", None)
        except Exception:
            pass
    if val == "teacher":
        st.session_state.app_role = "teacher"
        reset_teacher_session_soft()
        reset_student_session_soft()
        st.rerun()
    elif val == "student":
        st.session_state.app_role = "student"
        reset_teacher_session_soft()
        reset_student_session_soft()
        st.rerun()


def render_role_selection() -> None:
    _consume_role_query_param()

    landing_html = """
<div class="landing-wrap" style="text-align: center; max-width: 960px; margin: 0 auto; padding: 2.5rem 1.25rem 3rem; font-family: 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; background: #f1f5f9; border-radius: 20px;">
<style>
  .landing-wrap .landing-hero {
    background: linear-gradient(145deg, #bbf7d0 0%, #86efac 35%, #4ade80 70%, #22c55e 100%);
    border-radius: 18px;
    padding: 2rem 1.5rem 2.15rem;
    margin: 0 0 1.85rem 0;
    box-shadow: 0 8px 28px rgba(34, 197, 94, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.45);
  }
  .landing-wrap .landing-title {
    font-size: clamp(2.15rem, 5.2vw, 3.25rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.18;
    margin: 0;
    color: #ffffff;
    text-shadow: 0 2px 8px rgba(21, 83, 45, 0.35), 0 1px 2px rgba(0, 0, 0, 0.2);
  }
  .landing-wrap .landing-sub {
    font-size: clamp(1.25rem, 2.8vw, 1.55rem);
    font-weight: 600;
    color: #ffffff;
    margin: 0.85rem 0 0 0;
    letter-spacing: 0.03em;
    line-height: 1.45;
    text-shadow: 0 1px 6px rgba(21, 83, 45, 0.3), 0 1px 2px rgba(0, 0, 0, 0.15);
  }
  .landing-wrap .landing-hint {
    font-size: 1rem;
    color: #334155;
    margin: 0 0 2.25rem 0;
    line-height: 1.65;
    font-weight: 500;
  }
  .landing-wrap .mode-cards {
    display: flex;
    justify-content: center;
    align-items: stretch;
    flex-wrap: wrap;
    gap: 1.75rem;
    margin: 0 auto;
  }
  .landing-wrap .mode-card {
    display: flex;
    flex-direction: column;
    justify-content: center;
    width: min(100%, 340px);
    min-height: 200px;
    padding: 1.65rem 1.5rem;
    border-radius: 18px;
    text-decoration: none;
    text-align: center;
    box-sizing: border-box;
    transition: transform 0.22s ease, box-shadow 0.22s ease, filter 0.22s ease;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
    border: 2px solid transparent;
  }
  .landing-wrap .mode-card:hover {
    transform: scale(1.045);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.14);
    filter: brightness(1.03);
  }
  .landing-wrap .mode-card:active {
    transform: scale(1.01);
  }
  .landing-wrap .mode-card-teacher {
    background: linear-gradient(160deg, #fffde7 0%, #fff59d 40%, #fdd835 100%);
    border-color: #f9a825;
    color: #3e2723;
  }
  .landing-wrap .mode-card-teacher:hover {
    background: linear-gradient(160deg, #fff9c4 0%, #ffee58 35%, #ffca28 100%);
  }
  .landing-wrap .mode-card-student {
    background: linear-gradient(160deg, #e3f2fd 0%, #90caf9 45%, #42a5f5 100%);
    border-color: #1565c0;
    color: #0d47a1;
  }
  .landing-wrap .mode-card-student:hover {
    background: linear-gradient(160deg, #e1f5fe 0%, #81d4fa 40%, #29b6f6 100%);
  }
  .landing-wrap .mode-card-label {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
  }
  .landing-wrap .mode-card-desc {
    font-size: 0.95rem;
    line-height: 1.55;
    opacity: 0.95;
  }
  .landing-wrap .landing-foot {
    margin-top: 2.75rem;
    font-size: 0.88rem;
    color: #64748b;
    line-height: 1.55;
    font-weight: 500;
  }
</style>
  <div class="landing-hero">
    <h1 class="landing-title">자동차 고장진단 AI tutor</h1>
    <p class="landing-sub">자동차 전기전자 제어</p>
  </div>
  <p class="landing-hint">역할을 선택하면 해당 화면으로 이동합니다. 세션 동안 유지되며,<br/>이후 사이드바에서 언제든 역할을 바꿀 수 있습니다.</p>
  <div class="mode-cards">
    <a class="mode-card mode-card-teacher" href="?role=teacher" target="_self">
      <span class="mode-card-label">교사 모드</span>
      <span class="mode-card-desc">선생님용: 학습 현황 관리</span>
    </a>
    <a class="mode-card mode-card-student" href="?role=student" target="_self">
      <span class="mode-card-label">학생 모드</span>
      <span class="mode-card-desc">학생용: 고장진단 실습 시작</span>
    </a>
  </div>
  <p class="landing-foot">NCS 수행준거 기반 · 소크라테스식 AI 학습 지원</p>
</div>
"""
    st.markdown(landing_html, unsafe_allow_html=True)

    st.markdown(
        '<div style="text-align:center; margin-top:1.25rem;">'
        '<p style="color:#475569;font-size:0.92rem;margin:0;font-weight:500;">카드 링크가 차단된 경우 아래 버튼으로 진입할 수 있습니다.</p></div>',
        unsafe_allow_html=True,
    )
    _sp, bc1, bc2, _sp2 = st.columns([1.2, 1, 1, 1.2])
    with bc1:
        if st.button("교사 모드로 진입", key="landing_btn_teacher", use_container_width=True):
            st.session_state.app_role = "teacher"
            reset_teacher_session_soft()
            reset_student_session_soft()
            st.rerun()
    with bc2:
        if st.button("학생 모드로 진입", key="landing_btn_student", use_container_width=True):
            st.session_state.app_role = "student"
            reset_teacher_session_soft()
            reset_student_session_soft()
            st.rerun()


st.set_page_config(
    page_title="자동차 고장진단 AI tutor",
    page_icon="🚗",
    layout="wide",
)
# 전역 글자 크기 업스케일 — 교실 빔 프로젝터/태블릿에서도 잘 보이도록 본문/캡션/입력/버튼 폰트를 키운다.
st.markdown(
    """
    <style>
      html, body, [class*="st-emotion"] { font-size: 17px; }
      .stApp { font-size: 17px; line-height: 1.6; }
      .stApp h1 { font-size: 2.2rem !important; }
      .stApp h2 { font-size: 1.75rem !important; }
      .stApp h3 { font-size: 1.4rem !important; }
      .stApp h4 { font-size: 1.2rem !important; }
      .stApp h5 { font-size: 1.08rem !important; }
      .stMarkdown p, .stMarkdown li { font-size: 1.05rem; line-height: 1.65; }
      [data-testid="stCaptionContainer"], .stCaption, small { font-size: 0.95rem !important; }
      .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] *,
      .stNumberInput input, .stDateInput input { font-size: 1.05rem !important; }
      .stTextInput label, .stTextArea label, .stSelectbox label, .stRadio label,
      .stCheckbox label, .stFileUploader label { font-size: 1.05rem !important; font-weight: 600 !important; }
      .stRadio div[role="radiogroup"] label p { font-size: 1.05rem !important; }
      .stButton button, .stDownloadButton button { font-size: 1.05rem !important; font-weight: 600; padding: 0.55rem 1rem !important; }
      .stTabs [data-baseweb="tab"] { font-size: 1.1rem !important; font-weight: 600; }
      [data-testid="stMetricValue"] { font-size: 2.1rem !important; }
      [data-testid="stMetricLabel"] { font-size: 1.0rem !important; }
      [data-testid="stMetricDelta"] { font-size: 0.95rem !important; }
      [data-testid="stExpander"] summary p { font-size: 1.05rem !important; font-weight: 600; }
      .stDataFrame, .stTable { font-size: 1.0rem !important; }
      [data-testid="stAlert"] p { font-size: 1.02rem !important; }
      [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { font-size: 1.05rem !important; }
      .stProgress > div > div > div { height: 14px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)
init_session_state()
if st.session_state.app_role is None:
    render_role_selection()
    st.stop()
with st.sidebar:
    st.markdown("### 세션")
    role_label = "교사" if st.session_state.app_role == "teacher" else "학생"
    st.caption(f"현재 역할: **{role_label} 모드**")
    if st.button("역할 다시 선택"):
        st.session_state.app_role = None
        reset_teacher_session_soft()
        reset_student_session_soft()
        st.rerun()
    if st.session_state.app_role == "teacher" and st.session_state.get("teacher_logged_in"):
        render_teacher_password_sidebar()
        # 교사도 DB 저장 상태를 즉시 진단할 수 있게 동일 패널을 노출한다.
        render_db_diagnostic_panel()
    if st.session_state.app_role == "student" and st.session_state.get("student_logged_in"):
        st.markdown("---")
        st.markdown("#### 학생 계정")
        st.caption(f"**{st.session_state.get('student_display_name') or '-'}** · 학번 `{st.session_state.get('student_id') or '-'}`")
        # ── DB 연결 확인용: 현재 캐시에 보관 중인 누적 실습 이력 수를 노출 ──
        try:
            _my_records_count = len(get_my_history_records())
        except Exception:
            _my_records_count = 0
        st.markdown(
            f'<div style="font-size:0.85rem;color:#1e293b;background:#f1f5f9;'
            f'border:1px solid #cbd5e1;border-radius:8px;padding:0.45rem 0.7rem;'
            f'margin:0.3rem 0 0.55rem 0;">'
            f'📚 현재 연결된 누적 실습 이력: <b style="color:#1d4ed8;">{_my_records_count}건</b>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c_sync, c_out = st.columns(2)
        with c_sync:
            if st.button("🔄 동기화", key="student_sync_btn",
                          help="구글 시트 history 탭에서 내 기록을 다시 끌어옵니다."):
                refreshed = refresh_my_history_cache()
                st.toast(f"누적 실습 이력 {len(refreshed)}건을 다시 불러왔어요.", icon="📚")
                st.rerun()
        with c_out:
            if st.button("로그아웃", key="student_logout_btn"):
                reset_student_session_soft()
                st.rerun()
        # 시트 쓰기/읽기 진단 패널 — 학습 결과가 시트에 저장되지 않을 때 즉시 원인 파악
        render_db_diagnostic_panel()
if st.session_state.app_role == "teacher":
    if not st.session_state.get("teacher_logged_in"):
        st.title("자동차 전기전자제어 — 교사 모드")
        render_teacher_login()
        st.stop()
    st.title("자동차 전기전자제어 — 교사 모드")
    render_teacher_mode()
else:
    if not st.session_state.get("student_logged_in"):
        st.title("자동차 전기전자제어 — 학생 모드")
        render_student_login()
        st.stop()
    st.title("자동차 전기전자제어 — 학생 모드")
    render_student_mode()
st.markdown("---")
st.caption("입력한 증상과 측정 데이터를 바탕으로 NCS 수행준거 기반 진단 학습을 진행할 수 있습니다.")

