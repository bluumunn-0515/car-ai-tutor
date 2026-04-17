import re
from datetime import datetime
from pathlib import Path
from typing import Optional

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

# Gemini 모델명은 여기서 한 번에 관리한다.
GEMINI_MODEL_NAME = "gemini-2.0-flash-exp"


st.set_page_config(
    page_title="자동차 전기전자제어 학습지원 시스템",
    page_icon="🚗",
    layout="wide",
)

st.title("자동차 전기전자제어 학습지원 시스템")
st.caption("AI 튜터와 함께 자동차 고장 진단 과정을 학습해보세요.")

if "diagnosis_history" not in st.session_state:
    st.session_state.diagnosis_history = []
if "latest_result" not in st.session_state:
    st.session_state.latest_result = ""
if "latest_mode" not in st.session_state:
    st.session_state.latest_mode = "학습 모드"
if "latest_symptom" not in st.session_state:
    st.session_state.latest_symptom = ""
if "latest_generated_at" not in st.session_state:
    st.session_state.latest_generated_at = ""


def build_learning_prompt(user_symptom: str) -> str:
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    return f"""
너는 특성화고 자동차 전기전자제어 실습 수업을 돕는 AI 튜터다.
아래 NCS 능력단위와 수행준거를 반영하여 학생이 스스로 답을 찾도록 스캐폴딩 방식으로 지도하라.

[NCS 능력단위]
- 자동차 전기전자장치 고장진단
- 자동차 엔진 제어장치 점검
- 자동차 샤시 제어장치 점검

[학생 입력 증상]
{symptom_block}

작성 원칙:
- 친절하고 교육적인 어조
- 정답을 바로 단정하지 말고 힌트와 소크라테스식 질문 포함
- 안전 점검 우선
- 학생이 질문 없이 사진만 올린 경우에도 반드시 대응
- 부품 식별 신뢰도가 낮으면 "신뢰도 낮음"을 명시하고 추가 사진 요청을 먼저 제시
- 추가 사진 요청 시 각도(정면/측면/후면), 거리(근접/중간), 초점(커넥터/라벨/배선)을 구체적으로 안내

다음 형식으로 한국어로 답변:
1) 사진 속 부품 명칭 추정(신뢰도와 함께)
2) 해당 부품의 일반적인 고장 증상과 입력 증상 연결
3) 가장 먼저 해야 할 측정 작업(우선순위 1~3, 안전 주의사항 포함)
4) 멀티미터 측정 위치 안내(리드봉을 어디에 대는지 구체적으로)
5) 추가 촬영 가이드(신뢰도 낮을 때 필수)와 학생 스스로 생각해볼 질문/핵심 정리
""".strip()


def build_evaluation_prompt(user_symptom: str, student_reasoning: str) -> str:
    symptom_block = user_symptom if user_symptom else "학생이 구체적인 질문 없이 부품 사진만 업로드함."
    return f"""
너는 특성화고 자동차 전기전자제어 실습의 평가 코치다.
아래 NCS 능력단위 수행준거에 따라 학생의 진단 논리와 측정 접근을 평가하라.

[NCS 능력단위]
- 자동차 전기전자장치 고장진단
- 자동차 엔진 제어장치 점검
- 자동차 샤시 제어장치 점검

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
    image_file: Optional[st.runtime.uploaded_file_manager.UploadedFile],
    key: str,
) -> str:
    client = genai.Client(api_key=key)

    prompt = (
        build_learning_prompt(user_symptom)
        if mode == "학습 모드"
        else build_evaluation_prompt(user_symptom, student_reasoning)
    )

    parts = [types.Part.from_text(text=prompt)]
    if image_file is not None:
        image_bytes = image_file.getvalue()
        image_mime_type = image_file.type or "image/jpeg"
        # 텍스트-only 입력 또는 비정상 파일 상태에서는 이미지 파트를 만들지 않는다.
        if image_bytes:
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type))

    contents = [types.Content(role="user", parts=parts)]
    try:
        response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=contents)
    except TimeoutError as exc:
        raise RuntimeError(
            "Gemini 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 잠시 후 다시 시도해 주세요."
        ) from exc
    except Exception as exc:
        error_text = str(exc).lower()
        if "timeout" in error_text or "timed out" in error_text or "deadline" in error_text:
            raise RuntimeError(
                "Gemini API 호출 중 타임아웃이 발생했습니다. 입력을 간단히 하거나 잠시 후 다시 시도해 주세요."
            ) from exc
        raise RuntimeError(f"Gemini API 호출 중 오류가 발생했습니다: {exc}") from exc

    return response.text if response and response.text else "응답을 받지 못했습니다. 다시 시도해 주세요."


def split_sections(result_text: str) -> dict:
    pattern = r"(?:^|\n)\s*(1\)|2\)|3\)|4\)|5\))\s*"
    parts = re.split(pattern, result_text)
    sections = {
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
            "부품 명칭 추정",
            "고장 증상 연결",
            "우선 측정 작업",
            "멀티미터 측정 위치",
            "질문/핵심 정리",
        ]
    else:
        titles = [
            "부품 명칭 추정/증상 연결",
            "NCS 기준 진단 분석",
            "보완이 필요한 능력 단위 요소",
            "우선 측정 작업",
            "멀티미터 위치/다음 실습 과제",
        ]

    col1, col2 = st.columns(2)
    with col1:
        st.info(f"### {titles[0]}\n\n{parsed['영역 1'] or '응답 내용 없음'}")
        st.warning(f"### {titles[1]}\n\n{parsed['영역 2'] or '응답 내용 없음'}")
    with col2:
        st.success(f"### {titles[2]}\n\n{parsed['영역 3'] or '응답 내용 없음'}")
        st.markdown(f"### {titles[3]}\n\n{parsed['영역 4'] or '응답 내용 없음'}")
    st.markdown(f"### {titles[4]}\n\n{parsed['영역 5'] or '응답 내용 없음'}")


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
) -> bytes:
    if FPDF is None:
        raise RuntimeError("fpdf2 라이브러리가 필요합니다.")

    parsed = split_sections(result_text)
    sections = [
        ("1) 영역 1", parsed["영역 1"]),
        ("2) 영역 2", parsed["영역 2"]),
        ("3) 영역 3", parsed["영역 3"]),
        ("4) 영역 4", parsed["영역 4"]),
        ("5) 영역 5", parsed["영역 5"]),
    ]

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
        # 배포 환경에서 폰트 등록이 실패해도 PDF 생성은 계속 진행한다.
        pdf.set_font("Helvetica", size=12)

    pdf.multi_cell(0, 8, "자동차 전기전자제어 진단 결과 리포트")
    pdf.ln(2)
    pdf.multi_cell(0, 8, f"진단 일시: {generated_at}")
    pdf.multi_cell(0, 8, f"선택 모드: {mode}")
    pdf.multi_cell(0, 8, f"NCS 성취도 점수: {ncs_score:.1f}%")
    pdf.ln(2)
    pdf.multi_cell(0, 8, "[입력 증상]")
    pdf.multi_cell(0, 8, symptom if symptom else "사진 기반 진단(텍스트 입력 없음)")
    pdf.ln(2)

    pdf.multi_cell(0, 8, "[AI 피드백 5개 영역]")
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


with st.sidebar:
    st.header("설정")
    secret_api_key = st.secrets.get("GEMINI_API_KEY", "")
    manual_api_key = ""
    if secret_api_key:
        api_key = secret_api_key
        st.success("Streamlit Secrets에서 API 키를 불러왔습니다.")
    else:
        manual_api_key = st.text_input("API 키 입력 (로컬 테스트용)", type="password")
        api_key = manual_api_key.strip()
    mode = st.radio("운영 모드 선택", ["학습 모드", "평가 모드"], index=0)
    if not api_key:
        st.info("Gemini API 키를 입력해 주세요.")
    st.markdown("#### 반영 NCS 능력단위")
    for unit in NCS_UNITS:
        st.markdown(f"- {unit}")

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
                    )
                    st.session_state.latest_result = result_text
                    st.session_state.latest_mode = mode
                    st.session_state.latest_symptom = symptom_text.strip()
                    st.session_state.latest_generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.diagnosis_history.append(
                        {
                            "mode": mode,
                            "symptom": symptom_text.strip(),
                            "reasoning": student_reasoning.strip(),
                            "result": result_text,
                        }
                    )
                    st.success("AI 피드백이 생성되었습니다. [AI 피드백] 탭에서 확인해 보세요.")
                except Exception as exc:
                    st.error(f"진단 요청 중 오류가 발생했습니다: {exc}")

with tab_feedback:
    st.subheader("AI 진단 피드백")
    if st.session_state.latest_result:
        st.caption(f"현재 결과 모드: {st.session_state.latest_mode}")
        render_photo_retake_notice(st.session_state.latest_result)
        render_feedback_cards(st.session_state.latest_result, st.session_state.latest_mode)

        st.markdown("---")
        st.markdown("#### 진단 결과 저장")
        if FPDF is None:
            st.info("PDF 저장 기능을 사용하려면 `pip install fpdf2`를 실행해 주세요.")
        else:
            try:
                ncs_data = calculate_ncs_scores(st.session_state.latest_result, st.session_state.latest_mode)
                pdf_bytes = build_pdf_bytes(
                    generated_at=st.session_state.latest_generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    mode=st.session_state.latest_mode,
                    symptom=st.session_state.latest_symptom,
                    result_text=st.session_state.latest_result,
                    ncs_score=ncs_data["overall_rate"],
                )
                st.download_button(
                    "진단 결과 PDF로 저장하기",
                    data=pdf_bytes,
                    file_name=f"diagnosis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
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

st.markdown("### 진단 이력")
if st.session_state.diagnosis_history:
    if st.button("진단 이력 초기화"):
        st.session_state.diagnosis_history = []
        st.session_state.latest_result = ""
        st.rerun()

    for idx, item in enumerate(reversed(st.session_state.diagnosis_history), start=1):
        history_title = item["symptom"][:30] if item["symptom"] else "사진 기반 진단"
        with st.expander(f"이력 {idx} - {item['mode']} - {history_title}..."):
            st.markdown("**입력 증상**")
            st.write(item["symptom"])
            if item.get("reasoning"):
                st.markdown("**학생 진단 논리**")
                st.write(item["reasoning"])
            st.markdown("**AI 진단 피드백**")
            render_feedback_cards(item["result"], item["mode"])
else:
    st.caption("아직 저장된 진단 이력이 없습니다.")

st.markdown("---")
st.write("입력한 증상과 측정 데이터를 바탕으로 NCS 수행준거 기반 진단 학습을 진행할 수 있습니다.")
