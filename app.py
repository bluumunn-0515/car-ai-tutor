import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import streamlit as st
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
def get_diagnostic_records() -> list[dict]:
    return st.session_state.diagnostic_records
def append_diagnostic_record(record: dict) -> None:
    st.session_state.diagnostic_records.append(record)
    st.session_state.diagnosis_history = [
        {
            "mode": r["mode"],
            "symptom": r["symptom"],
            "reasoning": r["reasoning"],
            "result": r["result"],
        }
        for r in st.session_state.diagnostic_records
    ]
def migrate_legacy_history_if_needed() -> None:
    if st.session_state.diagnostic_records:
        return
    legacy = st.session_state.get("diagnosis_history") or []
    if not legacy:
        return
    for item in legacy:
        st.session_state.diagnostic_records.append(
            {
                "record_id": str(uuid.uuid4()),
                "submitted_at": st.session_state.get("latest_generated_at") or "",
                "student_id": "legacy",
                "student_display_name": "이관 데이터",
                "subject": "자동차 전기전자제어",
                "unit": NCS_UNITS[0],
                "mode": item.get("mode", "학습 모드"),
                "symptom": item.get("symptom", ""),
                "reasoning": item.get("reasoning", ""),
                "result": item.get("result", ""),
                "teacher_feedback": "",
                "teacher_feedback_updated_at": "",
            }
        )
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
def render_teacher_mode() -> None:
    st.header("교사 대시보드")
    st.caption("제출된 진단 기록을 한눈에 보고, 성취도를 분석하며 피드백을 남길 수 있습니다.")
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
                for r in st.session_state.diagnostic_records:
                    if r["record_id"] == current["record_id"]:
                        r["teacher_feedback"] = feedback_text.strip()
                        r["teacher_feedback_updated_at"] = now
                        break
                st.success("피드백이 기록에 저장되었습니다.")
                st.rerun()
            if (current.get("teacher_feedback") or "").strip():
                st.caption(f"마지막 저장: {current.get('teacher_feedback_updated_at') or '-'}")
    st.markdown("---")
    if records and st.button("모든 진단 기록 초기화 (데모용)"):
        st.session_state.diagnostic_records = []
        st.session_state.diagnosis_history = []
        st.session_state.latest_result = ""
        st.rerun()


def render_student_mode() -> None:
    st.header("학생 학습 경로")
    st.caption("교과·단원을 고른 뒤 AI 튜터와 실습하고, 포트폴리오 PDF로 정리할 수 있습니다.")
    with st.sidebar:
        st.header("학생 설정")
        secret_api_key = st.secrets.get("GEMINI_API_KEY", "")
        if secret_api_key:
            api_key = secret_api_key
            st.success("Streamlit Secrets에서 API 키를 불러왔습니다.")
        else:
            api_key = st.text_input("API 키 입력 (로컬 테스트용)", type="password").strip()
        st.session_state.student_id = st.text_input(
            "학생 ID 또는 이름",
            value=st.session_state.get("student_id") or "학생001",
        )
        st.session_state.student_display_name = st.text_input(
            "표시 이름 (선택)",
            value=st.session_state.get("student_display_name") or st.session_state.student_id,
        )
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
                        append_diagnostic_record(record)
                        st.success("AI 피드백이 생성되었습니다. [AI 피드백] 탭에서 확인해 보세요.")
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
        "diagnostic_records": [],
        "latest_result": "",
        "latest_mode": "학습 모드",
        "latest_symptom": "",
        "latest_generated_at": "",
        "latest_subject": "",
        "latest_unit": "",
        "student_id": "학생001",
        "student_display_name": "학생001",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    if "diagnosis_history" not in st.session_state:
        st.session_state.diagnosis_history = []
    migrate_legacy_history_if_needed()
def render_role_selection() -> None:
    st.title("자동차 전기전자제어 학습지원 시스템")
    st.caption("역할을 선택한 뒤 해당 모드로 진입합니다.")
    choice = st.radio(
        "역할 선택",
        ["교사 모드", "학생 모드"],
        horizontal=True,
        help="선택은 세션 동안 유지되며, 사이드바에서 언제든 변경할 수 있습니다.",
    )
    if st.button("선택한 역할로 시작", type="primary"):
        st.session_state.app_role = "teacher" if choice.startswith("교사") else "student"
        st.rerun()
st.set_page_config(
    page_title="자동차 전기전자제어 학습지원 시스템",
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
        st.rerun()
if st.session_state.app_role == "teacher":
    st.title("자동차 전기전자제어 — 교사 모드")
    render_teacher_mode()
else:
    st.title("자동차 전기전자제어 — 학생 모드")
    render_student_mode()
st.markdown("---")
st.caption("입력한 증상과 측정 데이터를 바탕으로 NCS 수행준거 기반 진단 학습을 진행할 수 있습니다.")

