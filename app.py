import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
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
GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
GEMINI_RETRY_DELAYS_SECONDS = [1.5, 3.0, 5.0]

# --- 교사 인증(세션 전용; DB 미연동 시 재시작·새로고침 시 초기화) ---
TEACHER_PASSWORD_DEFAULT = "0000"


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
    for widget_key in (
        "diag_target_part",
        "diag_current_state",
        "diag_learning_question",
        "diag_uploaded_image",
        "diag_execution_result",
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
- ✅ 진단 방향과 측정/점검 절차를 **'미션' 형태**로 제시.
- ✅ 장황한 서술 대신 **불렛(•)과 표(Markdown table)**를 적극 사용.
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
| 단계 | 행동(미션) | 안전·규정값 핵심 포인트 |
| --- | --- | --- |
| 1 | 안전 점검(절연장갑·단자 보호 등) | 단락 방지, 점화스위치 OFF 확인 |
| 2 | 회로도 분석: 전원→퓨즈→스위치/릴레이→부하→접지 | 단원 핵심 회로 흐름 명시 |
| 3 | 측정 미션 1 | 규정값 범위(예: OCV 12.3~12.9V) |
| 4 | 측정 미션 2 | … |
| 5 | (필요 시) 스캐너 진단 | DTC→센서데이터→강제구동 순서 |

## ⚠ 안전 주의
• …
• …

## 💡 학습 질문 힌트
• (학생의 [학습 질문]을 그대로 인용한 뒤, 답이 아니라 **다음에 어떤 측정/관찰을 해보면 단서가 잡힐지** 힌트만 제시)
• 소크라테스식 되묻기 1~2개

## 📷 추가 촬영 가이드 (신뢰도 낮은 경우만)
• 각도/거리/초점 …

[중요] 위 7개 섹션 헤더(##)를 정확히 그대로 사용한다. 표는 반드시 Markdown 표 형식으로 작성한다.
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
- ✅ **불렛(•)과 표(Markdown table)** 를 적극 사용해 가독성 우선.
- ✅ [단계 1 AI 가이드]의 미션 단계와 학생 수행 결과를 **표로 1:1 비교**해 충실도를 별점/이모지(★★★ / ★★☆ / ★☆☆ / ☆☆☆)로 표기.
- ✅ 표준 절차 (가)안전 점검 / (나)회로도 분석 / (다)시험등 vs DMM / (라)스캐너 절차(DTC→센서데이터→강제구동) 네 측면에서 강·약점을 짚는다.
- ✅ 단원 핵심 키워드(OCV 12.3~12.9V, 발전기 13.8~14.9V, 전압강하 0.2V, 종단저항 120Ω, 솔레노이드 B/ST/M, 릴레이 30/87/85/86, BCM/IPS/B-CAN, bus-off/time-out 등)를 인용해 구체화.
- ✅ [학생 입력 증상]에 [학습 질문]이 있다면, `다음 학습 미션` 섹션에서 그 질문에 직접적으로 도움이 되는 후속 실습을 제안한다.

[출력 형식 — 아래 마크다운 구조를 그대로 따른다]

## 📋 평가 한줄 요약
• (이번 실습 수행을 한 줄로 평가)

## ✅ 가이드 대비 수행 충실도
| 미션 단계 | 가이드 권장 동작 | 학생 수행 결과 | 충실도 |
| --- | --- | --- | --- |
| 1 | 안전 점검 | … | ★★☆ |
| 2 | 회로도 분석(전원→…→접지) | … | ★☆☆ |
| 3 | 측정 미션 1 | … | ★★★ |
| 4 | 측정 미션 2 | … | ☆☆☆ |
| 5 | (해당 시) 스캐너 절차 | … | … |

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

[중요] 위 4개 섹션 헤더(##)를 정확히 그대로 사용한다. 표는 반드시 Markdown 표 형식으로 작성한다.
""".strip()
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
        image_bytes = image_file.getvalue()
        image_mime_type = image_file.type or "image/jpeg"
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
            "문제가 반복되면 입력을 조금 줄이거나 다른 시간대에 재시도해 주세요."
        )
    raise RuntimeError(
        "현재 계정에서 사용 가능한 Gemini 모델을 찾지 못했습니다. "
        "Google AI Studio에서 지원 모델명을 확인한 뒤 상단 GEMINI_MODEL_CANDIDATES를 수정해 주세요. "
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


def render_mission_card(guidance_text: str) -> None:
    """[단계 1] AI 미션/가이드 카드 렌더링.

    프롬프트가 지시한 마크다운(##, 표, 불렛)을 그대로 렌더하되, 카드 컨테이너로 감싼다.
    """
    if not guidance_text or not guidance_text.strip():
        st.caption("아직 생성된 가이드가 없습니다.")
        return
    with st.container(border=True):
        st.markdown("##### 🧭 AI 진단 가이드 (Mission)")
        st.caption("정답이 아니라 '진단 방향'과 '측정/점검 방법'을 미션 형태로 안내합니다.")
        st.markdown(guidance_text)


def render_evaluation_card(evaluation_text: str) -> None:
    """[단계 2] 실습 수행 평가 카드 렌더링."""
    if not evaluation_text or not evaluation_text.strip():
        st.caption("아직 생성된 평가가 없습니다.")
        return
    with st.container(border=True):
        st.markdown("##### 📝 실습 수행 평가 (Step 2 Result)")
        st.caption("[단계 1] 가이드 대비 학생 수행 결과의 충실도와 NCS 정렬도를 평가합니다.")
        st.markdown(evaluation_text)


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
        render_mission_card(guidance_text)
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
    with st.expander("촬영 전 체크리스트 (권장)", expanded=True):
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
    """
    weights = MODE_RUBRIC_WEIGHTS.get(mode, {})
    has_guidance = bool(guidance_text and guidance_text.strip())
    result_lower = (result_text or "").lower()
    guidance_lower = (guidance_text or "").lower()

    unit_scores = []
    total_weighted_score = 0.0
    total_weighted_items = 0.0
    for unit in NCS_UNITS:
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
def render_ncs_achievement(result_text: str, mode: str, guidance_text: str = "") -> None:
    st.markdown("#### NCS 능력단위 성취도 체크")
    if not result_text:
        st.caption("아직 분석할 결과가 없습니다. 먼저 [단계 2] 실습 수행 결과를 제출해 주세요.")
        return
    score_data = calculate_ncs_scores(result_text, mode, guidance_text=guidance_text)
    unit_scores = score_data["unit_scores"]
    if score_data.get("guidance_aware"):
        st.caption("✅ AI 가이드 충실도 가중치가 반영된 성취도입니다 (가이드 이행=만점, 자율 수행=70%).")
    radar_labels = []
    radar_values = []
    ai_overview = []
    for unit_data in unit_scores:
        unit = unit_data["unit"]
        criteria = NCS_RUBRIC[unit]
        matched_labels = []
        missing_labels = unit_data["missing_labels"]
        evidence_map = {}
        unit_score = 0
        completion = unit_data["completion"]
        lowered = result_text.lower()
        for label, keywords in criteria:
            matched_keywords = [keyword for keyword in keywords if keyword.lower() in lowered]
            if matched_keywords:
                matched_labels.append(label)
                evidence_map[label] = [
                    (keyword, extract_evidence_snippet(result_text, keyword)) for keyword in matched_keywords[:2]
                ]
                unit_score += 1
        if completion >= 0.75:
            st.success(f"{unit}: {unit_score}/{len(criteria)} (가중 양호)")
        elif completion >= 0.5:
            st.warning(f"{unit}: {unit_score}/{len(criteria)} (가중 보통)")
        else:
            st.error(f"{unit}: {unit_score}/{len(criteria)} (가중 보완 필요)")
        st.progress(completion)
        st.caption(f"달성 항목: {', '.join(matched_labels) if matched_labels else '확인된 항목 없음'}")
        st.caption(f"보완 항목: {', '.join(missing_labels) if missing_labels else '보완 항목 없음'}")
        if evidence_map:
            st.caption("매칭 근거 (키워드 + 원문 스니펫)")
            for label, evidences in evidence_map.items():
                for keyword, snippet in evidences:
                    st.caption(f"- {label} | 키워드: {keyword} | 근거: {snippet}")
        st.markdown("---")
        short_name = unit.replace("자동차 ", "").replace(" 점검", "").replace(" 고장진단", "")
        radar_labels.append(short_name)
        radar_values.append(round(completion * 100, 1))
        if missing_labels:
            ai_overview.append(f"- {short_name}: `{missing_labels[0]}` 중심 보완이 필요합니다.")
        else:
            ai_overview.append(f"- {short_name}: 핵심 수행 항목이 전반적으로 잘 반영되었습니다.")
    weighted_achievement_rate = score_data["overall_rate"]
    st.metric("모드 반영 NCS 루브릭 성취율", f"{weighted_achievement_rate:.1f}%")
    st.caption(f"현재 적용 모드: {mode} (모드별 가중치 적용)")
    st.caption("참고: 업로드 문서 없이 동작하는 기본 체크리스트 기반 분석입니다.")
    if go is not None and radar_labels:
        radar_labels_closed = radar_labels + [radar_labels[0]]
        radar_values_closed = radar_values + [radar_values[0]]
        fig = go.Figure(
            data=[
                go.Scatterpolar(
                    r=radar_values_closed,
                    theta=radar_labels_closed,
                    fill="toself",
                    name="능력단위 성취율",
                )
            ]
        )
        fig.update_layout(
            polar={"radialaxis": {"visible": True, "range": [0, 100]}},
            showlegend=False,
            margin={"l": 30, "r": 30, "t": 40, "b": 30},
            title="NCS 능력단위 성취율 레이더 차트",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("레이더 차트를 보려면 `pip install plotly`로 Plotly를 설치해 주세요.")
    st.markdown("#### AI 총평")
    for summary in ai_overview:
        st.markdown(summary)
    with st.expander("NCS 기반 분석 원문 보기"):
        st.write(result_text)
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


def append_diagnostic_record(record: dict) -> None:
    """진단 완료 시 history 시트에 append.

    신 포맷 result는 ``compose_combined_result`` 로 가이드+평가를 한 필드에 합쳐 저장한다.
    NCS 점수 계산 시 가이드를 분리해 충실도 기반 가중치를 적용한다.
    """
    if not gs_app_sheets_ready():
        raise RuntimeError("Google Sheets에 연결할 수 없습니다. secrets.toml [connections.gsheets] 를 확인하세요.")
    combined = record.get("result") or ""
    guidance_text, evaluation_text = split_combined_result(combined)
    score_input_text = evaluation_text or combined
    ncs = calculate_ncs_scores(
        score_input_text,
        record.get("mode") or "학습 모드",
        guidance_text=guidance_text,
    )["overall_rate"]
    shb.append_history_from_record(record, ncs)
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
        score_data = calculate_ncs_scores(score_input_text, mode, guidance_text=guidance_text)
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
    records = get_diagnostic_records()
    st.subheader("학생 실황 — 진단 제출 현황")
    if not records:
        st.info("아직 제출된 진단 기록이 없습니다. 학생 모드에서 진단을 실행하면 여기에 표시됩니다.")
    else:
        rows = []
        for rec in reversed(records):
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
    st.subheader("성취도 분석 — 전체 학생 NCS 능력단위 평균")
    labels, values = compute_class_average_unit_scores(records)
    if not labels or go is None:
        if not records:
            st.caption("데이터가 쌓이면 학급 평균 레이더 차트가 표시됩니다.")
        elif go is None:
            st.info("레이더 차트를 보려면 `pip install plotly`로 Plotly를 설치해 주세요.")
        else:
            st.caption("유효한 AI 결과가 있는 기록이 없어 평균을 계산할 수 없습니다.")
    else:
        labels_closed = labels + [labels[0]]
        values_closed = values + [values[0]]
        fig = go.Figure(
            data=[
                go.Scatterpolar(
                    r=values_closed,
                    theta=labels_closed,
                    fill="toself",
                    name="학급 평균 성취율(%)",
                )
            ]
        )
        fig.update_layout(
            polar={"radialaxis": {"visible": True, "range": [0, 100]}},
            showlegend=False,
            margin={"l": 30, "r": 30, "t": 40, "b": 30},
            title="전체 학생 NCS 능력단위별 평균 점수 (루브릭 기반 추정)",
        )
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("과제 관리 — 진단 리포트별 상세 피드백 (초안)")
    if not records:
        st.caption("피드백을 남길 제출물이 없습니다.")
    else:
        options: list[tuple[str, str]] = []
        for rec in reversed(records):
            sid = rec.get("student_id", "")
            ts = rec.get("submitted_at", "")
            unit = rec.get("unit", "")
            rid = rec["record_id"][:8]
            label = f"{ts} | {sid} | {unit} | #{rid}"
            options.append((label, rec["record_id"]))
        labels_only = [o[0] for o in options]
        id_by_label = dict(options)
        picked_label = st.selectbox("피드백할 제출 선택", labels_only, index=0)
        picked_id = id_by_label.get(picked_label)
        rec_by_id = {r["record_id"]: r for r in records}
        current = rec_by_id.get(picked_id) if picked_id else None
        if current:
            with st.expander("선택한 제출의 요약 / 리포트 미리보기", expanded=True):
                st.markdown(f"**학생:** {current.get('student_display_name')} (`{current.get('student_id')}`)")
                st.markdown(f"**교과·단원:** {current.get('subject')} → {current.get('unit')}")
                st.markdown(f"**모드:** {current.get('mode')}")
                st.markdown("**입력 증상**")
                st.write(current.get("symptom") or "(없음)")
                if current.get("reasoning"):
                    st.markdown("**실습 수행 결과 / 진단 논리**")
                    st.write(current.get("reasoning"))
                st.markdown("**AI 진단 피드백 (가이드+평가, 앞부분)**")
                preview = (current.get("result") or "")[:2000]
                st.text(preview + ("…" if len(current.get("result") or "") > 2000 else ""))
            fb_key = f"teacher_fb_draft_{current['record_id']}"
            if fb_key not in st.session_state:
                st.session_state[fb_key] = current.get("teacher_feedback") or ""
            feedback_text = st.text_area(
                "교사 상세 피드백",
                key=fb_key,
                height=200,
                placeholder="예: 측정 포인트 선택은 좋았으나, 접지 경로를 먼저 확인하는 절차를 추가해 보세요.",
            )
            if st.button("피드백 저장", type="primary"):
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
    if records and st.button("모든 진단 기록 초기화 (데모용)"):
        try:
            shb.clear_history_worksheet()
            st.success("history 시트를 비웠습니다.")
        except Exception as exc:
            st.error(f"시트 초기화 실패: {exc}")
        st.rerun()


def complete_student_login(student_no: str, name: str) -> None:
    """가입/로그인 성공 후 세션에 반영한다."""
    reset_student_auth_form()
    st.session_state.student_logged_in = True
    st.session_state.student_id = student_no
    st.session_state.student_display_name = name
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
                            "입력하신 이름이 이 학번으로 등록된 정보와 다릅니다. "
                            "본인 학번·이름과 동일하게 입력했는지 확인해 주세요."
                        )
                    else:
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
    ("input", "1단계 · 진단 입력", "부품·증상·학습 질문을 입력합니다."),
    ("guidance", "2단계 · AI 가이드 → 실습 결과", "AI 미션을 따라 실측한 결과를 입력합니다."),
    ("result", "3단계 · 평가 & NCS 성취도", "충실도·NCS 정렬을 분석합니다."),
]


def _diag_step_index(step: str) -> int:
    for idx, (key, _label, _desc) in enumerate(_DIAG_STEPS):
        if key == step:
            return idx
    return 0


def _render_diagnosis_progress(step: str) -> None:
    """단계별 진행 상황 안내 + 진행 바."""
    idx = _diag_step_index(step)
    cols = st.columns(len(_DIAG_STEPS))
    for col_idx, (key, label, desc) in enumerate(_DIAG_STEPS):
        with cols[col_idx]:
            if col_idx < idx:
                st.markdown(f"**✅ {label}**")
            elif col_idx == idx:
                st.markdown(f"**🟦 {label}**")
            else:
                st.markdown(f":gray[⬜ {label}]")
            st.caption(desc)
    progress_value = (idx + 1) / len(_DIAG_STEPS)
    st.progress(progress_value)
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
        st.subheader("① 진단 입력")
        st.caption("부품과 증상을 적은 뒤 [1단계: AI 가이드 받기]를 누르면, AI 튜터가 측정 미션을 안내해 줍니다.")
        render_photo_upload_checklist(selected_unit)
        hints = UNIT_INPUT_HINTS.get(
            selected_unit,
            {
                "target": "예: 점검 중인 부품 이름을 적어 주세요",
                "state": "예: 측정값/관찰한 증상을 적어 주세요",
                "question": "예: 가장 헷갈리는 부분을 적어 주세요",
            },
        )
        target_part = st.text_input(
            "① 대상 부품 — 점검 중인 부품이 무엇인가요?",
            placeholder=hints["target"],
            key="diag_target_part",
            help="회로도 상의 부품 이름이나 커넥터 번호를 함께 적으면 더 정확한 안내가 가능합니다.",
        )
        current_state = st.text_area(
            "② 현재 상태 — 어떤 증상/측정값이 나타나나요?",
            placeholder=hints["state"],
            height=120,
            key="diag_current_state",
            help="멀티미터/스캐너로 측정한 값, 작동·미작동 상황, DTC 코드 등을 구체적으로 적어 주세요.",
        )
        learning_question = st.text_area(
            "③ 학습 질문 — 가장 궁금하거나 해결하기 어려운 부분은 무엇인가요?",
            placeholder=hints["question"],
            height=100,
            key="diag_learning_question",
            help="AI 튜터가 이 질문을 우선 다뤄 힌트를 줍니다(정답을 바로 알려주지는 않아요).",
        )
        symptom_text = compose_structured_symptom(target_part, current_state, learning_question)
        uploaded_image = st.file_uploader(
            "부품/측정 사진 업로드 (선택)",
            type=["png", "jpg", "jpeg", "webp"],
            key="diag_uploaded_image",
        )
        if uploaded_image is not None:
            st.image(uploaded_image, caption="업로드된 사진", use_container_width=True)
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
        st.caption(
            "위 미션의 각 단계를 실제로 수행한 결과(측정값·관찰·판단)를 적어 주세요. "
            "AI는 이 결과를 가이드와 비교해 충실도(★★★)와 NCS 수행준거 정렬을 평가합니다."
        )
        execution_result = st.text_area(
            "실습 수행 결과",
            placeholder=(
                "예시)\n"
                "• 안전 점검: 점화스위치 OFF, 절연장갑 착용 후 단자 보호 확인\n"
                "• OCV 측정값: 12.45V (규정 12.3~12.9V 범위 내, 양호)\n"
                "• 암전류 측정: 32mA (50mA 미만, 양호)\n"
                "• 최종 판단: 배터리 자체는 정상, 시동 불량 원인은 솔레노이드 ST단자 전압강하로 추정"
            ),
            height=240,
            key="diag_execution_result",
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
            st.session_state.diag_step = "result"
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
            }
            try:
                append_diagnostic_record(record)
                shb.invalidate_all_sheet_caches()
                st.success("실습 평가가 완료되어 history 시트에 저장되었습니다. [AI 피드백] · [NCS 성취도 분석] 탭에서 확인하세요.")
            except Exception as sheet_exc:
                st.warning(f"평가는 생성되었으나 Google Sheets 저장에 실패했습니다: {sheet_exc}")
            st.rerun()
        return

    # ──────────────────── [단계 3] 결과 표시 / 새 진단 ────────────────────
    st.subheader("③ 진단 완료")
    st.success("🎉 모든 단계가 완료되었습니다. 결과는 [AI 피드백] · [NCS 성취도 분석] 탭에서 확인하세요.")
    with st.expander("이번 진단 입력 요약", expanded=False):
        st.code(st.session_state.get("latest_symptom") or "(미입력)")
        if st.session_state.get("latest_execution_result"):
            st.markdown("**실습 수행 결과**")
            st.code(st.session_state.get("latest_execution_result", ""))
    if st.button("🔄 새 진단 시작하기", type="primary", use_container_width=True):
        reset_diagnosis_flow()
        st.rerun()


def _render_diagnosis_feedback_tab() -> None:
    """AI 피드백 탭: 단계별로 가이드/평가 카드를 보여주고, 완료 시 PDF 다운로드를 제공한다."""
    st.subheader("AI 진단 피드백")
    diag_step = st.session_state.get("diag_step", "input")
    guidance_text = st.session_state.get("latest_guidance", "")
    evaluation_text = st.session_state.get("latest_evaluation", "")
    if diag_step == "input" and not guidance_text:
        st.caption("아직 생성된 피드백이 없습니다. [진단 입력] 탭에서 1단계를 먼저 진행해 주세요.")
        return
    st.caption(
        f"교과: {st.session_state.get('latest_subject', '')} | 단원: {st.session_state.get('latest_unit', '')} | 모드: {st.session_state.get('latest_mode', '')}"
    )
    if guidance_text:
        render_photo_retake_notice(guidance_text)
        render_mission_card(guidance_text)
    if diag_step == "guidance" and not evaluation_text:
        st.info("📌 [단계 2] 실습 수행 결과를 [진단 입력] 탭에서 제출하면 평가가 이 카드 아래에 추가됩니다.")
    if evaluation_text:
        st.markdown("---")
        render_evaluation_card(evaluation_text)
    if evaluation_text:
        st.markdown("---")
        st.markdown("#### 포트폴리오 — 진단 결과 PDF 저장")
        if FPDF is None:
            st.info("PDF 저장 기능을 사용하려면 `pip install fpdf2`를 실행해 주세요.")
            return
        try:
            ncs_data = calculate_ncs_scores(
                st.session_state.get("latest_evaluation", "") or st.session_state.get("latest_execution_result", ""),
                st.session_state.get("latest_mode", "학습 모드"),
                guidance_text=st.session_state.get("latest_guidance", ""),
            )
            pdf_bytes = build_pdf_bytes(
                generated_at=st.session_state.get("latest_generated_at")
                or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                mode=st.session_state.get("latest_mode", "학습 모드"),
                symptom=st.session_state.get("latest_symptom", ""),
                result_text=st.session_state.get("latest_result", ""),
                ncs_score=ncs_data["overall_rate"],
                subject=st.session_state.get("latest_subject") or "",
                unit=st.session_state.get("latest_unit") or "",
                student_id=st.session_state.get("student_id") or "",
                execution_result=st.session_state.get("latest_execution_result", ""),
            )
            st.download_button(
                "진단 결과 PDF로 저장하기",
                data=pdf_bytes,
                file_name=f"portfolio_{st.session_state.get('student_id', 'student')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"PDF 생성 중 오류가 발생했습니다: {exc}")


def _render_diagnosis_ncs_tab() -> None:
    """NCS 성취도 탭: [단계 2] 결과 입력이 끝난 뒤에만 분석/레이더를 보여 준다."""
    st.subheader("NCS 성취도 분석")
    diag_step = st.session_state.get("diag_step", "input")
    if diag_step != "result":
        st.info(
            "📊 NCS 성취도 분석은 **[단계 2] 실습 수행 결과** 제출이 끝난 뒤에 생성됩니다.\n\n"
            "• 1단계: 부품·증상 입력 → AI 가이드 받기\n"
            "• 2단계: 가이드를 따라 측정·판단 → 결과 입력 후 제출\n"
            "• 3단계: 여기에서 NCS 성취도 레이더와 가이드 충실도 분석을 확인할 수 있어요."
        )
        return
    render_ncs_achievement(
        st.session_state.get("latest_evaluation", "") or st.session_state.get("latest_execution_result", ""),
        st.session_state.get("latest_mode", "학습 모드"),
        guidance_text=st.session_state.get("latest_guidance", ""),
    )


def render_student_mode() -> None:
    sname = (st.session_state.get("student_display_name") or "").strip() or "학생"
    st.success(f"안녕하세요, {sname} 학생! 오늘도 즐겁게 실습해봅시다.")
    st.header("학생 학습 경로")
    st.caption("교과·단원을 고른 뒤 AI 튜터와 실습하고, 포트폴리오 PDF로 정리할 수 있습니다.")
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
        mode = st.radio("운영 모드 선택", ["학습 모드", "평가 모드"], index=0)
        if not api_key:
            st.info("Gemini API 키를 입력해 주세요.")
        st.markdown("#### 반영 NCS 능력단위 (참고)")
        for unit in NCS_UNITS:
            st.markdown(f"- {unit}")
    selected_subject = "자동차 전기전자제어"
    unit_choices = CURRICULUM[selected_subject]
    selected_unit = st.selectbox("단원 선택", unit_choices, index=0)
    st.info(f"교과: **{selected_subject}** → 단원: **{selected_unit}**")
    _render_diagnosis_progress(st.session_state.get("diag_step", "input"))
    tab_input, tab_feedback, tab_ncs = st.tabs(["진단 입력", "AI 피드백", "NCS 성취도 분석"])
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
    st.markdown("### 나의 진단 이력")
    mine = [r for r in get_diagnostic_records() if r.get("student_id") == st.session_state.get("student_id")]
    if mine:
        for idx, item in enumerate(reversed(mine), start=1):
            history_title = item["symptom"][:30] if item["symptom"] else "사진 기반 진단"
            with st.expander(f"이력 {idx} - {item['mode']} - {item.get('unit', '')} - {history_title}..."):
                st.markdown("**교과·단원**")
                st.write(f"{item.get('subject')} → {item.get('unit')}")
                st.markdown("**입력 증상**")
                st.write(item["symptom"])
                if item.get("reasoning"):
                    st.markdown("**실습 수행 결과 / 진단 논리**")
                    st.write(item["reasoning"])
                if (item.get("teacher_feedback") or "").strip():
                    st.markdown("**교사 피드백**")
                    st.success(item["teacher_feedback"])
                st.markdown("**AI 진단 피드백 (가이드 + 평가)**")
                render_feedback_cards(item["result"], item["mode"])
    else:
        st.caption("이 계정으로 저장된 진단 이력이 없습니다.")


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
    if st.session_state.app_role == "student" and st.session_state.get("student_logged_in"):
        st.markdown("---")
        st.markdown("#### 학생 계정")
        st.caption(f"**{st.session_state.get('student_display_name') or '-'}** · 학번 `{st.session_state.get('student_id') or '-'}`")
        if st.button("로그아웃 (다른 학생으로 로그인)", key="student_logout_btn"):
            reset_student_session_soft()
            st.rerun()
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

