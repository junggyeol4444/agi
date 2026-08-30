# -*- coding: utf-8 -*-
# 명사-동사 의미 짝 로더 (kollocate, 한국어 세종 말뭉치 연어)
# "물 마시다", "공 던지다" 같은 어울리는 짝을 빈도로 가져온다.
# 필요: pip install kollocate
# 출처: github.com/Kyubyong/kollocate (세종 말뭉치 기반)

# 명사가 아닌 것(조사·의존명사 등) 거르기
_STOP = {"것","수","을","를","로","라","들","등","리","데","때","바","줄","점","면",
         "이","그","저","적","및","의","에","은","는","가","도","만","과","와","나",
         "년","월","일","개","번","명","분","뿐","채","터","축","측","건","바람"}

def load_pairs(verbs, topn=5):
    """동사 리스트 → {동사: [어울리는 명사들]} 반환.
       kollocate가 없으면 빈 dict(연결 안 함)."""
    try:
        from kollocate import Kollocate
    except Exception:
        return {}
    k = Kollocate()
    out = {}
    for verb in verbs:
        stem = verb[:-1] if verb.endswith("다") else verb  # '마시다'->'마시'
        try:
            cols = k(stem)
        except Exception:
            continue
        nouns = []
        for pos, c in cols.items():
            if "noun" in c:
                for word, cnt in c["noun"]:
                    if word not in _STOP:  # 불용어만 제외(1글자 핵심명사 물·책·공 살림)
                        nouns.append(word)
                    if len(nouns) >= topn:
                        break
            break  # 첫 품사(주 의미)만
        if nouns:
            out[verb] = nouns
    return out

if __name__ == "__main__":
    pairs = load_pairs(["마시다","읽다","던지다","사다"], topn=5)
    for v, ns in pairs.items():
        print(f"{v} ← {ns}")
