# -*- coding: utf-8 -*-
# 일본어 기초사전 로더 (JLPT 단어, open-anki-jlpt-decks)
# 출처: github.com/jamsinclair/open-anki-jlpt-decks (CC BY, tanos.co.uk 기반)
# 형식: expression,reading,meaning,tags,guid (CSV)
import os, csv, urllib.request

BASE="https://raw.githubusercontent.com/jamsinclair/open-anki-jlpt-decks/main/src"
FILES=["n5.csv","n4.csv"]   # 기초(N5,N4)부터. 유아기엔 적게.
HERE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(HERE,"dict_cache_ja")
LICENSE_NOTE="JLPT vocab (open-anki-jlpt-decks, CC BY, tanos.co.uk 기반)"

def _download(fn):
    os.makedirs(CACHE,exist_ok=True)
    p=os.path.join(CACHE,fn)
    if os.path.exists(p) and os.path.getsize(p)>0: return p
    urllib.request.urlretrieve(f"{BASE}/{fn}",p)
    return p

def load_words(levels=None, pos_filter=("명사",), limit=200, files=None, save=False):
    """일본어 단어를 한국어 로더와 같은 형식으로.
       품사 추정: 뜻이 'to '로 시작 → 동사. 'い'로 끝나고 형용사스러우면 제외.
       그 외 → 명사."""
    use=files if files else FILES
    out=[]; seen=set()
    want_noun = "명사" in (pos_filter or [])
    want_verb = "동사" in (pos_filter or [])
    for fn in use:
        try: path=_download(fn)
        except Exception: continue
        with open(path,encoding="utf-8") as f:
            r=csv.DictReader(f)
            for row in r:
                word=(row.get("expression") or "").strip()
                meaning=(row.get("meaning") or "").strip()
                if not word or word in seen: continue
                is_verb = meaning.lower().startswith("to ")
                is_adj = word.endswith("い") and not is_verb
                if is_verb and want_verb:
                    pos="동사"
                elif (not is_verb and not is_adj) and want_noun:
                    pos="명사"
                else:
                    continue
                seen.add(word)
                out.append({"word":word,"pos":pos,
                            "definition":meaning,"category":None})
                if limit and len(out)>=limit: break
        if limit and len(out)>=limit: break
    return out

if __name__=="__main__":
    n=load_words(pos_filter=("명사",),limit=10)
    v=load_words(pos_filter=("동사",),limit=10)
    print("일본어 명사:",[w["word"] for w in n])
    print("일본어 동사:",[w["word"] for w in v])
