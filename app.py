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
NCS_UNITS = [
    "자동차 전기전자장치 고장진단",
    "자동차 엔진 제어장치 점검",
    "자동차 샤시 제어장치 점검",
]
# 교과 → 단원(능력단위) 매핑
CURRICULUM = {
    "자동차 전기전자제어": list(NCS_UNITS),
}
NCS_RUBRIC = {
    "자동차 전기전자장치 고장진단": [
        ("안전 절차 언급", ["안전", "주의", "보호구", "감전"]),
        ("원인 가설 수립", ["원인", "가설", "가능한 원인", "고장 요인"]),
        ("회로/배선 점검 계획", ["배선", "회로", "커넥터", "단선", "접지"]),
        ("멀티미터 측정 근거", ["멀티미터", "전압", "저항", "연속성", "측정 포인트"]),
    ],
    "자동차 엔진 제어장치 점검": [
        ("센서/액추에이터 점검", ["센서", "액추에이터", "스로틀", "점화코일", "인젝터"]),
        ("ECU 신호 해석", ["ecu", "엔진 제어", "신호", "입력값", "출력값"]),
        ("진단 절차의 순서성", ["단계", "순서", "우선", "점검 절차"]),
        ("개선 실습 제안", ["실습", "재점검", "보완", "개선", "다음 과제"]),
    ],
    "자동차 샤시 제어장치 점검": [
        ("샤시 제어계통 언급", ["샤시", "abs", "eps", "브레이크", "조향", "현가"]),
        ("고장 영향 분석", ["영향", "증상", "연계", "원인-결과"]),
        ("측정값 비교/판단", ["기준", "정상 범위", "비교", "판단", "해석"]),
        ("재발 방지/정리", ["재발", "예방", "핵심 정리", "정리", "피드백"]),
    ],
}
MODE_RUBRIC_WEIGHTS = {
    "학습 모드": {
        "안전 절차 언급": 1.3,
        "원인 가설 수립": 1.2,
        "회로/배선 점검 계획": 1.0,
        "멀티미터 측정 근거": 1.0,
        "센서/액추에이터 점검": 1.0,
        "ECU 신호 해석": 0.9,
        "진단 절차의 순서성": 1.2,
        "개선 실습 제안": 1.2,
        "샤시 제어계통 언급": 0.9,
        "고장 영향 분석": 1.0,
        "측정값 비교/판단": 0.9,
        "재발 방지/정리": 1.2,
    },
    "평가 모드": {
        "안전 절차 언급": 1.1,
        "원인 가설 수립": 1.0,
        "회로/배선 점검 계획": 1.1,
        "멀티미터 측정 근거": 1.3,
        "센서/액추에이터 점검": 1.1,
        "ECU 신호 해석": 1.3,
        "진단 절차의 순서성": 1.0,
        "개선 실습 제안": 0.9,
        "샤시 제어계통 언급": 1.0,
        "고장 영향 분석": 1.1,
        "측정값 비교/판단": 1.3,
        "재발 방지/정리": 0.9,
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
def _rubric_lines_for_unit(unit: str) -> str:
    lines = NCS_RUBRIC.get(unit, [])
    if not lines:
        return "(해당 단원 수행준거 정보 없음)"
    return "\n".join(f"- {label}: 키워드 예시 {', '.join(kws)}" for label, kws in lines)
def build_learning_prompt(
    user_symptom: str,
    selected_subject: str,
    selected_unit: str,
) -> str:
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    rubric_block = _rubric_lines_for_unit(selected_unit)
    return f"""
너는 특성화고 자동차 전기전자제어 실습 수업을 돕는 AI 튜터다.
[선택 교과]
{selected_subject}
[선택 단원(능력단위) — 이 단원의 NCS 수행준거에 집중]
{selected_unit}
[이 단원의 수행준거 요약]
{rubric_block}
[학생 입력 증상]
{symptom_block}
작성 원칙:
- 친절하고 교육적인 어조
- 정답을 바로 단정하지 말고 힌트와 소크라테스식 질문 포함
- 안전 점검 우선
- 위 단원 수행준거에 맞춰 학습 대화를 이끌 것
- 학생이 질문 없이 사진만 올린 경우에도 반드시 대응
- 부품 식별 신뢰도가 낮으면 "신뢰도 낮음"을 명시하고 추가 사진 요청을 먼저 제시
- 추가 사진 요청 시 각도(정면/측면/후면), 거리(근접/중간), 초점(커넥터/라벨/배선)을 구체적으로 안내
반드시 지킬 출력 순서:
0) **학습 시작 질문**: 선택 단원 수행준거 중 가장 핵심이 되는 요소 하나를 골라, 학생이 스스로 생각하게 만드는 소크라테스식 개방형 질문 1문장으로 시작한다. (이 문장이 전체 답변의 첫 문장이어야 한다.)
그 다음 형식으로 한국어로 답변:
1) 사진 속 부품 명칭 추정(신뢰도와 함께)
2) 해당 부품의 일반적인 고장 증상과 입력 증상 연결
3) 가장 먼저 해야 할 측정 작업(우선순위 1~3, 안전 주의사항 포함)
4) 멀티미터 측정 위치 안내(리드봉을 어디에 대는지 구체적으로)
5) 추가 촬영 가이드(신뢰도 낮을 때 필수)와 학생 스스로 생각해볼 질문/핵심 정리
""".strip()
def build_evaluation_prompt(
    user_symptom: str,
    student_reasoning: str,
    selected_subject: str,
    selected_unit: str,
) -> str:
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    rubric_block = _rubric_lines_for_unit(selected_unit)
    return f"""
너는 특성화고 자동차 전기전자제어 실습의 평가 코치다.
[선택 교과]
{selected_subject}
[선택 단원(능력단위) — 이 단원 기준으로 평가]
{selected_unit}
[이 단원의 수행준거 요약]
{rubric_block}
[학생 입력 증상]
{symptom_block}
[학생 진단 논리/측정 해석]
{student_reasoning}
작성 원칙:
- '합격/불합격' 표현 금지
- 부족한 점은 "보완이 필요한 능력 단위 요소" 중심으로 제시
- 개선을 위한 구체적 실습 제안 포함
- 사진만 있는 경우 먼저 부품 명칭을 추정하고 평가 근거를 설명
- 부품 식별 신뢰도가 낮으면 우선 평가를 단정하지 말고 "추가 사진 필요"를 먼저 제시
- 추가 사진 요청 시 각도(정면/측면/후면), 거리(근접/중간), 초점(커넥터/라벨/배선) 체크리스트를 제공
다음 형식으로 한국어로 답변:
1) 사진 속 부품 명칭 추정 및 관련 고장 증상 연결
2) NCS 기준 진단 분석(강점/근거 포함)
3) 보완이 필요한 능력 단위 요소
4) 가장 먼저 해야 할 측정 작업 우선순위
5) 멀티미터 측정 위치, 추가 촬영 가이드(필요 시), 다음 실습 과제
""".strip()
def ask_gemini(
    mode: str,
    user_symptom: str,
    student_reasoning: str,
    image_file: Optional[Any],
    key: str,
    selected_subject: str,
    selected_unit: str,
) -> str:
    client = genai.Client(api_key=key)
    if mode == "학습 모드":
        prompt = build_learning_prompt(user_symptom, selected_subject, selected_unit)
    else:
        prompt = build_evaluation_prompt(user_symptom, student_reasoning, selected_subject, selected_unit)
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
def render_feedback_cards(result_text: str, mode: str) -> None:
    parsed = split_sections(result_text)
    if mode == "학습 모드":
        titles = [
            "학습 시작 질문",
            "부품 명칭 추정",
            "고장 증상 연결",
            "우선 측정 작업",
            "멀티미터 측정 위치",
            "질문/핵심 정리",
        ]
        keys = ["영역 0", "영역 1", "영역 2", "영역 3", "영역 4", "영역 5"]
    else:
        titles = [
            "부품 명칭 추정/증상 연결",
            "NCS 기준 진단 분석",
            "보완이 필요한 능력 단위 요소",
            "우선 측정 작업",
            "멀티미터 위치/다음 실습 과제",
        ]
        keys = ["영역 1", "영역 2", "영역 3", "영역 4", "영역 5"]
    if mode == "학습 모드":
        col1, col2 = st.columns(2)
        with col1:
            st.success(f"### {titles[0]}\n\n{parsed[keys[0]] or '응답 내용 없음'}")
            st.info(f"### {titles[1]}\n\n{parsed[keys[1]] or '응답 내용 없음'}")
            st.warning(f"### {titles[2]}\n\n{parsed[keys[2]] or '응답 내용 없음'}")
        with col2:
            st.success(f"### {titles[3]}\n\n{parsed[keys[3]] or '응답 내용 없음'}")
            st.markdown(f"### {titles[4]}\n\n{parsed[keys[4]] or '응답 내용 없음'}")
        st.markdown(f"### {titles[5]}\n\n{parsed[keys[5]] or '응답 내용 없음'}")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"### {titles[0]}\n\n{parsed[keys[0]] or '응답 내용 없음'}")
            st.warning(f"### {titles[1]}\n\n{parsed[keys[1]] or '응답 내용 없음'}")
        with col2:
            st.success(f"### {titles[2]}\n\n{parsed[keys[2]] or '응답 내용 없음'}")
            st.markdown(f"### {titles[3]}\n\n{parsed[keys[3]] or '응답 내용 없음'}")
        st.markdown(f"### {titles[4]}\n\n{parsed[keys[4]] or '응답 내용 없음'}")
def render_photo_retake_notice(result_text: str) -> None:
    lowered = result_text.lower()
    trigger_keywords = ["신뢰도 낮음", "추가 사진", "추가 촬영", "재촬영", "식별 어려움"]
    if any(keyword in lowered for keyword in trigger_keywords):
        st.info(
            "사진 식별 신뢰도가 낮은 것으로 판단되었습니다. "
            "정면/측면/후면, 근접/중간 거리, 커넥터/라벨/배선이 보이도록 다시 촬영해 업로드해 주세요."
        )
def render_photo_upload_checklist() -> None:
    with st.expander("촬영 전 체크리스트 (권장)", expanded=True):
        st.markdown(
            """
- 정면, 측면, 후면 사진을 각각 1장 이상 촬영했나요?
- 부품 전체가 보이는 중간 거리 사진과 커넥터/라벨이 보이는 근접 사진이 있나요?
- 커넥터 핀, 배선 색상, 단자 부식 여부가 흐리지 않게 보이나요?
- 그림자/역광이 심하지 않고, 손떨림 없이 초점이 맞았나요?
- 가능하면 부품 주변 위치(엔진룸 내 상대 위치)도 함께 보이게 촬영했나요?
            """.strip()
        )
        st.caption("체크리스트를 만족할수록 부품 식별 신뢰도와 측정 안내 정확도가 올라갑니다.")
def calculate_ncs_scores(result_text: str, mode: str) -> dict:
    weights = MODE_RUBRIC_WEIGHTS.get(mode, {})
    lowered = result_text.lower()
    unit_scores = []
    total_weighted_score = 0.0
    total_weighted_items = 0.0
    for unit in NCS_UNITS:
        criteria = NCS_RUBRIC[unit]
        missing_labels = []
        unit_weighted_score = 0.0
        unit_weight_total = 0.0
        for label, keywords in criteria:
            criterion_weight = weights.get(label, 1.0)
            unit_weight_total += criterion_weight
            if any(keyword.lower() in lowered for keyword in keywords):
                unit_weighted_score += criterion_weight
            else:
                missing_labels.append(label)
        completion = unit_weighted_score / unit_weight_total if unit_weight_total else 0.0
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
    return {"overall_rate": overall_rate, "unit_scores": unit_scores}
def build_pdf_bytes(
    generated_at: str,
    mode: str,
    symptom: str,
    result_text: str,
    ncs_score: float,
    subject: str,
    unit: str,
    student_id: str,
) -> bytes:
    if FPDF is None:
        raise RuntimeError("fpdf2 라이브러리가 필요합니다.")
    parsed = split_sections(result_text)
    sections = [
        ("0) 학습 시작 질문", parsed.get("영역 0", "")),
        ("1) 영역 1", parsed["영역 1"]),
        ("2) 영역 2", parsed["영역 2"]),
        ("3) 영역 3", parsed["영역 3"]),
        ("4) 영역 4", parsed["영역 4"]),
        ("5) 영역 5", parsed["영역 5"]),
    ]
    if mode != "학습 모드":
        sections = [(t, b) for t, b in sections if not t.startswith("0)")]
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
    pdf.multi_cell(0, 8, "[AI 피드백 영역]")
    for title, body in sections:
        pdf.multi_cell(0, 8, title)
        pdf.multi_cell(0, 8, body if body else "응답 내용 없음")
        pdf.ln(1)
    return bytes(pdf.output(dest="S"))
def render_ncs_achievement(result_text: str, mode: str) -> None:
    st.markdown("#### NCS 능력단위 성취도 체크")
    if not result_text:
        st.caption("아직 분석할 결과가 없습니다. 먼저 AI 피드백을 생성해 주세요.")
        return
    score_data = calculate_ncs_scores(result_text, mode)
    unit_scores = score_data["unit_scores"]
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
    """진단 완료 시 history 시트에 append."""
    if not gs_app_sheets_ready():
        raise RuntimeError("Google Sheets에 연결할 수 없습니다. secrets.toml [connections.gsheets] 를 확인하세요.")
    ncs = calculate_ncs_scores(record.get("result") or "", record.get("mode") or "학습 모드")["overall_rate"]
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
        score_data = calculate_ncs_scores(result, mode)
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
                    st.markdown("**학생 진단 논리**")
                    st.write(current.get("reasoning"))
                st.markdown("**AI 진단 피드백 (앞부분)**")
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
    subject_keys = list(CURRICULUM.keys())
    col_a, col_b = st.columns(2)
    with col_a:
        selected_subject = st.selectbox("교과 선택", subject_keys, index=0)
    with col_b:
        unit_choices = CURRICULUM[selected_subject]
        selected_unit = st.selectbox("단원 선택", unit_choices, index=min(1, len(unit_choices) - 1))
    st.info(f"선택됨: **{selected_subject}** → **{selected_unit}**")
    tab_input, tab_feedback, tab_ncs = st.tabs(["진단 입력", "AI 피드백", "NCS 성취도 분석"])
    with tab_input:
        st.subheader("고장 진단 입력")
        render_photo_upload_checklist()
        symptom_text = st.text_area(
            "고장 증상을 입력하세요",
            placeholder="예: 시동은 걸리지만 계기판 경고등이 점등되고, 전조등 밝기가 불안정합니다.",
            height=180,
        )
        student_reasoning = ""
        if mode == "평가 모드":
            student_reasoning = st.text_area(
                "학생 진단 논리 설명(평가 모드 필수)",
                placeholder="예: 배터리 전압 강하를 의심하여 발전기 출력과 접지 저항을 먼저 점검했습니다...",
                height=160,
            )
        uploaded_image = st.file_uploader(
            "멀티미터 측정 사진 업로드",
            type=["png", "jpg", "jpeg", "webp"],
        )
        if uploaded_image is not None:
            st.image(uploaded_image, caption="업로드된 멀티미터 측정 사진", use_container_width=True)
        run_diagnosis = st.button("AI 진단 피드백 생성", type="primary")
        if run_diagnosis:
            if genai is None:
                st.error("Gemini 라이브러리가 설치되지 않았습니다. `pip install google-genai` 후 다시 실행해 주세요.")
            elif not api_key:
                st.warning("Gemini API 키를 먼저 설정해 주세요. (배포: Streamlit Secrets / 로컬: 사이드바 입력)")
            elif not symptom_text.strip() and uploaded_image is None:
                st.warning("고장 증상 또는 부품 사진 중 하나 이상을 입력해 주세요.")
            elif mode == "평가 모드" and not student_reasoning.strip():
                st.warning("평가 모드에서는 학생 진단 논리 설명을 입력해 주세요.")
            else:
                with st.spinner("AI 튜터가 NCS 기준 피드백을 작성 중입니다..."):
                    try:
                        result_text = ask_gemini(
                            mode=mode,
                            user_symptom=symptom_text.strip(),
                            student_reasoning=student_reasoning.strip(),
                            image_file=uploaded_image,
                            key=api_key,
                            selected_subject=selected_subject,
                            selected_unit=selected_unit,
                        )
                        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.session_state.latest_result = result_text
                        st.session_state.latest_mode = mode
                        st.session_state.latest_symptom = symptom_text.strip()
                        st.session_state.latest_generated_at = generated_at
                        st.session_state.latest_subject = selected_subject
                        st.session_state.latest_unit = selected_unit
                        record = {
                            "record_id": str(uuid.uuid4()),
                            "submitted_at": generated_at,
                            "student_id": st.session_state.student_id,
                            "student_display_name": st.session_state.get("student_display_name")
                            or st.session_state.student_id,
                            "subject": selected_subject,
                            "unit": selected_unit,
                            "mode": mode,
                            "symptom": symptom_text.strip(),
                            "reasoning": student_reasoning.strip(),
                            "result": result_text,
                            "teacher_feedback": "",
                            "teacher_feedback_updated_at": "",
                        }
                        try:
                            append_diagnostic_record(record)
                            shb.invalidate_all_sheet_caches()
                            st.success(
                                "AI 피드백이 생성되었고 history 시트에 저장되었습니다. [AI 피드백] 탭에서 확인해 보세요."
                            )
                        except Exception as sheet_exc:
                            st.warning(f"AI 피드백은 생성되었으나 Google Sheets 저장에 실패했습니다: {sheet_exc}")
                    except Exception as exc:
                        st.error(f"진단 요청 중 오류가 발생했습니다: {exc}")
    with tab_feedback:
        st.subheader("AI 진단 피드백")
        if st.session_state.latest_result:
            st.caption(
                f"교과: {st.session_state.get('latest_subject', '')} | 단원: {st.session_state.get('latest_unit', '')} | 모드: {st.session_state.latest_mode}"
            )
            st.caption(f"현재 결과 모드: {st.session_state.latest_mode}")
            render_photo_retake_notice(st.session_state.latest_result)
            render_feedback_cards(st.session_state.latest_result, st.session_state.latest_mode)
            st.markdown("---")
            st.markdown("#### 포트폴리오 — 진단 결과 PDF 저장")
            if FPDF is None:
                st.info("PDF 저장 기능을 사용하려면 `pip install fpdf2`를 실행해 주세요.")
            else:
                try:
                    ncs_data = calculate_ncs_scores(st.session_state.latest_result, st.session_state.latest_mode)
                    pdf_bytes = build_pdf_bytes(
                        generated_at=st.session_state.latest_generated_at
                        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        mode=st.session_state.latest_mode,
                        symptom=st.session_state.latest_symptom,
                        result_text=st.session_state.latest_result,
                        ncs_score=ncs_data["overall_rate"],
                        subject=st.session_state.get("latest_subject") or "",
                        unit=st.session_state.get("latest_unit") or "",
                        student_id=st.session_state.get("student_id") or "",
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
        else:
            st.caption("아직 생성된 피드백이 없습니다. [진단 입력] 탭에서 먼저 실행해 주세요.")
    with tab_ncs:
        st.subheader("NCS 성취도 분석")
        render_ncs_achievement(st.session_state.latest_result, st.session_state.latest_mode)
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
                    st.markdown("**학생 진단 논리**")
                    st.write(item["reasoning"])
                if (item.get("teacher_feedback") or "").strip():
                    st.markdown("**교사 피드백**")
                    st.success(item["teacher_feedback"])
                st.markdown("**AI 진단 피드백**")
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

