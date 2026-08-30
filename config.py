# -*- coding: utf-8 -*-
"""
config.py — AGI 설정. 네가 직접 고치는 곳.
"""
import os

# ── 학습 데이터: AGI 폴더 안에 둔다(경로 지정 대상 아님) ──
# 아기가 배운 기억·캐시는 이 AGI 파일들과 같은 폴더 안에 저장된다.
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "agi_data")   # AGI 폴더 안. 건드리지 않아도 됨.

def data_path(name):
    p = os.path.join(DATA_DIR, name)
    os.makedirs(p, exist_ok=True)
    return p

# ── 프로그램 설치 경로 (네가 지정) ──
# 이 AGI를 돌리는 데 필요한 '프로그램'(브라우저, OCR 등)이 깔릴 곳.
# 인스톨 파일이 이 경로에 설치한다. 원하는 경로로 바꿔라.
#   예) 윈도우:  r"D:\AGI_programs"     맥/리눅스: "/opt/agi_programs"
INSTALL_DIR = os.environ.get("AGI_INSTALL_DIR",
                             os.path.join(HERE, "programs"))

# playwright 브라우저가 깔릴 경로(이 경로로 환경변수 설정해 설치)
BROWSER_DIR = os.path.join(INSTALL_DIR, "browsers")

# ── 검색엔진 (여러 개 — 하나 막히면 다음으로) ──
SEARCH_ENGINES = ["google", "bing", "duckduckgo", "naver"]

# ── 로그인 계정 (회원가입한 사이트, 어려운 곳 들어가기용) ──
# 네가 만든 계정을 여기 넣으면 그 사이트에 로그인해서 들어간다.
#   예) ACCOUNTS = {"naver.com": {"id":"내아이디", "pw":"내비번"}}
ACCOUNTS = {
    # "사이트도메인": {"id": "...", "pw": "..."},
}

# ── 화면 보는 방식 / 행동 ──
SEE_LIKE_HUMAN = True   # True면 스크린샷+OCR로 사람처럼 화면 보기(OCR 설치 필요)
HUMAN_LIKE = True        # 사람처럼 마우스·스크롤·대기(캡차 회피 확률↑)
SHOW_BROWSER = True      # 사람처럼 진짜 브라우저 창이 뜬다(네 컴퓨터). 창을 못 띄우면 자동으로 화면만.

# ── VirusTotal 검사 (안전 필터에 추가) ──
# 사이트를 열기 전에 VirusTotal(70여 개 백신)로도 검사한다.
# 쓰려면 무료 API 키가 필요하다:
#   1) https://www.virustotal.com 가입
#   2) 로그인 후 우측 상단 이름 > API key 복사
#   3) 아래에 붙여넣기 (또는 환경변수 VT_API_KEY 로 설정)
# 무료 제한: 하루 500회, 분당 4회. 그래서 정적 필터를 통과한 URL만 검사한다.
# 키가 비어 있으면 VirusTotal 검사는 꺼지고, 기존 정적 필터만 동작한다.
VIRUSTOTAL_API_KEY = ""
# 악성 판정 엔진이 몇 개 이상이면 위험으로 볼지(1이면 한 개만 걸려도 막음)
VIRUSTOTAL_MALICIOUS_THRESHOLD = 1
# VirusTotal을 사람처럼(브라우저로 사이트 방문) 검사할지. True=사람 방식 우선.
# 브라우저 검사가 실패하면 자동으로 API로 넘어간다(API 키가 있을 때).
VIRUSTOTAL_USE_BROWSER = True
# VirusTotal 검사 자체를 켤지/끌지. 너무 느리면 False로 끄면 된다
# (그래도 위험파일·유튜브·생IP·의심도메인·URLhaus 정적 필터는 계속 동작).
VIRUSTOTAL_ENABLE = True
