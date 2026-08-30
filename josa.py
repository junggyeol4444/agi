# -*- coding: utf-8 -*-
# 한국어 조사 붙이기 — 받침 규칙(음운). 데이터 불필요, 계산으로.
def has_batchim(word):
    if not word: return None
    last = word[-1]
    if not ('가' <= last <= '힣'): return None
    return (ord(last) - 0xAC00) % 28 != 0

_TABLE = {
    "object":  ("을", "를"),   # 목적어
    "subject": ("이", "가"),   # 주어
    "topic":   ("은", "는"),   # 주제
    "with":    ("과", "와"),   # ~와/과
    "to":      ("으로", "로"), # ~로 (받침 ㄹ 예외는 단순화)
}

def attach(word, kind="object"):
    b = has_batchim(word)
    if b is None or kind not in _TABLE:
        return word
    wb, wob = _TABLE[kind]
    return word + (wb if b else wob)

if __name__ == "__main__":
    for w,k in [("물","object"),("사과","object"),("엄마","subject"),("밥","subject")]:
        print(w,k,"→",attach(w,k))
