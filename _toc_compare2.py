import re
from pathlib import Path

text = Path(r"C:\Users\user\Documents\car-diagnostic-app\_pdf_pages.txt").read_text(encoding="utf-8")
pages = []
for m in re.finditer(r"===== PAGE (\d+) =====\n(.*?)(?=\n===== PAGE |\Z)", text, re.S):
    pdf_page = int(m.group(1))
    content = m.group(2).strip()
    body_page = None
    lines = content.split("\n")
    if lines and re.fullmatch(r"\d+", lines[0].strip()):
        body_page = int(lines[0].strip())
    pages.append({"pdf": pdf_page, "body": body_page, "content": content})

# Unique anchors - first occurrence in body
anchors = [
    ("국문초록", "국 문 초 록"),
    ("Ⅰ. 서론", "Ⅰ. 서론"),
    ("2. 프로젝트 목표 및 내용", "2. 프로젝트 목표 및 내용"),
    ("3. 용어의 정의", "3. 용어의 정의"),
    ("가. 생성형 AI", "  가. 생성형 AI"),
    ("라. 가이드레일과 AI 찬스", "  라. 가이드레일과 AI 찬스"),
    ("마. 소크라테스식 발문", "  마. 소크라테스식 발문"),
    ("Ⅱ. 프로젝트의 배경", "Ⅱ. 프로젝트의 배경"),
    ("나. 자동차 전기·전자 제어 실기 교육", "  나. 자동차 전기·전자 제어 실기 교육"),
    ("다. AI 기반 학습지원 앱", "  다. AI 기반 학습지원 앱"),
    ("2) AI 기반 학습지원 앱의 유형과 기능", "    2) AI 기반 학습지원 앱의 유형과 기능"),
    ("3) AI 기반 학습지원 앱 관련 선행 연구 고찰", "    3) AI 기반 학습지원 앱 관련 선행 연구 고찰"),
    ("2. 프로젝트 관련 기술 및 시스템 동향", "  2. 프로젝트 관련 기술 및 시스템 동향"),
    ("가. 멀티모달 생성형 AI", "    가. 멀티모달 생성형 AI"),
    ("나. 프롬프트 내장형 도메인 지식", "    나. 프롬프트 내장형 도메인 지식"),
    ("다. 생성형 AI 기반 실시간 피드백", "    다. 생성형 AI 기반 실시간 피드백"),
    ("라. 생성형 AI 기반 학습 활동 분석", "    라. 생성형 AI 기반 학습 활동 분석"),
    ("Ⅲ. 프로젝트 방법", "Ⅲ. 프로젝트 방법"),
    ("1. 프로젝트 모형", "  1. 프로젝트 모형"),
    ("2. 프로젝트 개발 도구", "  2. 프로젝트 개발 도구"),
    ("3. 프로젝트 적용 대상", "  3. 프로젝트 적용 대상"),
    ("4. 프로젝트 개발 방법론 및 산출물", "  4. 프로젝트 개발 방법론 및 산출물"),
    ("5. 프로젝트 결과물 효과성 검증 방법", "  5. 프로젝트 결과물 효과성 검증 방법"),
    ("Ⅳ. 프로젝트 결과", "Ⅳ. 프로젝트 결과"),
    ("1. 프로그램 설계 및 개발 결과", "  1. 프로그램 설계 및 개발 결과"),
    ("2. 프로젝트 결과물 효과성 검증", "  2. 프로젝트 결과물 효과성 검증"),
    ("Ⅴ. 결론 및 제언", "Ⅴ. 결론 및 제언"),
    ("2. 프로젝트의 한계점 및 제언", "  2. 프로젝트의 한계점 및 제언"),
    ("참고문헌", "참 고 문 헌"),
    ("<표 4>", "<표 4>"),
    ("[그림 5]", "[그림 5]"),
    ("[그림 6]", "[그림 6]"),
    ("[그림 7]", "[그림 7]"),
    ("[그림 8]", "[그림 8]"),
    ("[그림 9]", "[그림 9]"),
    ("[그림 10]", "[그림 10]"),
    ("[그림 11]", "[그림 11]"),
    ("[그림 13]", "[그림 13]"),
    ("[그림 14]", "[그림 14]"),
    ("[그림 24]", "[그림 24]"),
    ("[그림 25]", "[그림 25]"),
]

found = {}
for name, key in anchors:
    for p in pages:
        if p["body"] is None:
            continue
        if key in p["content"]:
            found[name] = p["body"]
            break

# TOC from document
TOC = {
    "국문초록": 7,  # vii in roman - user sees vii
    "Ⅰ. 서론": 1,
    "2. 프로젝트 목표 및 내용": 3,
    "3. 용어의 정의": 5,
    "가. 생성형 AI": 5,
    "라. 가이드레일과 AI 찬스": 6,
    "마. 소크라테스식 발문": 6,
    "Ⅱ. 프로젝트의 배경": 7,
    "나. 자동차 전기·전자 제어 실기 교육": 10,
    "다. AI 기반 학습지원 앱": 13,
    "2) AI 기반 학습지원 앱의 유형과 기능": 19,
    "3) AI 기반 학습지원 앱 관련 선행 연구 고찰": 21,
    "2. 프로젝트 관련 기술 및 시스템 동향": 23,
    "가. 멀티모달 생성형 AI": 23,
    "나. 프롬프트 내장형 도메인 지식": 24,
    "다. 생성형 AI 기반 실시간 피드백": 25,
    "라. 생성형 AI 기반 학습 활동 분석": 25,
    "Ⅲ. 프로젝트 방법": 27,
    "1. 프로젝트 모형": 25,  # TOC error - listed as 25 under III but III is 27
    "2. 프로젝트 개발 도구": 26,
    "3. 프로젝트 적용 대상": 30,
    "4. 프로젝트 개발 방법론 및 산출물": 30,
    "5. 프로젝트 결과물 효과성 검증 방법": 36,
    "Ⅳ. 프로젝트 결과": 42,
    "1. 프로그램 설계 및 개발 결과": 42,
    "2. 프로젝트 결과물 효과성 검증": 56,
    "Ⅴ. 결론 및 제언": 62,
    "2. 프로젝트의 한계점 및 제언": 63,
    "참고문헌": 97,
    "<표 4>": 35,
    "[그림 5]": 28,
    "[그림 6]": 30,
    "[그림 7]": 32,
    "[그림 8]": 36,
    "[그림 9]": 37,
    "[그림 10]": 42,
    "[그림 11]": 49,
    "[그림 13]": 51,
    "[그림 14]": 54,
    "[그림 24]": None,
    "[그림 25]": None,
}

print(f"{'항목':<45} {'목차':>4} {'본문':>4} {'차이':>5}")
print("-" * 62)
for k, toc in TOC.items():
    act = found.get(k)
    if act is None:
        print(f"{k:<45} {str(toc):>4} {'?':>4} {'N/A':>5}")
        continue
    if toc is None:
        print(f"{k:<45} {'없음':>4} {act:>4} {'누락':>5}")
        continue
    d = act - toc
    mark = "OK" if d == 0 else "!!"
    print(f"{mark} {k:<42} {toc:>4} {act:>4} {d:>+5}")

# Detect systematic offset from III onward
print("\n--- Systematic pattern ---")
pairs = [(k, TOC[k], found[k], found[k]-TOC[k]) for k in TOC if k in found and TOC[k] is not None]
for k,t,a,d in pairs:
    if d != 0:
        pass

# Count offset after chapter III
ch3_items = [d for k,d in pairs if found[k] >= 27 and TOC[k] >= 27]
if ch3_items:
    from collections import Counter
    c = Counter([d for _,t,a,d in pairs if t>=42])
    print("Offset for TOC>=42:", dict(c))
