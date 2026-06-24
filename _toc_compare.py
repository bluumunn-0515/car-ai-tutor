import re
from pathlib import Path

text = Path(r"C:\Users\user\Documents\car-diagnostic-app\_pdf_pages.txt").read_text(encoding="utf-8")
pages = {}
for m in re.finditer(r"===== PAGE (\d+) =====\n(.*?)(?=\n===== PAGE |\Z)", text, re.S):
    pdf_page = int(m.group(1))
    content = m.group(2).strip()
    body_page = None
    lines = content.split("\n")
    if lines and re.fullmatch(r"\d+", lines[0].strip()):
        body_page = int(lines[0].strip())
    pages[pdf_page] = {"content": content, "body_page": body_page, "pdf_page": pdf_page}

# Manual TOC from pages 5-7 (more reliable than regex split)
TOC_SECTIONS = [
    ("Ⅰ. 서론", 1),
    ("1. 프로젝트의 필요성 및 목적", 1),
    ("2. 프로젝트 목표 및 내용", 3),
    ("3. 용어의 정의", 5),
    ("가. 생성형 AI", 5),
    ("나. 자동차 고장진단", 5),
    ("다. 학습지원 앱", 5),
    ("라. 가이드레일과 AI 찬스", 6),
    ("마. 소크라테스식 발문", 6),
    ("Ⅱ. 프로젝트의 배경", 7),
    ("1. 프로젝트 관련 이론", 7),
    ("가. 특성화고 자동차 교과 교육", 7),
    ("1) 특성화고 자동차 교과 교육의 현황과 이슈", 7),
    ("2) 특성화고 자동차 교과 교육 관련 선행 연구", 9),
    ("나. 자동차 전기·전자 제어 실기 교육", 10),
    ("1) 자동차 전기·전자 제어 실기 교육의 현황과 이슈", 10),
    ("2) NCS 기반 자동차 전기·전자장치 정비 직무능력", 11),
    ("3) 자동차 전기·전자 제어 실기 교육 관련 선행 연구", 12),
    ("다. AI 기반 학습지원 앱", 13),
    ("1) AI와 학습지원", 13),
    ("2) AI 기반 학습지원 앱의 유형과 기능", 19),
    ("3) AI 기반 학습지원 앱 관련 선행 연구 고찰", 21),
    ("2. 프로젝트 관련 기술 및 시스템 동향", 23),
    ("가. 멀티모달 생성형 AI와 비전·언어 통합 처리 기술", 23),
    ("나. 프롬프트 내장형 도메인 지식과 정답 비교 기술", 24),
    ("다. 생성형 AI 기반 실시간 피드백 시스템", 25),
    ("라. 생성형 AI 기반 학습 활동 분석 시스템", 25),
    ("Ⅲ. 프로젝트 방법", 27),
    ("1. 프로젝트 모형", 25),  # TOC says 25 - likely wrong
    ("2. 프로젝트 개발 도구", 26),
    ("3. 프로젝트 적용 대상", 30),
    ("4. 프로젝트 개발 방법론 및 산출물", 30),
    ("가. 요구사항 분석", 31),
    ("나. 설계", 33),
    ("다. 구현", 34),
    ("라. 테스트", 35),
    ("마. 운영 및 유지보수", 36),
    ("5. 프로젝트 결과물 효과성 검증 방법", 36),
    ("가. 형성평가", 36),
    ("나. 교사 인터뷰", 38),
    ("다. 학생 설문조사", 39),
    ("Ⅳ. 프로젝트 결과", 42),
    ("1. 프로그램 설계 및 개발 결과", 42),
    ("가. 시스템 전체 흐름 및 화면 구성 결과", 43),
    ("나. NCS 단원 선택 및 진단 입력 기능 구현 결과", 44),
    ("다. 소크라테스식 발문 구현 결과", 45),
    ("라. 4단계 미션 카드 기반 스캐폴딩 기능 구현 결과", 45),
    ("마. AI 찬스 메커니즘 구현 결과", 48),
    ("바. NCS 루브릭 기반 자동 평가 기능 구현 결과", 50),
    ("사. 교사 모드 및 누적 포트폴리오 PDF 구현 결과", 52),
    ("아. 학습 활동 분석 대시보드 구현 결과", 55),
    ("2. 프로젝트 결과물 효과성 검증 결과", 56),
    ("가. 형성평가", 57),
    ("나. 교사 인터뷰", 58),
    ("다. 학생 설문조사", 59),
    ("Ⅴ. 결론 및 제언", 62),
    ("1. 프로젝트 결론 및 시사점", 62),
    ("2. 프로젝트의 한계점 및 제언", 63),
    ("참고문헌", 97),
]

TOC_TABLES = [
    ("<표 1>", 11),
    ("<표 2>", 15),
    ("<표 3>", 17),
    ("<표 4>", 35),
    ("<표 5>", 39),
    ("<표 6>", 44),
    ("<표 7>", 45),
    ("<표 8>", 47),
    ("<표 9>", 65),
    ("<표 10>", 67),
    ("<표 11>", 69),
]

TOC_FIGURES = [
    ("[그림 1]", 8),
    ("[그림 2]", 14),
    ("[그림 3]", 18),
    ("[그림 4]", 19),
    ("[그림 5]", 28),
    ("[그림 6]", 30),
    ("[그림 7]", 32),
    ("[그림 8]", 36),
    ("[그림 9]", 37),
    ("[그림 10]", 42),
    ("[그림 11]", 49),
    ("[그림 12]", 49),
    ("[그림 13]", 51),
    ("[그림 14]", 54),
    ("[그림 15]", 55),
    ("[그림 16]", 56),
    ("[그림 17]", 57),
    ("[그림 18]", 59),
    ("[그림 19]", 60),
    ("[그림 20]", 61),
    ("[그림 21]", 62),
    ("[그림 22]", 63),
    ("[그림 23]", 64),
    ("[그림 24]", None),
    ("[그림 25]", None),
    ("[그림 26]", None),
    ("[그림 27]", None),
    ("[그림 28]", None),
    ("[그림 29]", None),
]

body_pages = [(p, d) for p, d in sorted(pages.items()) if d["body_page"] is not None]


def norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = s.replace("·", "").replace("–", "-").replace("—", "-")
    return s


def find_section(title: str):
    search = title
    search = search.replace("·", "")
    variants = [search, search.replace("전기·전자", "전기전자"), search.replace("전기·전자", "전기·전자")]
    if title.startswith("1. ") or title.startswith("2. ") or title.startswith("3. "):
        variants.append(title[3:])
    if re.match(r"^[가-힣]\.", title):
        variants.append(title.split(".", 1)[-1].strip())

    for pdf_p, d in body_pages:
        c = d["content"]
        cn = norm(c)
        for v in variants:
            if not v:
                continue
            if v in c or norm(v) in cn:
                return d["body_page"], pdf_p
    return None, None


def find_label(label: str):
    for pdf_p, d in body_pages:
        if label in d["content"]:
            return d["body_page"], pdf_p
    return None, None


print("=" * 90)
print("본문 장·절 목차 vs 실제 페이지 (부록 제외)")
print("=" * 90)
mismatches = []
for title, toc_page in TOC_SECTIONS:
    if title == "참고문헌":
        actual, pdf_p = None, None
        for p, d in pages.items():
            if "참 고 문 헌" in d["content"] or d["content"].startswith("참 고 문 헌"):
                actual, pdf_p = d["body_page"], p
                break
    else:
        actual, pdf_p = find_section(title)
    diff = actual - toc_page if actual is not None else None
    status = "OK" if diff == 0 else "DIFF"
    if diff != 0:
        mismatches.append(("section", title, toc_page, actual, diff))
    print(f"{status:4} | TOC {toc_page:3} | ACT {str(actual):>3} | {diff if diff is not None else 'N/A':>4} | {title}")

print("\n" + "=" * 90)
print("표 목차 vs 실제")
print("=" * 90)
for label, toc_page in TOC_TABLES:
    actual, pdf_p = find_label(label)
    diff = actual - toc_page if actual is not None else None
    status = "OK" if diff == 0 else "DIFF"
    if diff != 0:
        mismatches.append(("table", label, toc_page, actual, diff))
    print(f"{status:4} | TOC {toc_page:3} | ACT {str(actual):>3} | {diff if diff is not None else 'N/A':>4} | {label}")

print("\n" + "=" * 90)
print("그림 목차 vs 실제")
print("=" * 90)
for label, toc_page in TOC_FIGURES:
    actual, pdf_p = find_label(label)
    if toc_page is None:
        print(f"MISS | TOC --- | ACT {str(actual):>3} | N/A  | {label} (목차 페이지 번호 없음)")
        mismatches.append(("figure", label, None, actual, "no_toc_page"))
        continue
    diff = actual - toc_page if actual is not None else None
    status = "OK" if diff == 0 else "DIFF"
    if diff != 0:
        mismatches.append(("figure", label, toc_page, actual, diff))
    print(f"{status:4} | TOC {toc_page:3} | ACT {str(actual):>3} | {diff if diff is not None else 'N/A':>4} | {label}")

print("\n" + "=" * 90)
print(f"총 불일치: {len(mismatches)}건")
print("=" * 90)
