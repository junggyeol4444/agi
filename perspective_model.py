"""Keep other agents' evidence and beliefs separate from the agent's own knowledge."""

import json


class PerspectiveModelMixin:
    """Model what each agent has observed without copying global truth into their mind."""

    def _perspective_key(self, subject, relation):
        return json.dumps([subject, relation], ensure_ascii=False,
                          separators=(",", ":"), default=str)

    def observe_for_agent(self, agent, subject, relation, obj, source=None,
                          supports=True):
        if not isinstance(getattr(self, "perspective_models", None), dict):
            self.perspective_models = {}
        agent_memory = self.perspective_models.setdefault(str(agent), {})
        key = self._perspective_key(subject, relation)
        belief = agent_memory.setdefault(key, {
            "subject": subject, "relation": relation, "candidates": {},
            "observations": 0, "updated_at": getattr(self, "lived", 0)})
        candidate_key = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), default=str)
        candidate = belief["candidates"].setdefault(candidate_key, {
            "value": obj, "support": {}, "oppose": {}})
        evidence_key = str(source or f"observation-{belief['observations'] + 1}")
        side = "support" if supports else "oppose"
        candidate[side][evidence_key] = {"source": source,
                                         "at": getattr(self, "lived", 0)}
        belief["observations"] += 1
        belief["updated_at"] = getattr(self, "lived", 0)
        return self.perspective_belief(agent, subject, relation)

    def perspective_belief(self, agent, subject, relation="is_a", min_evidence=2):
        belief = (getattr(self, "perspective_models", {}) or {}).get(
            str(agent), {}).get(self._perspective_key(subject, relation))
        if not belief:
            return {"known": False, "agent": agent, "subject": subject,
                    "relation": relation, "reason": "그 행위자가 관찰한 근거가 없음",
                    "candidates": []}
        candidates = []
        for item in belief["candidates"].values():
            support, oppose = len(item["support"]), len(item["oppose"])
            candidates.append({"value": item["value"], "support": support,
                               "oppose": oppose, "score": support - oppose})
        candidates.sort(key=lambda item: (-item["score"], -item["support"],
                                          json.dumps(item["value"], default=str)))
        best = candidates[0]
        runner_score = candidates[1]["score"] if len(candidates) > 1 else 0
        known = best["support"] >= min_evidence and best["score"] > runner_score \
            and best["score"] > 0
        return {"known": known, "agent": agent, "subject": subject,
                "relation": relation, "conclusion": best["value"] if known else None,
                "candidates": candidates,
                "reason": ("그 행위자에게 독립된 관찰 근거가 충분함" if known else
                           "그 행위자의 근거가 부족하거나 후보가 충돌함")}

    def compare_perspective(self, agent, subject, relation="is_a"):
        other = self.perspective_belief(agent, subject, relation)
        own = None
        if relation == "is_a":
            own = (getattr(self, "isa", {}) or {}).get(subject)
        if not other["known"] or own is None:
            status = "unknown"
        elif other["conclusion"] == own:
            status = "agrees"
        else:
            status = "disagrees"
        return {"agent": agent, "subject": subject, "relation": relation,
                "own_conclusion": own, "other": other, "status": status,
                "note": "불일치는 상대가 거짓말하거나 틀렸다는 자동 판정이 아님"}

    def share_observation(self, observers, subject, relation, obj, event_id=None):
        """Give evidence only to agents explicitly listed as observers."""
        results = {}
        for agent in observers or []:
            source = f"shared-event:{event_id}" if event_id is not None else None
            results[str(agent)] = self.observe_for_agent(
                agent, subject, relation, obj, source=source, supports=True)
        return results
