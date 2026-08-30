
import hashlib
from PIL import Image, ImageDraw
import numpy as np


# ── 망막: 이미지 → 시각 특징 (검증된 코드) ──
def retina(img):
    """이미지에서 밝기/색/가장자리/채움 특징을 뽑는다(0~1 범위)."""
    a = np.asarray(img.convert("RGB"), dtype=float)
    bright = a.mean() / 255
    r, g, b = a[:, :, 0].mean(), a[:, :, 1].mean(), a[:, :, 2].mean()
    tot = r + g + b + 1e-6
    gray = a.mean(axis=2)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge = float((gx > 40).mean() * 0.5 + (gy > 40).mean() * 0.5)
    filled = float((gray > gray.mean() + 10).mean())
    return {
        "bright": round(bright, 3),
        "red": round(r / tot, 3),
        "green": round(g / tot, 3),
        "blue": round(b / tot, 3),
        "edge": round(edge, 3),
        "filled": round(filled, 3),
    }


# 특징을 "거친 신호 토큰"으로 (아기 입력용; 연속값을 단계로 묶음)
def features_to_signal(feat):
    """특징을 단계 토큰으로 바꾼다(예: 밝기 high/mid/low).
       아기는 이 토큰들을 '본 것'으로 받아 학습한다."""
    def band(x, lo=0.33, hi=0.66):
        return "low" if x < lo else ("high" if x > hi else "mid")
    # 색은 셋 중 가장 큰 것
    cols = {"red": feat["red"], "green": feat["green"], "blue": feat["blue"]}
    dom_color = max(cols, key=cols.get)
    return (
        "br_" + band(feat["bright"]),
        "col_" + dom_color,
        "edge_" + band(feat["edge"], 0.005, 0.02),
        "fill_" + band(feat["filled"], 0.1, 0.4),
    )


# ── 사물 이미지 (검증용 샘플) ──
# 사물 이름을 해시로 색·모양을 정해, 사물마다 시각적으로 다르게 보이게 한다.
def get_image_sample(name, size=64):
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    shape = int(h[6], 16) % 3       # 0 원, 1 사각, 2 빈배경
    img = Image.new("RGB", (size, size), (20, 20, 20))
    d = ImageDraw.Draw(img)
    if shape == 0:
        d.ellipse([12, 12, size-12, size-12], fill=(r, g, b))
    elif shape == 1:
        d.rectangle([10, 10, size-10, size-10], fill=(r, g, b))
    else:
        img = Image.new("RGB", (size, size), (r, g, b))
    return img


# ── 사물 이미지 (진짜 사진) ──
# 위키미디어 공용 등에서 단어로 검색해 CC 이미지를 받는 자리.
# ※ 작업 환경에선 위키미디어 접속이 막혀 검증 불가 → 네 컴퓨터에서 검증.
def get_image_real(name, nth=0):
    """단어로 위키미디어 공용에서 CC 이미지를 실시간으로 받아 메모리에서 연다.
       ★ 디스크에 저장하지 않는다(용량 보호). 받아서 특징만 뽑고 사진은 버린다.
       반환: PIL Image 또는 None(실패 시).
       ※ 이 코드를 만든 작업 환경에선 위키미디어 접속이 막혀 검증 불가.
         네 개인 컴퓨터의 AGI는 인터넷 접속이 되므로 거기서 작동/검증한다.
       출처/라이선스 표시 의무(CC-BY 등). 비상업전용/저작권불명은 제외 권장."""
    import io, json, urllib.parse, urllib.request
    try:
        q = urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": name,
            "srnamespace": "6", "srlimit": "5", "format": "json"})
        url = "https://commons.wikimedia.org/w/api.php?" + q
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        hits = data.get("query", {}).get("search", [])
        if not hits:
            return None
        title = hits[min(max(0,int(nth)), len(hits)-1)]["title"]   # nth: 볼 때마다 다른 사진
        q2 = urllib.parse.urlencode({
            "action": "query", "titles": title, "prop": "imageinfo",
            "iiprop": "url", "iiurlwidth": "96", "format": "json"})
        url2 = "https://commons.wikimedia.org/w/api.php?" + q2
        with urllib.request.urlopen(url2, timeout=15) as r:
            data2 = json.load(r)
        for p in data2.get("query", {}).get("pages", {}).values():
            info = p.get("imageinfo", [{}])[0]
            src = info.get("thumburl") or info.get("url")
            if src:
                # 메모리로만 받음 — 디스크 저장 안 함
                with urllib.request.urlopen(src, timeout=15) as r:
                    raw = r.read()
                return Image.open(io.BytesIO(raw))
    except Exception:
        return None
    return None


# 사물 → 시각 신호 (use_real=True면 진짜 사진 시도, 실패/False면 샘플)
def see(name, use_real=False, nth=0):
    img = None
    if use_real:
        # 진짜 이미지를 본다. 못 받으면 '지금은 못 봤다'(None)로 정직하게 둔다.
        #  가짜 샘플로 몰래 때우지 않는다 — 그래야 아기가 진짜로 본 것만 배우고,
        #  진짜 못 보는 것(사랑·시간 같은 추상)은 계속 특징이 없어 스스로 발견한다.
        img = get_image_real(name, nth=nth)
        if img is None:
            return None
        return features_to_signal(retina(img))
    # 테스트 모드(use_real=False): 샘플 이미지로 구조만 확인.
    img = get_image_sample(name)
    return features_to_signal(retina(img))


if __name__ == "__main__":
    print("=== 사물별 시각 신호(샘플 이미지) — 사물마다 달라야 정상 ===")
    for name in ["고양이", "물", "공", "가게", "하늘"]:
        print(f"  {name} → {see(name)}")

