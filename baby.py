import random, json, os, time, threading
from collections import defaultdict, deque
from action_selection import ActionSelectionMixin
from belief_system import EvidenceBeliefMixin
from experience import ExperienceMemoryMixin
from motivation import IntrinsicMotivationMixin
from plan_executor import PlanExecutionMixin
from planner import PlannerMixin
from world_model import WorldModelMixin
try:
    import vision
    HAS_VISION = True
except Exception:
    HAS_VISION = False
try:
    import audio
    HAS_AUDIO = True
except Exception:
    HAS_AUDIO = False
# 실시간 사진을 인터넷에서 받을지. 네 컴퓨터(인터넷 됨)=True가 기본.
#  아기가 사물을 만날 때 진짜 이미지를 보고 시각 특징을 뽑는다.
#  (인터넷이 막힌 환경에선 자동으로 특징 없음 처리 — 안 죽는다.)
USE_REAL_IMAGE = True
# 실시간 소리를 인터넷에서 받을지(네 컴퓨터=True), 샘플로 검증할지(False).
USE_REAL_SOUND = False
# 실시간으로 계속 소리내기. 지금은 학습기간이라 꺼둠.
# 나중에 시간 배율을 인간 속도로 맞추면 True로 켜서 사람처럼 실시간 발성.
USE_REALTIME_SPEECH = False
# 번역을 kaikki에서 실시간으로 받을지(네 컴퓨터=True), 샘플로 검증할지(False).
USE_REAL_TRANSLATION = False

# 화면 버튼으로 런타임에 켜고 끄는 설정. (사이트에서 자동 다운로드 ON/OFF)
SETTINGS = {
    'real_image': USE_REAL_IMAGE,
    'real_sound': USE_REAL_SOUND,
    'real_translation': USE_REAL_TRANSLATION,
    'real_search': True,   # 사람처럼 브라우저로 검색엔진 조사 — 기본 켜짐(네 컴퓨터).
                           # 아이가 찾는 방법 = 사람: 검색창에 치고 → 사이트 열어 읽음.
                           # (⚙설정에서 끌 수 있음. playwright 없으면 자동으로 못 켜짐)
}

def set_setting(key, value):
    """화면 버튼이 부르는 함수. 설정을 켜고/끄고, 관련 캐시를 비워 새로 받게 한다."""
    if key not in SETTINGS:
        return False
    SETTINGS[key] = bool(value)
    b = _current.get('baby')
    if b is not None:
        # 켜면 다음에 새 특징을 받아오도록 캐시를 비운다
        if key == 'real_image':
            b.world.vision_cache.clear()
        elif key == 'real_sound':
            b.world.audio_cache.clear()
    return True

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baby_memory.json")

# ── 나이 환산 (네가 정한 것) ──
#  1틱 = AGI가 인간 "1일"치를 배우는 양.  AGI 1살 = 365틱.
#  현실 1일 = AGI 10살치 성장.
TICKS_PER_YEAR = 365

STAGES = [
    {"id":0,"from":0.0,"name":"신생아 · 패턴 쌓기","built":True},
    {"id":1,"from":1.0,"name":"기분이 생김","built":True},
    {"id":2,"from":2.0,"name":"행동을 스스로 고르기 (진짜 학습)","built":True},
    {"id":3,"from":4.0,"name":"기억을 길게 잇기 · 지연 인과","built":True},
    {"id":4,"from":6.0,"name":"단어를 배우고 말함 (소리-경험 연결)","built":True},
    {"id":5,"from":8.0,"name":"두 단어를 이어 짧은 문장 (어순)","built":True},
]
def stage_for_age(years):
    cur=STAGES[0]
    for s in STAGES:
        if years>=s["from"]: cur=s
    return cur

def stage_for_learning(baby):
    """단계를 '나이'가 아니라 '학습한 내용'으로 정한다.
       살수록 자동으로 오르는 게 아니라, 진짜 배워야 다음 단계로."""
    words = len(getattr(baby, "word_link", {}))
    grammar = sum(getattr(baby, "syntax3", {}).get("ko", {}).values()) if hasattr(baby, "syntax3") else 0
    rels = len(getattr(baby, "relations", {}))
    isa = len(getattr(baby, "isa", {}))
    causes = len(getattr(baby, "causes", {}))
    # 위에서부터: 많이 배운 단계일수록 먼저 검사
    if isa >= 3 or causes >= 2:
        return {"id":4, "name":"추론 · 생각하기"}        # 분류·인과를 안다
    if rels >= 2:
        return {"id":3, "name":"호기심 · 스스로 배우기"}   # 찾아 배운 게 있다
    if words >= 300 and grammar >= 100:
        return {"id":2, "name":"말하기 · 단어와 문장"}     # 단어·문법을 익혔다
    if words >= 50:
        return {"id":1, "name":"말 트임 · 단어 익히는 중"} # 단어를 배우는 중
    return {"id":0, "name":"유아기 · 보고 듣기"}          # 막 시작

# ── 세상 ──
#  밝기/소리 신호 + 숨은 보상 규칙.
#  '상황'은 (직전 신호들)이고, 상황마다 좋은 행동이 정해져 있다(아기는 모름).
#  행동은 여러 개. 아기는 겪으며 "이 상황엔 이 행동" 을 스스로 배운다.
LIGHT=["dark","dim","bright"]; SOUND=["quiet","soft","loud"]
ACTIONS=["gaze","reach","still","cry"]   # 본다 / 뻗는다 / 가만히 / 운다
# 4단계: 옹알이 후보(아직 뜻 없는 소리 조각).
BABBLE=["ba","mu","da","go","ne","pa","ti","lo","wa","ki","bo","na","se","ru","mi"]
# 환경의 사물들: 사물(경험) -> {언어코드: 단어}.
# 모국어는 한국어(ko). 같은 사물에 외국어를 추가로 얹을 수 있다(ko는 유지).
# 하드코딩 정답표가 아니라 "환경이 들려주는 소리"일 뿐 — 들으며 스스로 연결.
OBJECTS={}   # 비움 — 내가 멋대로 박은 단어 제거. 사전(dict_loader)에서 채운다.
# 5단계: 두 단어 문장. 한국어 어순 (대상)(행동). 사물에 어울리는 행동을 환경이 들려준다(아기는 모른 채 어순을 배운다).
# 5단계 다국어 문장. (의미) -> 언어 -> (대상단어, 행동단어).
# 어순은 언어마다 다르다: 한국어/일본어는 대상→행동, 영어는 행동→대상.
# 문장 어순 규칙(언어별). 단어는 사전에서 온다 — 여기에 단어를 박지 않는다.
# thing_first: 명사(대상)->동사(행동)  /  action_first: 동사->명사
SENT_ORDER = {"ko":"thing_first", "ja":"thing_first", "en":"action_first"}


class World:
    """발달형 세상: 아기가 자랄수록(나이) 신호 채널이 늘어 상황이 풍부해진다.
       어릴 땐 단순(밝기만), 크면 소리·촉각·위치가 추가돼 배울 게 계속 생긴다.
       상황마다 좋은 행동이 정해져 있고(아기는 모름), 겪으며 스스로 배운다."""
    def __init__(self, seed=7, scripted_rewards=False):
        self.rng=random.Random(seed); self.i=0; self.dir=1
        self.scripted_rewards=bool(scripted_rewards)
        self.best={}
        self.pending=[]   # 3단계: 지연 보상 큐
        self.objects={o:dict(langs) for o,langs in OBJECTS.items()}  # 사물->{언어:단어}
        self.obj_attr={}  # 사물 -> 속성(의미범주). 단어와 함께 경험하는 신호.
        self.nouns=[]     # 사전에서 온 명사(문장 어순용)
        self.subjects=[]  # (구) 한국어 사람류
        self.subjects_by_lang={}  # 언어 -> 주어 후보 목록
        self.subj_pairs_by_lang={}  # 언어 -> {동사: [주어]} (영어 nsubj 등)
        self.verbs=[]     # 사전에서 온 동사(문장 어순용)
        self.verbs_by_lang={}  # 언어별 동사 목록
        self.collocations={}   # (구) 한국어 호환용
        self.colloc_by_lang={}  # 언어 -> {동사: [어울리는 명사]} (의미 짝)
        self.vision_cache={}  # 사물 -> 시각특징(한 번 본 건 기억; 사진은 저장 안 함)
        self.sightings={}     # (33) 사물 -> 볼 때마다의 모습들(최대 3) — 일정한지 스스로 본다
        self.last_vision=None
        self.audio_cache={}   # 사물 -> 청각특징(한 번 들은 건 기억; 소리는 저장 안 함)
        self.last_audio=None
        self.active_langs=["ko"]   # 환경이 들려주는 언어(기본 한국어)
        self.last_object=None
        self.last_lang=None
        self.last_attr=None
        self.last_word=None
    def _best(self, sit):
        if sit not in self.best:
            self.best[sit]=self.rng.choice(ACTIONS)
        return self.best[sit]
    def channels_for_age(self, years):
        if years<1: return 1
        if years<2: return 2
        if years<4: return 3
        return 4
    def step(self, action, prev_sit, years):
        self.i+=self.dir
        if self.i>=2:self.i=2;self.dir=-1
        elif self.i<=0:self.i=0;self.dir=1
        ch=self.channels_for_age(years)
        parts=[LIGHT[self.i]]
        if ch>=2: parts.append(self.rng.choice(SOUND))
        if ch>=3: parts.append(self.rng.choice(["touch","notouch"]))
        if ch>=4: parts.append(self.rng.choice(["left","right"]))
        # 4단계: 눈앞의 사물 하나 + 환경이 들려주는 단어(활성 언어 중 하나).
        if not self.objects:
            # 사물이 아직 없음(사전 로드 전/실패) — 이 턴은 사물 없이 넘어간다.
            return tuple(parts), 0.0, None, None
        obj=self.rng.choice(list(self.objects.keys()))
        langs=self.objects[obj]
        avail=[l for l in self.active_langs if l in langs]
        heard_word=None; heard_lang=None
        if avail:
            heard_lang=self.rng.choice(avail)
            if self.rng.random()<0.75:
                heard_word=langs[heard_lang]                 # 정답
            else:
                pool=[L[heard_lang] for L in self.objects.values() if heard_lang in L]
                heard_word=self.rng.choice(pool)             # 잡음(같은 언어 다른 사물)
        self.last_object=obj; self.last_lang=heard_lang; self.last_word=heard_word
        self.last_attr=self.obj_attr.get(obj)   # 이 사물의 속성도 함께
        parts.append(obj)
        # ── 시각: 사물을 '본다'. 사진→특징(밝기·색·형태). 글자가 아니라 본 것.
        vsig = self._see(obj)
        if vsig:
            parts.extend(vsig)
        self.last_vision = vsig
        # ── 청각: 사물의 '소리를 듣는다'. 소리→특징(높낮이·세기·길이·거칠기).
        asig = self._hear(obj)
        if asig:
            parts.extend(asig)
        self.last_audio = asig
        sig=tuple(parts)
        # 즉시 보상: 이 상황의 좋은 행동을 했나
        # 정답 행동표 보상은 비교 실험에서만 명시적으로 켠다. 기본 삶에서는 꺼져 있다.
        immediate = (1.0 if (self.scripted_rewards and prev_sit is not None
                              and action==self._best(prev_sit)) else 0.0)
        # 3단계(4살~): 일부 보상은 시간차로 온다.
        #   prev_sit이 "지연 상황"이고 거기서 reach를 했으면 2틱 뒤에 보상 예약.
        delayed = 0.0
        if self.scripted_rewards and years >= 4.0:
            if prev_sit is not None and self._is_delay_cue(prev_sit) and action=="reach":
                self.pending.append([2, 1.0])
            nxt=[]
            for lr in self.pending:
                lr[0]-=1
                if lr[0]<=0: delayed += lr[1]
                else: nxt.append(lr)
            self.pending=nxt
        return sig, immediate + delayed, heard_word, heard_lang
    def add_object(self, obj, word, lang="ko"):
        if obj not in self.objects: self.objects[obj]={}
        self.objects[obj][lang]=word
    def enable_lang(self, lang):
        if lang not in self.active_langs: self.active_langs.append(lang)
    def _see(self, obj):
        """사물을 본다 → 시각 특징.
           핵심: 진짜 이미지 다운로드를 '그 자리에서 기다리지 않는다'.
           - 이미 본 사물: 기억한 특징을 바로 준다(빠름).
           - 처음 보는 사물: '이미지 받아줘'라고 주문만 남기고 지금은 None.
             별도 일꾼(_img_worker)이 뒤에서 받아와 채운다 → 삶(자동)이 안 멈춘다."""
        if not HAS_VISION:
            return None
        if obj in self.vision_cache:
            v = self.vision_cache[obj]
            if v == "_pending":
                return None                      # 아직 받는 중
            # (33) 가끔 같은 걸 '다시 본다' — 볼 때마다 모습이 일정한지 스스로 알기 위해
            try:
                s = self.sightings.setdefault(obj, [v] if v else [])
                if v and len(s) < 3 and self.rng.random() < 0.03:
                    self._img_ensure_worker()
                    self.img_queue.append((obj, len(s)))
            except Exception:
                pass
            return v
        # 처음 보는 사물 → 주문만 남기고 넘어간다
        self.vision_cache[obj] = "_pending"   # 중복 주문 방지 표시
        try:
            self._img_ensure_worker()
            self.img_queue.append((obj, 0))
        except Exception:
            self.vision_cache[obj] = None
        return None

    def _img_ensure_worker(self):
        """이미지 받는 별도 일꾼(백그라운드)을 한 번만 띄운다."""
        import threading
        if not hasattr(self, "img_queue"):
            self.img_queue = []
            self.img_lock = threading.Lock()
            self._img_worker_on = False
        if not self._img_worker_on:
            self._img_worker_on = True
            t = threading.Thread(target=self._img_worker, daemon=True)
            t.start()

    def _img_worker(self):
        """주문된 사물의 진짜 이미지를 하나씩 받아 특징을 채운다(삶과 별개로)."""
        import time as _t
        while True:
            obj = None
            try:
                if self.img_queue:
                    item = self.img_queue.pop(0)
                    obj, _nth = item if isinstance(item, tuple) else (item, 0)
            except Exception:
                obj = None
            if obj is None:
                _t.sleep(0.3); continue
            try:
                sig = vision.see(obj, use_real=SETTINGS['real_image'], nth=_nth)
            except Exception:
                sig = None
            # 받은 특징을 채운다(못 받았으면 None으로 — 다음에 다시 시도 가능하게 지움)
            if sig:
                if self.vision_cache.get(obj) in (None, "_pending"):
                    self.vision_cache[obj] = sig
                s = self.sightings.setdefault(obj, [])
                if len(s) < 3:
                    s.append(sig)   # (33) 이번에 본 모습 기록
            else:
                # 진짜 못 봤으면 '_pending' 표시를 지워서 나중에 다시 주문될 수 있게
                if self.vision_cache.get(obj) == "_pending":
                    self.vision_cache[obj] = None
    def _hear(self, obj):
        """사물의 소리를 듣는다 → 청각 특징. 한 번 들은 건 기억(소리 재다운로드/저장 안 함)."""
        if not HAS_AUDIO:
            return None
        if obj in self.audio_cache:
            return self.audio_cache[obj]
        try:
            sig = audio.hear(obj, use_real=SETTINGS['real_sound'])
        except Exception:
            sig = None
        self.audio_cache[obj] = sig
        return sig
    def hear_sentence_3(self):
        """세 단어 문장을 들려준다: (주어, 목적어, 동사)와 각 역할.
           아기는 단어와 함께 '역할(주어/목적어/동사)'을 위치로 듣고 순서를 배운다.
           반환: (lang, [(단어,역할),...]) 또는 (None, None)."""
        lang = self.rng.choice([l for l in self.active_langs if l in SENT_ORDER] or ["ko"])
        colloc = self.colloc_by_lang.get(lang, {})
        if not colloc or not self.subjects:
            return None, None
        verbs = [v for v in colloc if colloc[v]]
        if not verbs:
            return None, None
        self.rng.shuffle(verbs)
        verb = verbs[0]
        objs = [o for o in colloc[verb] if o in self.nouns]
        if not objs:
            return None, None
        obj = self.rng.choice(objs)
        # 그 언어의 주어 후보(없으면 이 언어는 세 단어 건너뜀)
        subs = self.subjects_by_lang.get(lang) or (self.subjects if lang == "ko" else [])
        # 영어 등: 그 동사의 주어 짝이 있으면 우선
        sp = getattr(self, "subj_pairs_by_lang", {}).get(lang, {})
        if verb in sp and sp[verb]:
            cand = [s for s in sp[verb] if s in self.nouns] or sp[verb]
            subj = self.rng.choice(cand)
        elif subs:
            subj = self.rng.choice(subs)
        else:
            return None, None
        order = SENT_ORDER.get(lang, "thing_first")
        # 역할 단위로 들려준다(어순은 언어별)
        if order == "thing_first":   # 주어 목적어 동사 (한/일)
            seq = [(subj, "S"), (obj, "O"), (verb, "V")]
        else:                         # 주어 동사 목적어 (영)
            seq = [(subj, "S"), (verb, "V"), (obj, "O")]
        # 70% 정답 순서, 30% 섞음(아기가 옳은 순서를 빈도로 가려내게)
        if self.rng.random() < 0.3:
            self.rng.shuffle(seq)
        return lang, seq

    def hear_sentence(self):
        # 사전에서 온 명사·동사로 두 단어 문장을 들려준다(언어별 어순).
        # 단어를 박지 않는다 — 명사/동사는 사전에서 채워진 것.
        if not self.nouns or not self.verbs:
            return None, None, None
        lang = self.rng.choice([l for l in self.active_langs if l in SENT_ORDER] or ["ko"])
        # 그 언어의 명사·동사로 문장(없으면 전체에서)
        vbl = getattr(self, "verbs_by_lang", {})
        nl = [o for o in self.nouns if lang in self.objects.get(o, {})] or self.nouns
        vl = vbl.get(lang) or self.verbs
        if not nl or not vl:
            return None, None, None
        # 의미 짝: 그 언어의 연어가 있으면 어울리는 명사+동사를 고른다.
        #   (무작위가 아니라 "물 마시다"/"drink water"처럼). 80% 어울리는 짝, 20% 무작위.
        noun = verb = None
        colloc = self.colloc_by_lang.get(lang)
        if colloc and self.rng.random() < 0.8:
            cand_verbs = [v for v in colloc if v in vl]
            self.rng.shuffle(cand_verbs)
            for v in cand_verbs:
                good_nouns = [n for n in colloc[v] if n in nl]
                if good_nouns:
                    verb = v
                    noun = self.rng.choice(good_nouns)
                    break
        if noun is None or verb is None:
            noun = self.rng.choice(nl)
            verb = self.rng.choice(vl)
        thing_first = (SENT_ORDER.get(lang, "thing_first") == "thing_first")
        r = self.rng.random()
        if r < 0.7:        # 정답 어순
            seq = (noun, verb) if thing_first else (verb, noun)
        else:              # 뒤집힘(잡음)
            seq = (verb, noun) if thing_first else (noun, verb)
        return lang, seq[0], seq[1]
    def _is_delay_cue(self, sit):
        # 상황의 첫 신호(밝기)가 bright면 '지연 단서'로 삼는다(아기는 모름)
        return len(sit)>0 and sit[0]=="bright"

def load_dictionary_into(world, levels=("초급",), pos=("명사",), limit=200, files=None, lang="ko"):
    """공개 사전에서 단어를 가져와 환경(world)에 채운다(언어별).
       명사: 사물로 추가(그 언어 단어로) + 속성.  동사: 그 언어 어순용 동사 목록에.
       lang="ko": 국립국어원 한국어기초사전.  lang="en": Longman 영어 기초단어.
       내가 고른 단어가 아니라 공개 사전에서 온 진짜 단어."""
    # 언어별 로더 선택
    try:
        if lang == "ko":
            import dict_loader as DL
        elif lang == "en":
            import dict_loader_en as DL
        elif lang == "ja":
            import dict_loader_ja as DL
        else:
            return 0
    except Exception:
        return 0

    # 언어별 동사 목록 보관소 준비
    if not hasattr(world, "verbs_by_lang"):
        world.verbs_by_lang = {}
    world.verbs_by_lang.setdefault(lang, [])

    n = 0
    # 명사 → 사물(그 언어 단어 달기)
    if "명사" in pos:
        try:
            nouns = DL.load_words(levels=levels, pos_filter=("명사",),
                                  limit=limit, files=files, save=False)
        except Exception:
            nouns = []
        for w in nouns:
            name = w["word"]
            if name not in world.objects:
                world.objects[name] = {}
                cat = (w.get("category") or "미상")
                world.obj_attr[name] = cat.split(">")[0].strip()
            world.objects[name][lang] = name   # 그 언어 단어
            if name not in world.nouns:
                world.nouns.append(name)
            # 사람류 명사(친족/사람종류/직업/인간관계)는 주어 후보로
            _cat = (w.get("category") or "")
            _sub = _cat.split(">")[-1].strip()
            if lang == "ko" and _sub in ("친족 관계","사람의 종류","직업","인간관계"):
                if name not in world.subjects:
                    world.subjects.append(name)
                world.subjects_by_lang.setdefault("ko", [])
                if name not in world.subjects_by_lang["ko"]:
                    world.subjects_by_lang["ko"].append(name)
            n += 1
        world.enable_lang(lang)
    # 동사 → 그 언어 어순용 목록
    if "동사" in pos:
        try:
            verbs = DL.load_words(levels=levels, pos_filter=("동사",),
                                  limit=limit, files=files, save=False)
        except Exception:
            verbs = []
        for w in verbs:
            v = w["word"]
            if v not in world.verbs_by_lang[lang]:
                world.verbs_by_lang[lang].append(v)
            if v not in world.verbs:
                world.verbs.append(v)
            # 타동사 여부: 뜻풀이에 '~을/를 ...'이 있으면 목적어를 가진다
            if lang == "ko":
                import re as _re
                d = w.get("definition") or ""
                if not hasattr(world, "transitive"):
                    world.transitive = {}
                world.transitive[v] = bool(_re.search(r'[가-힣]+[을를]\s', d))
            n += 1
    return n


# 받을 언어들. 네 컴퓨터에서 kaikki가 이 언어들의 번역을 준다.
# 'ALL' 로 두면 kaikki가 가진 모든 언어(수백 개)를 다 받는다(진짜 '모든 나라').
TARGET_LANGS = ('ko','ja','zh','fr','es','de','ru','it','pt','ar','hi','vi','th','id')
TRANSLATE_ALL_LANGS = False   # True면 위 목록 무시하고 kaikki의 모든 언어

# 검증용 샘플 번역 (kaikki 막힌 환경에서 연결 로직 확인용 — 여러 나라 언어).
# 진짜는 translate_loader.fetch_translations_real 로 네 컴퓨터에서 받는다.
_SAMPLE_TRANSLATIONS = {
    "apple":  {"ko":"사과","ja":"リンゴ","zh":"苹果","fr":"pomme","es":"manzana","de":"Apfel","ru":"яблоко"},
    "water":  {"ko":"물","ja":"水","zh":"水","fr":"eau","es":"agua","de":"Wasser","ru":"вода"},
    "dog":    {"ko":"개","ja":"犬","zh":"狗","fr":"chien","es":"perro","de":"Hund","ru":"собака"},
    "cat":    {"ko":"고양이","ja":"猫","zh":"猫","fr":"chat","es":"gato","de":"Katze","ru":"кошка"},
    "school": {"ko":"학교","ja":"学校","zh":"学校","fr":"école","es":"escuela","de":"Schule","ru":"школа"},
    "friend": {"ko":"친구","ja":"友達","zh":"朋友","fr":"ami","es":"amigo","de":"Freund","ru":"друг"},
    "book":   {"ko":"책","ja":"本","zh":"书","fr":"livre","es":"libro","de":"Buch","ru":"книга"},
    "tree":   {"ko":"나무","ja":"木","zh":"树","fr":"arbre","es":"árbol","de":"Baum","ru":"дерево"},
    "hand":   {"ko":"손","ja":"手","zh":"手","fr":"main","es":"mano","de":"Hand","ru":"рука"},
    "fire":   {"ko":"불","ja":"火","zh":"火","fr":"feu","es":"fuego","de":"Feuer","ru":"огонь"},
}


# 검증용 샘플 페이지(크롤링 막힌 환경에서 꼬리물기 구조 확인).
# 진짜는 crawler가 위키백과를 긁어온다(네 컴퓨터).
_SAMPLE_PAGES = {
    "공룡":   {"summary":"공룡은 중생대에 번성한 파충류이다.", "links":["파충류","백악기","조류","멸종"]},
    "파충류": {"summary":"파충류는 척추동물의 한 무리이다.", "links":["동물","뱀","거북","공룡"]},
    "백악기": {"summary":"백악기는 중생대의 마지막 시기이다.", "links":["중생대","공룡","멸종"]},
    "조류":   {"summary":"조류는 날개를 가진 동물이다.", "links":["동물","새","공룡"]},
    "멸종":   {"summary":"멸종은 한 종이 사라지는 것이다.", "links":["동물","공룡"]},
    "동물":   {"summary":"동물은 살아 움직이는 생물이다.", "links":["식물","생물"]},
}


def link_translations_into(world, eng_words, want_langs=None):
    """영어 단어들의 번역을 받아 한 사물에 여러 언어를 단다.
       사과=apple=リンゴ 처럼 한 사물을 여러 언어로 알게 된다.
       진짜 받기(kaikki)는 네 컴퓨터에서. 막힌 환경에선 샘플로 연결 로직만 검증.
       반환: 번역이 붙은 사물 수."""
    if want_langs is None:
        want_langs = None if TRANSLATE_ALL_LANGS else TARGET_LANGS
    real = False
    try:
        if SETTINGS['real_translation']:
            import translate_loader
            real = True
    except Exception:
        real = False
    n = 0
    for ew in eng_words:
        tr = None
        if real:
            try:
                tr = translate_loader.fetch_translations_real(ew, want_langs=want_langs)
            except Exception:
                tr = None
        if not tr:
            tr = _SAMPLE_TRANSLATIONS.get(ew)
        if not tr:
            continue
        # 사물 키는 영어 단어. 거기에 en + 번역 언어들을 단다.
        if ew not in world.objects:
            world.objects[ew] = {}
            world.obj_attr.setdefault(ew, "미상")
        world.objects[ew]["en"] = ew
        if ew not in world.nouns:
            world.nouns.append(ew)
        for code, w in tr.items():
            world.objects[ew][code] = w
            world.enable_lang(code)
        world.enable_lang("en")
        n += 1
    return n


class Baby(ActionSelectionMixin, EvidenceBeliefMixin, ExperienceMemoryMixin,
           IntrinsicMotivationMixin, PlannerMixin, PlanExecutionMixin,
           WorldModelMixin):
    def __init__(self, mem_len=2):
        import threading as _th
        self.lock = _th.RLock()   # 자동 스레드와 메인이 동시에 안 건드리게
        # 진짜 이해/사회성 상태 미리 준비 (없어서 나는 오류 원천 차단)
        self.isa={}; self.causes={}; self.relations={}; self.doubts={}
        self.concept_web={}; self.metaphors={}; self.grounding={}
        self.partner_said={}; self.talk_topics=[]; self.first_words=[]
        # 주장 자체와 그 근거를 분리해서 기억한다. 같은 말을 많이 들었다고 바로
        # 참으로 만들지 않고, 출처별 지지/반박과 수정 이력을 보존한다.
        self.beliefs={}; self.belief_revisions=[]; self.answer_history=[]
        self.verification_tasks={}; self.verification_runs=[]
        self.contextual_conclusions={}
        self.events=[]; self.event_seq=0; self.transition_model={}
        self.action_decisions=[]
        self.plans=[]
        self.plan_runs=[]
        self.drive_weights=dict(self.DEFAULT_DRIVE_WEIGHTS)
        self.mem_len=mem_len
        self.memory=defaultdict(lambda:defaultdict(int))   # 0단계: 패턴
        self.hist=[]
        self.hits=0; self.chances=0; self.lived=0
        self.world=World()
        self.mood=0.0; self.mood_sum=0.0; self.last_feeling=None
        # 2단계: 행동 가치 (상황->행동->평균보상) + 학습 진척용
        self.q=defaultdict(lambda:{a:0.0 for a in ACTIONS})
        self.qn=defaultdict(lambda:{a:0 for a in ACTIONS})
        self.explore=0.15
        self.trace=deque(maxlen=4)   # 3단계: 최근 (상황,행동)
        self.word_link=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # 사물->언어->단어
        self.obj_attr=defaultdict(lambda: defaultdict(int))  # 사물->속성->경험횟수 (의미)
        self.syntax=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))   # 5단계: 언어->단어->다음단어 빈도
        self.sentences_heard=0
        # B-2: 세 단어 역할 순서 학습. 언어->역할순서튜플 빈도 (예: ('S','O','V'))
        self.syntax3=defaultdict(lambda: defaultdict(int))
        # 역할별로 어떤 단어가 오는지(주어자리엔 사람 등) 언어->역할->단어빈도
        self.role_words=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.words_known=0       # 연결이 잡힌 경험 수
        self.reward_sum=0.0; self.reward_n=0
        self.recent_reward=deque(maxlen=2000)  # 최근 보상(성장곡선용)
        self.growth_curve=[]   # (나이, 그 구간 평균행동성공) 점들
        self._bin_sum=0.0; self._bin_n=0; self._bin_size=200
        self.last_signal=None
        self.last_action=None

    def _key(self):
        if len(self.hist)<self.mem_len: return None
        return tuple(self.hist[-self.mem_len:])
    def predict(self):
        k=self._key()
        if k is None or k not in self.memory or not self.memory[k]: return None
        return max(self.memory[k],key=self.memory[k].get)

    def choose_action(self):
        sig=self.last_signal
        decision = self.select_action(list(sig) if sig else None, ACTIONS)
        return decision["action"]

    # 몇 번 이상 같은 이름을 들어야 그 사물을 '확실히 안다'고 친다.
    KNOW_THRESHOLD = 3
    def _count_known(self):
        """확실히 아는 사물 수 = 어떤 언어로든 같은 이름을 KNOW_THRESHOLD번 이상
           들어서 굳어진 사물. 한두 번 본 건 '아직 배우는 중'이라 안 센다."""
        n = 0
        for obj, langs in list(self.word_link.items()):
            confident = False
            for lang, words in langs.items():
                for w, cnt in words.items():
                    if cnt >= self.KNOW_THRESHOLD:
                        confident = True; break
                if confident: break
            if confident: n += 1
        return n
    def known_objects(self):
        """확실히 아는 사물 목록(확인용)."""
        out=[]
        for obj, langs in list(self.word_link.items()):
            for lang, words in langs.items():
                if any(c>=self.KNOW_THRESHOLD for c in words.values()):
                    out.append(obj); break
        return out

    def live_one(self, injected=None, action_override=None):
        guess=self.predict()
        action=action_override if action_override in ACTIONS else self.choose_action()
        prev=self.last_signal
        years=self.lived/TICKS_PER_YEAR
        if injected is not None:
            actual=tuple(injected); reward=0.0; heard_word=None; heard_lang=None
        else:
            actual,reward,heard_word,heard_lang=self.world.step(action, prev, years)

        # 0단계 패턴 + 적중
        status="new"; stable=0.0
        if guess is not None:
            self.chances+=1
            if guess==actual: self.hits+=1; status="hit"; stable=1.0
            else: status="miss"; stable=-0.5
        k=self._key()
        first=(k is not None and actual not in self.memory[k])
        if k is not None: self.memory[k][actual]+=1
        self.hist.append(actual)

        model_before = self.predict_effects(list(prev) if prev else None, action)
        model_after = self.learn_transition(list(prev) if prev else None, action,
                                            list(actual), reward)
        motivation = self.intrinsic_motivation(
            novelty=1.0 if first else 0.0,
            uncertainty_before=model_before["uncertainty"],
            uncertainty_after=model_after["uncertainty"],
        )
        learning_reward = float(reward) + motivation["total"]

        # 1단계 기분 = 예측안정 + 호기심 + (2단계)행동보상
        feeling=0.5*stable + 0.2*(1.0 if first else 0.0) + 0.3*learning_reward
        self.mood=0.8*self.mood+0.2*feeling
        self.mood_sum+=self.mood

        # 2+3단계 학습: 방금 (상황,행동)을 흔적에 남기고,
        # 보상이 오면 최근 행동들에 시간차로 공을 나눈다(가까운 과거일수록 크게).
        if prev is not None:
            self.trace.append((prev, action))
            self.reward_sum+=learning_reward; self.reward_n+=1
            self.recent_reward.append(learning_reward)
        if learning_reward>0 and self.trace:
            for i,(s,a) in enumerate(reversed(self.trace)):
                credit=learning_reward*(0.6**i) # 외부 정답표가 아닌 경험 기반 동기도 포함
                # 안전: 상태 dict에 행동 키가 없어도 터지지 않게(항상 모든 행동 보장)
                if a not in self.qn[s]: self.qn[s][a]=0
                if a not in self.q[s]:  self.q[s][a]=0.0
                self.qn[s][a]+=1; n=self.qn[s][a]
                self.q[s][a]=self.q[s][a]+(credit-self.q[s][a])/n
            self._bin_sum+=learning_reward; self._bin_n+=1
            if self._bin_n>=self._bin_size:
                yrs=round(self.lived/TICKS_PER_YEAR,2)
                self.growth_curve.append([yrs, round(self._bin_sum/self._bin_n*100,1)])
                if len(self.growth_curve)>300: self.growth_curve=self.growth_curve[-300:]
                self._bin_sum=0.0; self._bin_n=0

        # 4단계: 들린 단어를 (눈앞 사물, 언어)에 연결.
        if heard_word is not None and heard_lang is not None and len(actual)>0:
            obj=getattr(self.world, "last_object", None) or actual[-1]
            _prev=self.word_link[obj][heard_lang][heard_word]
            self.word_link[obj][heard_lang][heard_word]+=1
            # (36) 처음으로 '확실히 알게 된' 순간 → 그 말로 말해본다(배움→말하기 연결)
            if _prev+1==self.KNOW_THRESHOLD:
                if not isinstance(getattr(self,"first_words",None), list): self.first_words=[]
                _vb=None
                for _v2,_os in self.world.colloc_by_lang.get("ko",{}).items():
                    if obj in _os: _vb=_v2; break
                self.first_words.append({"단어":obj, "말":(obj+" "+_vb) if _vb else obj})
                if len(self.first_words)>30: del self.first_words[:len(self.first_words)-30]
            # (겪음 장부) 이 사물을 실제로 봤나·들었나 + 그때 기분(47 좋아/싫어의 재료)
            if not isinstance(getattr(self,"grounding",None), dict): self.grounding={}
            _gg=self.grounding.setdefault(obj,{"본적":0,"들은적":0,"글자로만":0,"기분합":0.0,"기분n":0})
            _vc=self.world.vision_cache.get(obj)
            if _vc and _vc!="_pending": _gg["본적"]=_gg.get("본적",0)+1
            _ac=getattr(self.world,"audio_cache",{}).get(obj) if hasattr(self.world,"audio_cache") else None
            if _ac: _gg["들은적"]=_gg.get("들은적",0)+1
            _gg["기분합"]=_gg.get("기분합",0.0)+float(self.mood); _gg["기분n"]=_gg.get("기분n",0)+1
            # 단어와 함께 사물의 속성도 경험(글자만이 아니라 "어떤 것인지")
            attr=getattr(self.world, "last_attr", None)
            if attr is not None:
                self.obj_attr[obj][attr]+=1
            # (스스로 호기심) 눈앞에 보이는데 아직 확실히 모르는 사물이면
            #  "이게 뭐지?" 하고 스스로 궁금해한다 — 사람이 안 알려줘도 알아서.
            #  세상(인터넷)을 살아가다 마주친 모르는 것에서 궁금증이 자란다.
            try:
                _known_here=False
                for _lg,_ws in self.word_link.get(obj,{}).items():
                    if any(_cnt>=self.KNOW_THRESHOLD for _cnt in _ws.values()):
                        _known_here=True; break
                if not _known_here:
                    self._wonder(obj)   # 아직 확실히 모름 → 스스로 궁금
            except Exception:
                pass
        self.words_known=self._count_known()
        # 5단계(8살~): 환경이 가끔 두 단어 문장을 들려주고, 아기가 어순을 배운다.
        years_now=self.lived/TICKS_PER_YEAR
        if years_now>=8.0 and injected is None and random.random()<0.5:
            # 대부분 두 단어, 가끔(30%) 세 단어 문장도 듣는다
            if self.world.rng.random() < 0.3:
                lng3, seq3 = self.world.hear_sentence_3()
                if lng3 is not None:
                    self.hear_sentence_3(lng3, seq3)
            else:
                lng,s1,s2=self.world.hear_sentence()
                if lng is not None:
                    self.hear_sentence(lng,s1,s2)
        self.last_signal=actual; self.last_action=action; self.lived+=1
        # 언어 문장이 아니라 실제 상태-행동-결과 사건을 기억하고 세계 모델에 반영한다.
        self.record_event(
            "interaction", actor="self", action=action,
            obj=getattr(self.world, "last_object", None),
            outcome={"state": list(actual), "external_reward": reward,
                     "intrinsic_reward": motivation["total"]},
            context={"previous_state": list(prev) if prev else None},
            source="direct",
            metadata={"decision": self.action_decisions[-1]
                      if self.action_decisions else None},
        )
        if status=="hit": self.last_feeling="안정"
        elif first: self.last_feeling="호기심"
        elif learning_reward>0: self.last_feeling="배움"
        elif status=="miss": self.last_feeling="어긋남"
        else: self.last_feeling="덤덤"

        return {"t":self.lived,"seen":list(actual),
                "guess":list(guess) if guess else None,"status":status,
                "action":action,"reward":reward,
                "external_reward":reward,"intrinsic_reward":motivation["total"],
                "motivation":motivation,
                "decision":self.action_decisions[-1] if self.action_decisions else None,
                "mood":round(self.mood,3),"feeling":self.last_feeling}

    def say(self, obj, lang="ko"):
        """사물을 주면 그 언어로 말한다. 모르면 옹알이.
           새 정보가 있으면 새 걸 먼저(현재값), 옛날 건 history에 보관."""
        # 새 정보(current) 우선
        cur = getattr(self, "word_current", {})
        if obj in cur and lang in cur.get(obj, {}):
            return cur[obj][lang], True
        if obj in self.word_link and lang in self.word_link[obj] and self.word_link[obj][lang]:
            wl=self.word_link[obj][lang]
            return max(wl, key=wl.get), True
        return random.choice(BABBLE), False

    def update_word(self, obj, lang, new_word):
        """원본 데이터(사전 등)가 업데이트되어 새 단어가 들어올 때.
           기존에 배운 것과 많이 다르면(다른 단어면):
             - 옛날 것을 history에 보관(까먹지 않음)
             - 새 것을 현재값(current)으로 = 먼저 떠올림
           같으면 그대로(빈도만 올림)."""
        if not hasattr(self, "word_current"):
            self.word_current = {}           # 사물->언어->현재(최신) 단어
        if not hasattr(self, "word_history"):
            self.word_history = {}           # 사물->언어->[옛날 단어들]
        # 지금 알고 있는 단어(빈도 최대 또는 현재값)
        known = None
        cur = self.word_current.get(obj, {})
        if lang in cur:
            known = cur[lang]
        elif obj in self.word_link and lang in self.word_link[obj] and self.word_link[obj][lang]:
            wl = self.word_link[obj][lang]
            known = max(wl, key=wl.get)
        if known is not None and known != new_word:
            # 많이 다름 → 옛날 걸 history에 보관
            self.word_history.setdefault(obj, {}).setdefault(lang, [])
            if known not in self.word_history[obj][lang]:
                self.word_history[obj][lang].append(known)
        # 새 걸 현재값으로(먼저 떠올림)
        self.word_current.setdefault(obj, {})[lang] = new_word
        # 학습 기록에도 반영(까먹지 않게)
        self.word_link[obj][lang][new_word] += 3
        return {"new": new_word, "old_kept": self.word_history.get(obj, {}).get(lang, [])}

    def recall_history(self, obj, lang="ko"):
        """옛날 정보(보관된 것)를 꺼내본다. 까먹지 않았음을 확인."""
        return getattr(self, "word_history", {}).get(obj, {}).get(lang, [])

    def _say_orig(self, obj, lang="ko"):
        if obj in self.word_link and lang in self.word_link[obj] and self.word_link[obj][lang]:
            wl=self.word_link[obj][lang]
            return max(wl, key=wl.get), True
        return random.choice(BABBLE), False
    def attr_of(self, obj):
        """아기가 이 사물에 대해 경험한 속성(가장 자주 함께 온 것)."""
        if obj in self.obj_attr and self.obj_attr[obj]:
            return max(self.obj_attr[obj], key=self.obj_attr[obj].get)
        return None
    def speak_object(self, obj):
        """아기가 사물을 '소리내어' 말한다. 들었던 청각 특징으로 wav를 만든다.
           안 배운 사물/시각청각 없으면 옹알이. 반환: wav bytes 또는 None."""
        if not HAS_AUDIO:
            return None
        # 이 사물을 들었던 청각 특징(환경 캐시)
        feat = None
        try:
            feat = self.world.audio_cache.get(obj)
        except Exception:
            feat = None
        try:
            return audio.speak(list(feat) if feat else None)
        except Exception:
            return None
    def known_langs(self, obj):
        return [l for l in self.word_link.get(obj,{}) if self.word_link[obj][l]]
    def hear_sentence_3(self, lang, seq):
        """세 단어 문장을 듣고 역할 순서를 배운다. seq=[(단어,역할),...]"""
        roles = tuple(r for _, r in seq)
        self.syntax3[lang][roles] += 1
        for word, role in seq:
            self.role_words[lang][role][word] += 1
        self.sentences_heard += 1

    def preferred_order3(self, lang="ko"):
        """배운 것 중 가장 흔한 세 자리 역할 순서."""
        d = self.syntax3.get(lang, {})
        if not d:
            return None
        return max(d, key=d.get)

    def make_sentence_3_learned(self, lang="ko"):
        """아기가 '배운' 역할 순서로 세 단어 문장을 만든다(규칙이 아니라 학습 결과).
           역할 순서도, 각 역할에 올 단어도 자기가 들은 빈도에서 고른다."""
        order = self.preferred_order3(lang)
        rw = self.role_words.get(lang, {})
        if not order or not rw:
            return None
        out = []
        for role in order:
            words = rw.get(role)
            if not words:
                return None
            # 그 역할에서 가장 자주 들은 단어군 중 무작위(상위)
            top = sorted(words, key=words.get, reverse=True)[:8]
            out.append(self.world.rng.choice(top))
        # 조사: S=주어(이/가), O=목적어(을/를)
        if lang == "ko":
            try:
                import josa
                res = []
                for (word), role in zip(out, order):
                    if role == "S":
                        res.append(josa.attach(word, "subject"))
                    elif role == "O":
                        res.append(josa.attach(word, "object"))
                    else:
                        res.append(word)
                return tuple(res)
            except Exception:
                pass
        return tuple(out)

    def hear_sentence(self, lang, w1, w2):
        # 그 언어 안에서 '첫 단어 다음에 둘째 단어'라는 순서를 빈도로 쌓는다.
        self.syntax[lang][w1][w2]+=1
        self.sentences_heard+=1
    def make_sentence(self, start_word, lang="ko"):
        # 두 단어 문장을 만들고, 한국어면 조사를 붙인다(받침 규칙).
        seq = self._make_sentence_raw(start_word, lang)
        if lang == "ko" and len(seq) == 2:
            seq = self._add_korean_josa(seq)
        return seq

    def _add_korean_josa(self, seq):
        """한국어 (명사, 동사)에 조사를 붙인다. 첫 단어가 진짜 명사일 때만."""
        try:
            import josa
        except Exception:
            return seq
        noun, verb = seq
        # 첫 단어가 진짜 명사가 아니면(동사 등) 조사 안 붙임
        try:
            nouns = set(self.world.nouns)
        except Exception:
            nouns = set()
        if noun not in nouns:
            return seq
        kind = "object"
        subj = getattr(self.world, "subj_pairs", {})
        if verb in subj and noun in subj.get(verb, ()):
            kind = "subject"
        return (josa.attach(noun, kind), verb)

    def make_sentence_3(self, lang="ko"):
        """세 단어 문장: (주어+조사) (목적어+조사) (동사). 한국어 먼저.
           주어=사람류 명사, 목적어+동사=의미 짝(연어), 조사=받침 규칙."""
        colloc = self.world.colloc_by_lang.get(lang, {})
        subs = self.world.subjects
        if not colloc or not subs:
            return None
        # 목적어 짝이 있는 동사 중 하나
        verbs = [v for v in colloc if colloc[v]]
        if not verbs:
            return None
        # (9) 아무 말이나 조합하지 않는다 — 확실히 아는 것들로 문장을 만든다
        _known = set(self.known_objects())
        self.world.rng.shuffle(verbs)
        verb = None
        if _known:
            for _v in verbs:
                if any(o in _known for o in colloc[_v]):
                    verb = _v; break
        if verb is None:
            verb = verbs[0]
        trans = getattr(self.world, "transitive", {})
        # 자동사(목적어 안 가짐)면 "주어가 동사"만 — "별이 빛나다"(O), "별을 늙다"(X 방지)
        is_trans = trans.get(verb, True)   # 모르면 타동사로 가정
        subj = self.world.rng.choice(subs)
        try:
            import josa
            subj2 = josa.attach(subj, "subject")
        except Exception:
            subj2 = subj
        if not is_trans:
            # 자동사: 목적어 없이 주어+동사
            return (subj2, verb)
        # 타동사: 어울리는 목적어 붙이기
        objs = [o for o in colloc[verb] if o in self.world.nouns]
        _ko2 = [o for o in objs if o in _known]
        if _ko2: objs = _ko2   # 아는 것 우선
        if not objs:
            return (subj2, verb)   # 목적어 후보 없으면 주어+동사
        obj = self.world.rng.choice(objs)
        try:
            import josa
            obj2 = josa.attach(obj, "object")
        except Exception:
            obj2 = obj
        order = SENT_ORDER.get(lang, "thing_first")
        if order == "thing_first":   # 한국어/일본어: 주어 목적어 동사
            return (subj2, obj2, verb)
        else:                         # 영어: 주어 동사 목적어
            return (subj2, verb, obj2)

    def _make_sentence_raw(self, start_word, lang="ko"):
        # 시작 단어로 그 언어의 두 단어 문장을 만든다.
        sx = self.syntax.get(lang, {})
        if start_word in sx and sx[start_word]:
            nxt=max(sx[start_word], key=sx[start_word].get)
            return (start_word, nxt)
        # 직접 안 배운 단어도, 그 언어의 어순 규칙을 일반화한다.
        from collections import Counter
        try:
            nouns = set(self.world.nouns)
            vbl = getattr(self.world, "verbs_by_lang", {})
            verbs = set(vbl.get(lang, [])) or set(self.world.verbs)
        except Exception:
            nouns = set(); verbs = set()
        order = SENT_ORDER.get(lang, "thing_first")
        # thing_first(한국어): 명사로 시작 → 동사 붙임
        # action_first(영어):  동사로 시작 → 명사 붙임
        start_is_noun = start_word in nouns
        start_is_verb = start_word in verbs
        want_second = None
        if order == "thing_first" and start_is_noun:
            want_second = verbs           # 명사 다음 동사
        elif order == "action_first" and start_is_verb:
            want_second = nouns           # 동사 다음 명사
        if want_second:
            after = Counter()
            for w1, nxts in sx.items():
                for w2, c in nxts.items():
                    if w2 in want_second:
                        after[w2] += c
            if after:
                return (start_word, after.most_common(1)[0][0])
            # 학습된 게 없으면 그 부류에서 아무거나(어순만이라도 맞춤)
            if want_second:
                import random as _r
                pool = list(want_second)
                if pool:
                    return (start_word, _r.choice(pool))
        return (start_word,)   # 아직 모르면 한 단어
    def correct_sentence(self, w1, w2, lang="ko"):
        # 사람이 교정: 그 언어에서 'w1 다음 w2가 맞다'. 기존 최다를 확실히 넘게.
        cur = self.syntax[lang][w1]
        cur_max = max(cur.values()) if cur else 0
        self.syntax[lang][w1][w2] = cur_max + 50
        return self.syntax[lang][w1][w2]
    def teach(self, obj, word, lang="ko", times=15):
        """사람이 직접 가르친다: (사물, 언어)=단어. 즉석 연결. 기존 언어는 유지."""
        for _ in range(max(1,times)):
            self.word_link[obj][lang][word]+=1
        self.words_known=self._count_known()
        return self.word_link[obj][lang][word]
    def hear_and_react(self, word):
        self.lock.acquire()
        try:
            return self._hear_and_react(word)
        finally:
            self.lock.release()
    def _hear_and_react(self, word):
        """사람이 단어를 주면 그 단어가 가리키는 사물을 떠올린다.
           지시어(그거/it/それ 등)면 최근 기억(working memory)에서 떠올린다.
           사물을 떠올리면 그 사물을 단기 기억에 쌓는다(맥락)."""
        if not hasattr(self, "working_memory"):
            from collections import deque
            self.working_memory = deque(maxlen=5)   # 최근 나온 사물들(맥락)
        # 지시어 목록(다국어). 받침 붙은 형태(그것을/그걸)도 처리.
        DEICTIC = ("그거","그것","이거","이것","저거","저것","그걸","이걸",
                   "it","that","this","これ","それ","あれ")
        w = word.strip()
        base = w
        for josa in ("을","를","이","가","은","는","과","와"):
            if base.endswith(josa) and len(base) > 1:
                base = base[:-1]; break
        if base in DEICTIC or w in DEICTIC:
            # 지시어 → 가장 최근 사물을 떠올린다
            if self.working_memory:
                recalled = self.working_memory[-1]
                return recalled, -1, "deictic"   # n=-1: 기억에서 떠올림 표시
            return None, 0, None
        # 일반 단어 → 평소대로 사물 떠올리기
        best=None; bestn=0; best_lang=None
        for obj, langs in self.word_link.items():
            for lang, words in langs.items():
                n=words.get(word,0)
                if n>bestn: bestn=n; best=obj; best_lang=lang
        if best is not None:
            self.working_memory.append(best)   # 맥락에 쌓기
        else:
            # 모른다! 호기심 — "이게 뭐지?" 하고 궁금한 것 목록에 담아둔다.
            self._wonder(word)
        return best, bestn, best_lang

    def _wonder(self, thing):
        """모르는 것을 만나면 궁금해한다. 궁금한 것 목록에 담고 횟수를 센다.
           (자주 만나는 모르는 것일수록 더 궁금해진다 = 우선 배운다.)"""
        if not hasattr(self, "curiosity"):
            self.curiosity = {}            # 모르는 것 -> 만난 횟수(궁금한 정도)
        if not thing or not thing.strip():
            return
        self.curiosity[thing] = self.curiosity.get(thing, 0) + 1

    def what_im_curious(self, top=10):
        """지금 가장 궁금한 것들(자주 만난 모르는 것 순). 호기심 목록."""
        c = getattr(self, "curiosity", {})
        return sorted(c.items(), key=lambda x: -x[1])[:top]

    def respond(self, word):
        self.lock.acquire()
        try:
            result = self._attach_pending_corrections(word, self._respond(word))
            return self._record_answer(word, result)
        finally:
            self.lock.release()
    def chat(self, text):
        """대화: 아는 건 아기가 배운 걸로 답하고, 모르는 건 인터넷을 검색해서
           알려준다. LLM처럼 통째로 아는 척이 아니라 — 알거나/찾아보거나(사람처럼).
           반환: {say, source, mind}."""
        with self.lock:
            r = self._attach_pending_corrections(text, self._respond(text))
            r = self._record_answer(text, r)
        def finish(result):
            # _respond의 첫 답은 이미 기록했다. 검색으로 답이 바뀌면 최종 답도 남긴다.
            return self._record_answer(text, self._attach_pending_corrections(text, result))
        mind = r.get("mind", "")
        say = r.get("say", "…")
        # 아는 것으로 답했으면 그대로
        if "모르는 것" not in mind:
            return {"say": say, "source": "배운 것", "mind": mind}
        # 모르는 것 → 인터넷 검색해서 알려준다(사람이 모르면 찾아보듯)
        w = (text or "").strip()
        w = w.split()[-1] if " " in w else w
        if not (SETTINGS.get('real_search') or SETTINGS.get('real_translation')
                or SETTINGS.get('real_image')):
            return finish({"say": say + " (검색이 꺼져 있어 못 찾아봤어 — ⚙설정에서 검색을 켜줘)",
                    "source": "모름(검색 꺼짐)", "mind": mind})
        try:
            with self.lock:
                info = self._search_and_learn(w)
            summ = ((info or {}).get("summary") or "").strip()
            src = (info or {}).get("source") or "인터넷"
            err = (info or {}).get("error")
            if summ:
                return finish({"say": f"나도 잘 몰랐는데 찾아봤어. {summ[:400]}",
                        "source": src, "mind": "모르는 것 → 검색해서 알려줌"})
            elif err:
                return finish({"say": f"'{w}' 찾아보려는데 잘 안 됐어. ({err[:80]})",
                        "source": src, "mind": "검색 시도했지만 실패"})
            else:
                return finish({"say": f"'{w}' 찾아봤는데 확실한 내용을 못 가져왔어.",
                        "source": src, "mind": "검색했지만 내용 없음"})
        except Exception as e:
            return finish({"say": f"찾아보다 문제가 생겼어: {type(e).__name__}",
                    "source": "오류", "mind": str(e)[:80]})

    def _respond(self, word):
        """진짜 대화: 한 마디를 받아 응답한다.
           유창한 가짜가 아니라 '어눌해도 진짜' — 아는 것만 말하고, 모르면
           되묻고, 모순되면 의심하고, 맥락을 잇는다.
           반환: {말, 속마음(왜 그렇게 답했나)}."""
        w = (word or "").strip()
        if not w:
            return {"say": "...", "mind": "들은 게 없음"}
        # (35·45) 문장으로 말하면: 거기서 배우고, 어긋나면 되묻는다
        if " " in w:
            _st = self._learn_from_statement(w)
            if _st: return _st
        obj, strength, lang = self.hear_and_react(w)
        # (43) 상대가 말한 것 기억
        if not isinstance(getattr(self,"partner_said",None), dict): self.partner_said={}
        self.partner_said[w]=self.partner_said.get(w,0)+1
        _again = self.partner_said[w]>=3
        # (18) 대화 주제 기억 — 아까 얘기와 이어주기
        if not isinstance(getattr(self,"talk_topics",None), list): self.talk_topics=[]
        _extra_parts=[]
        if obj is not None:
            _isa=getattr(self,"isa",{})
            for _prev in reversed(self.talk_topics[-5:]):
                if _prev!=obj and _isa.get(_prev) and _isa.get(_prev)==_isa.get(obj):
                    _extra_parts.append(f"아까 {_prev} 얘기했지 — {obj}도 {self._j(_isa[obj],'이야','야')}.")
                    break
            self.talk_topics.append(obj)
            if len(self.talk_topics)>20: del self.talk_topics[:len(self.talk_topics)-20]
            # (34) 비유로 아는 것이면 곁들임
            _m=getattr(self,"metaphors",{}) or {}
            if obj in _m:
                _extra_parts.append(f"사람들은 {self._j(obj,'을','를')} {_m[obj].get('처럼')}처럼 말하기도 해.")
            # (44) 감정이라고 '배운' 것이면 공감 — 내 기분 경험으로
            try:
                _cc=self.concept_of(obj)
                if _cc.get("종류") and ("감정" in str(_cc.get("종류"))):
                    _extra_parts.append("그건 감정이구나. 나도 기분이 좋을 때랑 별로일 때가 있어.")
            except Exception: pass
            # (47) 겪은 기분에서 나온 좋아/싫어
            _fl=self.my_feeling(obj)
            if _fl=="좋아": _extra_parts.append(f"나는 {obj} 좋아 — 겪을 때 기분이 좋았거든.")
            elif _fl=="별로": _extra_parts.append(f"나는 {obj}는 좀 별로야.")
            # (37) 형제 개념에서 옮겨온 추측 — 확신 강도까지 붙여 말한다
            _tg=self.transfer_guess(obj)
            if _tg:
                _g0=_tg[0]
                _extra_parts.append(f"({_g0['확신']}: {_g0['추측']} — {_g0['근거']})")
        if _again: _extra_parts.append("이거 자주 물어보네!")
        _extra=(" "+" ".join(_extra_parts)) if _extra_parts else ""

        # 1) 모르는 것 → 솔직히 모른다 하고 되묻는다 (지어내지 않음)
        if obj is None:
            self._wonder(w)
            return {"say": f"'{w}'? 그게 뭐야?",
                    "mind": "모르는 것 — 지어내지 않고 되물음"}

        # 2) 아는 것 → 아는 걸 보탠다 (추론/분류 활용)
        key = obj
        # 분류를 알면: "아, X? 그건 ~이야"
        thoughts = self.say_thought(key, lang="ko") if hasattr(self, "say_thought") else []
        # 모순(의심) 중이면 솔직히 헷갈린다고
        doubting = key in getattr(self, "doubts", {})
        # 인과를 알면 곁들임
        why = self.why(key) if hasattr(self, "why") else []

        ko_name = self.world.objects.get(key, {}).get("ko", key)
        if doubting:
            conf = " 아니면 ".join(self.doubts[key])
            return {"say": f"음… {ko_name}? 그게 {conf} 중 뭔지 헷갈려.",
                    "mind": "모순을 알아챔 — 확신 안 하고 의심"}
        if thoughts:
            t = thoughts[0]["sentence"]
            return {"say": f"아, {ko_name}? {t}.{_extra}",
                    "mind": f"아는 것 + 추론을 보탬 ({thoughts[0]['because']})",
                    "beliefs_used": [self._belief_key(key, "is_a", self.isa[key])]}
        if why:
            return {"say": f"{ko_name}? 그건 {why[0]['because']} {why[0]['how']} 그래.{_extra}",
                    "mind": "아는 인과를 보탬"}
        # 분류·인과는 모르지만 사물은 앎 → 솔직히 거기까지만
        return {"say": f"응, {ko_name} 알아.{_extra}",
                "mind": "사물은 알지만 더는 모름 — 아는 만큼만 말함"}

    def converse(self, words):
        """여러 마디를 주고받는다(맥락 이어서). words: 사람이 말한 것들."""
        out = []
        for w in words:
            r = self.respond(w)
            out.append({"heard": w, "reply": r["say"], "mind": r["mind"]})
        return out

    def concept_of(self, obj):
        """한 사물에 흩어진 갈래를 하나의 '개념 덩어리'로 묶는다.
           이름·보임·들림·속성·하는일(연어)·종류(분류)·관련을 한꺼번에."""
        c = {"개념": obj, "이름": {}, "보임": None, "들림": None,
             "속성": None, "하는일": [], "종류": None, "관련": []}
        # 1) 여러 언어 이름
        langs = self.world.objects.get(obj, {})
        c["이름"] = dict(langs) if isinstance(langs, dict) else {}
        # 2) 보이는 모습(시각특징)
        _v2 = self.world.vision_cache.get(obj) if hasattr(self.world,"vision_cache") else None
        if _v2 and _v2 != "_pending":
            c["보임"] = _v2
        # 3) 들리는 소리(청각특징)
        if hasattr(self.world, "audio_cache") and obj in self.world.audio_cache:
            c["들림"] = self.world.audio_cache[obj]
        # 4) 속성(의미범주)
        if hasattr(self.world, "obj_attr"):
            # (6) 속성도 '겪어서' — 여러 번 함께 겪은 속성만 확실히 안다 (사전 주입 아님)
            _mine = getattr(self, "obj_attr", {}).get(obj)
            if _mine:
                _ba = max(_mine.items(), key=lambda x: x[1])
                c["속성"] = _ba[0] if _ba[1] >= 2 else None
        # 5) 하는 일 — 이 사물이 목적어로 어울리는 동사들(물→마시다)
        for lang, colloc in getattr(self.world, "colloc_by_lang", {}).items():
            for verb, objs in colloc.items():
                if obj in objs and verb not in c["하는일"]:
                    c["하는일"].append(verb)
        # 6) 종류(분류, isa)
        c["종류"] = getattr(self, "isa", {}).get(obj)
        # 7) 관련된 것들(크롤링 연결)
        c["관련"] = getattr(self, "relations", {}).get(obj, [])
        # 8) (33) 추상/구체 — 규칙 딱지가 아니라 아이가 '겪은 사실'에서 스스로 안다:
        #    · 볼 때마다 모습이 일정하면(사과) → 실체가 있다 = 구체
        #    · 볼 때마다 제각각이거나, 본 적이 없는데 말·글에서만 나오면(사랑) → 추상
        c["다른나라말"] = self.my_translations(obj)
        _g = (getattr(self, "grounding", {}) or {}).get(obj, {})
        _sights = (getattr(self.world, "sightings", {}) or {}).get(obj, [])
        if not _sights:
            # 재시작하면 world는 비니, 겪음 장부에 남긴 모습들로 판단(영구 기억)
            _sights = [tuple(str(x).split("~")) for x in (_g.get("모습들") or [])]
        c["모습들"] = len(_sights)
        c["감각경험"] = _g or None
        _steady = None
        if len(_sights) >= 2:
            _ps=[]
            for _i in range(len(_sights)):
                for _j in range(_i+1, len(_sights)):
                    _sa,_sb=set(_sights[_i]),set(_sights[_j])
                    _ps.append(len(_sa&_sb)/max(1,len(_sa|_sb)))
            _avg=sum(_ps)/len(_ps)
            _steady = _avg >= 0.5
        _seen = _g.get("본적", 0); _textonly = _g.get("글자로만", 0)
        if _steady is True:
            c["추상"] = False; c["모습"] = "볼 때마다 비슷 — 실체 있음"
        elif _steady is False:
            c["추상"] = True;  c["모습"] = "볼 때마다 제각각 — 잡히는 모습 없음"
        elif _seen == 0 and (_textonly > 0 or c["종류"] or c["관련"]):
            c["추상"] = True;  c["모습"] = "본 적 없음 — 말·글로만 만남"
        elif _seen > 0:
            c["추상"] = False; c["모습"] = "본 적 있음"
        else:
            c["추상"] = None;  c["모습"] = "아직 모름"
        return c

    def find_analogy(self, word):
        """34번(비유의 씨앗): 관계 구조가 닮은 개념을 찾는다.
           진짜 은유 이해는 아니고, '같은 상위로 분류되거나 같은 관계를 가진 것'을
           찾아 'A는 B와 비슷하다'의 재료를 만든다.
           예) 공룡·악어가 둘 다 (부분-전체)→파충류 이면 '공룡은 악어와 비슷하다'.
        """
        isa = getattr(self, "isa", {})
        web = getattr(self, "concept_web", {})
        similar = []
        my_up = isa.get(word)
        my_rels = set(self._web_pairs(word))
        for other in set(list(isa.keys()) + list(web.keys())):
            if other == word:
                continue
            reasons = []
            if my_up and isa.get(other) == my_up:
                reasons.append(f"둘 다 {my_up}")
            common = my_rels & set(self._web_pairs(other))
            for kind, tgt in common:
                reasons.append(f"둘 다 {tgt}{'의 일부' if kind=='부분-전체' else '와 관계'}")
            if reasons:
                similar.append({"other": other, "why": ", ".join(reasons[:2])})
        return similar[:8]

    def invent_metaphor(self, word=None, top=5):
        """(34 심화) 아무도 안 알려줘도 아기가 스스로 은유를 '만든다'.
           learn_isa는 '누가 시간은 돈이다라고 말해줬을 때' 알아듣는 수동 방식.
           이건 반대로 — 아는 개념들을 스스로 훑어 '분류는 다른데 하는 일이
           겹치는 짝'을 먼저 발견해 은유 후보로 내놓는다.
           예) 시간과 돈은 분류(isa)가 다른데 둘 다 '쓰다·아끼다'와 같이 쓰임
               → 아기가 스스로 "시간은 돈 같은 거네"라고 만들어봄.
           규칙 딱지가 아니라 '겪은 연어(_shared_verbs)'에서만 나온다."""
        isa = getattr(self, "isa", {}) or {}
        # 후보 단어: 분류를 아는 것들(비교의 기준이 있어야 함)
        pool = [w for w in isa.keys() if isa.get(w)]
        made = []
        seen_pairs = set()
        targets = [word] if word else pool
        for a in targets:
            if a not in isa or not isa.get(a):
                continue
            for b in pool:
                if b == a:
                    continue
                pair = tuple(sorted((a, b)))
                if pair in seen_pairs:
                    continue
                # 이미 (말해줘서든 스스로든) 아는 은유면 건너뜀
                _m = getattr(self, "metaphors", {}) or {}
                if a in _m and _m[a].get("처럼") == b:
                    continue
                # 조건 1: 분류가 서로 다르고, 같은 갈래도 아니어야(진짜 이질적)
                if isa.get(a) == isa.get(b):
                    continue
                if self._same_branch(a, b):
                    continue
                # 조건 2: 그런데 '같이 쓰는 동사'가 2개+ 겹친다 → 은유의 씨앗
                shared = self._shared_verbs(a, b)
                if len(shared) >= 2:
                    seen_pairs.add(pair)
                    made.append({
                        "말": a, "처럼": b,
                        "왜": f"{a}과(와) {b}은(는) 서로 다른 것({isa.get(a)}·{isa.get(b)})"
                              f"인데 둘 다 {'·'.join(shared[:3])}와(과) 같이 쓰여서",
                        "같이쓰는말": shared[:4],
                    })
                    if len(made) >= top:
                        break
            if len(made) >= top:
                break
        # 발견한 은유를 metaphors에 저장(말해준 것과 구분: 스스로 발견 표시)
        if not isinstance(getattr(self, "metaphors", None), dict):
            self.metaphors = {}
        for mm in made:
            if mm["말"] not in self.metaphors:
                self.metaphors[mm["말"]] = {
                    "처럼": mm["처럼"], "같이쓰는말": mm["같이쓰는말"],
                    "스스로발견": True,
                }
        return made[:top]

    def understand(self, obj):
        """개념을 '안다'고 말할 수 있는지 — 갈래가 몇 개나 묶였나.
           단어만 알면 얕고, 여러 갈래가 묶일수록 깊이 이해한 것."""
        c = self.concept_of(obj)
        depth = 0
        if len(c["이름"]) >= 1: depth += 1     # 이름을 안다
        if c["보임"]: depth += 1               # 어떻게 생겼는지
        if c["들림"]: depth += 1               # 어떤 소리인지
        if c["속성"]: depth += 1               # 어떤 종류의 것인지
        if c["하는일"]: depth += 1             # 무엇과 함께 쓰는지
        if c["종류"]: depth += 1               # 무엇의 한 종류인지
        if c["관련"]: depth += 1               # 무엇과 관련되는지
        levels = ["전혀 모름","글자만","조금","어느정도","꽤","깊이","아주 깊이","완전히"]
        return {"obj": obj, "이해깊이": depth, "수준": levels[min(depth, 7)],
                "묶인 갈래": [k for k in ["이름","보임","들림","속성","하는일","종류","관련"]
                            if c.get(k)]}

    def set_own_goals(self, top=3):
        """스스로 목표 정하기 (능동적 호기심). 누가 안 던져줘도, 자기 지식
           상태를 보고 '더 팔 곳'을 스스로 고른다.
           ※ 진짜 의지가 아니라, 아는 것과 모르는 것의 틈을 찾는 규칙.
           목표에는 '종류'(무엇을 하려는가)가 붙고, 한 번 세운 목표는 기억해
           두어 이미 이룬 것은 새 목표에서 뺀다(같은 자리 맴돌지 않게)."""
        rel = getattr(self, "relations", {})
        isa = getattr(self, "isa", {})
        explored = getattr(self, "explored", set())
        if not hasattr(self, "goal_log"):
            self.goal_log = {}   # {대상: {"종류","이룸"}} — 세운 목표를 기억
        scores = {}   # {대상: (점수, 이유, 종류)}
        # 규칙 1: 여러 곳에서 연결됐는데 아직 안 판 것(관심이 모이는 곳)
        mention = {}
        for src, links in rel.items():
            for w in links:
                mention[w] = mention.get(w, 0) + 1
        for w, cnt in mention.items():
            if w not in explored and cnt >= 2:
                scores[w] = (cnt * 2, f"여러 곳({cnt})에서 나오는데 안 알아봄", "알아내기")
        # 규칙 2: 분류는 아는데 그 위를 모르는 것(사슬이 끊긴 곳)
        for w, up in isa.items():
            if up not in isa and up not in explored:
                prev = scores.get(up, (0, "", "알아내기"))
                scores[up] = (prev[0] + 3, "분류는 아는데 그 위를 모름", "알아내기")
        # 규칙 3: 자주 마주친 궁금한 것
        for w, cnt in getattr(self, "curiosity", {}).items():
            if w not in explored:
                prev = scores.get(w, (0, "", "알아내기"))
                scores[w] = (prev[0] + cnt, prev[1] or "자주 마주침", prev[2])
        # 규칙 4: 모순이 걸린 것 — '확인하기' 목표(먼저 풀어야 믿음이 안 흔들림)
        for w, cand in (getattr(self, "doubts", {}) or {}).items():
            n_cand = len(cand) if hasattr(cand, "__len__") else 1
            prev = scores.get(w, (0, "", ""))
            scores[w] = (prev[0] + 4 + n_cand, "모순이 걸려 어느 쪽이 맞는지 확인 필요", "확인하기")
        # 이미 이룬(충분히 판) 목표는 뺀다 — 같은 자리 맴돌지 않게
        for w in list(scores.keys()):
            if self.goal_log.get(w, {}).get("이룸"):
                del scores[w]
        goals = sorted(scores.items(), key=lambda x: -x[1][0])[:top]
        out = []
        for w, (sc, why, kind) in goals:
            self._wonder(w)   # 스스로 궁금증에 올린다
            self.goal_log[w] = {"종류": kind, "이룸": False}   # 세운 목표를 기억
            # 이미 어느 정도 알게 됐으면 그 목표는 '이룸'으로 표시(다음엔 안 고름)
            try:
                if self.understand(w).get("이해깊이", 0) >= 4:
                    self.goal_log[w]["이룸"] = True
            except Exception:
                pass
            out.append({"goal": w, "why": why, "kind": kind, "score": sc})
        return out

    def pursue_goals(self, depth=2):
        self.lock.acquire()
        try:
            return self._pursue_goals(depth=2)
        finally:
            self.lock.release()
    def _pursue_goals(self, depth=2):
        """스스로 목표를 정하고 직접 파고든다(능동 학습 한 바퀴)."""
        goals = self.set_own_goals()
        if not goals:
            return {"goals": [], "learned": []}
        learned = self.explore_curiosity(max_items=3, depth=depth)
        return {"goals": goals,
                "learned": [(t, info.get("summary")) for t, info in learned]}

    def explore_curiosity(self, max_items=3, depth=1):
        self.lock.acquire()
        try:
            return self._explore_curiosity(max_items=3, depth=1)
        finally:
            self.lock.release()
    def _explore_curiosity(self, max_items=3, depth=1):
        """호기심: 궁금한 것을 스스로 크롤링해서 배우고, 거기 연결된 것들을
           또 궁금해하며 꼬리에 꼬리를 물고 뻗어나간다(depth만큼).
           ※ 진짜 크롤링은 네 컴퓨터에서(인터넷). AI 작업환경은 위키백과 막힘.
           반환: 배운 것들 [(궁금했던것, 정보), ...]."""
        if not hasattr(self, "curiosity") or not self.curiosity:
            return []
        if not hasattr(self, "explored"):
            self.explored = set()    # 이미 찾아본 것(무한 반복 방지)
        learned = []
        last_error = None
        frontier = [t for t, _ in self.what_im_curious(max_items)]
        for d in range(max(1, depth)):
            next_frontier = []
            for thing in frontier:
                if thing in self.explored:
                    continue
                self.explored.add(thing)
                info = self._search_and_learn(thing)
                if info and info.get("error"):
                    last_error = info["error"]      # 왜 안 됐는지 기억
                if info and (info.get("summary") or info.get("links") or info.get("langs")):
                    learned.append((thing, info))
                    self.curiosity.pop(thing, None)
                    # 호기심으로 배운 단어를 환경에 추가한다 → 이후 살아갈 때
                    # 이 단어로도 문장을 듣고 어순·조사(문법)를 같이 배운다.
                    try:
                        w = self.world
                        if thing not in w.objects:
                            w.objects[thing] = {}
                        w.objects[thing].setdefault("ko", thing)
                        # 번역으로 알게 된 다른 언어 이름도 환경에 단다
                        for lg, word in (info.get("langs") or {}).items():
                            w.objects[thing][lg] = word
                        if hasattr(w, "nouns") and thing not in w.nouns:
                            w.nouns.append(thing)
                        # 아기도 이 단어-경험을 연결(말로 쓸 수 있게)
                        self.teach(thing, thing, lang="ko", times=1)  # 물어봐서 한 번 들음 — 세상에서 다시 겪으며 굳는다
                        # 동사 짝 붙이기: 이 단어에 어울리는 동사를 연어사전에서 찾아
                        # colloc에 넣는다 → 이후 이 단어로 문장을 만들고 어순을 배운다.
                        try:
                            from kollocate import Kollocate
                            if not hasattr(self, "_kollo"):
                                self._kollo = Kollocate()
                            cols = self._kollo(thing)
                            verbs = []
                            for pos, c in cols.items():
                                if "verb" in c:
                                    verbs = [v + "다" for v, _ in c["verb"][:5]]
                                break
                            ko = w.colloc_by_lang.setdefault("ko", {})
                            for vb in verbs:
                                ko.setdefault(vb, [])
                                if thing not in ko[vb]:
                                    ko[vb].append(thing)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # 연결을 지식 그래프에 저장(추론의 재료): thing → 연결된 것들
                    if not hasattr(self, "relations"):
                        self.relations = {}
                    self.relations.setdefault(thing, [])
                    for link in info.get("links", []):
                        if link not in self.relations[thing]:
                            self.relations[thing].append(link)
                    # 설명에서 분류(~은 ~이다)를 배운다 — 정확한 추론의 재료
                    self.learn_isa(thing, info.get("summary"), source=info.get("source"))
                    self.learn_cause(thing, info.get("summary"))
                    # 6단계(진짜 이해): 관계망도 배운다 (부분-전체·가짐·반대·인과)
                    self.learn_relation(thing, info.get("summary"), source=info.get("source"))
                    # (겪음 장부) 이건 '글자·설명으로만' 만난 것 — 추상 발견의 재료(33)
                    if not isinstance(getattr(self,"grounding",None), dict): self.grounding={}
                    _g2=self.grounding.setdefault(thing,{"본적":0,"들은적":0,"글자로만":0,"기분합":0.0,"기분n":0})
                    _g2["글자로만"]=_g2.get("글자로만",0)+1
                    # 꼬리물기: 페이지에서 연결된 것들을 또 궁금해한다
                    for link in info.get("links", []):
                        if link not in self.explored and not self._already_know(link):
                            self._wonder(link)
                            next_frontier.append(link)
            # 다음 깊이에서 탐험할 것(연결된 것 중 일부)
            frontier = next_frontier[:max_items]
            if not frontier:
                break
        self.last_explore_error = last_error   # 검색이 왜 안 됐는지(화면 표시용)
        return learned

    def _already_know(self, word):
        """이 단어를 이미 아는가(환경 사물이거나 단어로 연결됨)."""
        if word in self.world.objects:
            return True
        for obj, langs in self.word_link.items():
            for lang, words in langs.items():
                if word in words:
                    return True
        return False

    def infer(self, start, max_depth=3):
        """추론 1단계: 연결을 타고 추측(관련의 관련). 확신 아님."""
        rel = getattr(self, "relations", {})
        if start not in rel:
            return []
        direct = set(rel.get(start, []))
        guesses = []
        seen = {start} | direct
        frontier = [(b, [start, b]) for b in direct]
        depth = 1
        while frontier and depth < max_depth:
            nxt = []
            for node, path in frontier:
                for c in rel.get(node, []):
                    if c in seen:
                        continue
                    seen.add(c)
                    guesses.append((c, path + [c]))
                    nxt.append((c, path + [c]))
            frontier = nxt
            depth += 1
        return guesses

    def _extract_isa(self, word, summary):
        """설명 문장에서 'word는 ... B이다'(분류, IS-A)를 뽑는다.
           'XX의 한 무리/종류'는 XX, 시공간·현상 명사는 분류로 안 침. B or None."""
        if not summary:
            return None
        import re
        not_class = {"시기","때","곳","장소","현상","상태","것","무리","가지",
                     "종류","하나","부분","모습","사실","경우","정도"}
        m = re.search(r'([가-힣]{2,})의 한 (?:종류|무리|가지)', summary)
        if m and m.group(1) not in not_class:
            return m.group(1)
        # 'A는 B이다' 또는 'A는 B다' (B는 1글자도 허용: 돈, 물 등)
        for cand in reversed(re.findall(r'([가-힣]+?)(?:이다|다)(?:\.|$|\s)', summary)):
            cand = cand.strip()
            if len(cand) >= 1 and cand not in not_class and not cand.endswith(("하", "그렇", "이렇", "저렇")):
                return cand
        return None

    def _web_pairs(self, word):
        """concept_web[word]에서 (관계종류, 상대) 쌍만 뽑아 준다.
           내부 저장은 증거({for,against,sources})를 담은 dict 리스트지만,
           기존 코드(비유·전이·stats)는 (kind,to) 쌍만 필요하므로 여기서 변환.
           반대증거가 본증거보다 많은(뒤집힌) 관계는 빼고 준다 — 지금 안 믿으니까."""
        out = []
        for e in (getattr(self, "concept_web", {}) or {}).get(word, []):
            if isinstance(e, dict):
                if e.get("for", 0) > e.get("against", 0):   # 아직 믿는 것만
                    out.append((e.get("kind"), e.get("to")))
            elif isinstance(e, (list, tuple)) and len(e) == 2:
                out.append((e[0], e[1]))   # 옛 형식(튜플)도 호환
        return out

    def _web_confidence(self, word, kind, to):
        """이 관계를 지금 '얼마나 확실히 여기는가' — 볼 때마다 증거로 다시 계산.
           고정 임계값 없음. 저장된 숫자도 아님. 언제든 흔들리고 뒤집힐 수 있다.
           많이 볼수록↑, 반대로 본 게 있으면↓. '몇 곳=사실'이 아니라
           '지금까지 겪은 증거로 이 정도 확실해 보인다'일 뿐(가짜뉴스 다수도 여기선 그냥 증거량)."""
        for e in (getattr(self, "concept_web", {}) or {}).get(word, []):
            if isinstance(e, dict) and e.get("kind") == kind and e.get("to") == to:
                f = e.get("for", 0); a = e.get("against", 0)
                if f + a == 0:
                    return 0.0
                ratio = f / (f + a)              # 본 것 vs 반대 본 것
                # 증거가 적으면 확신도 낮게(1곳만 봤으면 확신 못 함). 상한 없음.
                import math
                evidence = 1 - 1 / (1 + math.log1p(f + a))
                return round(ratio * evidence, 3)
        return 0.0

    def _web_add_evidence(self, word, kind, to, source=None, against=False):
        """관계에 증거를 '한 번 봤다'로 누적한다(덮어쓰지 않음 — 다 쌓아둔다).
           against=True면 '반대로 본' 증거. 반대가 쌓이면 _web_pairs에서 빠지고
           나중에 더 쌓이면 완전히 뒤집힌다. 상한 없음 — 계속 갱신 가능."""
        if not hasattr(self, "concept_web"):
            self.concept_web = {}
        lst = self.concept_web.setdefault(word, [])
        # 옛 튜플 형식이 섞여 있으면 dict로 승격
        for i, e in enumerate(lst):
            if isinstance(e, (list, tuple)) and len(e) == 2:
                lst[i] = {"kind": e[0], "to": e[1], "for": 1, "against": 0, "sources": []}
        for e in lst:
            if isinstance(e, dict) and e.get("kind") == kind and e.get("to") == to:
                if against:
                    e["against"] = e.get("against", 0) + 1
                else:
                    e["for"] = e.get("for", 0) + 1
                if source and source not in e.setdefault("sources", []):
                    e["sources"].append(source)
                return e
        # 처음 보는 관계
        e = {"kind": kind, "to": to,
             "for": 0 if against else 1, "against": 1 if against else 0,
             "sources": [source] if source else []}
        lst.append(e)
        return e

    def learn_relation(self, word, summary, source=None):
        """6단계(진짜 이해): 설명에서 '관계의 종류'를 뽑아 개념 관계망을 만든다.
           분류(~이다)만이 아니라 부분-전체, 가짐(속성), 반대, 인과까지.
           예) '파충류는 척추동물의 한 무리이다' → (파충류)-부분-(척추동물)
               '조류는 날개를 가진 동물이다' → (조류)-가짐-(날개)
           (가) 방식: 관계를 덮어쓰지 않고 '증거'로 누적한다(본 횟수·출처 보존).
           같은 관계종류인데 상대가 다르면 '모순' — 새 것엔 증거를, 기존 다른 것엔
           반대증거를 넣어 서로 경쟁시킨다. 임계값 없이 계속 재평가돼 뒤집힐 수 있다."""
        if not hasattr(self, "concept_web"):
            self.concept_web = {}   # word -> [증거dict]
        if not summary or not isinstance(summary, str):
            return
        import re
        rels = []
        m = re.search(r"([가-힣A-Za-z]+)의\s*(?:한\s*)?(?:무리|부분|일부|종류|구성원|갈래)", summary)
        if m: rels.append(("부분-전체", m.group(1)))
        m = re.search(r"([가-힣A-Za-z]+)(?:을|를)\s*(?:가진|가지고 있는)", summary)
        if m: rels.append(("가짐", m.group(1)))
        m = re.search(r"([가-힣A-Za-z]+)(?:와|과|의)\s*반대", summary)
        if m: rels.append(("반대", m.group(1)))
        m = re.search(r"([가-힣A-Za-z]+)\s*(?:때문|로 인해|으로 인해)", summary)
        if m: rels.append(("원인-결과", m.group(1)))
        m = re.search(r"([가-힣A-Za-z]+)의\s*(?:마지막|첫|중간)?\s*(?:시기|시대|때)", summary)
        if m: rels.append(("시기", m.group(1)))
        for kind, to in rels:
            if to == word:
                continue
            existing = self.concept_web.get(word, [])
            # 모순 검사: 같은 kind인데 다른 to가 이미 있으면, 그것엔 반대증거를 준다
            #  (서로 경쟁 — 나중에 더 많이/자주 본 쪽이 이긴다. 확정 아님)
            for e in existing:
                if isinstance(e, dict) and e.get("kind") == kind and e.get("to") != to:
                    self._web_add_evidence(word, kind, e.get("to"), source=None, against=True)
                    if not hasattr(self, "doubts"):
                        self.doubts = {}
                    # 의심 목록에도 올려 나중에 가설·검증이 다루게
                    self.doubts.setdefault(word, [])
                    for cand in (e.get("to"), to):
                        if cand and cand not in self.doubts[word]:
                            self.doubts[word].append(cand)
            # 이 관계에 '봤다' 증거 누적(출처 기록)
            self._web_add_evidence(word, kind, to, source=source, against=False)
        return rels

    def _shared_verbs(self, a, bword):
        """(34) 두 말이 '같이 쓰는 동사'가 겹치나 — 겪은 연어에서 찾는다(규칙 아님)."""
        out=[]
        try:
            ko=self.world.colloc_by_lang.get("ko",{})
            for vb,objs in ko.items():
                if a in objs and bword in objs: out.append(vb)
        except Exception: pass
        if len(out)<2:
            try:
                from kollocate import Kollocate
                if not hasattr(self,"_kollo"): self._kollo=Kollocate()
                def vset(w):
                    s=set()
                    for pos,c in self._kollo(w).items():
                        for v,_ in c.get("verb",[])[:12]: s.add(v)
                        break
                    return s
                out=sorted(set(out)|(vset(a)&vset(bword)))
            except Exception: pass
        return out

    def my_translations(self, obj):
        """(14) 번역을 미리 잇지 않는다 — 두 언어 다 '확실히 겪은' 이름만 스스로 잇는다."""
        out={}
        for lg,words in (self.word_link.get(obj) or {}).items():
            best=None; bc=0
            for w,c in words.items():
                if c>bc: best,bc=w,c
            if best and bc>=self.KNOW_THRESHOLD: out[lg]=best
        # 한 언어만 알면 그건 그냥 이름 — 두 언어 다 겪었을 때만 스스로 잇는다
        return out if len(out)>=2 else {}

    def _j(self, w, with_batchim, without):
        """받침 있으면 앞엣것, 없으면 뒤엣것을 붙인다(간단 조사)."""
        try:
            code=ord(str(w)[-1])
            if 0xAC00<=code<=0xD7A3 and (code-0xAC00)%28: return f"{w}{with_batchim}"
            return f"{w}{without}"
        except Exception:
            return f"{w}{with_batchim}"

    def my_feeling(self, obj):
        """(47) 좋아/싫어는 규칙이 아니라 '겪을 때 기분'에서 나온다."""
        g=getattr(self,"grounding",{}) or {}
        e=g.get(obj) or {}
        n=e.get("기분n",0)
        if n<3: return "모름"
        mine=e.get("기분합",0.0)/n
        ts=sum(x.get("기분합",0.0) for x in g.values()); tn=sum(x.get("기분n",0) for x in g.values())
        base=(ts/tn) if tn else 0.0
        if mine>base+0.08: return "좋아"
        if mine<base-0.08: return "별로"
        return "그냥"

    def transfer_guess(self, word):
        """(37 심화) 전이: 같은 부류 형제가 가진 관계를 이 아이도 가질 거라 '추측'.
           확신 아님. 심화 포인트 — 형제 중 몇 명이 그 관계를 함께 가졌는지 세서
           '추측의 근거 강도'를 붙인다. 사람이 "이건 거의 확실"과 "그냥 한번 넘겨짚음"을
           구분하듯. 형제 4명 중 3명이 다리를 가지면 강한 추측, 1명만이면 약한 추측."""
        isa = getattr(self, "isa", {}); k = isa.get(word)
        if not k:
            return []
        web = getattr(self, "concept_web", {}) or {}
        # 같은 분류의 형제들(나 자신 제외)
        sibs = [s for s, kk in isa.items() if kk == k and s != word]
        if not sibs:
            return []
        mine = set(self._web_pairs(word))
        # (관계종류, 대상) 별로 그걸 가진 형제 수를 센다
        share = {}   # (kind,tgt) -> 형제 이름 목록
        for sib in sibs:
            for kind, tgt in self._web_pairs(sib):
                if (kind, tgt) in mine:
                    continue   # 이미 내가 아는 건 추측할 필요 없음
                share.setdefault((kind, tgt), []).append(sib)
        total = len(sibs)
        out = []
        # 많은 형제가 공유하는 관계일수록 앞에(강한 추측부터)
        for (kind, tgt), owners in sorted(share.items(), key=lambda x: -len(x[1])):
            cnt = len(owners)
            ratio = cnt / total
            if ratio >= 0.6:
                strength = "거의 그럴 거야"
            elif ratio >= 0.3:
                strength = "그럴 수도"
            else:
                strength = "혹시"
            rel = f"{tgt}{'의 일부' if kind == '부분-전체' else '와(과) 관계'}"
            eg = owners[0]
            out.append({
                "추측": f"{word}도 {rel}일지도",
                "확신": strength,
                "근거": f"{k} 형제 {total}개 중 {cnt}개가 그래 (예: {eg})",
                "비율": round(ratio, 2),
            })
            if len(out) >= 3:
                break
        return out

    def guess_partner_mind(self, word=None):
        """(43 심화) 상대의 '마음 상태'를 추측한다(확신 아님).
           지금까지는 partner_said로 '몇 번 물었나'만 셌다(단순 카운트).
           심화 — 그 빈도에서 상대의 상태를 미루어 짐작한다:
             · 내가 아는 건데 상대가 자꾸 물으면 → "상대는 이걸 아직 모르나 봐"
             · 상대가 자주 꺼내는 말 → "상대가 이걸 궁금해하는(관심 있는) 것 같아"
           내 마음이 아니라 '상대'를 추측하는 것. 그래서 다 '~인 듯/봐'로 말한다."""
        said = getattr(self, "partner_said", {}) or {}
        if not said:
            return []
        words = [word] if word else list(said.keys())
        out = []
        for w in words:
            n = said.get(w, 0)
            if n <= 0:
                continue
            i_know = self._already_know(w)
            if n >= 3 and i_know:
                guess = f"'{w}'을(를) 자꾸 묻는 걸 보니 상대는 아직 이걸 잘 모르나 봐"
                mind = "상대: 모름(추측)"
            elif n >= 3 and not i_know:
                guess = f"'{w}'을(를) 자주 꺼내는 걸 보니 상대가 이걸 궁금해하는 것 같아"
                mind = "상대: 관심(추측)"
            elif n == 2:
                guess = f"'{w}'을(를) 또 물어봤네 — 이게 상대한테 중요한가 봐"
                mind = "상대: 신경 씀(추측)"
            else:
                continue   # 한 번뿐이면 아직 판단 보류(넘겨짚지 않음)
            out.append({"말": w, "추측": guess, "상대마음": mind, "물은횟수": n})
        # 자주 물은 것부터
        out.sort(key=lambda x: -x["물은횟수"])
        return out

    def empathize(self, obj, partner_feeling=None):
        """(44 심화) 공감 — 상대가 어떤 것에 대해 감정을 말하면,
           내가 그걸 겪은 기분(my_feeling)에 비추어 상대 마음을 함께 느껴본다.
           로드맵 원칙: '감정이라고 배운 것'에 한해서만, 겪은 기분에서 나온다.
           내가 안 겪어본 것엔 지어내지 않고 정직하게 '나는 그건 잘 몰라'.
           partner_feeling: 상대가 밝힌 감정('좋아'/'싫어' 등, 없으면 추측만)."""
        mine = self.my_feeling(obj)   # "좋아"/"별로"/"그냥"/"모름"
        # 내가 그걸 겪어본 적이 있나(감각경험 장부)
        g = (getattr(self, "grounding", {}) or {}).get(obj) or {}
        felt_n = g.get("기분n", 0)
        if felt_n < 3 or mine == "모름":
            # 안 겪어봤으면 공감 흉내 내지 않고 정직히
            return {
                "대상": obj, "공감": False,
                "말": f"나는 {obj}을(를) 겪어본 적이 별로 없어서, 그 기분은 잘 몰라.",
                "내기분": mine,
            }
        # 상대가 밝힌 감정이 있으면 내 기분과 견줘본다
        if partner_feeling:
            same = (partner_feeling in ("좋아", "좋음") and mine == "좋아") or \
                   (partner_feeling in ("싫어", "별로", "싫음") and mine == "별로")
            if same:
                msg = f"나도 {obj} 그래 — 겪어보니 나도 {mine}였거든. 그 기분 알아."
            elif mine == "그냥":
                msg = f"너는 {obj}에 대해 {partner_feeling}구나. 나는 그냥 그랬는데, 사람마다 다른가 봐."
            else:
                msg = f"너는 {partner_feeling}구나. 나는 {obj} 겪을 땐 {mine}였어 — 우린 좀 다르네."
        else:
            # 상대 감정 모르면 내 경험을 근거로 조심스레
            if mine == "좋아":
                msg = f"{obj} 얘기구나. 나는 그거 겪을 때 기분이 좋았어 — 너도 그랬을까?"
            elif mine == "별로":
                msg = f"{obj} 얘기구나. 나는 그거 좀 별로였는데 — 너는 어땠어?"
            else:
                msg = f"{obj}은(는) 나한텐 그냥 그랬어. 너는 어떤 기분이야?"
        return {"대상": obj, "공감": True, "말": msg,
                "내기분": mine, "상대기분": partner_feeling, "겪은횟수": felt_n}

    def make_plan(self, n=3):
        """(39·41) 계획: 무엇을 어떤 순서로 알아볼지 스스로 정한다.
           궁금 목록 재포장이 아니라, 세 갈래의 '할 일'을 모아 우선순위로 세운다:
             (a) 모르는 것 찾아보기   — 자주 마주친 순(궁금 횟수)
             (b) 의심 해소하기        — 모순이 걸린 것(먼저 풀어야 다른 게 안 흔들림)
             (c) 얕게 아는 것 더 파기 — 이름만 알고 갈래가 적은 것
           각 할 일에는 '다음 행동'(검색/되짚기/더 겪기)을 붙인다.
           순서는 종류 가중치 × 절박함으로 정한다. 궁금함의 방향이 곧 계획이 됨."""
        tasks = []

        # (b) 의심 해소 — 가장 급함(모순을 안 풀면 믿는 게 계속 흔들림)
        doubts = getattr(self, "doubts", {}) or {}
        for w, cand in list(doubts.items()):
            n_cand = len(cand) if hasattr(cand, "__len__") else 1
            tasks.append({
                "할일": f"'{w}' 의심 풀기",
                "이유": f"모순({n_cand}개 후보)이 걸려 있어 먼저 확인해야 함",
                "다음행동": "search",   # 재조사해서 어느 쪽이 맞는지 증거 모으기
                "대상": w,
                "종류": "의심",
                "점수": 3.0 + 0.2 * n_cand,
            })

        # (a) 모르는 것 찾아보기 — 자주 마주친 순
        for w, cnt in self.what_im_curious(top=n + 5):
            tasks.append({
                "할일": f"'{w}' 알아보기",
                "이유": f"{cnt}번 마주쳤는데 아직 모름",
                "다음행동": "search",
                "대상": w,
                "종류": "궁금",
                "점수": 2.0 + 0.1 * cnt,
            })

        # (c) 얕게 아는 것 더 파기 — 이름만 알고 갈래가 적은 것
        try:
            isa = getattr(self, "isa", {}) or {}
            for w in list(isa.keys())[:40]:
                try:
                    depth = self.understand(w).get("이해깊이", 0)
                except Exception:
                    depth = 0
                if 0 < depth <= 2:   # 조금 알지만 얕음 → 더 팔 가치
                    tasks.append({
                        "할일": f"'{w}' 더 깊이 알기",
                        "이유": f"이름 정도만 앎(깊이 {depth}) — 모습·하는일·관계를 더 겪기",
                        "다음행동": "experience",   # 더 겪어서 갈래 채우기
                        "대상": w,
                        "종류": "얕음",
                        "점수": 1.0 + (2 - depth) * 0.3,
                    })
        except Exception:
            pass

        # 우선순위로 정렬(점수 높은 순), 같은 대상 중복은 첫 것만
        tasks.sort(key=lambda t: -t["점수"])
        seen, plan = set(), []
        for t in tasks:
            if t["대상"] in seen:
                continue
            seen.add(t["대상"])
            plan.append(t)
            if len(plan) >= n:
                break
        return plan

    def self_assess(self):
        """(40·48) 자기평가: 뭘 확실히 알고, 뭘 배우는 중이고, 뭘 모르는지 스스로 본다."""
        known=self._count_known()
        abstracts=[]
        try:
            for wd in list(getattr(self,"isa",{}).keys())[:30]:
                if self.concept_of(wd).get("추상") is True: abstracts.append(wd)
        except Exception: pass
        return {"확실": known,
                "배우는중": max(0,len(self.word_link)-known),
                "궁금": len(getattr(self,"curiosity",{}) or {}),
                "의심": len(getattr(self,"doubts",{}) or {}),
                "관계": sum(len(v) for v in (getattr(self,"concept_web",{}) or {}).values()),
                "비유": len(getattr(self,"metaphors",{}) or {}),
                "추상으로_아는것": abstracts[:8]}

    def _learn_from_statement(self, text):
        """(35·45) 사람이 '문장'으로 말하면 → 배우고, 내가 아는 것과 어긋나면
           그대로 믿지 않고 되묻는다. 어긋나도 같이 쓰는 말이 겹치면 비유로 알아듣는다."""
        t=text.strip()
        first=t.split()[0]
        for p in ("은","는","이","가"):
            if first.endswith(p) and len(first)>1:
                first=first[:-1]; break
        old=getattr(self,"isa",{}).get(first)
        m0=set((getattr(self,"metaphors",{}) or {}).keys())
        bnew=self.learn_isa(first, t)
        try: self.learn_relation(first, t)
        except Exception: pass
        try: self.learn_cause(first, t)
        except Exception: pass
        m1=getattr(self,"metaphors",{}) or {}
        if first in m1 and first not in m0:
            mm=m1[first]
            return {"say": f"아, 그건 비유구나 — 사람들이 {self._j(first,'을','를')} {mm.get('처럼')}처럼 말하네({', '.join(mm.get('같이쓰는말',[])[:2])} 같이 써서).",
                    "mind": "(34) 분류는 어긋나지만 같이 쓰는 말이 겹침 → 비유로 이해"}
        if old and bnew and old!=bnew and first in getattr(self,"doubts",{}):
            return {"say": f"어? 나는 {self._j(first,'이','가')} {self._j(old,'이라고','라고')} 알아. 농담이야, 아니면 내가 틀린 거야?",
                    "mind": "(45) 들은 말이 아는 것과 어긋남 — 그대로 안 믿고 되물음(의심에 기록)"}
        if bnew and bnew!=first:
            return {"say": f"오, {self._j(first,'이','가')} {self._j(bnew,'이구나','구나')}. 기억할게.",
                    "mind": "(35) 사람이 말한 문장에서 배움 — 말한 걸 추론 재료로"}
        return None

    def learn_isa(self, word, summary, source=None):
        """설명에서 분류를 배운다. 단, 기존과 다른 분류가 오면 덮어쓰지 않고
           '모순'으로 표시해 의심한다(아무거나 안 믿기)."""
        if not hasattr(self, "isa"):
            self.isa = {}     # word -> 상위 분류(믿는 것)
        if not hasattr(self, "doubts"):
            self.doubts = {}  # word -> [충돌하는 분류들] (의심 중)
        b = self._extract_isa(word, summary)
        if not b or b == word:
            return b
        self.revise_belief_observation(word, "is_a", b, source=source,
                                       evidence=summary)
        old = self.isa.get(word)
        if old is None:
            # 처음 들은 주장은 후보로만 보존한다. 검증 전에는 추론용 isa에 넣지 않는다.
            return b
        elif old != b and not self._same_branch(old, b):
            # (34) 분류는 어긋나는데 '같이 쓰는 말'이 겹치면 — 비유로 알아듣는다.
            #  예) "시간은 돈이다": 시간≠돈이지만 둘 다 '쓰다·아끼다'와 같이 쓰임 → 비유.
            _shared = self._shared_verbs(word, b)
            if len(_shared) >= 2:
                if not isinstance(getattr(self, "metaphors", None), dict): self.metaphors={}
                self.metaphors[word] = {"처럼": b, "같이쓰는말": _shared[:4]}
            else:
                # 겹치지도 않으면 진짜 모순 → 의심한다
                self.doubts.setdefault(word, [])
                for x in (old, b):
                    if x not in self.doubts[word]:
                        self.doubts[word].append(x)
        # 같은 갈래면(파충류 vs 척추동물) 더 구체적인 걸 유지
        return b

    def _same_branch(self, a, b):
        """a와 b가 같은 분류 갈래인가(한쪽이 다른쪽의 상위/하위)."""
        isa = getattr(self, "isa", {})
        # a 위로 올라가며 b 만나나
        cur = a; seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur == b: return True
            cur = isa.get(cur)
        cur = b; seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur == a: return True
            cur = isa.get(cur)
        return False

    def detect_contradictions(self):
        """배운 것끼리 안 맞는 것(모순)을 찾는다. 의심 목록을 돌려준다."""
        out = []
        for word, conflicting in getattr(self, "doubts", {}).items():
            if len(conflicting) >= 2:
                out.append({"about": word, "conflict": conflicting,
                            "note": f"'{word}'이(가) {' / '.join(conflicting)} 중 무엇인지 안 맞음"})
        return out

    def what_to_recheck(self):
        """모순 때문에 다시 확인해야 할 것들 → 호기심에 올려 재조사하게."""
        rechecks = []
        for c in self.detect_contradictions():
            self._wonder(c["about"])   # 다시 궁금해함(확인하려고)
            rechecks.append(c["about"])
        return rechecks

    def make_hypothesis(self, word):
        """가설 세우기: 모순난 후보 중 어느 게 더 그럴듯한지 추측한다.
           근거 — 그 후보가 자기가 아는 다른 것들과 얼마나 일관되나(연결).
           반환: {가설, 후보별 점수, 근거}."""
        candidates = getattr(self, "doubts", {}).get(word)
        if not candidates:
            return None
        rel = getattr(self, "relations", {})
        isa = getattr(self, "isa", {})
        # word와 연결된(관련된) 것들
        neighbors = set(rel.get(word, []))
        # 이웃들이 어떤 분류에 속하는지 — 가장 많은 분류가 그럴듯
        score = {c: 0 for c in candidates}
        reasons = {c: [] for c in candidates}
        for nb in neighbors:
            nb_class = isa.get(nb)
            for c in candidates:
                # 이웃의 분류가 후보와 같거나, 이웃 자체가 후보면 점수
                if nb_class == c or nb == c:
                    score[c] += 2
                    reasons[c].append(f"{nb}이(가) {c}와 통함")
                # 후보가 이웃의 상위 분류면 점수
                cur = isa.get(nb); hops = 0
                while cur and hops < 3:
                    if cur == c:
                        score[c] += 1
                        reasons[c].append(f"{nb}→…→{c}")
                        break
                    cur = isa.get(cur); hops += 1
        best = max(score, key=score.get)
        if score[best] == 0:
            # 근거 없으면 가설 못 세움(그냥 더 찾아봐야)
            return {"word": word, "hypothesis": None, "scores": score,
                    "note": "어느 쪽이 맞을지 근거가 부족 — 더 조사 필요"}
        return {"word": word, "hypothesis": best, "scores": score,
                "because": reasons[best][:3],
                "note": f"아마 '{word}'은(는) '{best}'일 것 같다"}

    def verify_hypothesis(self, word):
        """가설 자체를 근거로 채택하지 않고, 별도로 축적된 증거로만 검증한다."""
        v = self.verify_belief(word, "is_a")
        return {"word": word, "resolved": v.get("verified", False),
                "conclusion": v.get("conclusion"), "changed": v.get("changed", False),
                "previous": v.get("previous"), "evidence": {
                    "support_sources": v.get("support_sources", []),
                    "oppose_sources": v.get("oppose_sources", []),
                }, "note": ("독립 근거를 비교해 결론을 수정함" if v.get("changed")
                            else "독립 근거로 확인함" if v.get("verified")
                            else v.get("reason", "검증할 근거 부족"))}

    def learn_cause(self, word, summary):
        """설명 문장에서 인과(원인→결과)를 배운다. 'A 때문에 B', 'A면 B'.
           추론 3단계 — '왜?'에 답하기 위한 재료. (분류보다 어려워 신뢰도 낮음)"""
        if not summary:
            return []
        if not hasattr(self, "causes"):
            self.causes = {}   # 결과 -> [(원인, 방식), ...]
        import re
        found = []
        s = summary.strip()
        m = re.search(r'(\S+(?:\s+\S+)?)\s*때문에\s*(.+?)[.다]?$', s)
        if m:
            found.append((m.group(1).strip(), m.group(2).strip().rstrip('.'), "때문에"))
        m = re.search(r'(.+?)(?:으면|면)\s+(.+?)[.]?$', s)
        if m and not found:
            found.append((m.group(1).strip(), m.group(2).strip().rstrip('.'), "~면"))
        for cause, effect, how in found:
            self.causes.setdefault(effect, [])
            if (cause, how) not in self.causes[effect]:
                self.causes[effect].append((cause, how))
            # word 자체도 결과 키로 (공룡 멸종 → 공룡으로도 찾게)
            self.causes.setdefault(word, [])
            if (cause, how) not in self.causes[word]:
                self.causes[word].append((cause, how))
        return found

    def why(self, thing):
        """'왜?'에 답한다 — 배운 인과에서 원인을 찾아.
           thing(결과)의 원인을 안다면 '~때문에/~면 ~'으로."""
        causes = getattr(self, "causes", {})
        out = []
        # thing이 결과로 등장한 인과 찾기
        for effect, lst in causes.items():
            if thing in effect or effect in thing:
                for cause, how in lst:
                    out.append({"because": cause, "how": how, "effect": effect})
        return out

    def infer_isa(self, start, max_depth=5):
        """추론 2단계: 분류(IS-A)만 타고 정확히 추론한다.
           공룡→파충류→척추동물→동물 이면 '공룡은 동물이다'.
           1단계(관련의 관련)와 달리 '~은 ~이다'만 타므로 더 정확."""
        isa = getattr(self, "isa", {})
        chain = []
        cur = start
        seen = {start}
        for _ in range(max_depth):
            up = isa.get(cur)
            if not up or up in seen:
                break
            seen.add(up)
            chain.append(up)
            cur = up
        # start는 chain의 모든 상위 분류'이다'
        return [{"is_a": c, "because": f"{start}" + "".join(f"→{x}" for x in chain[:chain.index(c)+1])}
                for c in chain]

    def what_i_inferred(self, start, top=8):
        """추론 결과: 분류 기반(정확) 우선, 그 다음 관련 기반(추측)."""
        out = []
        for r in self.infer_isa(start):
            out.append({"guess": r["is_a"], "kind": "분류(~이다)", "because": r["because"]})
        for thing, path in self.infer(start):
            if thing not in [o["guess"] for o in out]:
                out.append({"guess": thing, "kind": "관련(추측)", "because": " → ".join(path)})
            if len(out) >= top:
                break
        return out[:top]

    def say_thought(self, start, lang="ko"):
        """통합: 추론한 것을 '말로' 표현한다 (생각 → 언어).
           추론(분류 사슬)을 'A는 B이다' 문장으로 만든다.
           지금까진 추론 결과가 데이터로만 있었는데, 이제 입 밖으로 낸다."""
        thoughts = self.infer_isa(start)
        if not thoughts:
            return []
        said = []
        for r in thoughts:
            b = r["is_a"]
            if lang == "ko":
                # 'A는 B이다' — 받침 규칙으로 은/는, 이다/다
                try:
                    import josa
                    topic = josa.attach(start, "topic")     # 공룡은
                except Exception:
                    topic = start
                # B가 받침 있으면 '이다', 없으면 '다'
                ida = "이다" if josa.has_batchim(b) else "다"
                sentence = f"{topic} {b}{ida}"
            else:
                sentence = f"{start} is a {b}"   # 영어 기본
            said.append({"sentence": sentence, "because": r["because"]})
        return said

    def _search_and_learn(self, thing):
        """모르는 것 하나를 크롤링·번역으로 찾아 환경에 새 사물로 추가하고 학습.
           크롤링(설명·연결단어·사진) + 번역. 못 찾으면 None."""
        result = {"learned_as": thing, "langs": {}, "summary": None, "links": [],
                  "image": None, "error": None, "source": None, "sources": []}
        got = False
        # 1) 크롤링/검색: 진짜는 네 컴퓨터.
        try:
            if SETTINGS.get('real_search'):
                # 사람처럼 브라우저로 검색엔진에서 검색 → 여러 사이트 조사
                import browser_search
                res = browser_search.research(thing, max_sites=20)
                if res and (res.get("summary") or res.get("links")):
                    result["summary"] = res.get("summary")
                    result["links"] = res.get("links", [])
                    result["image"] = (res.get("images") or [None])[0]
                    # 출처: 어느 사이트에서 가져왔나
                    sites = res.get("sites") or []
                    if sites:
                        urls = [s.get("url") for s in sites if s.get("url")]
                        result["sources"] = urls
                        result["source"] = "🌐 인터넷 검색 — " + ", ".join(urls[:2]) if urls else "🌐 인터넷 검색"
                    else:
                        result["source"] = "🌐 인터넷 검색"
                    got = True
                else:
                    result["error"] = "검색은 됐지만 내용을 못 가져왔어요(결과 없음/구조 다름)."
            elif SETTINGS.get('real_translation') or SETTINGS.get('real_image'):
                import crawler
                page = crawler.crawl(thing, "ko")
                if page and (page.get("summary") or page.get("links")):
                    result["summary"] = page.get("summary")
                    result["links"] = page.get("links", [])
                    result["image"] = page.get("image")
                    result["source"] = f"🌐 위키백과 (ko.wikipedia.org/wiki/{thing})"
                    got = True
        except Exception as e:
            # 에러를 삼키지 않고 남긴다 — 왜 안 되는지 알 수 있게(playwright 없음 등)
            result["error"] = f"{type(e).__name__}: {e}"
        # 검증용: 막힌 환경이면 샘플 페이지로 꼬리물기 구조 확인
        if not got and thing in _SAMPLE_PAGES:
            p = _SAMPLE_PAGES[thing]
            result["summary"] = p.get("summary")
            result["links"] = p.get("links", [])
            result["source"] = "📦 샘플(내장 — 인터넷 아님)"
            got = True
        # 2) 번역(kaikki/샘플)
        tr = None
        try:
            if SETTINGS.get('real_translation'):
                import translate_loader
                tr = translate_loader.fetch_translations_real(thing, want_langs=None)
        except Exception:
            tr = None
        if not tr:
            tr = _SAMPLE_TRANSLATIONS.get(thing)
        if tr:
            result["langs"] = dict(tr)
            got = True
        if not got:
            # 못 배웠어도 에러가 있으면 그건 돌려준다(왜 안 됐는지 화면에 보이게)
            return result if result.get("error") else None
        # 환경에 새 사물로 추가 + 학습
        obj = thing
        self.world.add_object(obj, thing, "ko")
        self.teach(obj, thing, "ko", times=5)
        for code, w in result["langs"].items():
            self.world.add_object(obj, w, code)
            self.world.enable_lang(code)
            self.teach(obj, w, code, times=4)
        if obj not in self.world.nouns:
            self.world.nouns.append(obj)
        return result

    def _verification_evidence_provider(self, task):
        """Acquire web evidence for one queued classification task."""
        info = self._search_and_learn(task["subject"]) or {}
        summary = (info.get("summary") or "").strip()
        candidate = self._extract_isa(task["subject"], summary) if summary else None
        if not candidate:
            return []
        sources = info.get("sources") or [info.get("source") or "unknown"]
        return [{"object": candidate, "source": source, "evidence": summary,
                 "context": task.get("context") or {}} for source in sources]

    def run_verification(self, limit=1):
        """Run prioritized verification tasks using the configured acquisition tools."""
        with self.lock:
            return self.execute_verification(self._verification_evidence_provider, limit)

    def run_action_plan(self, plan, max_replans=2):
        """Execute and replan atomically against the live environment."""
        with self.lock:
            return self.execute_action_plan(
                plan,
                lambda action: self.live_one(action_override=action),
                lambda: list(self.last_signal) if self.last_signal else None,
                ACTIONS,
                max_replans=max_replans,
                learn_observations=False,
            )

    def live(self, steps, injected=None):
        with self.lock:
            evs=[]
            for n in range(steps):
                evs.append(self.live_one(injected if n==0 else None))
            self.save()
            return evs

    def stats(self):
        rate=(self.hits/self.chances*100) if self.chances else None
        avg_mood=(self.mood_sum/self.lived) if self.lived else None
        days=self.lived; years=days/TICKS_PER_YEAR
        st=stage_for_learning(self)   # 나이가 아니라 학습으로 단계 판정
        avg_reward=(self.reward_sum/self.reward_n*100) if self.reward_n else None
        recent=(sum(self.recent_reward)/len(self.recent_reward)*100) if self.recent_reward else None
        return {
            "lived":self.lived,"rate":rate,"patterns":len(self.memory),
            "mem_len":self.mem_len,"saved":os.path.exists(MEMORY_FILE),
            "mood":round(self.mood,3),
            "avg_mood":round(avg_mood,3) if avg_mood is not None else None,
            "feeling":self.last_feeling,
            "age_days":days,"age_years":round(years,2),
            "age_label":f"{int(years)}살 {int(days % TICKS_PER_YEAR)}일",
            "stage_id":st["id"],"stage_name":st["name"],"stage_built":st.get("built",True),
            # 2단계: 진짜 학습 지표
            "skill_lifetime":round(avg_reward,1) if avg_reward is not None else None,
            "skill_recent":round(recent,1) if recent is not None else None,
            "situations_learned":len(self.q),
            "words_known":self.words_known,
            "sentences_heard":self.sentences_heard,
            "syntax_pairs":sum(len(words) for lang in self.syntax.values() for words in [lang] for t in words),
            "growth_curve":self.growth_curve[-120:],
        }

    # ── 자동 저장 대상: 단순 dict 학습 상태들 ──
    # 새 능력을 만들면 여기에 이름만 추가하면 save/load가 자동 처리.
    # (손으로 나열하다 자꾸 빼먹던 문제를 근본 해결)
    _SIMPLE_STATE = [
        "word_current", "word_history", "curiosity",
        "relations", "isa", "causes", "doubts", "concept_web",
        "grounding", "metaphors", "talk_topics", "partner_said", "first_words",
        "goal_log",
        "beliefs", "belief_revisions", "answer_history", "verification_tasks",
        "verification_runs",
        "contextual_conclusions",
        "events", "event_seq", "transition_model",
        "drive_weights",
        "action_decisions",
        "plans",
        "plan_runs",
    ]

    def save(self):
        def sig2s(t): return "~".join(t)        # 가변 길이 신호 → 문자열
        mem={}
        for key,nx in list(self.memory.items()):
            ks="|".join(sig2s(t) for t in key)
            mem[ks]={sig2s(t):c for t,c in list(nx.items())}
        q={}; qn={}
        for sig,av in list(self.q.items()):
            sk=sig2s(sig)
            q[sk]={k:v for k,v in av.items()} if isinstance(av,dict) else {a:0.0 for a in ACTIONS}
            _nv=self.qn.get(sig)
            # 항상 모든 행동을 담아 저장한다(빈 dict/일부만 저장 금지 → 불러올 때 KeyError 방지)
            qn[sk]={a:int((_nv or {}).get(a,0)) for a in ACTIONS}
        data={"mem_len":self.mem_len,"hits":self.hits,"chances":self.chances,
              "lived":self.lived,"mood":self.mood,"mood_sum":self.mood_sum,
              "reward_sum":self.reward_sum,"reward_n":self.reward_n,
              "hist_tail":self.hist[-self.mem_len:] if self.hist else [],
              "memory":mem,"q":q,"qn":qn,
              "last_signal":list(self.last_signal) if self.last_signal else None,
              "growth_curve":self.growth_curve,
              "word_link":{o:{l:dict(w) for l,w in langs.items()} for o,langs in list(self.word_link.items())},
              "obj_attr":{o:dict(a) for o,a in list(self.obj_attr.items())},
              "syntax":{lg:{t:dict(n) for t,n in words.items()} for lg,words in list(self.syntax.items())},
              "syntax3":{lg:{",".join(roles):cnt for roles,cnt in d.items()} for lg,d in list(self.syntax3.items())},
              "role_words":{lg:{r:dict(w) for r,w in roles.items()} for lg,roles in list(self.role_words.items())},
              "sentences_heard":self.sentences_heard}
        # 자동 저장: 등록된 단순 상태들(빼먹지 않게)
        for name in self._SIMPLE_STATE:
            v = getattr(self, name, {})
            data[name] = dict(v) if isinstance(v, dict) else v
        # 자가진단: dict인데 저장 목록에 없는 '학습스러운' 속성 경고
        self._warn_unsaved(data)
        with open(MEMORY_FILE,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False)

    def _warn_unsaved(self, data):
        """저장 안 된 학습 상태가 있으면 알려준다(까먹음 방지 안전장치)."""
        known = set(data.keys()) | {
            "memory","q","qn","trace","recent_reward","world","rng",
            "working_memory","explored","hist","last_signal","growth_curve",
        }
        for attr, val in list(self.__dict__.items()):
            if attr in known or attr.startswith("_"):
                continue
            # dict인데 내용이 있고 저장 안 됨 = 까먹을 위험
            if isinstance(val, dict) and len(val) > 0:
                print(f"[저장경고] '{attr}' 가 저장 목록에 없음 — _SIMPLE_STATE 에 추가 권장")

    def load(self):
        if not os.path.exists(MEMORY_FILE): return False
        with open(MEMORY_FILE,encoding="utf-8") as f: d=json.load(f)
        self.mem_len=d.get("mem_len",self.mem_len)
        self.hits=d.get("hits",0); self.chances=d.get("chances",0)
        self.lived=d.get("lived",0)
        self.mood=d.get("mood",0.0); self.mood_sum=d.get("mood_sum",0.0)
        self.reward_sum=d.get("reward_sum",0.0); self.reward_n=d.get("reward_n",0)
        self.hist=[tuple(x) for x in d.get("hist_tail",[])]
        ls=d.get("last_signal"); self.last_signal=tuple(ls) if ls else None
        self.growth_curve=d.get("growth_curve",[])
        self.word_link=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for o,langs in d.get("word_link",{}).items():
            for l,w in langs.items():
                for wd,c in w.items(): self.word_link[o][l][wd]=c
        self.words_known=self._count_known()
        def s2sig(s): return tuple(s.split("~"))
        self.memory=defaultdict(lambda:defaultdict(int))
        for ks,nx in d.get("memory",{}).items():
            key=tuple(s2sig(p) for p in ks.split("|"))
            for ns,c in nx.items():
                self.memory[key][s2sig(ns)]=c
        self.q=defaultdict(lambda:{a:0.0 for a in ACTIONS})
        self.qn=defaultdict(lambda:{a:0 for a in ACTIONS})
        for sk,av in d.get("q",{}).items():
            if isinstance(av,dict):   # 모든 행동이 다 있는 틀에 덮어씌운다(키 빠짐 방지)
                base={a:0.0 for a in ACTIONS}
                for k,v in av.items():
                    try: base[k]=float(v)
                    except Exception: pass
                self.q[s2sig(sk)]=base
        for sk,nv in d.get("qn",{}).items():
            if isinstance(nv,dict):   # 빈 dict나 일부만 저장된 옛 파일도 여기서 고쳐짐
                base={a:0 for a in ACTIONS}
                for k,v in nv.items():
                    try: base[k]=int(v)
                    except Exception: pass
                self.qn[s2sig(sk)]=base
        self.syntax=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for lg,words in d.get("syntax",{}).items():
            for t,n in words.items():
                for w,c in n.items(): self.syntax[lg][t][w]=c
        self.sentences_heard=d.get("sentences_heard",0)
        if not hasattr(self,'role_words') or True:
            self.role_words=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
            for lg, roles in d.get("role_words",{}).items():
                for r, w in roles.items():
                    for word, c in w.items():
                        self.role_words[lg][r][word]=c
        self.word_current=d.get("word_current",{})
        self.word_history=d.get("word_history",{})
        self.curiosity=d.get("curiosity",{})
        self.relations=d.get("relations",{})
        self.isa=d.get("isa",{})
        # 자동 복원: 등록된 단순 상태들(빼먹지 않게)
        for name in self._SIMPLE_STATE:
            setattr(self, name, d.get(name, {}))
        # 목록형 상태는 목록으로 (옛 저장 호환)
        for _nm in ("talk_topics","first_words"):
            if not isinstance(getattr(self,_nm,None), list): setattr(self,_nm,[])
        for _nm in ("grounding","metaphors","partner_said"):
            if not isinstance(getattr(self,_nm,None), dict): setattr(self,_nm,{})
        # 세 단어 문법 학습 복원 (까먹지 않게)
        self.syntax3=defaultdict(lambda: defaultdict(int))
        for lg, dd in d.get("syntax3",{}).items():
            for roles_str, cnt in dd.items():
                self.syntax3[lg][tuple(roles_str.split(","))]=cnt
        self.role_words=defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for lg, roles in d.get("role_words",{}).items():
            for r, w in roles.items():
                for word, c in w.items():
                    self.role_words[lg][r][word]=c
        self.obj_attr=defaultdict(lambda: defaultdict(int))
        for o,a in d.get("obj_attr",{}).items():
            for k,c in a.items(): self.obj_attr[o][k]=c
        return True


MIN_LOOPS_DEFAULT=10000
class AutoGrow:
    def __init__(self, get_baby):
        self.get_baby=get_baby; self.running=False; self.rate=200
        self.loops=0; self.min_loops=MIN_LOOPS_DEFAULT; self.target_years=None; self._t=None
        self.curious_auto=True     # 살아가며 스스로 호기심 탐험할지
        self.curious_every=3        # 몇 루프마다 탐험/로그할지(자주 보이게)
        self.activity=[]            # 최근 한 일(화면에 실시간 표시)
    def _log(self, msg):
        self.activity.append(msg)
        self.activity = self.activity[-30:]   # 최근 30개만
    def _status_line(self, b, curious_now, search_on):
        """지금 상태 한 줄 — 살아있는 동안 계속 나오는 실황."""
        try:
            age=int(b.lived/TICKS_PER_YEAR); known=b._count_known()
        except Exception:
            age=0; known=0
        if not curious_now:
            return f"🍼 살아가는 중 — 나이 {age}살, 아는 단어 {known}개 (세상을 둘러보는 중 — 아직 확실히 모르는 걸 모으고 있어요)"
        names = ", ".join(c[0] for c in curious_now[:3])
        if not search_on:
            return f"❓ 궁금: {names} — 검색이 꺼져 있어요 (⚙설정)"
        return f"⏳ 궁금: {names} — 곧 찾아볼게요 (나이 {age}살, 아는 단어 {known}개)"

    def _loop(self, mygen=0):
        err_run = 0
        CHUNK = 100   # 잘게 살면서 사이사이 실황을 뱉는다 — 기계가 느려도 로그가 안 끊긴다
        while self.running and getattr(self, "_gen", mygen) == mygen:
            try:
                b=self.get_baby()
                # ① 살기: 한 덩어리를 잘게 쪼개고, 3초마다 무조건 실황 한 줄
                done=0; total=max(1,self.rate)
                while done < total and self.running and getattr(self,"_gen",mygen)==mygen:
                    step=min(CHUNK, total-done)
                    b.live(step)          # live가 스스로 잠깐 락을 잡음 — 말 걸기와 교대 가능
                    done+=step
                    if time.time()-getattr(self,"_beat",0.0) >= 3.0:
                        with b.lock:
                            curious_now = b.what_im_curious(5) if hasattr(b,"what_im_curious") else []
                            line = self._status_line(b, curious_now, SETTINGS.get('real_search'))
                        self._log(line)
                        self._beat=time.time()
                if not (self.running and getattr(self,"_gen",mygen)==mygen):
                    break
                self.loops+=1
                # ② 탐험/보고: 몇 덩어리마다. 에러는 절대 조용히 삼키지 않는다
                if self.curious_auto and self.loops % self.curious_every == 0:
                    try:
                        with b.lock:
                            curious_now = b.what_im_curious(5) if hasattr(b,"what_im_curious") else []
                            search_on = SETTINGS.get('real_search')
                            learned=b.explore_curiosity(max_items=3, depth=2)
                            if learned:
                                for thing, info in learned:
                                    summ=(info.get("summary") or "")[:40]
                                    src2=info.get("source") or ""
                                    line=f"🔍 '{thing}' 찾아 배움" + (f" — {summ}" if summ else "")
                                    if src2: line += f"\n      └ 출처: {src2}"
                                    self._log(line)
                                    try:
                                        thoughts=b.say_thought(thing) if hasattr(b,"say_thought") else []
                                        for t in thoughts[:1]:
                                            self._log(f"💭 추론: {t['sentence']}")
                                    except Exception:
                                        pass
                            else:
                                self._log(self._status_line(b, curious_now, search_on))
                            try:
                                for c in b.detect_contradictions()[:1]:
                                    self._log(f"❓ 의심: {c['note']}")
                            except Exception:
                                pass
                            # (36) 처음 확실히 알게 된 말 — 말해본 걸 알려준다
                            try:
                                _fw=getattr(b,"first_words",[]) or []
                                if not hasattr(self,"_fw_seen"): self._fw_seen=0
                                for _it in _fw[self._fw_seen:][:3]:
                                    self._log(f"🗣 '{_it.get('단어')}' 확실히 알게 됨 — 처음 말해봄: {_it.get('말')}")
                                self._fw_seen=len(_fw)
                            except Exception: pass
                            # (39·40) 계획과 자기평가를 가끔 소리내어
                            if self.loops % (self.curious_every*4) == 0:
                                try:
                                    _pl=b.make_plan(3)
                                    if _pl: self._log("📋 계획: " + " → ".join(p["할일"] for p in _pl))
                                    _sa=b.self_assess()
                                    self._log(f"🪞 자기평가: 확실 {_sa['확실']} · 배우는중 {_sa['배우는중']} · 궁금 {_sa['궁금']} · 의심 {_sa['의심']} · 비유 {_sa['비유']}")
                                except Exception: pass
                            if self.loops % (self.curious_every*3) == 0:
                                goals=b.pursue_goals(depth=2)
                                for g in (goals.get("goals") or [])[:1]:
                                    self._log(f"🎯 스스로 목표: '{g['goal']}' ({g['why']})")
                        self._beat=time.time()
                    except Exception as e:
                        self._log(f"💥 탐험 중 문제: {type(e).__name__}: {str(e)[:80]}")
                err_run = 0
            except Exception as e:
                # 자동이 소리 없이 죽지 않는다 — 무슨 일인지 화면 로그에 보인다
                err_run += 1
                self._log(f"💥 자동이 문제를 만남: {type(e).__name__}: {str(e)[:90]}")
                try:
                    import traceback; traceback.print_exc()
                except Exception:
                    pass
                if err_run >= 3:
                    self._log("⏸ 같은 문제가 반복돼 자동을 멈춥니다 — 위 💥 내용을 그대로 알려주세요")
                    self.running=False
                    break
                time.sleep(1.0)
                continue
            if self.target_years is not None:
                if self.get_baby().lived/TICKS_PER_YEAR>=self.target_years and self.loops>=self.min_loops:
                    self.running=False; break
            time.sleep(0.5)
    def start(self,rate=None,min_loops=None,target_years=None,curious_auto=None):
        if rate:self.rate=rate
        if min_loops is not None:self.min_loops=max(1,int(min_loops))
        if curious_auto is not None:self.curious_auto=bool(curious_auto)
        self.target_years=target_years
        if self.running:return
        # 켤 때마다 새로 — 껐다 켜도 실황이 바로 나온다(루프번호·박동시계 리셋).
        # 세대 표식: 빨리 껐다 켜도 옛 스레드는 자기 세대가 끝난 걸 보고 즉시 죽는다(두 개 안 돎).
        self._gen = getattr(self, "_gen", 0) + 1
        self.loops = 0
        self._beat = 0.0
        self._log("▶ 자동 성장 시작 — 알아서 살고 배웁니다")
        self._log("🍼 깨어났어요 — 몇 초 안에 실황이 떠요")
        self.running=True
        self._t=threading.Thread(target=self._loop, args=(self._gen,), name=f"autogrow-{self._gen}", daemon=True)
        self._t.start()
    def stop(self):
        self.running=False; self._log("⏸ 멈춤")
    def status(self):
        return {"running":self.running,"rate":self.rate,"loops":self.loops,
                "min_loops":self.min_loops,"target_years":self.target_years,
                "curious_auto":self.curious_auto,
                "activity":list(reversed(self.activity))}   # 최신이 위로

def _make():
    b=Baby(mem_len=2); b.load()
    for lg in ('en','ja'):
        b.world.enable_lang(lg)
    # 사전에서 초급 명사를 환경에 채운다(유아기엔 적게 시작).
    # 처음 1회는 사전 XML을 받느라 시간이 걸린다(dict_cache에 저장 후 빨라짐).
    try:
        # 모국어(한국어) + 외국어(영어) 기초 단어를 같이 로드 — 처음부터 다국어.
        load_dictionary_into(b.world, levels=('초급',), pos=('명사','동사'), limit=2000, lang='ko')
        load_dictionary_into(b.world, pos=('명사','동사'), limit=600, lang='en')
        # 일본어 기초 단어(JLPT N5·N4) — 명사·동사. 어순은 명사→동사(한국어와 같음).
        load_dictionary_into(b.world, pos=('명사','동사'), limit=400, lang='ja')
        # 번역 연결: 한 사물에 여러 언어 달기(사과=apple=リンゴ).
        # 샘플 단어로 시작. 네 컴퓨터(USE_REAL_TRANSLATION=True)에선 더 많이 가능.
        link_translations_into(b.world, list(_SAMPLE_TRANSLATIONS.keys()))
        # 명사-동사 의미 짝(연어) 로드 — '물 마시다'처럼 어울리는 짝.
        try:
            import collocation_loader
            ko_verbs = b.world.verbs_by_lang.get('ko', [])[:120]
            ko_pairs = collocation_loader.load_pairs(ko_verbs, topn=5)
            b.world.colloc_by_lang['ko'] = ko_pairs
            b.world.collocations = ko_pairs   # 구 호환
        except Exception as e:
            print('한국어 연어 건너뜀(kollocate 없음?):', e)
        try:
            import collocation_loader_en
            # 영어는 동사 전체로(파일 작아 빠름)
            en_pairs = collocation_loader_en.load_pairs(topn=5, min_score=4.0)
            b.world.colloc_by_lang['en'] = en_pairs
            # 영어 주어 짝(nsubj): people eat 같은. 세 단어 주어용.
            if not hasattr(b.world, 'subj_pairs_by_lang'):
                b.world.subj_pairs_by_lang = {}
            b.world.subj_pairs_by_lang['en'] = collocation_loader_en.load_subjects(min_score=4.0)
            # 영어 주어 후보 전체(목록)
            allsub = set()
            for vs in b.world.subj_pairs_by_lang['en'].values():
                allsub.update(vs)
            b.world.subjects_by_lang['en'] = [s for s in allsub if s in b.world.nouns] or list(allsub)
        except Exception as e:
            print('영어 의미짝 건너뜀:', e)
        # (백지 원칙) 태어날 때는 아무 단어도 미리 가르치지 않는다.
        #  세상엔 사물이 '존재'하지만(world.objects), 아기는 겪어서(보고+이름 듣고
        #  여러 번 반복해서) 스스로 알아간다. 번역 연결(사과=apple)도 아기가
        #  둘 다 겪은 뒤에 잇는다 — 미리 주입하지 않는다.
    except Exception as e:
        print('사전 로드 건너뜀(나중에 가능):', e)
    # 진단: 사물이 몇 개 로드됐나. 0이면 사전 다운로드가 안 된 것.
    _n = len(b.world.objects)
    if _n == 0:
        print('=' * 50)
        print('[경고] 사물(단어)이 0개입니다. 사전을 못 받았습니다.')
        print('  인터넷 연결을 확인하세요. 사전은 github에서 받습니다.')
        print('  (회사망/방화벽이 github를 막으면 실패할 수 있습니다.)')
        print('  사물이 0개면 살게하기/문장 버튼이 작동하지 않습니다.')
        print('=' * 50)
    else:
        print(f'[준비됨] 사물 {_n}개 로드. 이제 살게하기를 눌러도 됩니다.')
    return b
_current={"baby":None}
def get_baby():
    """처음 실제로 필요할 때 세상을 만든다.

    모듈을 읽는 것만으로 사전 다운로드와 거대한 초기화를 시작하지 않으므로
    학습기관을 외부 정답 없이 독립적으로 시험할 수 있다.
    """
    if _current["baby"] is None:
        _current["baby"]=_make()
    return _current["baby"]
def reset_baby(mem_len=2):
    if os.path.exists(MEMORY_FILE):os.remove(MEMORY_FILE)
    _current["baby"]=Baby(mem_len=mem_len); return _current["baby"]
auto=AutoGrow(get_baby)
# 자동 성장은 사용자가 '자동 성장 시작' 버튼을 눌러야 시작된다.
# (서버 켰다고 멋대로 돌지 않는다.)

if __name__=="__main__":
    b=Baby()
    # 진짜 학습 검증: 초반 vs 후반 행동 성공률(보상)
    early=[]; late=[]
    N=60000
    for t in range(N):
        ev=b.live_one()
        if ev["reward"] is not None and b.last_signal is not None:
            if t<N*0.1: early.append(ev["reward"])
            elif t>N*0.9: late.append(ev["reward"])
    s=b.stats()
    print(f"나이 {s['age_label']} / 단계 {s['stage_id']} {s['stage_name']}")
    e=sum(early)/len(early)*100; l=sum(late)/len(late)*100
    print(f"행동 성공률  초반 {e:.1f}%  →  후반 {l:.1f}%   (오르면 진짜 학습)")
    print(f"평생 {s['skill_lifetime']}%  /  최근 {s['skill_recent']}%  /  배운 상황 {s['situations_learned']}개")
