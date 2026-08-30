# -*- coding: utf-8 -*-
# 번역 연결 로더 — kaikki.org(Wiktextract) 데이터로 언어 간 번역을 잇는다.
# 형식(공식 문서 확인): 단어 dict에 "translations" 리스트,
#   각 항목 {"code":언어코드, "lang":언어명, "word":번역어, "sense":뜻}
# 출처: kaikki.org / Wiktionary, CC BY-SA.
import io, json, urllib.request, urllib.parse

# 단어별 다운로드 URL 패턴 (kaikki: 영어판에서 추출, 단어별 JSON 받기)
# 예: https://kaikki.org/dictionary/English/meaning/a/ap/apple.json
def _kaikki_url(word):
    w=word.lower()
    a=w[0]
    ab=w[:2] if len(w)>=2 else w
    return (f"https://kaikki.org/dictionary/English/meaning/"
            f"{a}/{ab}/{urllib.parse.quote(w)}.json")

def fetch_translations_real(eng_word, want_langs=("ko","ja")):
    """영어 단어의 번역을 kaikki에서 실시간으로 받아 {lang:word} 반환.
       ※ 작업 환경(AI)은 kaikki 접속이 막혀 검증 불가 → 네 컴퓨터에서 작동.
       디스크 저장 안 함(메모리만)."""
    try:
        url=_kaikki_url(eng_word)
        with urllib.request.urlopen(url, timeout=15) as r:
            raw=r.read().decode("utf-8")
        out={}
        for line in raw.splitlines():      # JSONL: 한 줄에 한 뜻
            if not line.strip(): continue
            d=json.loads(line)
            for t in d.get("translations",[]):
                code=t.get("code"); word=t.get("word")
                if (want_langs is None or code in want_langs) and word and code not in out:
                    out[code]=word
        return out
    except Exception:
        return None

def parse_translations(word_json_obj, want_langs=("ko","ja")):
    """이미 받은 단어 JSON 객체에서 번역 뽑기 (샘플 검증용 — 다운로드 없이)."""
    out={}
    for t in word_json_obj.get("translations",[]):
        code=t.get("code"); word=t.get("word")
        if (want_langs is None or code in want_langs) and word and code not in out:
            out[code]=word
    return out
