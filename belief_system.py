"""Evidence-based belief learning, verification, and correction behavior.

This module is intentionally independent from the world and language-learning setup in
``baby.py``.  ``EvidenceBeliefMixin`` expects its host to provide the small integration
surface documented on the class, while all belief state transitions live here.
"""

import json


class EvidenceBeliefMixin:
    """Belief subsystem mixed into ``Baby``.

    The host supplies ``isa``, ``doubts``, ``lived``, ``_wonder()`` and ``_j()``.
    Keeping this subsystem separate makes it testable without initializing the world.
    """

    def _belief_key(self, subject, relation, obj):
        """JSON에도 그대로 저장할 수 있는 안정적인 믿음 식별자."""
        return f"{subject}\u241f{relation}\u241f{obj}"

    _EVIDENCE_WEIGHT = {
        "direct": 1.5,       # 직접 감각으로 겪음
        "experiment": 2.0,   # 조건을 바꿔 다시 확인함
        "testimony": 1.0,    # 다른 사람·문서가 말함
        "inference": 0.35,   # 다른 믿음에서 추론함(검증 대신 쓰면 안 됨)
    }

    def observe_belief(self, subject, relation, obj, source=None, supports=True,
                       evidence=None, kind="testimony", reliability=1.0,
                       context=None, evidence_id=None, independence_group=None):
        """주장을 참/거짓으로 확정하지 않고 한 번의 근거로 기록한다.

        출처 하나가 같은 말을 반복해도 독립 근거 하나로 센다. 원문 기록은 남겨
        나중에 왜 믿었고 왜 고쳤는지 되짚을 수 있게 한다.
        """
        if not isinstance(getattr(self, "beliefs", None), dict):
            self.beliefs = {}
        source = (source or "unknown").strip()
        kind = kind if kind in self._EVIDENCE_WEIGHT else "testimony"
        independence_group = self._evidence_independence_group(
            source, kind, evidence_id, independence_group)
        try: reliability = max(0.0, min(1.0, float(reliability)))
        except (TypeError, ValueError): reliability = 0.5
        key = self._belief_key(subject, relation, obj)
        b = self.beliefs.setdefault(key, {
            "subject": subject, "relation": relation, "object": obj,
            "observations": [],
            "status": "unverified", "created_at": self.lived,
            "updated_at": self.lived,
        })
        # 증언은 같은 출처가 반복해도 하나의 근거다. 직접 관찰·실험은 호출자가
        # 서로 다른 evidence_id를 주었을 때만 독립된 반복으로 인정한다.
        unit = evidence_id or f"{kind}:{source}"
        observation = {
            "id": unit,
            "source": source, "supports": bool(supports),
            "independence_group": independence_group,
            "kind": kind, "reliability": reliability,
            "context": context or {}, "evidence": (evidence or "")[:500],
            "at": self.lived,
        }
        # 같은 근거 단위가 다시 들어오면 최신 관찰로 교체한다. 반복 횟수로 진실을
        # 부풀리지 않으면서, 그 출처가 정정한 것은 반영한다. 교체 전 내용은 감사
        # 이력에 남겨 출처가 언제 말을 바꿨는지도 잃지 않는다.
        replaced = [o for o in b["observations"] if o.get("id") == unit]
        if replaced:
            b.setdefault("observation_history", []).extend(replaced)
            b["observation_history"] = b["observation_history"][-100:]
        b["observations"] = [o for o in b["observations"] if o.get("id") != unit]
        b["observations"].append(observation)
        b["observations"] = b["observations"][-100:]
        b["updated_at"] = self.lived
        task = (getattr(self, "verification_tasks", {}) or {}).get(
            self._verification_key(subject, relation, context))
        if task:
            task["last_evidence_at"] = self.lived
            task["evidence_seen"] = task.get("evidence_seen", 0) + 1
            if task.get("status") == "resolved":
                task["status"] = "reopened"
        totals = self._belief_evidence_totals(b)
        if totals["support"] and totals["oppose"]:
            b["status"] = "disputed"
        elif totals["support"] >= 2.0:
            b["status"] = "supported"
        else:
            b["status"] = "unverified"
        return b

    def revise_belief_observation(self, subject, relation, obj, source=None,
                                  evidence=None, kind="testimony", reliability=1.0,
                                  context=None, evidence_id=None,
                                  independence_group=None):
        """한 근거 계통이 이전 후보를 철회하고 새 후보로 정정한 것을 기록한다.

        새 주장만 추가하면 이전 주장이 계속 지지된 것처럼 남는다. 단일 값 관계에서
        동일 출처가 후보를 바꾸면 예전 관찰은 반대 관찰로 전환하고 변경 이력을 보존한다.
        """
        source = (source or "unknown").strip()
        group = self._evidence_independence_group(
            source, kind, evidence_id, independence_group)
        retracted = []
        for belief in (getattr(self, "beliefs", {}) or {}).values():
            if (belief.get("subject") != subject or belief.get("relation") != relation
                    or belief.get("object") == obj):
                continue
            for old_observation in list(belief.get("observations", [])):
                old_group = old_observation.get("independence_group")
                if old_group is None:
                    old_group = self._evidence_independence_group(
                        old_observation.get("source", "unknown"),
                        old_observation.get("kind", "testimony"),
                        old_observation.get("id"))
                if old_group == group and old_observation.get("supports"):
                    self.observe_belief(
                        subject, relation, belief.get("object"), source=source,
                        supports=False,
                        evidence=f"이전 주장을 철회함: {evidence or obj}",
                        kind=kind, reliability=reliability, context=context,
                        evidence_id=old_observation.get("id"),
                        independence_group=group,
                    )
                    retracted.append(belief.get("object"))
                    break
        current = self.observe_belief(
            subject, relation, obj, source=source, supports=True,
            evidence=evidence, kind=kind, reliability=reliability,
            context=context, evidence_id=evidence_id,
            independence_group=group,
        )
        return {"belief": current, "retracted": retracted}

    def _evidence_independence_group(self, source, kind, evidence_id=None,
                                     independence_group=None):
        """복제된 증언을 독립 근거로 세지 않기 위한 근거 계통 식별자."""
        if independence_group:
            return str(independence_group).strip()
        # 직접 관찰과 실험은 호출자가 서로 다른 실행 ID를 준 경우에만 독립이다.
        if kind in ("direct", "experiment"):
            return str(evidence_id or f"{kind}:{source}")
        # 같은 웹사이트의 URL이 달라도 기본적으로 같은 출판 계통으로 본다.
        try:
            from urllib.parse import urlparse
            parsed = urlparse(source)
            if parsed.scheme in ("http", "https") and parsed.hostname:
                host = parsed.hostname.lower().removeprefix("www.")
                return f"publisher:{host}"
        except (TypeError, ValueError):
            pass
        return f"source:{source}"

    def _observation_applies(self, observation, context):
        """Return whether an observation is usable in the requested context."""
        if context is None:
            return True
        observed_context = observation.get("context") or {}
        # Context-free evidence is a general claim. Conditional evidence only applies
        # when every recorded condition is present in the question's context.
        return all(context.get(key) == value for key, value in observed_context.items())

    def _belief_evidence_totals(self, belief, context=None):
        """근거의 종류와 신뢰도를 반영한 지지/반박량. 문장 확률과 무관하다."""
        # 같은 원문을 복제한 기사나 같은 출판사의 여러 URL은 가장 강한 하나만 센다.
        # 출처 문자열 개수가 아니라 독립된 증거 계통 개수를 평가한다.
        support_groups, oppose_groups = {}, {}
        support_sources, oppose_sources = set(), set()
        for o in belief.get("observations", []):
            if not self._observation_applies(o, context):
                continue
            weight = self._EVIDENCE_WEIGHT.get(o.get("kind"), 0.0)
            weight *= max(0.0, min(1.0, float(o.get("reliability", 0.5))))
            group = o.get("independence_group") or self._evidence_independence_group(
                o.get("source", "unknown"), o.get("kind", "testimony"), o.get("id"))
            if o.get("supports"):
                support_groups[group] = max(weight, support_groups.get(group, 0.0))
                support_sources.add(o.get("source", "unknown"))
            else:
                oppose_groups[group] = max(weight, oppose_groups.get(group, 0.0))
                oppose_sources.add(o.get("source", "unknown"))
        support = sum(support_groups.values())
        oppose = sum(oppose_groups.values())
        # 이전 버전 저장 파일을 읽을 때 출처 장부를 잃지 않는다.
        if not belief.get("observations"):
            support_sources.update(belief.get("support_sources", []))
            oppose_sources.update(belief.get("oppose_sources", []))
            support += len(support_sources); oppose += len(oppose_sources)
        return {"support": round(support, 3), "oppose": round(oppose, 3),
                "support_sources": sorted(support_sources),
                "oppose_sources": sorted(oppose_sources),
                "support_groups": sorted(support_groups),
                "oppose_groups": sorted(oppose_groups)}

    def belief_about(self, subject, relation="is_a", context=None):
        """대상에 관한 후보와 근거를 반환한다. 문장 생성 확률은 사용하지 않는다."""
        out = []
        for b in (getattr(self, "beliefs", {}) or {}).values():
            if b.get("subject") == subject and b.get("relation") == relation:
                item = dict(b)
                totals = self._belief_evidence_totals(b, context=context)
                if context is not None and not (totals["support"] or totals["oppose"]):
                    continue
                item.update(totals)
                total = totals["support"] + totals["oppose"] + 1.0
                item["confidence"] = round(totals["support"] / total, 3)
                out.append(item)
        return sorted(out, key=lambda x: (x["support"]-x["oppose"], x["support"]), reverse=True)

    def _context_key(self, subject, relation, context):
        normalized = json.dumps(context or {}, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"))
        return f"{subject}\u241f{relation}\u241f{normalized}"

    def verify_belief(self, subject, relation="is_a", min_evidence=2.0,
                      context=None):
        """독립 출처와 반대 근거를 비교해 현재 결론을 갱신한다.

        증거가 부족하거나 후보들이 비슷하면 결론을 내리지 않는다. 결론을 바꿀 때에는
        이전 결론, 새 결론, 사용한 근거를 수정 장부에 남긴다.
        """
        candidates = self.belief_about(subject, relation, context=context)
        if context is None:
            old = self.isa.get(subject) if relation == "is_a" else None
        else:
            old = (getattr(self, "contextual_conclusions", {}) or {}).get(
                self._context_key(subject, relation, context))
        ranked = []
        for b in candidates:
            score = b["support"] - b["oppose"]
            if b["support"] >= min_evidence and score >= 1.0 and b["confidence"] >= 0.6:
                ranked.append((score, b["support"], b))
        if not ranked:
            # 한 번 채택한 결론도 영구 고정하지 않는다. 그 결론 자체에 반대 근거가
            # 지지만큼 쌓이면 추론 그래프에서 빼고 '모름' 상태로 되돌린다.
            current = next((b for b in candidates if b.get("object") == old), None)
            if old is not None and current and current["oppose"] >= current["support"]:
                revision = self._suspend_belief(
                    subject, relation, old,
                    "반대 근거가 기존 지지 이상으로 쌓여 결론을 보류함",
                    current, context=context,
                )
                self._finish_verification_task(subject, relation, "suspended", None,
                                               context=context)
                return {"subject": subject, "verified": False,
                        "reason": "기존 결론을 반증해 판단 보류", "suspended": True,
                        "previous": old, "revision": revision, "candidates": candidates}
            return {"subject": subject, "verified": False, "reason": "독립 근거 부족", "candidates": candidates}
        ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.75:
            # 서로 충분히 강한 결론이 맞서면 예전 결론을 계속 사실처럼 사용하지 않는다.
            revision = None
            if old is not None:
                revision = self._suspend_belief(
                    subject, relation, old,
                    "서로 양립할 수 없는 후보의 근거가 비슷해 결론을 보류함",
                    ranked[0][2], context=context,
                )
            self._finish_verification_task(subject, relation, "blocked", None,
                                           context=context)
            return {"subject": subject, "verified": False, "reason": "근거가 맞서 결론 보류", "candidates": candidates}
        winner = ranked[0][2]
        new = winner["object"]
        if context is not None:
            if not isinstance(getattr(self, "contextual_conclusions", None), dict):
                self.contextual_conclusions = {}
            self.contextual_conclusions[self._context_key(subject, relation, context)] = new
        elif relation == "is_a":
            self.isa[subject] = new
            self.doubts.pop(subject, None)
        changed = old is not None and old != new
        if changed:
            if not isinstance(getattr(self, "belief_revisions", None), list):
                self.belief_revisions = []
            self.belief_revisions.append({
                "subject": subject, "relation": relation, "from": old, "to": new,
                "at": self.lived, "support_sources": list(winner["support_sources"]),
                "oppose_sources": list(winner["oppose_sources"]),
                "context": context or {},
                "reason": "독립 근거를 다시 비교해 이전 결론 수정",
            })
            if context is None:
                self._invalidate_answers(
                    self._belief_key(subject, relation, old), new,
                    revision=self.belief_revisions[-1],
                )
        # belief_about은 외부에 줄 복사본이므로 원본 상태를 명시적으로 바꾼다.
        original = self.beliefs.get(self._belief_key(subject, relation, new))
        if original is not None and context is None:
            original["status"] = "accepted"
        self._finish_verification_task(subject, relation, "resolved", new,
                                       context=context)
        return {"subject": subject, "verified": True, "conclusion": new,
                "changed": changed, "previous": old,
                "context": context or {},
                "support_sources": list(winner["support_sources"]),
                "oppose_sources": list(winner["oppose_sources"]),
                "confidence": winner["confidence"]}

    def _suspend_belief(self, subject, relation, old, reason, evidence=None,
                        context=None):
        """반증되거나 해결되지 않은 결론을 추론용 지식에서 제거한다."""
        if context is not None:
            getattr(self, "contextual_conclusions", {}).pop(
                self._context_key(subject, relation, context), None)
        elif relation == "is_a" and self.isa.get(subject) == old:
            self.isa.pop(subject, None)
        if not isinstance(getattr(self, "belief_revisions", None), list):
            self.belief_revisions = []
        revision = {
            "subject": subject, "relation": relation, "from": old, "to": None,
            "at": self.lived,
            "support_sources": list((evidence or {}).get("support_sources", [])),
            "oppose_sources": list((evidence or {}).get("oppose_sources", [])),
            "reason": reason, "status": "suspended",
            "context": context or {},
        }
        self.belief_revisions.append(revision)
        original = self.beliefs.get(self._belief_key(subject, relation, old))
        if original is not None:
            original["status"] = "disputed"
        self.doubts.setdefault(subject, [])
        if context is None:
            self._invalidate_answers(self._belief_key(subject, relation, old), None,
                                     revision=revision)
        return revision

    def deliberate(self, subject, relation="is_a", context=None):
        """무조건 예측하지 않고 현재 상태에 맞는 사고 행동을 고른다.

        아는 근거가 없으면 조사, 충돌하면 검증, 검증됐으면 근거 회상, 아직 약하면
        보류한다. 출력의 steps는 실제로 어떤 기억을 확인했는지 보여준다.
        """
        candidates = self.belief_about(subject, relation, context=context)
        steps = ["질문에서 대상과 관계를 분리함", "관련된 경험과 출처를 기억에서 찾음"]
        if not candidates:
            self._wonder(subject)
            plan = self.make_verification_plan(subject, relation, context=context)
            return {"subject": subject, "action": "investigate", "conclusion": None,
                    "steps": steps + ["근거가 없어 조사 대상으로 올림"],
                    "verification_plan": plan, "candidates": []}
        if len(candidates) > 1 or any(c.get("status") == "disputed" or c["oppose"] > 0 for c in candidates):
            self._wonder(subject)
            plan = self.make_verification_plan(subject, relation, context=context)
            return {"subject": subject, "action": "verify", "conclusion": None,
                    "steps": steps + ["서로 맞지 않는 근거를 발견함", "반증 가능한 추가 확인이 필요함"],
                    "verification_plan": plan, "candidates": candidates}
        verified = self.verify_belief(subject, relation, context=context)
        if verified.get("verified"):
            return {"subject": subject, "action": "recall", "conclusion": verified["conclusion"],
                    "confidence": verified.get("confidence"),
                    "steps": steps + ["지지·반박 근거를 비교함", "현재 결론을 근거와 함께 회상함"],
                    "candidates": candidates}
        self._wonder(subject)
        plan = self.make_verification_plan(subject, relation, context=context)
        return {"subject": subject, "action": "withhold", "conclusion": None,
                "steps": steps + ["근거가 있지만 아직 부족해 판단을 보류함"],
                "verification_plan": plan, "candidates": candidates}

    def _verification_key(self, subject, relation, context=None):
        if context is None:
            return f"{subject}\u241f{relation}"
        return self._context_key(subject, relation, context)

    def make_verification_plan(self, subject, relation="is_a", context=None):
        """모순을 발견하는 데서 멈추지 않고, 무엇을 확인할지 작업으로 만든다."""
        if not isinstance(getattr(self, "verification_tasks", None), dict):
            self.verification_tasks = {}
        candidates = self.belief_about(subject, relation, context=context)
        hypotheses = []
        for candidate in candidates:
            hypotheses.append({
                "claim": candidate.get("object"),
                "support": candidate.get("support", 0.0),
                "oppose": candidate.get("oppose", 0.0),
                "independent_support_groups": len(candidate.get("support_groups", [])),
                "independent_oppose_groups": len(candidate.get("oppose_groups", [])),
                "need": max(0.0, round(2.0 - candidate.get("support", 0.0), 3)),
                "disconfirm": f"{subject}가 {candidate.get('object')}가 아닌 독립 사례 찾기",
            })
        if not hypotheses:
            next_actions = ["서로 독립된 출처 두 곳에서 후보 설명 수집",
                            "가능하면 직접 관찰이나 반복 실험으로 후보 생성"]
        else:
            next_actions = ["각 후보를 지지하는 독립 근거를 같은 조건에서 비교",
                            "현재 가장 강한 후보의 반례를 먼저 탐색",
                            "출처의 원문과 서로 복제된 정보인지 확인"]
        key = self._verification_key(subject, relation, context)
        previous = self.verification_tasks.get(key, {})
        task = {
            "id": key, "subject": subject, "relation": relation,
            "context": context or {},
            "status": "open" if previous.get("status") != "reopened" else "reopened",
            "created_at": previous.get("created_at", self.lived),
            "updated_at": self.lived,
            "evidence_seen": previous.get("evidence_seen", 0),
            "hypotheses": hypotheses, "next_actions": next_actions,
            "stop_condition": "한 후보가 최소 근거를 넘고 경쟁 후보보다 명확히 강함",
        }
        self.verification_tasks[key] = task
        return dict(task)

    def _finish_verification_task(self, subject, relation, status, conclusion,
                                  context=None):
        task = (getattr(self, "verification_tasks", {}) or {}).get(
            self._verification_key(subject, relation, context))
        if task:
            task["status"] = status
            task["conclusion"] = conclusion
            task["updated_at"] = self.lived

    def _record_answer(self, question, result):
        if not isinstance(getattr(self, "answer_history", None), list): self.answer_history=[]
        used=[]
        text=(question or "")+" "+str((result or {}).get("say", ""))
        for subject, obj in (getattr(self,"isa",{}) or {}).items():
            if subject in text:
                used.append(self._belief_key(subject,"is_a",obj))
        self.answer_history.append({"question":question,"answer":(result or {}).get("say"),
                                    "beliefs_used":used,"at":self.lived,
                                    "invalidated":False})
        self.answer_history=self.answer_history[-500:]
        return result

    def _invalidate_answers(self, old_belief_key, replacement, revision=None):
        """믿음 수정 때 과거 답을 숨기지 않고 '정정 필요'로 표시한다."""
        for answer in getattr(self,"answer_history",[]) or []:
            if old_belief_key in answer.get("beliefs_used",[]):
                answer["invalidated"] = True
                answer["correction"] = {
                    "subject": (revision or {}).get("subject"),
                    "relation": (revision or {}).get("relation", "is_a"),
                    "previous": (revision or {}).get("from"),
                    "replacement": replacement,
                    "reason": (revision or {}).get(
                        "reason", "새 근거로 이전 결론을 수정함"),
                    "support_sources": list((revision or {}).get("support_sources", [])),
                    "at": self.lived,
                    "delivered": False,
                }

    def pending_corrections(self, subject=None, include_delivered=False):
        """아직 사용자에게 알리지 않은 과거 답변의 정정을 반환한다.

        결론만 조용히 덮어쓰지 않고, 어떤 답이 왜 무효가 됐는지 추적한다.
        같은 믿음을 사용한 답이 여러 개여도 한 번의 정정으로 묶는다.
        """
        pending = []
        seen = set()
        for answer in getattr(self, "answer_history", []) or []:
            correction = answer.get("correction") or {}
            if not answer.get("invalidated") or not correction:
                continue
            if not include_delivered and correction.get("delivered"):
                continue
            if subject and correction.get("subject") != subject:
                continue
            key = (correction.get("subject"), correction.get("relation"),
                   correction.get("previous"), correction.get("replacement"))
            if key in seen:
                continue
            seen.add(key)
            pending.append({
                "question": answer.get("question"),
                "old_answer": answer.get("answer"),
                **dict(correction),
            })
        return pending

    def acknowledge_corrections(self, corrections):
        """전달한 정정을 같은 수정 건에 속한 모든 과거 답변에 표시한다."""
        keys = {(c.get("subject"), c.get("relation"), c.get("previous"),
                 c.get("replacement")) for c in corrections}
        for answer in getattr(self, "answer_history", []) or []:
            c = answer.get("correction") or {}
            key = (c.get("subject"), c.get("relation"), c.get("previous"),
                   c.get("replacement"))
            if key in keys:
                c["delivered"] = True
                c["delivered_at"] = self.lived

    def _attach_pending_corrections(self, question, result):
        """다음 대화에서 미전달 오류를 먼저 인정하고 현재 답을 이어 말한다."""
        corrections = self.pending_corrections()
        if not corrections:
            return result
        notices = []
        for c in corrections[:3]:
            subject = c.get("subject") or "그 내용"
            previous = c.get("previous") or "이전 결론"
            replacement = c.get("replacement")
            if replacement is None:
                notices.append(
                    f"정정할게. 전에 {subject}에 대해 {self._j(previous,'이라고','라고')} "
                    "말했지만, 반대 근거를 확인해 그 결론을 취소하고 판단을 보류했어."
                )
            else:
                notices.append(
                    f"정정할게. 전에 {subject}에 대해 {self._j(previous,'이라고','라고')} "
                    f"말했지만, 독립된 근거를 다시 확인해 {self._j(replacement,'이라고','라고')} 고쳤어."
                )
        self.acknowledge_corrections(corrections[:3])
        updated = dict(result or {})
        current = updated.get("say") or ""
        updated["say"] = " ".join(notices + ([current] if current else []))
        updated["corrections"] = corrections[:3]
        updated["mind"] = "과거 오류를 먼저 인정하고 수정 근거를 밝힘; " + updated.get("mind", "")
        return updated
