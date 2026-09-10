"""Track viewpoint-dependent situational knowledge for other agents."""

import json


class TheoryOfMindMixin:
    """Remember what each agent last witnessed when the world later changes."""

    def _situational_key(self, subject, relation):
        return json.dumps([subject, relation], ensure_ascii=False,
                          separators=(",", ":"), default=str)

    def record_world_change(self, subject, relation, value, observers=None,
                            event_id=None, at=None):
        if not isinstance(getattr(self, "situational_facts", None), dict):
            self.situational_facts = {}
        if not isinstance(getattr(self, "perspective_states", None), dict):
            self.perspective_states = {}
        moment = int(getattr(self, "lived", 0) if at is None else at)
        key = self._situational_key(subject, relation)
        previous = self.situational_facts.get(key)
        current = {"subject": subject, "relation": relation, "value": value,
                   "at": moment, "event_id": event_id}
        self.situational_facts[key] = current
        updated = []
        for agent in observers or []:
            memory = self.perspective_states.setdefault(str(agent), {})
            memory[key] = dict(current)
            updated.append(str(agent))
        return {"previous": dict(previous) if previous else None,
                "current": dict(current), "observers_updated": updated}

    def perspective_state(self, agent, subject, relation):
        key = self._situational_key(subject, relation)
        state = (getattr(self, "perspective_states", {}) or {}).get(str(agent), {}).get(key)
        if not state:
            return {"known": False, "agent": agent, "subject": subject,
                    "relation": relation, "reason": "그 행위자가 이 상태를 본 기록이 없음"}
        return {"known": True, "agent": agent, **dict(state)}

    def compare_situational_perspective(self, agent, subject, relation):
        """Compare last witnessed state without rewriting the other agent's memory."""
        key = self._situational_key(subject, relation)
        actual = (getattr(self, "situational_facts", {}) or {}).get(key)
        believed = self.perspective_state(agent, subject, relation)
        if actual is None or not believed.get("known"):
            status = "unknown"
        elif actual["value"] == believed["value"]:
            status = "current"
        else:
            status = "outdated"
        return {"agent": agent, "subject": subject, "relation": relation,
                "status": status, "actual": dict(actual) if actual else None,
                "last_witnessed": believed,
                "note": "outdated는 마지막 관찰 차이이며 거짓말 판정이 아님"}

    def expected_search_location(self, agent, subject, relation="location"):
        """Answer where an agent should search from that agent's witnessed state."""
        comparison = self.compare_situational_perspective(agent, subject, relation)
        witnessed = comparison["last_witnessed"]
        return {"known": witnessed.get("known", False), "agent": agent,
                "subject": subject,
                "location": witnessed.get("value") if witnessed.get("known") else None,
                "perspective_status": comparison["status"],
                "reason": ("그 행위자가 마지막으로 직접 본 위치를 사용"
                           if witnessed.get("known") else witnessed.get("reason"))}
