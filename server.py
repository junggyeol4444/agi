import os as _os
try:
    import config as _cfg
    _os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _cfg.BROWSER_DIR)
except Exception:
    pass
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import baby

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8000

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _json(self,obj,code=200):
        body=json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.end_headers()
        self.wfile.write(body)
    def _file(self,path,ctype):
        with open(path,"rb") as f: body=f.read()
        self.send_response(200); self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body))); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path in ("/","/index.html"):
            self._file(os.path.join(HERE,"index.html"),"text/html; charset=utf-8")
        elif self.path.startswith("/browsing"):
            # 아이의 브라우저가 지금 뭘 하는지 (오른쪽 패널 실황)
            try:
                import browser_search
                self._json({"ok":True, **browser_search.now()})
            except Exception as e:
                self._json({"ok":False,"error":str(e)[:100]})
        elif self.path.startswith("/browser_view.png"):
            # 아이가 보고 있는 브라우저 화면(스크린샷 한 장)
            try:
                import browser_search
                p = browser_search.SHOT_PATH
                if os.path.exists(p):
                    body=open(p,"rb").read()
                    self.send_response(200)
                    self.send_header("Content-Type","image/png")
                    self.send_header("Content-Length",str(len(body)))
                    self.send_header("Cache-Control","no-store")
                    self.end_headers(); self.wfile.write(body)
                else:
                    self.send_response(404); self.end_headers()
            except Exception:
                self.send_response(404); self.end_headers()
        elif self.path=="/stats":
            s=baby.get_baby().stats(); s["auto"]=baby.auto.status(); self._json(s)
        else: self._json({"error":"not found"},404)
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0))
        raw=self.rfile.read(n) if n else b"{}"
        try: data=json.loads(raw.decode("utf-8") or "{}")
        except: data={}
        if self.path=="/reset":
            baby.auto.stop()
            baby.reset_baby(mem_len=int(data.get("mem_len",2)))
            s=baby.get_baby().stats(); s["auto"]=baby.auto.status()
            self._json({"ok":True,"stats":s})
        elif self.path=="/live":
            steps=max(1,min(20000,int(data.get("steps",50))))
            ml=int(data.get("mem_len",baby.get_baby().mem_len))
            if ml!=baby.get_baby().mem_len:
                baby.auto.stop(); baby.reset_baby(mem_len=ml)
            inj=None
            sig=(data.get("signal") or "").strip().lower().split()
            if len(sig)==2 and sig[0] in baby.LIGHT and sig[1] in baby.SOUND:
                inj=(sig[0],sig[1])
            evs=baby.get_baby().live(steps,injected=inj)
            s=baby.get_baby().stats(); s["auto"]=baby.auto.status()
            self._json({"ok":True,"events":evs[-60:],"stats":s})
        elif self.path=="/auto":
            if data.get("on"):
                ty = data.get("target_years", None)
                ty = float(ty) if ty not in (None,"","null") else None
                baby.auto.start(rate=int(data.get("rate",200)),
                                min_loops=int(data.get("min_loops",10000)),
                                target_years=ty,
                                curious_auto=data.get("curious_auto", True))
            else:
                baby.auto.stop()
            s=baby.get_baby().stats(); s["auto"]=baby.auto.status()
            self._json({"ok":True,"stats":s})
        elif self.path=="/toggle":
            # 화면 버튼: 자동 다운로드 설정 켜고/끄기
            key=(data.get("key") or "").strip()
            val=bool(data.get("value"))
            ok=baby.set_setting(key, val)
            self._json({"ok":ok,"settings":dict(baby.SETTINGS)})
        elif self.path=="/settings":
            self._json({"ok":True,"settings":dict(baby.SETTINGS)})
        elif self.path=="/explore":
            # 아기가 궁금한 것을 스스로 찾아 배운다(호기심)
            b=baby.get_baby()
            depth=int(data.get("depth",2))
            learned=b.explore_curiosity(max_items=3, depth=depth)
            # 진단: 왜 검색이 되는지/안 되는지 무조건 알려준다
            diag=[]
            diag.append("검색설정: "+("켜짐" if baby.SETTINGS.get("real_search") else "꺼짐(⚙설정에서 검색 켜기)"))
            try:
                import browser_search; diag.append("browser_search: 임포트됨")
                if not getattr(browser_search,"_PLAYWRIGHT_OK",True):
                    diag.append("playwright: 설치 안 됨(설치 필요)")
            except Exception as e:
                diag.append("browser_search 임포트 실패: "+str(e)[:60])
            self._json({"ok":True,
                        "learned":[{"was":t,"summary":info.get("summary"),
                                    "links":info.get("links",[]),"langs":info.get("langs",{})} for t,info in learned],
                        "still_curious":b.what_im_curious(10),
                        "search_error":getattr(b,"last_explore_error",None),
                        "diag":diag})
        elif self.path=="/pursue":
            # 스스로 목표 정하고 직접 파고들기(능동 호기심)
            b=baby.get_baby()
            r=b.pursue_goals(depth=int(data.get("depth",2)))
            self._json({"ok":True,"goals":r["goals"],
                        "learned":[{"was":t,"summary":s} for t,s in r["learned"]]})
        elif self.path=="/concept":
            # 진짜 이해: 한 개념에 묶인 모든 갈래 + 이해 깊이
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"concept":b.concept_of(word),"understand":b.understand(word)})
        elif self.path=="/hypothesis":
            # 가설 세우고 검증 (모순 풀기)
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"word":word,
                        "hypothesis":b.make_hypothesis(word),
                        "verify":b.verify_hypothesis(word)})
        elif self.path=="/belief":
            # 확률 높은 문장을 만드는 게 아니라, 실제로 모은 지지/반박 근거와 수정 이력.
            word=(data.get("word") or "").strip()
            context=data.get("context") if isinstance(data.get("context"),dict) else None
            b=baby.get_baby()
            self._json({"ok":True,"word":word,"context":context or {},
                        "beliefs":b.belief_about(word, context=context),
                        "revisions":[r for r in getattr(b,"belief_revisions",[])
                                     if r.get("subject")==word]})
        elif self.path=="/reason":
            # 모든 입력을 예측하지 않는다. 근거 상태에 따라 조사/보류/검증/회상을 선택한다.
            word=(data.get("word") or "").strip()
            context=data.get("context") if isinstance(data.get("context"),dict) else None
            b=baby.get_baby()
            self._json({"ok":True,"thought":b.deliberate(word, context=context)})
        elif self.path=="/verification-plan":
            # 모순·불확실성을 실제로 확인할 다음 행동과 반증 목표로 바꾼다.
            word=(data.get("word") or "").strip()
            relation=(data.get("relation") or "is_a").strip()
            context=data.get("context") if isinstance(data.get("context"),dict) else None
            b=baby.get_baby()
            self._json({"ok":True,"plan":b.make_verification_plan(word, relation, context)})
        elif self.path=="/verification-queue":
            # 해결되지 않은 검증 작업을 충돌·재검증 필요도 순으로 반환한다.
            b=baby.get_baby()
            self._json({"ok":True,"queue":b.verification_queue(data.get("limit",10))})
        elif self.path=="/verification-run":
            # 대기열의 우선 과제를 실제 조사하고 근거 장부에 넣은 뒤 다시 검증한다.
            b=baby.get_baby()
            self._json({"ok":True,"runs":b.run_verification(data.get("limit",1)),
                        "queue":b.verification_queue(10)})
        elif self.path=="/plan-actions":
            # 학습한 세계 모델만 사용해 목표 상태까지 짧은 행동열을 찾는다.
            b=baby.get_baby()
            state=data.get("state", list(b.last_signal) if b.last_signal else None)
            goal=data.get("goal")
            actions=data.get("actions") if isinstance(data.get("actions"),list) else baby.ACTIONS
            self._json({"ok":True,"plan":b.plan_actions(
                state, goal, actions, data.get("max_depth",3),
                action_costs=data.get("action_costs") if isinstance(data.get("action_costs"),dict) else None)})
        elif self.path=="/execute-plan":
            # 계획 행동을 실제 환경에 적용하고 예상과 다르면 현재 상태에서 재계획한다.
            b=baby.get_baby()
            plan=data.get("plan") if isinstance(data.get("plan"),dict) else {}
            run=b.run_action_plan(plan, data.get("max_replans",2))
            self._json({"ok":True,"run":run})
        elif self.path=="/calibration":
            # 자신이 말한 확신과 실제 성공률이 맞는지 수치로 확인한다.
            b=baby.get_baby()
            kind=(data.get("kind") or "").strip() or None
            self._json({"ok":True,"report":b.calibration_report(kind, data.get("bins",5))})
        elif self.path=="/corrections":
            # 결론이 바뀌었지만 아직 대화에서 알리지 않은 과거 답변 정정.
            word=(data.get("word") or "").strip() or None
            b=baby.get_baby()
            self._json({"ok":True,"corrections":b.pending_corrections(word)})
        elif self.path=="/doubts":
            # 모순 알아채기: 안 맞는 것 의심 + 재조사
            b=baby.get_baby()
            self._json({"ok":True,"contradictions":b.detect_contradictions(),
                        "recheck":b.what_to_recheck()})
        elif self.path=="/why":
            # 추론 3단계: '왜?'에 답하기 (배운 인과에서)
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"word":word,"why":b.why(word)})
        elif self.path=="/respond":
            # 진짜 대화: 한 마디 받아 정직하게 응답
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"heard":word,"reply":b.respond(word)})
        elif self.path=="/chat":
            # 채팅: 아는 건 배운 걸로 답, 모르는 건 인터넷 검색해서 알려줌
            text=(data.get("text") or data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"heard":text,"reply":b.chat(text)})
        elif self.path=="/think":
            # 통합: 추론한 것을 말로 표현 (생각 → 언어)
            word=(data.get("word") or "").strip()
            lang=(data.get("lang") or "ko").strip()
            b=baby.get_baby()
            self._json({"ok":True,"word":word,"said":b.say_thought(word,lang)})
        elif self.path=="/infer":
            # 추론: 연결을 타고 안 배운 새 사실 추측
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            self._json({"ok":True,"word":word,"inferred":b.what_i_inferred(word)})
        elif self.path=="/self":
            # (39·40) 아이 스스로: 자기평가 + 계획 + 처음 말해본 것
            b=baby.get_baby()
            try: _sa=b.self_assess()
            except Exception as e: _sa={"error":str(e)[:80]}
            try: _pl=b.make_plan(3)
            except Exception: _pl=[]
            _fw=(getattr(b,"first_words",[]) or [])[-6:][::-1]
            self._json({"ok":True,"assess":_sa,"plan":_pl,"first_words":_fw})
        elif self.path=="/social":
            # (34·43·45·47) 마음·사회: 좋아싫어(겪은 기분), 비유, 상대가 말한 것, 의심
            b=baby.get_baby()
            g=getattr(b,"grounding",{}) or {}
            prefs=[]
            for o in list(g.keys())[:300]:
                try: f=b.my_feeling(o)
                except Exception: f="모름"
                if f in ("좋아","별로"):
                    prefs.append({"것":o,"느낌":f})
                if len(prefs)>=10: break
            met=[{"말":k, "처럼":(v or {}).get("처럼"), "같이쓰는말":(v or {}).get("같이쓰는말",[])}
                 for k,v in list((getattr(b,"metaphors",{}) or {}).items())[:10]]
            ps=sorted((getattr(b,"partner_said",{}) or {}).items(), key=lambda x:-x[1])[:10]
            db=[{"말":k,"사이":v} for k,v in list((getattr(b,"doubts",{}) or {}).items())[:8]]
            # ── 심화(34 스스로 은유 / 43 상대 마음 추측 / 44 공감) ──
            try: invented=b.invent_metaphor(top=6)          # 34: 스스로 만든 은유
            except Exception: invented=[]
            try: mind_guess=b.guess_partner_mind()          # 43: 상대 마음 추측
            except Exception: mind_guess=[]
            # 44: 내가 겪어서 감정이 있는 것들에 대한 공감 한마디
            empathy=[]
            try:
                for o in list(g.keys())[:300]:
                    r=b.empathize(o)
                    if r.get("공감"):
                        empathy.append({"것":o,"말":r["말"],"내기분":r.get("내기분")})
                    if len(empathy)>=6: break
            except Exception: pass
            self._json({"ok":True,"prefs":prefs,"metaphors":met,
                        "partner":[{"말":k,"번":v} for k,v in ps],"doubts":db,
                        "invented_metaphors":invented,
                        "partner_mind":mind_guess,
                        "empathy":empathy})
        elif self.path=="/web":
            # 6단계(진짜 이해): 개념 관계망 — 분류 너머의 관계들
            b=baby.get_baby()
            web=getattr(b,"concept_web",{})
            items=[]
            for w in list(web.keys())[:30]:
                for kind,other in b._web_pairs(w):
                    conf=b._web_confidence(w,kind,other)
                    items.append({"from":w,"kind":kind,"to":other,"confidence":conf})
            # 추상 개념(33번): 감정·개념 등으로 분류된 것
            abstract=[]
            isa=getattr(b,"isa",{})
            for w in list(isa.keys())[:40]:
                c=b.concept_of(w)
                if c.get("추상") is True:
                    abstract.append({"word":w,"kind":c.get("종류")})
            # 닮은 개념(34번, 비유의 씨앗)
            analogy=[]
            seen=set()
            for w in list(isa.keys())[:20]:
                for a in b.find_analogy(w):
                    key=tuple(sorted([w,a["other"]]))
                    if key in seen: continue
                    seen.add(key)
                    analogy.append({"a":w,"b":a["other"],"why":a["why"]})
            self._json({"ok":True,"web":items,"count":len(items),
                        "abstract":abstract[:15],"analogy":analogy[:12]})
        elif self.path=="/mind":
            # 아이의 머릿속: 지금 아는 것(궁금·연결·분류·인과·모순)을 한 번에
            b=baby.get_baby()
            isa=getattr(b,"isa",{}); causes=getattr(b,"causes",{}); rels=getattr(b,"relations",{})
            inferred=[]
            for w,up in list(isa.items())[:15]:
                try:
                    th=b.say_thought(w)
                    inferred.append(th[0]["sentence"] if th else (w+" 은(는) "+up))
                except Exception:
                    inferred.append(w+" 은(는) "+up)
            self._json({"ok":True,
                "curious":[c[0] for c in b.what_im_curious(12)],
                "learned":list(rels.keys())[:20],
                "inferred":inferred,
                "causes":[f"{eff} ← {lst[0][0]} {lst[0][1]}" for eff,lst in list(causes.items())[:10] if lst],
                "doubts":[c["note"] for c in b.detect_contradictions()[:8]]})
        elif self.path=="/curious":
            # 아기가 지금 궁금해하는 것들(모르는 것)
            b=baby.get_baby()
            self._json({"ok":True,"curious":b.what_im_curious(15)})
        elif self.path=="/speak":
            # 아기가 사물을 소리내어 말한다 → wav를 base64로 보냄
            import base64
            obj=(data.get("obj") or "").strip()
            b=baby.get_baby()
            wav=b.speak_object(obj) if obj else None
            if wav:
                self._json({"ok":True,"obj":obj,
                            "wav_b64":base64.b64encode(wav).decode("ascii"),
                            "babble": obj not in b.world.audio_cache})
            else:
                self._json({"ok":False,"error":"소리를 못 냄(청각 비활성?)"})
        elif self.path=="/sentence":
            # 사물을 주면 아기가 두 단어 문장을 만든다
            obj=(data.get("obj") or "").strip()
            lang=(data.get("lang") or "ko").strip()
            b=baby.get_baby(); st=b.stats()
            if st["age_years"]<8:
                self._json({"ok":True,"sentence":obj,"note":"아직 8살 전 — 한 단어만(문장은 8살부터)"})
            else:
                sent=b.make_sentence(obj, lang)
                self._json({"ok":True,"sentence":" ".join(sent),"words":list(sent),
                            "lang":lang,"is_sentence":len(sent)>=2})
        elif self.path=="/sentence3":
            # 세 단어 문장 (주어가 목적어를 동사)
            lang=(data.get("lang") or "ko").strip()
            b=baby.get_baby(); st=b.stats()
            if st["age_years"]<8:
                self._json({"ok":True,"sentence":"","note":"아직 8살 전"})
            else:
                sent=b.make_sentence_3_learned(lang) or b.make_sentence_3(lang)
                if sent:
                    self._json({"ok":True,"sentence":" ".join(sent),"words":list(sent),"lang":lang})
                else:
                    self._json({"ok":False,"note":"세 단어 재료 부족(주어/의미짝 필요)"})
        elif self.path=="/correct":
            # 사람이 교정: w1 다음에 w2가 맞다
            w1=(data.get("w1") or "").strip(); w2=(data.get("w2") or "").strip()
            lang=(data.get("lang") or "ko").strip()
            b=baby.get_baby()
            if w1 and w2:
                b.correct_sentence(w1,w2,lang); b.save()
                self._json({"ok":True,"corrected":f"[{lang}] {w1} {w2}","now":" ".join(b.make_sentence(w1,lang))})
            else:
                self._json({"ok":False,"error":"w1과 w2 둘 다 필요"})
        elif self.path=="/teach":
            obj=(data.get("obj") or "").strip()
            word=(data.get("word") or "").strip()
            lang=(data.get("lang") or "ko").strip()
            b=baby.get_baby()
            if obj and word:
                b.world.add_object(obj, word, lang=lang)
                b.world.enable_lang(lang)
                n=b.teach(obj, word, lang=lang)
                b.save()
                self._json({"ok":True,"taught":f"[{lang}] {obj}={word}","strength":n,
                            "words_known":b.stats().get("words_known",0)})
            else:
                self._json({"ok":False,"error":"obj와 word 둘 다 필요"})
        elif self.path=="/talk":
            word=(data.get("word") or "").strip()
            b=baby.get_baby()
            obj, strength, lang = b.hear_and_react(word)
            st=b.stats()
            import random as _r
            reply=None; mode="옹알이"
            if st.get("words_known",0)==0 or st["age_years"]<6:
                reply=_r.choice(baby.BABBLE); mode="옹알이"
            elif obj is not None and strength!=0:
                said,known=b.say(obj, lang if lang and lang!="deictic" else "ko")
                reply=said; mode=("기억에서 떠올림" if strength==-1 else (f"{lang} 단어" if known else "옹알이"))
            else:
                reply=_r.choice(baby.BABBLE); mode="옹알이"
            attr=b.attr_of(obj) if obj else None
            self._json({"ok":True,"heard":word,"recalled_exp":obj,"lang":lang,
                        "attr":attr,
                        "strength":strength,"reply":reply,"reply_mode":mode,
                        "age":st["age_label"],"words_known":st.get("words_known",0)})
        else: self._json({"error":"not found"},404)

def main():
    srv=ThreadingHTTPServer(("127.0.0.1",PORT),Handler)
    print("─"*50)
    print(f" 아기가 깨어났다.  http://localhost:{PORT}")
    print(" 멈추려면 Ctrl + C.")
    print("─"*50)
    try: srv.serve_forever()
    except KeyboardInterrupt:
        baby.auto.stop(); print("\n 아기를 재웠습니다."); srv.shutdown()

if __name__=="__main__": main()
