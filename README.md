# 자동차 전기전자제어 학습지원 시스템

특성화고 자동차 전기전자제어 실습을 위한 Streamlit 기반 AI 학습지원 앱입니다.  
Gemini 멀티모달 API(`google-genai`)를 사용해 텍스트/이미지 기반 진단 피드백을 제공합니다.

## 1) 설치

```bash
pip install -r requirements.txt
```

## 2) 실행

```bash
streamlit run app.py
```

## 3) API 키 설정

### 배포 환경 (권장)

Streamlit Secrets에 `GEMINI_API_KEY`를 설정하면 앱이 해당 키를 우선 사용합니다.

예시 파일: `.streamlit/secrets.toml.example`

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
```

실사용 시에는 위 예시를 참고해 `.streamlit/secrets.toml` 파일을 만들고 실제 키를 입력하세요.
`.streamlit/secrets.toml`은 `.gitignore`에 포함되어 저장소에 커밋되지 않습니다.

### 로컬 테스트

`st.secrets`에 `GEMINI_API_KEY`가 없으면, 기존처럼 사이드바의 비밀번호 입력창에서 API 키를 직접 입력해 사용할 수 있습니다.

## 4) 사용 방법

1. `학습 모드` 또는 `평가 모드`를 선택합니다.
2. `진단 입력` 탭에서 고장 증상 또는 부품 사진(둘 중 하나 이상)을 입력합니다.
3. 필요 시 평가 모드에서 학생 진단 논리를 추가 입력합니다.
4. `AI 진단 피드백 생성` 버튼을 눌러 결과를 확인합니다.

## 5) 주요 기능

- NCS 능력단위 반영 피드백
  - 자동차 전기전자장치 고장진단
  - 자동차 엔진 제어장치 점검
  - 자동차 샤시 제어장치 점검
- 학습/평가 모드 분리
- 이미지 기반 부품 식별 및 측정 위치 안내
- NCS 루브릭 기반 성취도 분석

## 6) 의존성

- `streamlit`
- `google-genai`
