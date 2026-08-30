# -*- coding: utf-8 -*-
# 크롤러 — 웹페이지를 긁어 (설명, 연결된 단어들, 사진)을 뽑는다.
# API 안 씀. 그냥 페이지를 받아서 파싱(표준 라이브러리만).
# 진짜 작동은 인터넷 되는 컴퓨터에서(AI 작업환경은 위키백과 막힘).
import re
import urllib.request
import urllib.parse
import html as _html

UA = "Mozilla/5.0 (baby-agi learner)"

def fetch_html(word, lang="ko"):
    """위키백과에서 그 단어 페이지 HTML을 받는다(크롤링). 실패 시 None."""
    url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(word)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None

def parse_page(htmltext):
    """페이지 HTML에서 뽑는다:
       - summary: 설명(첫 문단 텍스트 일부)
       - links: 연결된 단어들(본문에 링크된 다른 표제어) ← 꼬리물기의 핵심
       - image: 대표 사진 URL(있으면)"""
    if not htmltext:
        return {"summary": None, "links": [], "image": None}
    # 연결된 표제어: /wiki/단어 형태 링크에서 단어만 (특수문서 제외)
    links = []
    for m in re.finditer(r'href="/wiki/([^":#?]+)"', htmltext):
        title = urllib.parse.unquote(m.group(1))
        # 특수/파일/분류 페이지 제외
        if ":" in title or title.startswith("파일") or "_(" in title:
            continue
        title = title.replace("_", " ")
        if title not in links:
            links.append(title)
    # 설명: 첫 <p> 태그 텍스트
    summary = None
    pm = re.search(r"<p>(.*?)</p>", htmltext, re.DOTALL)
    if pm:
        text = re.sub(r"<[^>]+>", "", pm.group(1))   # 태그 제거
        summary = _html.unescape(text).strip()[:200]
    # 사진: 첫 이미지
    image = None
    im = re.search(r'<img[^>]+src="(//upload[^"]+)"', htmltext)
    if im:
        image = "https:" + im.group(1)
    return {"summary": summary, "links": links[:20], "image": image}

def crawl(word, lang="ko"):
    """단어 하나를 크롤링해서 정보를 돌려준다."""
    return parse_page(fetch_html(word, lang))

if __name__ == "__main__":
    # 검증: 가짜 위키백과 HTML로 '연결된 단어 뽑기'가 되는지
    fake = '''<html><body>
    <p>공룡은 중생대에 번성했던 <a href="/wiki/파충류">파충류</a>이다.
    <a href="/wiki/백악기">백악기</a> 말에 <a href="/wiki/대멸종">대멸종</a>으로
    사라졌다. <a href="/wiki/조류">조류</a>는 공룡의 후손이다.
    <a href="/wiki/파일:Dino.jpg">사진</a> <a href="/wiki/분류:동물">분류</a></p>
    <img src="//upload.wikimedia.org/dino.jpg">
    </body></html>'''
    info = parse_page(fake)
    print("설명:", info["summary"])
    print("연결된 단어(꼬리물기 대상):", info["links"])
    print("사진:", info["image"])
