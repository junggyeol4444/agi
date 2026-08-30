# -*- coding: utf-8 -*-
# 영어 기초사전 로더 (Longman Communication, 가장 흔한 영어 단어)
# 출처: github.com/MuhammadYaseenKhan/Longman-Communication (품사 포함)
import os, json, urllib.request

BASE=("https://raw.githubusercontent.com/MuhammadYaseenKhan/"
      "Longman-Communication/master/longman-communication-9000")
POS_FILE="longman-communication-9000-pos-dictionary.json"
HERE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(HERE,"dict_cache_en")
LICENSE_NOTE="Longman Communication (가장 흔한 영어 단어), 품사 포함"
_POS_MAP={"noun":"명사","verb":"동사","adjective":"형용사","adverb":"부사"}

def _download():
    os.makedirs(CACHE,exist_ok=True)
    path=os.path.join(CACHE,POS_FILE)
    if os.path.exists(path) and os.path.getsize(path)>0: return path
    urllib.request.urlretrieve(f"{BASE}/{POS_FILE}",path)
    return path

def load_words(levels=None, pos_filter=("명사",), limit=200, files=None, save=False):
    d=json.load(open(_download(),encoding="utf-8"))
    want=set()
    for p in (pos_filter or []):
        for en,ko in _POS_MAP.items():
            if ko==p: want.add(en)
    out=[]; seen=set()
    for en_pos in want:
        for entry in d.get(en_pos,[]):
            word=entry[0]
            if " " in word or word in seen: continue
            seen.add(word)
            out.append({"word":word,"pos":_POS_MAP[en_pos],
                        "definition":None,"category":None})
            if limit and len(out)>=limit: break
        if limit and len(out)>=limit: break
    return out

if __name__=="__main__":
    n=load_words(pos_filter=("명사",),limit=12)
    v=load_words(pos_filter=("동사",),limit=12)
    print("영어 기초 명사:",[w["word"] for w in n])
    print("영어 기초 동사:",[w["word"] for w in v])
    print("출처:",LICENSE_NOTE)
