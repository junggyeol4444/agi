"""Discover epistemic goals from the agent's own unresolved experience."""

import json


class GoalDiscoveryMixin:
    """Turn knowledge gaps into persistent goals without a scripted reward target."""

    def _developmental_goal_id(self, kind, target):
        payload = json.dumps(target, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str)
        return f"{kind}:{payload}"

    def _upsert_developmental_goal(self, kind, target, reason, gap):
        if not isinstance(getattr(self, "developmental_goals", None), dict):
            self.developmental_goals = {}
        goal_id = self._developmental_goal_id(kind, target)
        goal = self.developmental_goals.setdefault(goal_id, {
            "id": goal_id, "kind": kind, "target": target, "reason": reason,
            "created_at": getattr(self, "lived", 0), "attempts": 0,
            "status": "open", "history": [],
        })
        if goal.get("status") != "completed":
            goal["status"] = "open"
        goal["knowledge_gap"] = round(max(0.0, min(1.0, float(gap))), 6)
        goal["updated_at"] = getattr(self, "lived", 0)
        return goal

    def discover_goals(self):
        """Refresh goals from weak concepts, variable rules, and belief conflicts."""
        discovered = []
        for concept in (getattr(self, "induced_concepts", {}) or {}).values():
            observations = int(concept.get("observations", 0))
            if observations < 3:
                discovered.append(self._upsert_developmental_goal(
                    "stabilize_concept", concept.get("id"),
                    "새 개념을 다른 경험에서도 다시 확인", (3 - observations) / 3))
        for key, rule in (getattr(self, "abstract_rules", {}) or {}).items():
            if rule.get("status") == "variable":
                discovered.append(self._upsert_developmental_goal(
                    "explain_exception", key, "같은 행동의 다른 결과를 설명",
                    1.0 - float(rule.get("reliability", 0.0))))
        for task in (getattr(self, "verification_tasks", {}) or {}).values():
            if task.get("status") not in ("resolved", "completed"):
                target = {"subject": task.get("subject"),
                          "relation": task.get("relation", "is_a")}
                discovered.append(self._upsert_developmental_goal(
                    "verify_belief", target, "충돌하거나 부족한 근거를 확인", 1.0))
        return [dict(goal) for goal in discovered]

    def select_developmental_goal(self):
        self.discover_goals()
        goals = [goal for goal in (getattr(self, "developmental_goals", {}) or {}).values()
                 if goal.get("status") == "open"]
        if not goals:
            return None
        # 지식 공백은 크게, 반복 실패 비용은 작게 반영한다.
        def score(goal):
            return float(goal.get("knowledge_gap", 0.0)) / (1 + goal.get("attempts", 0))
        chosen = max(goals, key=lambda goal: (score(goal), -goal.get("created_at", 0),
                                              goal.get("id", "")))
        result = dict(chosen)
        result["priority"] = round(score(chosen), 6)
        return result

    def record_goal_attempt(self, goal_id, progress=False, evidence=None):
        goal = (getattr(self, "developmental_goals", {}) or {}).get(goal_id)
        if not goal:
            return {"updated": False, "reason": "목표를 찾을 수 없음"}
        goal["attempts"] += 1
        goal["history"].append({"at": getattr(self, "lived", 0),
                                "progress": bool(progress), "evidence": evidence})
        goal["history"] = goal["history"][-50:]
        if progress:
            goal["knowledge_gap"] = round(max(0.0, goal["knowledge_gap"] - 0.5), 6)
        if goal["knowledge_gap"] <= 0.0:
            goal["status"] = "completed"
            goal["completed_at"] = getattr(self, "lived", 0)
        return {"updated": True, "goal": dict(goal)}
