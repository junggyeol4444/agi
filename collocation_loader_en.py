# -*- coding: utf-8 -*-
# 영어 명사-동사 의미 짝 로더 (SP-10K, selectional preference)
# 동사+목적어(dobj) 짝을 점수와 함께. "eat food", "drink water" 같은 어울리는 짝.
# 출처: github.com/HKUST-KnowComp/SP-10K (Wikipedia+말뭉치 기반, 사람이 점수 매김)
import os, urllib.request

BASE="https://raw.githubusercontent.com/HKUST-KnowComp/SP-10K/master/data"
HERE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(HERE,"sp10k_cache")

def _download(fn):
    os.makedirs(CACHE,exist_ok=True)
    p=os.path.join(CACHE,fn)
    if os.path.exists(p) and os.path.getsize(p)>0: return p
    urllib.request.urlretrieve(f"{BASE}/{fn}",p)
    return p

def load_pairs(verbs=None, topn=5, min_score=4.0):
    """동사 -> 어울리는 명사들. dobj(동사+목적어)와 nsubj(주어+동사) 둘 다.
       verbs가 주어지면 그 동사만. min_score 이상만(잘 어울리는 것).
       반환: {동사: [명사들]}"""
    pairs={}
    want=set(verbs) if verbs else None
    for fn in ("dobj_annotation.txt","nsubj_annotation.txt"):
        try:
            path=_download(fn)
        except Exception:
            continue
        for line in open(path,encoding="utf-8"):
            parts=line.rstrip("\n").split("\t")
            if len(parts)!=3: continue
            # dobj: 동사 명사 점수 / nsubj: 명사 동사 점수
            if fn.startswith("dobj"):
                verb,noun,score=parts[0],parts[1],parts[2]
            else:
                noun,verb,score=parts[0],parts[1],parts[2]
            try: sc=float(score)
            except: continue
            if sc<min_score: continue
            if want and verb not in want: continue
            pairs.setdefault(verb,[])
            if noun not in pairs[verb]:
                pairs[verb].append((noun,sc))
    # 점수순 정렬 후 topn
    out={}
    for v,ns in pairs.items():
        ns.sort(key=lambda x:-x[1])
        out[v]=[n for n,_ in ns[:topn]]
    return out

if __name__=="__main__":
    p=load_pairs(["eat","drink","read","throw","buy"], topn=5)
    for v,ns in p.items():
        print(f"{v} ← {ns}")


def load_subjects(verbs=None, topn=8, min_score=4.0):
    """동사별 '주어' 짝(nsubj). people eat, dog eat 같은. {동사:[주어명사]}"""
    import os
    path=_download("nsubj_annotation.txt") if False else None
    # _download 재사용
    try:
        p=_download("nsubj_annotation.txt")
    except Exception:
        return {}
    from collections import defaultdict
    subj=defaultdict(list)
    want=set(verbs) if verbs else None
    for line in open(p,encoding="utf-8"):
        parts=line.rstrip("\n").split("\t")
        if len(parts)!=3: continue
        verb,noun,score=parts[0],parts[1],parts[2]  # 동사 주어 점수
        try: sc=float(score)
        except: continue
        if sc<min_score: continue
        if want and verb not in want: continue
        subj[verb].append((noun,sc))
    out={}
    for v,ns in subj.items():
        ns.sort(key=lambda x:-x[1])
        out[v]=[n for n,_ in ns[:topn]]
    return out
