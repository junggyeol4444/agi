# -*- coding: utf-8 -*-
"""
browser_search.py — 진짜 브라우저를 '사람처럼' 운전해서 검색·조사한다.

핵심:
  1) 프로그램이 직접 긁으면(urllib) 봇으로 막힌다.
     → Playwright로 진짜 크롬을 띄워 사람이 검색·클릭·읽듯 조작한다.
  2) 미리 박은 패턴이 아니라, 접속 후 렌더링된 실제 페이지에서 그때 구조를
     파악해 본문·링크를 뽑는다 → 사이트 구조가 바뀌어도 견딘다.
  3) (캡차 대비) 화면을 '인간이 보는 방식'으로 본다:
     - 사람처럼 마우스 곡선 이동·사람 속도 스크롤·랜덤 대기 (HUMAN_LIKE)
     - 옵션: HTML을 읽지 않고 스크린샷을 찍어 OCR로 화면 글자를 읽음 (SEE_LIKE_HUMAN)
       → 학습(처리)은 기계가 빠르게, 화면을 받는 입구만 사람처럼.
  ※ 캡차를 100% 막진 못한다(사람이 들어가도 체크함). 걸릴 확률을 낮출 뿐.

필요(네 컴퓨터): playwright(+chromium). SEE_LIKE_HUMAN이면 tesseract OCR도.
※ AI 작업환경은 브라우저/네트워크/GUI 막혀 실제 실행 불가 → 네 컴퓨터에서 작동.
"""
import random
import time

try:
    import config
    HUMAN_LIKE = config.HUMAN_LIKE
    SEE_LIKE_HUMAN = config.SEE_LIKE_HUMAN
    SHOW_BROWSER = config.SHOW_BROWSER
except Exception:
    HUMAN_LIKE = True
    SEE_LIKE_HUMAN = False
    SHOW_BROWSER = False
    config = None


# ── 속도 배율 ──
#  사람처럼 '한 화면씩 눈으로' 보는 순서는 그대로 두되(봇처럼 코드 긁기·동시
#  병렬 아님), 사람의 '동작 속도'만 빠르게 한다. 값이 작을수록 빠르다.
#  1.0=예전(굼뜬 사람), 0.15=빠르게 훑는 사람. 캡차에 더 걸리면 값을 키워라.
SPEED = 0.15


# ── 사람처럼 '결과가 나오는지 보고 판단' ──
#  AI식으로 '정해진 시간 세고 넘어가기'가 아니다. 사람은 화면을 지켜보다가
#  결과가 나타나면 읽고, 안 나오면 다음 세 경우에만 '안 나온다'고 판단한다:
#    (1) 인터넷 연결 없음 화면   (2) 2분 넘게 결과가 안 뜸   (3) 오류
#  그 셋이 아니면 결과가 나타날 때까지 계속 지켜본다.
WATCH_MAX_SEC = 120   # 2분 — 사람이 '이건 안 되나 보다' 하고 포기하는 한계

def _looks_offline(page):
    """지금 화면이 '인터넷 연결 없음' 화면인가 (크롬 오프라인/연결 실패 화면)."""
    try:
        # 크롬 오류 페이지는 chrome-error:// 로 뜬다
        if str(page.url).startswith("chrome-error://"):
            return True
        # 브라우저가 온라인이 아니라고 하면 연결 없음
        online = page.evaluate("() => navigator.onLine")
        if online is False:
            return True
        # 크롬 오프라인 화면의 대표 오류코드/문구
        body = ""
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        except Exception:
            body = ""
        for k in ["ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED",
                  "ERR_CONNECTION", "인터넷에 연결할 수 없", "No internet",
                  "This site can’t be reached", "사이트에 연결할 수 없"]:
            if k in body:
                return True
    except Exception:
        pass
    return False

def _watch_until(page, is_ready, max_sec=WATCH_MAX_SEC):
    """결과가 나올 때까지 화면을 지켜본다(사람처럼).
       is_ready(page)->bool: 화면에 '결과'가 나타났으면 True.
       반환: ("ready", None) 결과 나옴 / ("offline", 이유) 인터넷없음 /
             ("timeout", 이유) 2분 초과 / ("error", 이유) 오류.
       0.5초마다 '보기만' 한다(스크린샷 비교·OCR 스캔이 아니라, 결과가
       화면에 떴는지 한 번 확인하는 것 = 사람이 흘깃 보는 것)."""
    import time as _t
    start = _t.time()
    while True:
        # (3) 오류: 화면 자체를 못 읽는 상태면 오류로 본다
        try:
            if _looks_offline(page):            # (1) 인터넷 없음
                return "offline", "인터넷 연결 없음 화면"
        except Exception as e:
            return "error", f"화면 확인 오류: {type(e).__name__}"
        # 결과가 나왔나 (사람이 화면 보고 '떴다' 판단)
        try:
            if is_ready(page):
                return "ready", None
        except Exception:
            pass
        # (2) 2분 넘으면 포기
        if _t.time() - start > max_sec:
            return "timeout", f"{int(max_sec)}초 넘게 결과가 안 뜸"
        page.wait_for_timeout(500)   # 잠깐 있다 다시 흘깃 본다


# ── 봇차단 대응: 동의/쿠키/개인정보 배너 자동 닫기 ──
#  검색엔진·사이트가 "쿠키 동의/개인정보 동의" 배너로 막는 일이 많다.
#  사람이 '동의' 눌러 넘어가듯, 그 버튼을 찾아 눌러 준다(못 찾으면 조용히 지나감).
_CONSENT_WORDS = [
    "모두 수락", "모두 허용", "전체 동의", "전체 허용", "동의", "수락", "허용", "확인",
    "계속", "닫기", "I agree", "Accept all", "Accept", "Agree", "Allow all",
    "Allow", "Got it", "Continue", "同意", "承諾",
]
def _dismiss_banners(page):
    """화면에 동의/쿠키 배너가 있으면 그 버튼을 눌러 닫는다(사람처럼).
       버튼/역할 요소를 글자로 찾아 첫 번째만 누른다. 없으면 아무것도 안 함."""
    try:
        clicked = False
        # 1) 버튼·역할버튼·링크 중에서 동의류 글자를 가진 것 찾기
        cands = []
        for sel in ["button", "[role=button]", "a", "input[type=button]", "input[type=submit]"]:
            try:
                cands.extend(page.query_selector_all(sel))
            except Exception:
                pass
        for el in cands[:120]:
            try:
                if not el.is_visible():
                    continue
                txt = (el.inner_text() or el.get_attribute("value") or "").strip()
                if not txt or len(txt) > 24:
                    continue
                if any(w.lower() == txt.lower() or w in txt for w in _CONSENT_WORDS):
                    el.click(timeout=2000)
                    clicked = True
                    _now(doing=f"🖱 동의/쿠키 배너 닫음('{txt[:12]}')")
                    page.wait_for_timeout(400)
                    break
            except Exception:
                continue
        return clicked
    except Exception:
        return False


def _has_search_results(page):
    """검색 결과가 실제로 화면에 떴는가(캡차/동의창이 아니라 결과인가) 판단.
       엔진별 결과 컨테이너 셀렉터를 우선 보고, 없으면 http 링크 개수로 대충 판단."""
    try:
        sels = ["#b_results", "#search a", ".b_algo", ".result", ".g",
                "ol#b_results", "[data-testid=result]", ".sa_conts", ".lst_total"]
        for s in sels:
            try:
                if page.query_selector(s):
                    return True
            except Exception:
                pass
        # 폴백: 외부 http 링크가 여러 개면 결과 화면으로 본다
        n = page.evaluate(
            "() => [...document.querySelectorAll('a[href^=\"http\"]')].length")
        return bool(n and n >= 8)
    except Exception:
        return False


# ── 광고·페이월·쓰레기 텍스트 걸러내기 ──
#  사람도 '로그인하세요/구독/쿠키 동의/광고' 같은 건 '내용'으로 안 배운다.
#  정답표가 아니라 '이건 글이 아니라 껍데기'라는 패턴. 학습 전에 버린다.
_JUNK_PAT = [
    "로그인", "회원가입", "구독하", "구독 신청", "무료체험", "무료 체험",
    "쿠키", "cookie", "개인정보처리방침", "이용약관", "저작권", "copyright",
    "광고", "sponsored", "스폰서", "프리미엄 결제", "결제하", "구매하기",
    "sign in", "log in", "subscribe", "newsletter", "advertisement",
    "댓글을 남기", "앱에서 열기", "알림 설정", "더보기", "자세히 보기",
]
def _is_junk_text(t):
    """이 문단이 내용이 아니라 광고/페이월/안내 껍데기인가."""
    if not t:
        return True
    low = t.lower().strip()
    # 너무 짧거나(버튼 라벨 등) 특정 껍데기 단어 위주면 버린다
    if len(low) < 25:
        return True
    hit = sum(1 for k in _JUNK_PAT if k in low)
    # 짧은 문단에 껍데기 단어가 있거나, 여러 개 겹치면 쓰레기로 본다
    if hit >= 2:
        return True
    if hit >= 1 and len(low) < 60:
        return True
    return False


def _human_pause(a=0.4, b=1.4):
    """사람처럼 잠깐 멈춤(랜덤). 단, 빠르게 훑는 사람 속도로(SPEED 배).
       (봇차단 대응) 매번 같은 리듬이면 봇 티가 난다 — 편차를 크게 두고,
       가끔(약 12%) '뭔가 읽느라 오래 멈추는' 긴 정지를 섞는다."""
    base = random.uniform(a, b)
    # 사람의 반응시간은 한쪽으로 치우친 분포에 가깝다 — 짧은 게 많고 가끔 길다
    jitter = random.random() ** 2      # 0~1, 대체로 작고 가끔 큼
    dur = base * (0.6 + jitter)        # 폭을 넓힌다
    if random.random() < 0.12:         # 가끔 길게 멈춤(읽는 척)
        dur += random.uniform(0.8, 2.0)
    time.sleep(dur * SPEED)


def _human_mouse(page):
    """사람처럼 마우스를 곡선으로 움직인다(봇은 직선·즉각이라 들킴).
       곡선 이동 자체는 사람다움이라 유지하되, 빠르게 움직인다."""
    try:
        for _ in range(random.randint(1, 2)):   # 횟수도 줄여 빠르게
            x = random.randint(100, 1100)
            y = random.randint(100, 700)
            page.mouse.move(x, y, steps=random.randint(3, 8))
            _human_pause(0.1, 0.4)
    except Exception:
        pass


def _human_scroll(page):
    """사람처럼 위에서 아래로 스크롤하며 읽는다(한 화면씩). 빠르게 훑는 속도로."""
    try:
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, random.randint(400, 900))   # 한 번에 더 많이
            _human_pause(0.2, 0.6)
    except Exception:
        pass



# playwright(진짜 브라우저)가 설치돼 있나 — 진단용
try:
    import playwright  # noqa
    _PLAYWRIGHT_OK = True
except Exception:
    _PLAYWRIGHT_OK = False

# ── 브라우저 실황: 아이가 '지금 뭘 보고 있는지'를 화면(오른쪽 패널)에 보여주기 위한 상태 ──
import os as _os
try:
    import safety
except Exception:
    safety=None
SHOT_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "browser_view.png")
NOW = {"doing": "대기 중", "url": None, "title": None, "shot": False, "t": 0}
LAST_DIAG = None  # 마지막 접속 실패 이유(원인 파악용)

def _now(**kw):
    """지금 뭐 하는지 갱신 (화면 패널이 읽어감)."""
    NOW.update(kw)
    NOW["t"] = time.time()

def _snap(page):
    """브라우저 화면을 한 장 찍어 둔다(패널에 보여줄 용도, 한 장만 덮어씀)."""
    try:
        page.screenshot(path=SHOT_PATH)
        NOW["shot"] = True
    except Exception:
        pass

def now():
    """화면 패널용: 지금 브라우저가 뭘 하는지 + 화면이 있는지."""
    d = dict(NOW)
    d["shot"] = bool(d.get("shot")) and _os.path.exists(SHOT_PATH)
    d["playwright"] = _PLAYWRIGHT_OK
    return d

def _make_browser():
    # 설치 스크립트가 크로미움을 프로그램 폴더(programs/browsers)에 넣는다.
    # 실행 때 그 경로를 playwright에 알려줘야 브라우저를 찾는다(안 하면 조용히 실패).
    _bdir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "programs", "browsers")
    if _os.path.isdir(_bdir):
        _os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _bdir)
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    # 사람처럼 '진짜 창'을 띄운다(SHOW_BROWSER=True). 창을 못 띄우는 환경이면
    # 화면(스크린샷)만이라도 나오게 headless로 자동 전환한다.
    _args = ["--no-sandbox", "--disable-blink-features=AutomationControlled",
             "--start-maximized"]
    try:
        browser = pw.chromium.launch(headless=not SHOW_BROWSER, args=_args)
    except Exception:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"),
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
    )
    return pw, browser, ctx


_OCR_WARNED = False   # OCR 라이브러리 없음 경고를 한 번만 띄우기 위한 표시

def _see_screen_text(page):
    """화면을 '사람처럼' 본다: 스크린샷을 찍어 OCR로 글자를 읽는다.
       HTML 코드를 읽는 게 아니라 그려진 화면을 본다(캡차 회피에 유리).
       라이브러리(PIL·pytesseract·tesseract 본체)가 없으면 '조용히 None'이 아니라
       패널에 딱 한 번 경고를 띄운다 — 안 그러면 OCR이 죽은 걸 아무도 모른다."""
    global _OCR_WARNED
    # 1) 라이브러리 미설치는 '사용자가 조치해야 할 것'이라 실제 오류와 구분해 알린다
    try:
        import io  # noqa
        from PIL import Image  # noqa
        import pytesseract  # noqa
    except Exception as ie:
        if not _OCR_WARNED:
            _OCR_WARNED = True
            global LAST_DIAG
            LAST_DIAG = (f"OCR 라이브러리 없음({type(ie).__name__}) — "
                         "화면 글자 읽기(사람처럼 보기)가 꺼진 채로 돕니다")
            _now(doing="⚠️ OCR 라이브러리 없음 — pip install pillow pytesseract + "
                       "tesseract 본체 설치 필요(화면 글자 읽기 비활성). HTML 텍스트로 대체 진행")
        return None
    # 2) 라이브러리는 있는데 실제 인식이 실패한 경우(스샷 오류·tesseract 실행 실패 등)
    try:
        import io
        from PIL import Image
        import pytesseract
        png = page.screenshot(full_page=True)
        img = Image.open(io.BytesIO(png))
        # 한국어+영어 화면 글자 인식
        text = pytesseract.image_to_string(img, lang="kor+eng")
        return text
    except Exception as e:
        if not _OCR_WARNED:
            _OCR_WARNED = True
            _now(doing=f"⚠️ 화면 글자 읽기 실패({type(e).__name__}) — "
                       "tesseract 본체가 없거나 실행 불가일 수 있음. HTML 텍스트로 대체 진행")
        return None


# 검색엔진별 검색 URL
_ENGINE_URL = {
    "google":     "https://www.google.com/search?q=",
    "bing":       "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "naver":      "https://search.naver.com/search.naver?query=",
}

# (봇차단 대응) 엔진별 '최근에 결과를 잘 줬나' 점수. 잘 주면 ↑, 0건/실패면 ↓.
#  다음 검색 때 점수 높은 엔진부터 돌린다(막힌 엔진은 뒤로 미룸). 세션 동안만 유지.
_ENGINE_SCORE = {}
def _engine_note(engine, got):
    """이 엔진이 이번에 결과를 줬는지 기록. got=결과 개수."""
    s = _ENGINE_SCORE.get(engine, 0.0)
    if got > 0:
        s = min(s + 1.0, 5.0)      # 잘 주면 가점(상한 5)
    else:
        s = max(s - 1.0, -5.0)     # 0건이면 감점(하한 -5)
    _ENGINE_SCORE[engine] = s

def _engines():
    try:
        base = list(config.SEARCH_ENGINES)
    except Exception:
        base = ["duckduckgo", "bing", "google"]
    # 점수 높은 순으로 재배치(동점은 원래 순서 유지 — 안정 정렬).
    #  아직 안 써본 엔진(점수 없음)은 0으로 봐서 원래 자리 근처에 둔다.
    return sorted(base, key=lambda e: -_ENGINE_SCORE.get(e, 0.0))

def _search_one(engine, query, max_results, ctx):
    """검색엔진 하나에서 결과 링크 뽑기."""
    url = _ENGINE_URL.get(engine)
    if not url:
        return []
    page = ctx.new_page()
    results = []
    try:
        _now(doing=f"🌐 {engine} 여는 중 — '{query}'", url=None, title=None)
        # 브라우저가 열린 증거: 검색엔진에 가기 전 빈 화면이라도 먼저 한 장 찍는다
        try:
            page.goto("about:blank", timeout=5000); _snap(page)
        except Exception:
            pass
        try:
            page.goto(url + query.replace(" ", "+"),
                      wait_until="domcontentloaded", timeout=25000)
        except Exception as ge:
            # goto가 왜 실패했는지 진짜 이유를 화면에 보여준다(원인 파악용)
            global LAST_DIAG
            LAST_DIAG = f"{engine} 접속 실패: {type(ge).__name__} {str(ge)[:90]}"
            _now(doing=f"⚠️ {LAST_DIAG}", url=url, title=None)
            _snap(page)   # 실패 화면도 남긴다
            return []
        # (봇차단 대응) 쿠키/동의 배너가 막고 있으면 사람처럼 눌러 닫는다
        _dismiss_banners(page)
        _now(doing=f"🔎 검색창에 '{query}' 입력 — {engine}", url=page.url, title=None)
        _snap(page)   # 지금 브라우저 화면(패널에 보임)
        if HUMAN_LIKE:
            _human_pause(); _human_mouse(page); _human_scroll(page)
        # (봇차단 대응) 결과가 실제로 떴는지 본다 — 안 떴으면 배너 한 번 더 닫고 잠깐 기다림
        if not _has_search_results(page):
            _dismiss_banners(page)
            page.wait_for_timeout(800)
            if not _has_search_results(page):
                # 결과가 안 뜬다 = 캡차/동의/차단일 가능성. 화면 남기고 진단 기록.
                # (LAST_DIAG는 이 함수 위에서 이미 global 선언됨 — 여기선 대입만)
                LAST_DIAG = f"{engine}: 검색 결과가 안 뜸(캡차/동의/차단 의심)"
                _now(doing=f"⚠️ {engine} — 결과가 안 떠요(캡차/동의 화면일 수 있음). 패널 화면 확인", url=page.url, title=None)
                _snap(page)
        seen = set()
        skip = ("google", "bing", "duckduckgo", "naver", "microsoft")
        for a in page.query_selector_all("a[href]"):
            href = a.get_attribute("href") or ""
            title = (a.inner_text() or "").strip()
            if href.startswith("http") and title and not any(s in href for s in skip):
                if href not in seen:
                    seen.add(href)
                    # 열기 전에 안전 검사 — 위험/유튜브는 결과에 담지 않는다
                    if safety is not None:
                        _ok,_why = safety.is_safe(href, ctx=ctx)
                        if not _ok:
                            continue
                    results.append({"title": title[:120], "url": href})
            if len(results) >= max_results:
                break
        _snap(page)   # 결과 뽑은 뒤 화면 한 번 더(무엇을 봤는지)
    except Exception:
        try:
            _snap(page)   # 실패해도 화면을 남긴다 — 캡차/동의 화면인지 눈으로 확인
        except Exception:
            pass
    finally:
        page.close()
    return results

def _search_all_engines(query, per_engine, ctx):
    """(브라우저를 넘겨받아) 모든 검색엔진을 사람처럼 하나씩 열어보고,
       각 엔진 결과를 '전부 합친다'(한 곳에서 멈추지 않음).
       같은 URL은 한 번만. 한 엔진이 막혀도 다른 엔진 결과로 채운다."""
    merged = []
    seen_urls = set()
    engine_report = []   # 어느 엔진이 몇 개 줬는지(로그용)
    for engine in _engines():
        try:
            r = _search_one(engine, query, per_engine, ctx)
        except Exception:
            r = []
        added = 0
        for item in r:
            u = item.get("url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                merged.append(item)
                added += 1
        _engine_note(engine, len(r))   # (봇차단 대응) 이 엔진 성패 기록 → 다음 순서에 반영
        engine_report.append(f"{engine}:{added}")
        _now(doing=f"🔎 '{query}' — 엔진 합치는 중 ({', '.join(engine_report)}) 누적 {len(merged)}곳")
    return merged


def search(query, max_results=5):
    """(하위호환 래퍼) 브라우저를 스스로 켜서 모든 엔진 결과를 합쳐 돌려준다.
       ※ research()는 이걸 쓰지 않고 브라우저를 한 번만 켜서 직접 처리한다."""
    _now(doing=f"🔎 '{query}' 검색 시작 — 브라우저 켜는 중", url=None, title=None)
    try:
        pw, browser, ctx = _make_browser()
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg or "BrowserType.launch" in msg:
            hint = "크로미움이 없어요 — 명령창에: python -m playwright install chromium"
        elif "playwright" in msg.lower():
            hint = "playwright 미설치 — pip install playwright 후 python -m playwright install chromium"
        else:
            hint = msg[:120]
        _now(doing=f"💥 브라우저를 못 켰어요 — {hint}", url=None, title=None)
        return []
    results = []
    try:
        # 엔진마다 max_results개씩 받아 합친 뒤, 요청 수만큼 자른다
        results = _search_all_engines(query, per_engine=max_results, ctx=ctx)[:max_results]
    finally:
        browser.close(); pw.stop()
    return results

def _find_box_near_label(page, label_words):
    """사람처럼 화면을 보고, label_words('아이디','비밀번호' 등) 글자 근처의
       입력칸을 찾는다. OCR로 화면에서 글자 위치를 찾고, 그 자리 가까운 input을 고른다.
       화면만 보므로 사이트마다 조정이 필요 없다(사람이 보는 방식)."""
    # 1) 사람처럼 화면 보기: 스크린샷에서 라벨 글자의 위치를 OCR로 찾기
    label_xy = None
    try:
        import io
        from PIL import Image
        import pytesseract
        png = page.screenshot()
        img = Image.open(io.BytesIO(png))
        data = pytesseract.image_to_data(img, lang="kor+eng",
                                         output_type=pytesseract.Output.DICT)
        for i, txt in enumerate(data["text"]):
            t = (txt or "").strip().lower()
            if not t:
                continue
            if any(w.lower() in t for w in label_words):
                label_xy = (data["left"][i] + data["width"][i] // 2,
                            data["top"][i] + data["height"][i] // 2)
                break
    except Exception:
        label_xy = None
    # 2) 화면에 보이는 입력칸들 중 라벨에 가장 가까운 것을 누른다
    boxes = page.query_selector_all("input")
    best = None
    best_d = 1e9
    for b in boxes:
        try:
            if not b.is_visible():
                continue
            bb = b.bounding_box()
            if not bb:
                continue
            cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            if label_xy:
                d = (cx - label_xy[0]) ** 2 + (cy - label_xy[1]) ** 2
            else:
                d = cy   # 라벨 못 찾으면 위에서부터
            if d < best_d:
                best_d = d
                best = b
        except Exception:
            continue
    return best


def _try_login(ctx, url):
    """로그인이 필요한 사이트면 계정으로 들어간다.
       사람처럼: 화면을 보고 아이디 칸·비밀번호 칸을 찾아 누르고 입력한다.
       (HTML 구조를 분석하지 않으므로 사이트마다 조정이 필요 없다.)"""
    try:
        accounts = config.ACCOUNTS
    except Exception:
        return
    import urllib.parse
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    for domain, cred in (accounts or {}).items():
        if domain in host:
            try:
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                _human_pause(); _human_mouse(page)
                # 아이디 칸: '아이디/이메일/로그인/ID' 글자 근처 입력칸을 보고 누른다
                idbox = _find_box_near_label(page, ["아이디", "이메일", "email", "id", "로그인"])
                if idbox:
                    idbox.click()
                    _human_pause(0.2, 0.6)
                    idbox.type(cred.get("id", ""), delay=120)   # 사람 타이핑 속도
                _human_pause(0.3, 0.8)
                # 비번 칸: '비밀번호/password' 글자 근처 입력칸을 보고 누른다
                pwbox = _find_box_near_label(page, ["비밀번호", "password", "pw"])
                if pwbox:
                    pwbox.click()
                    _human_pause(0.2, 0.6)
                    pwbox.type(cred.get("pw", ""), delay=120)
                    _human_pause(0.3, 0.8)
                    pwbox.press("Enter")
                    page.wait_for_timeout(2500)
                page.close()
            except Exception:
                pass
            break


def _read_page_in(url, ctx):
    """(브라우저를 넘겨받아) 한 페이지를 '사람처럼 한 화면씩' 열어 읽는다.
       탭(페이지)은 하나씩 열고 닫는다 — 동시에 여러 개 안 본다(그건 봇).
       브라우저를 새로 켜지 않으므로, 사람이 창 하나로 탭을 오가며 보는 것과 같다."""
    # 안전벽 — 위험/유튜브면 열지 않는다
    if safety is not None:
        _ok, _why = safety.is_safe(url, ctx=ctx)
        if not _ok:
            return {"url": url, "title": None, "text": None, "links": [], "images": [], "blocked": _why}
    out = {"url": url, "title": None, "text": None, "links": [], "images": []}
    page = None
    try:
        _try_login(ctx, url)   # 로그인 필요한 곳이면 계정으로
        page = ctx.new_page()
        # 사람처럼: 페이지를 열고 '본문 글이 나오는지 보고 판단'한다.
        #  시간 세고 넘어가지 않는다 — 인터넷없음/2분/오류가 아니면 계속 지켜본다.
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=WATCH_MAX_SEC*1000)
        except Exception as e:
            _now(doing=f"⚠️ 사이트 안 열림(오류) — {type(e).__name__}", url=url, title=None)
            return out
        if resp is not None and resp.status >= 400:   # (3) 오류: 404/500 등
            _now(doing=f"⚠️ 사이트 오류({resp.status}) — 안 나옴", url=url, title=None)
            return out
        # (봇차단 대응) 쿠키/동의 배너가 본문을 가리는 일이 많다 — 사람처럼 닫고 읽는다
        _dismiss_banners(page)
        # 본문 글(읽을 내용)이 화면에 나타났는가 = '결과가 나왔다'
        def _content_ready(pg):
            try:
                return bool(pg.evaluate(
                    "() => { const ps=[...document.querySelectorAll('p')];"
                    " for(const p of ps){ if((p.innerText||'').trim().length>40) return true; }"
                    " return false; }"))
            except Exception:
                return False
        st, why = _watch_until(page, _content_ready)
        if st != "ready":
            _now(doing=f"⚠️ 결과 안 나옴({why}) — {url[:40]}", url=url, title=None)
            return out
        if HUMAN_LIKE:
            _human_pause(); _human_mouse(page); _human_scroll(page)
        out["title"] = page.title()
        _now(doing="📖 사이트 읽는 중", url=url, title=out["title"])
        _snap(page)
        if SEE_LIKE_HUMAN:
            out["text"] = (_see_screen_text(page) or "")[:4000] or None
        if out["text"] is None:
            # OCR을 못 쓰거나(라이브러리 없음) 화면에서 글자를 못 읽었으면
            # HTML 본문으로 대체해 읽는다 — 조용히 빈손으로 돌아가지 않는다.
            # (SEE_LIKE_HUMAN이 꺼져 있을 때도 원래 이 길로 읽는다 — 기존과 동일)
            texts = []
            for p in page.query_selector_all("p"):
                t = (p.inner_text() or "").strip()
                if len(t) > 40 and not _is_junk_text(t):   # 광고·페이월 껍데기 제외
                    texts.append(t)
            out["text"] = "\n".join(texts[:20])[:4000] if texts else None
        links = []
        for a in page.query_selector_all("a[href]"):
            t = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if t and 1 < len(t) < 30 and href.startswith("http"):
                if t not in [l["title"] for l in links]:
                    links.append({"title": t, "url": href})
            if len(links) >= 40:
                break
        out["links"] = links
        for im in page.query_selector_all("img[src]"):
            src = im.get_attribute("src") or ""
            if src.startswith("http"):
                out["images"].append(src)
            if len(out["images"]) >= 5:
                break
    finally:
        if page is not None:
            try: page.close()   # 이 탭만 닫는다(브라우저는 살려둠 — 다음 사이트 재사용)
            except Exception: pass
    return out


def read_page(url):
    """(하위호환 래퍼) 브라우저를 스스로 켜서 한 페이지를 읽는다.
       ※ research()는 이걸 쓰지 않고 브라우저를 한 번만 켜서 재사용한다."""
    if safety is not None:
        _ok, _why = safety.is_safe(url)
        if not _ok:
            return {"url": url, "title": None, "text": None, "links": [], "images": [], "blocked": _why}
    pw, browser, ctx = _make_browser()
    try:
        return _read_page_in(url, ctx)
    finally:
        browser.close(); pw.stop()


def research(query, max_sites=20):
    """검색 → 여러 사이트를 '사람처럼 한 개씩 순서대로' 읽기 → 모아서 돌려준다.
       핵심 변경:
         · 검색엔진(구글·빙·덕덕고·네이버 등)을 모두 열어 결과를 '전부 합친다'.
         · 브라우저는 딱 한 번만 켠다(사이트마다 껐다 켜지 않음 — 그게 느림의 주범).
           그 안에서 탭을 하나씩 열어 사람처럼 한 화면씩 본다(동시 병렬 아님).
         · 봇으로 걸리는 요소(위장 UA·자동화표시 숨김·비headless·locale)는 유지,
           봇 감지와 무관한 굼뜬 대기만 줄여 빠르게(SPEED)."""
    _now(doing=f"🌐 '{query}' 조사 시작 — 여러 검색엔진을 사람처럼 열어봐요")
    # 브라우저 한 번만 켠다
    try:
        pw, browser, ctx = _make_browser()
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg or "BrowserType.launch" in msg:
            hint = "크로미움이 없어요 — 명령창에: python -m playwright install chromium"
        elif "playwright" in msg.lower():
            hint = "playwright 미설치 — pip install playwright 후 python -m playwright install chromium"
        else:
            hint = msg[:120]
        _now(doing=f"💥 브라우저를 못 켰어요 — {hint}", url=None, title=None)
        return {"query": query, "sites": [], "summary": None,
                "summaries": [], "links": [], "images": []}

    pages = []
    found = []
    try:
        # 1) 모든 엔진 결과 합치기 — 엔진마다 max_sites개씩 받아 합친 뒤 상한만큼
        found = _search_all_engines(query, per_engine=max_sites, ctx=ctx)[:max_sites]
        # 2) 열기 전 안전 검사 — 안전한 곳만
        safe_found = []
        blocked = []
        for r in found:
            if safety is not None:
                _ok, _why = safety.is_safe(r["url"], ctx=ctx)
                if not _ok:
                    blocked.append((r["url"], _why)); continue
            safe_found.append(r)
        if blocked:
            _now(doing=f"🛡 안전검사: {len(blocked)}곳 걸러냄 (예: {blocked[0][1]})")
        # 3) 사람처럼 '한 개씩 순서대로' 읽기(브라우저 재사용, 탭만 교체)
        for idx, r in enumerate(safe_found, 1):
            _now(doing=f"📖 '{query}' — {idx}/{len(safe_found)}곳째 읽는 중")
            try:
                pages.append(_read_page_in(r["url"], ctx))
            except Exception:
                continue
    finally:
        try: browser.close(); pw.stop()
        except Exception: pass

    all_links = []
    for p in pages:
        for l in p.get("links", []):
            if l["title"] not in all_links:
                all_links.append(l["title"])
    summaries = [p["text"] for p in pages if p.get("text")]
    # 여러 사이트에서 읽은 내용을 합친다(첫 곳만 쓰지 않음). 사이트가 많아진 만큼 여유.
    combined = ""
    for i, t in enumerate(summaries):
        combined += f"[출처{i+1}] " + t.strip() + "\n\n"
        if len(combined) > 12000:
            break
    combined = combined.strip()[:12000] or None
    # 정직한 상태 표시 — 0곳을 성공(✅)처럼 말하지 않는다.
    if pages:
        _now(doing=f"✅ '{query}' 조사 끝 — 사이트 {len(pages)}곳 읽음(엔진 합침)")
    elif found:
        _now(doing=f"⚠️ '{query}' — 검색 결과 {len(found)}개를 찾았지만 사이트 내용을 못 읽었어요")
    else:
        _diag = f" [{LAST_DIAG}]" if LAST_DIAG else ""
        _now(doing=f"⚠️ '{query}' — 검색 결과 0곳{_diag} (검색엔진이 자동 접근을 막았거나 접속 실패). 위 브라우저 화면 확인")
    return {
        "query": query,
        "sites": [{"title": p["title"], "url": p["url"]} for p in pages],
        "summary": combined,
        "summaries": [t[:1200] for t in summaries[:max_sites]],
        "links": all_links[:60],
        "images": [im for p in pages for im in p.get("images", [])][:5],
    }


VT_URL_PAGE = "https://www.virustotal.com/gui/home/url"

def vt_scan_browser(url, ctx=None):
    """사람처럼: 진짜 브라우저로 VirusTotal 사이트에 가서 URL을 넣고,
       결과 화면(악성 몇 개인지)을 읽는다.
       반환: (악성개수, 이유)  또는  (None, 실패이유).
       ctx를 넘겨받으면(=research가 이미 켠 브라우저) 그 안에서 탭만 열어 재사용한다
       — 사이트마다 브라우저를 새로 켜지 않기 위함. ctx가 없으면 예전처럼 스스로 켠다.
       정직하게 — VirusTotal은 JS가 무겁고 봇 감지가 있을 수 있어 실패할 수 있다.
       실패하면 (None, ...)을 주고, 부르는 쪽이 API로 넘어간다."""
    pw = browser = None
    own = ctx is None      # 내가 직접 켰나(그럼 내가 닫는다)
    page = None
    try:
        if own:
            pw, browser, ctx = _make_browser()
        page = ctx.new_page()
        _now(doing=f"🛡 VirusTotal에서 사람처럼 검사 중 — {url[:40]}", url=VT_URL_PAGE, title=None)
        page.goto(VT_URL_PAGE, wait_until="domcontentloaded", timeout=25000)
        _snap(page)
        # 검색창은 보통 자동 포커스됨 → URL 입력 후 엔터. (여러 방법 시도)
        try:
            page.wait_for_timeout(1500)
            page.keyboard.type(url, delay=20)
            page.keyboard.press("Enter")
        except Exception:
            pass
        # 사람처럼: 검사 결과(숫자)가 화면에 뜨는지 '보고 판단'한다.
        #  시간 세고 넘어가지 않는다 — 인터넷없음/2분/오류가 아니면 결과 나올 때까지 지켜본다.
        import re
        # VT 결과 화면 문구는 몇 가지다:
        #   · 악성 있음: "N/90 security vendors flagged this URL"  또는 "N security vendors ..."
        #   · 깨끗함(0): "No security vendors flagged this URL as malicious"
        #     → 이 경우도 '결과가 나온 것'이다(악성 0). 예전엔 이걸 못 잡아 2분 꽉 채웠음.
        _vt_pat = re.compile(r"(\d+)\s*/\s*\d+\s*(?:security vendors|보안 벤더|벤더|엔진)", re.I)
        _vt_pat2 = re.compile(r"(\d+)\s*(?:/\s*\d+\s*)?security vendors?.{0,40}?flagged", re.I | re.S)
        _vt_clean = re.compile(r"no\s+security\s+vendors?.{0,40}?flagged|(?:악성|위협).{0,30}?(?:없습니다|없음|아닙니다)|안전.{0,6}(?:벤더|엔진)", re.I | re.S)

        def _vt_read_count(body):
            """VT 결과 화면에서 '악성 개수'를 읽는다. 못 읽으면 None."""
            if not body:
                return None
            # 1) 깨끗함(0개)을 먼저 본다 — "No security vendors flagged" 등
            if _vt_clean.search(body):
                return 0
            # 2) "N/90 벤더" 형태
            m = _vt_pat.search(body)
            if m:
                return int(m.group(1))
            # 3) "N security vendors ... flagged" 형태
            m = _vt_pat2.search(body)
            if m:
                return int(m.group(1))
            # 4) 한글/기타 '악성' 문구 옆의 숫자
            if "flagged this URL as malicious" in body or "악성" in body:
                m2 = re.search(r"(\d+)", body)
                if m2:
                    return int(m2.group(1))
            return None

        def _vt_ready(pg):
            try:
                body = pg.evaluate("() => document.body ? document.body.innerText : ''") or ""
            except Exception:
                return False
            # 악성 개수를 '읽을 수 있으면'(0 포함) 결과가 뜬 것 — 여기서 2분 대기 끝.
            return _vt_read_count(body) is not None
        st, why = _watch_until(page, _vt_ready)
        _snap(page)   # 결과 화면을 패널에 남긴다(사람이 보듯)
        if st != "ready":
            # 인터넷없음/2분초과/오류 → 결과 안 나옴 → API 폴백으로
            return None, f"VirusTotal 결과 안 나옴({why})"
        # 결과가 화면에 떴다 — 숫자를 읽는다(판정 때와 같은 파서 사용)
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        except Exception:
            body = ""
        got = _vt_read_count(body)
        if got is not None:
            return got, f"VirusTotal(브라우저): 악성 {got}"
        return None, "VirusTotal 화면에서 결과를 못 읽음(봇 감지/로그인/화면 변경일 수 있음)"
    except Exception as e:
        return None, f"VirusTotal 브라우저 검사 실패: {type(e).__name__} {str(e)[:60]}"
    finally:
        # 넘겨받은 ctx면 탭만 닫는다(브라우저는 남의 것 — 안 닫음).
        if page is not None:
            try: page.close()
            except Exception: pass
        if own:
            try:
                if browser: browser.close()
                if pw: pw.stop()
            except Exception:
                pass


if __name__ == "__main__":
    print("browser_search 준비됨. 네 컴퓨터에서 research('단어') 실행.")
    print("HUMAN_LIKE:", HUMAN_LIKE, "/ SEE_LIKE_HUMAN:", SEE_LIKE_HUMAN)
