
import io
import wave
import hashlib
import numpy as np


# ── 달팽이관: 소리(wav bytes) → 청각 특징 (검증된 코드) ──
def ear(wav_bytes):
    """소리에서 높낮이/세기/길이/거칠기 특징을 뽑는다."""
    try:
        buf = io.BytesIO(wav_bytes)
        w = wave.open(buf, "rb")
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    except Exception:
        return None
    a = np.frombuffer(raw, dtype=np.int16).astype(float)
    if len(a) == 0:
        return None
    dur = n / sr
    loud = float(np.sqrt(np.mean(a ** 2)) / 32767)
    spec = np.abs(np.fft.rfft(a * np.hanning(len(a))))
    freqs = np.fft.rfftfreq(len(a), 1 / sr)
    pitch = float(freqs[np.argmax(spec)])
    spec_n = spec / (spec.sum() + 1e-9)
    rough = float(1 - spec_n.max())
    return {"pitch": round(pitch, 1), "loud": round(loud, 3),
            "dur": round(dur, 2), "rough": round(rough, 3)}


# 특징을 거친 신호 토큰으로 (아기 입력용)
def features_to_signal(feat):
    def band(x, lo, hi):
        return "low" if x < lo else ("high" if x > hi else "mid")
    return (
        "pitch_" + band(feat["pitch"], 300, 600),   # 낮음/중간/높음
        "loud_" + band(feat["loud"], 0.2, 0.5),
        "dur_" + band(feat["dur"], 0.3, 0.8),
        "rough_" + band(feat["rough"], 0.4, 0.7),
    )


# ── 검증용 샘플 소리 (사물 이름으로 높낮이·길이 결정) ──
def get_sound_sample(name, sr=8000):
    h = hashlib.md5(("snd" + name).encode("utf-8")).hexdigest()
    freq = 150 + (int(h[0:3], 16) % 800)        # 150~950Hz
    dur = 0.2 + (int(h[3], 16) % 10) / 10.0     # 0.2~1.1초
    noisy = (int(h[4], 16) % 3 == 0)
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sig = np.sin(2 * np.pi * freq * t)
    if noisy:
        sig += 0.4 * np.random.RandomState(int(h[5:9], 16)).randn(len(t))
    sig = (sig / (np.max(np.abs(sig)) + 1e-9) * 0.8 * 32767).astype(np.int16)
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(sig.tobytes()); w.close()
    buf.seek(0)
    return buf.read()


# ── 진짜 소리 (위키미디어 공용, 실시간) ──
def get_sound_real(name):
    """단어로 위키미디어 공용에서 CC 오디오를 실시간으로 받는다(메모리만, 저장 안 함).
       반환: wav bytes 또는 None.
       ※ 작업 환경에선 위키미디어 접속이 막혀 검증 불가 → 네 컴퓨터에서 검증.
       ※ 받은 게 ogg면 wav로 변환 필요(네 컴퓨터에서 ffmpeg 등). 여기선 wav만 처리."""
    import json, urllib.parse, urllib.request
    try:
        q = urllib.parse.urlencode({
            "action": "query", "list": "search",
            "srsearch": name + " audio", "srnamespace": "6",
            "srlimit": "3", "format": "json"})
        url = "https://commons.wikimedia.org/w/api.php?" + q
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        for hit in data.get("query", {}).get("search", []):
            title = hit["title"]
            if not title.lower().endswith((".wav",)):
                continue   # 여기선 wav만(ogg는 네 컴퓨터에서 변환)
            q2 = urllib.parse.urlencode({
                "action": "query", "titles": title, "prop": "imageinfo",
                "iiprop": "url", "format": "json"})
            url2 = "https://commons.wikimedia.org/w/api.php?" + q2
            with urllib.request.urlopen(url2, timeout=15) as r:
                d2 = json.load(r)
            for p in d2.get("query", {}).get("pages", {}).values():
                src = p.get("imageinfo", [{}])[0].get("url")
                if src:
                    with urllib.request.urlopen(src, timeout=15) as r:
                        return r.read()
    except Exception:
        return None
    return None


# 사물 → 청각 신호 (use_real=True면 진짜 소리 시도, 실패/False면 샘플)
def hear(name, use_real=False):
    raw = None
    if use_real:
        raw = get_sound_real(name)
    if raw is None:
        raw = get_sound_sample(name)
    feat = ear(raw)
    if feat is None:
        return None
    return features_to_signal(feat)


if __name__ == "__main__":
    print("=== 사물별 청각 신호(샘플 소리) — 사물마다 달라야 정상 ===")
    for name in ["고양이", "물", "공", "천둥", "새"]:
        print(f"  {name} → {hear(name)}")



# ── 입(발성): 청각 특징 토큰 → wav 소리. ear()의 반대 방향. ──
def speak(feat_tokens, sr=8000):
    """아기가 소리를 낸다. 배운 단어의 청각 특징으로 wav를 만든다.
       특징이 없으면(못 배웠으면) 옹알이(아무 소리)."""
    import random
    pitch={"pitch_low":250,"pitch_mid":450,"pitch_high":750}
    loud ={"loud_low":0.15,"loud_mid":0.35,"loud_high":0.6}
    dur  ={"dur_low":0.25,"dur_mid":0.55,"dur_high":0.9}
    rough={"rough_low":0.2,"rough_mid":0.5,"rough_high":0.85}
    if not feat_tokens:   # 옹알이
        feat_tokens=[random.choice(list(pitch)), random.choice(list(dur))]
    f=250; amp=0.35; d=0.5; rg=0.3
    for t in feat_tokens:
        if t in pitch: f=pitch[t]
        elif t in loud: amp=loud[t]
        elif t in dur: d=dur[t]
        elif t in rough: rg=rough[t]
    tt=np.linspace(0,d,int(sr*d),endpoint=False)
    sig=np.sin(2*np.pi*f*tt)
    if rg>0.4: sig += rg*np.random.RandomState(0).randn(len(tt))*0.5
    sig=(sig/(np.max(np.abs(sig))+1e-9)*amp*32767).astype(np.int16)
    buf=io.BytesIO(); w=wave.open(buf,"wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(sig.tobytes()); w.close(); buf.seek(0)
    return buf.read()
