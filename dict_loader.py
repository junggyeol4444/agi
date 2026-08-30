
import os
import json
import urllib.request
import xml.etree.ElementTree as ET

# 기초사전 XML 파일들 (실제 확인된 목록 — 추측 아님)
BASE_URL = "https://raw.githubusercontent.com/spellcheck-ko/korean-dict-nikl-krdict/master"
XML_FILES = ["5000.xml", "10000.xml", "15000.xml", "20000.xml", "25000.xml",
             "30000.xml", "35000.xml", "40000.xml", "45000.xml", "50000.xml", "51947.xml"]

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "dict_cache")     # 받은 XML 보관(재다운로드 방지)
OUT_FILE = os.path.join(HERE, "dictionary.json") # 뽑은 단어 저장

LICENSE_NOTE = ("국립국어원 한국어기초사전, CC BY-SA 2.0 KR. "
                "출처: https://krdict.korean.go.kr")


def _download(fname):
    """XML 한 개를 받아 캐시에 저장(이미 있으면 재사용)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = f"{BASE_URL}/{fname}"
    print(f"  내려받는 중: {fname} ...")
    urllib.request.urlretrieve(url, path)
    return path


def _parse(path, levels):
    """XML 하나에서 원하는 등급의 단어를 뽑는다.
       LexicalEntry 블록 단위로 잘라 각각 파싱하고, 깨진 블록은 건너뛴다.
       (사전 데이터에 간혹 이스케이프 안 된 특수문자가 있어 strict 파서가 멈추는 것 방지.
        표준 라이브러리만 사용 — 추가 설치 불필요.)
       반환: [(표제어, 품사, 등급, 뜻풀이, 의미범주), ...]"""
    import re
    out = []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for m in re.finditer(r"<LexicalEntry\b.*?</LexicalEntry>", text, re.DOTALL):
        try:
            entry = ET.fromstring(m.group(0))
        except ET.ParseError:
            continue   # 깨진 블록은 건너뛴다
        feats = {f.get("att"): f.get("val") for f in entry.findall("feat")}
        pos = feats.get("partOfSpeech")
        level = feats.get("vocabularyLevel")
        sem = feats.get("semanticCategory")
        lemma = entry.find("Lemma")
        written = None
        if lemma is not None:
            lf = {f.get("att"): f.get("val") for f in lemma.findall("feat")}
            written = lf.get("writtenForm")
        sense = entry.find("Sense")
        definition = None
        if sense is not None:
            sf = {f.get("att"): f.get("val") for f in sense.findall("feat")}
            definition = sf.get("definition")
        if written and (levels is None or level in levels):
            out.append((written, pos, level, definition, sem))
    return out


def load_words(levels=("초급",), pos_filter=("명사",), limit=None,
               files=None, save=True):
    """사전에서 단어를 뽑는다.
       levels: 가져올 등급들 (예: ('초급',) → 유아기). None이면 전부.
       pos_filter: 가져올 품사 (예: ('명사',)). None이면 전부.
       limit: 최대 개수 (None이면 제한 없음).
       files: 읽을 XML 목록 (None이면 전체 11개).
    """
    use_files = files if files else XML_FILES
    words = []
    seen = set()
    for fname in use_files:
        path = _download(fname)
        for written, pos, level, definition, sem in _parse(path, levels):
            if pos_filter and pos not in pos_filter:
                continue
            if written in seen:
                continue
            seen.add(written)
            words.append({
                "word": written, "pos": pos, "level": level,
                "definition": definition, "category": sem,
            })
            if limit and len(words) >= limit:
                break
        if limit and len(words) >= limit:
            break

    if save:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump({"license": LICENSE_NOTE, "count": len(words),
                       "words": words}, f, ensure_ascii=False, indent=1)
    return words


if __name__ == "__main__":
    # 기본: 초급 명사부터 (유아기). 일부 파일만으로 빠르게 시험.
    ws = load_words(levels=("초급",), pos_filter=("명사",),
                    files=["5000.xml"], save=True)
    print(f"\n뽑은 단어 수: {len(ws)}  (초급 명사)")
    print(f"출처: {LICENSE_NOTE}")
    print("예시:")
    for w in ws[:10]:
        print(f"  {w['word']} : {w['definition']}")

