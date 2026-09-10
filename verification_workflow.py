"""Deliberation and persistent verification-task planning."""


class VerificationWorkflowMixin:
    """Turn missing or conflicting evidence into explicit verification work.

    The host supplies ``belief_about()``, ``verify_belief()``, ``_context_key()``,
    ``_wonder()``, and ``lived``.
    """

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

    def verification_queue(self, limit=10):
        """Return unresolved verification work ordered by information urgency."""
        unresolved = {"open", "reopened", "blocked", "suspended"}
        queue = []
        status_weight = {"blocked": 4.0, "reopened": 3.0,
                         "suspended": 2.5, "open": 1.0}
        for task in (getattr(self, "verification_tasks", {}) or {}).values():
            status = task.get("status", "open")
            if status not in unresolved:
                continue
            hypotheses = task.get("hypotheses", []) or []
            conflict = sum(min(float(h.get("support", 0)),
                               float(h.get("oppose", 0))) for h in hypotheses)
            missing = sum(float(h.get("need", 0)) for h in hypotheses)
            priority = status_weight.get(status, 0.0) + conflict + min(missing, 3.0)
            item = dict(task)
            item["priority"] = round(priority, 3)
            queue.append(item)
        queue.sort(key=lambda item: (-item["priority"], item.get("created_at", 0),
                                     item.get("id", "")))
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 10
        return queue[:limit]
