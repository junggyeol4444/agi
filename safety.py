# -*- coding: utf-8 -*-
"""
사이트 안전 검사 — 조사(열기) 전에 먼저 거른다.
목적: 바이러스/랜섬웨어/악성 다운로드 사이트를 열지 않게.
     유튜브는 지금은 조사 대상에서 뺀다(나중에).

정직하게 — 이건 '기본 필터'다. 완벽한 백신이 아니다.
  · 정적 규칙(위험 확장자·의심 TLD·생 IP·유튜브)으로 1차로 거른다.
  · 네 컴퓨터(인터넷)에선 URLhaus(악성 URL 공개 목록)를 받아 대조한다.
    못 받으면 정적 규칙만으로 동작한다.
"""
import re
import urllib.parse
import urllib.request
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_URLHAUS_CACHE = os.path.join(HERE, "urlhaus_cache.txt")
_URLHAUS_URL = "https://urlhaus.abuse.ch/downloads/text_recent/"
_URLHAUS_TTL = 60 * 60 * 12   # 12시간마다 갱신

# 지금은 조사 안 함 — 나중에(사용자 지시)
DEFER_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "youtube-nocookie.com", "music.youtube.com",
}

# 실행/설치 파일 등 — 열면 위험(다운로드 유발)
DANGER_EXT = (
    ".exe", ".scr", ".msi", ".bat", ".cmd", ".com", ".pif", ".vbs",
    ".ps1", ".apk", ".dmg", ".pkg", ".jar", ".iso", ".img",
    ".rar", ".7z", ".ace", ".cab", ".hta", ".jse", ".wsf", ".lnk",
)

# 악용이 잦은 무료 TLD (보수적으로 최소만 — 오탐 줄이려 짧게)
SUSPICIOUS_TLD = (".tk", ".ml", ".ga", ".cf", ".gq", ".zip", ".mov", ".xyz.")

# 흔한 URL 단축(리다이렉트로 우회 가능) — 어디로 가는지 모름 → 막음
SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd",
    "buff.ly", "cutt.ly", "rebrand.ly", "shorturl.at",
}

_urlhaus_hosts = None      # 악성 호스트 집합(로드되면)
_urlhaus_loaded = False

# ── VirusTotal 검사 ──
try:
    import config as _cfg
    _VT_KEY = (getattr(_cfg, "VIRUSTOTAL_API_KEY", "") or
               os.environ.get("VT_API_KEY", "") or "").strip()
    _VT_THRESHOLD = int(getattr(_cfg, "VIRUSTOTAL_MALICIOUS_THRESHOLD", 1))
except Exception:
    _VT_KEY = os.environ.get("VT_API_KEY", "").strip()
    _VT_THRESHOLD = 1

_vt_cache = {}          # url -> (safe, reason)  이미 물어본 건 다시 안 물어봄
_vt_call_times = []     # 최근 호출 시각(분당 4회 제한 지키기)


def _vt_allowed_now():
    """VirusTotal 무료 제한: 분당 4회. 넘으면 이번엔 건너뛴다."""
    now = time.time()
    # 1분 지난 기록은 버림
    while _vt_call_times and now - _vt_call_times[0] > 60:
        _vt_call_times.pop(0)
    return len(_vt_call_times) < 4


def _vt_check(url):
    """VirusTotal로 URL 검사. 반환:
        (True, 이유)  안전(또는 판단 불가라 통과)
        (False, 이유) 악성으로 막음
       키 없음/제한 초과/오류 → (True, 이유)로 통과(정적 필터는 이미 통과함)."""
    if not _VT_KEY:
        return True, "VT 꺼짐(키 없음)"
    if url in _vt_cache:
        return _vt_cache[url]
    if not _vt_allowed_now():
        return True, "VT 건너뜀(분당 4회 초과)"
    try:
        import base64
        url_id = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
        req = urllib.request.Request(
            "https://www.virustotal.com/api/v3/urls/" + url_id,
            headers={"x-apikey": _VT_KEY, "User-Agent": "Mozilla/5.0"})
        _vt_call_times.append(time.time())
        with urllib.request.urlopen(req, timeout=15) as r:
            import json
            data = json.loads(r.read().decode("utf-8", "ignore"))
        stats = (data.get("data", {}).get("attributes", {})
                     .get("last_analysis_stats", {}))
        mal = int(stats.get("malicious", 0))
        sus = int(stats.get("suspicious", 0))
        if mal + sus >= _VT_THRESHOLD:
            res = (False, f"VirusTotal 위험(악성 {mal}·의심 {sus})")
        else:
            res = (True, f"VirusTotal 통과(악성 {mal})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            res = (True, "VT: 아직 검사된 적 없음(통과)")  # 미검사 = 악성 아님
        elif e.code == 429:
            res = (True, "VT: 할당량 초과(통과)")
        else:
            res = (True, f"VT 오류 {e.code}(통과)")
    except Exception as e:
        res = (True, f"VT 확인 실패(통과): {type(e).__name__}")
    _vt_cache[url] = res
    return res



def _host_of(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _load_urlhaus():
    """악성 URL 공개 목록을 받아 호스트 집합으로. 캐시 사용. 실패해도 조용히 넘어감."""
    global _urlhaus_hosts, _urlhaus_loaded
    if _urlhaus_loaded:
        return
    _urlhaus_loaded = True
    text = None
    # 캐시가 최근이면 캐시 사용
    try:
        if os.path.exists(_URLHAUS_CACHE) and \
           time.time() - os.path.getmtime(_URLHAUS_CACHE) < _URLHAUS_TTL:
            with open(_URLHAUS_CACHE, encoding="utf-8", errors="ignore") as f:
                text = f.read()
    except Exception:
        text = None
    # 없으면 내려받기(네 컴퓨터=인터넷). 실패하면 None.
    if text is None:
        try:
            req = urllib.request.Request(_URLHAUS_URL,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode("utf-8", "ignore")
            try:
                with open(_URLHAUS_CACHE, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass
        except Exception:
            text = None
    if not text:
        _urlhaus_hosts = None
        return
    hosts = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        h = _host_of(line)
        if h:
            hosts.add(h)
    _urlhaus_hosts = hosts or None


def is_safe(url, ctx=None):
    """(안전한가, 이유) 반환. 이유는 사람이 읽는 짧은 설명.
       ctx를 넘겨받으면 VirusTotal 브라우저 검사가 그 브라우저를 재사용한다
       (사이트마다 새 브라우저를 안 켜기 위함)."""
    if not url or not isinstance(url, str):
        return False, "빈 주소"
    u = url.strip()
    # 1) http/https 만
    try:
        p = urllib.parse.urlparse(u)
    except Exception:
        return False, "주소 해석 실패"
    if p.scheme not in ("http", "https"):
        return False, f"http(s) 아님({p.scheme or '스킴없음'})"
    host = (p.hostname or "").lower()
    if not host:
        return False, "호스트 없음"

    # 2) 유튜브 — 지금은 조사 안 함(나중에)
    base = host[4:] if host.startswith("www.") else host
    if host in DEFER_HOSTS or base in DEFER_HOSTS or base.endswith(".youtube.com"):
        return False, "유튜브는 나중에 조사"

    # 3) 생 IP 주소(도메인 없이 숫자) — 악성에 흔함
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        return False, "생 IP 주소(도메인 아님)"

    # 4) 단축 URL — 어디로 가는지 모름
    if base in SHORTENERS:
        return False, "단축 URL(목적지 불명)"

    # 5) 위험 확장자(다운로드 유발)
    path = (p.path or "").lower()
    if path.endswith(DANGER_EXT):
        return False, f"위험 파일({path.rsplit('.',1)[-1]})"

    # 6) 의심 TLD
    if host.endswith(SUSPICIOUS_TLD):
        return False, "의심 도메인(악용 잦은 TLD)"

    # 7) 악성 URL 목록(URLhaus) 대조 — 네 컴퓨터에서 목록을 받았을 때
    _load_urlhaus()
    if _urlhaus_hosts and host in _urlhaus_hosts:
        return False, "악성 목록(URLhaus)에 있음"

    # VT 검사 자체가 꺼져 있으면 여기서 통과(정적 필터는 이미 다 통과함)
    try:
        import config as _cc
        if not bool(getattr(_cc, "VIRUSTOTAL_ENABLE", True)):
            return True, "안전(정적 필터 통과, VT 꺼짐)"
    except Exception:
        pass
    # 8) VirusTotal 검사 — 위 정적 검사를 다 통과한 URL만(호출 아끼기)
    #    사람 방식(브라우저로 VT 사이트 방문) 먼저, 안 되면 API로.
    if u in _vt_cache:
        cached = _vt_cache[u]
        if not cached[0]:
            return cached
    else:
        use_browser = True
        try:
            import config as _c
            use_browser = bool(getattr(_c, "VIRUSTOTAL_USE_BROWSER", True))
        except Exception:
            pass
        decided = False
        if use_browser:
            try:
                import browser_search   # 늦은 임포트(순환 방지)
                mal, why = browser_search.vt_scan_browser(u, ctx=ctx)
                if mal is not None:      # 브라우저로 결과를 읽었다
                    if mal >= _VT_THRESHOLD:
                        _vt_cache[u] = (False, why); return False, why
                    _vt_cache[u] = (True, why); decided = True
            except Exception:
                pass
        if not decided:
            # 브라우저 방식 실패 → API로 폴백(키 있을 때). 키 없으면 그냥 통과.
            vt_ok, vt_why = _vt_check(u)
            _vt_cache[u] = (vt_ok, vt_why)
            if not vt_ok:
                return False, vt_why

    return True, "안전(기본 검사 통과)"


def filter_safe(urls):
    """URL 목록에서 안전한 것만 [(url, 이유)]로. 막힌 것도 [(url, 이유)]로 따로."""
    ok, blocked = [], []
    for u in urls:
        safe, why = is_safe(u)
        (ok if safe else blocked).append((u, why))
    return ok, blocked


if __name__ == "__main__":
    tests = [
        "https://ko.wikipedia.org/wiki/공룡",
        "https://www.youtube.com/watch?v=abc",
        "http://192.168.0.1/evil",
        "https://example.com/setup.exe",
        "https://foo.tk/page",
        "https://bit.ly/xyz",
        "ftp://x.com/file",
    ]
    for t in tests:
        print(is_safe(t), "  <-", t)
