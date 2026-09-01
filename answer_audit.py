"""Answer provenance, invalidation, and user-facing correction delivery."""


class AnswerAuditMixin:
    """Track which beliefs supported answers and disclose later corrections.

    The host supplies ``isa``, ``lived``, ``_belief_key()`` and ``_j()``.
    """

    def _record_answer(self, question, result):
        if not isinstance(getattr(self, "answer_history", None), list):
            self.answer_history = []
        result = result or {}
        # Callers that actually performed reasoning can report the exact beliefs used.
        # Text scanning remains only as compatibility for older response paths.
        explicit = result.get("beliefs_used")
        if isinstance(explicit, (list, tuple, set)):
            used = list(dict.fromkeys(str(key) for key in explicit if key))
        else:
            used = []
            text = (question or "") + " " + str(result.get("say", ""))
            for subject, obj in (getattr(self, "isa", {}) or {}).items():
                if subject in text:
                    used.append(self._belief_key(subject, "is_a", obj))
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
