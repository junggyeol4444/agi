"""Translate self-discovered learning goals into grounded next steps."""


class GoalExecutionMixin:
    """Plan developmental work without fabricating observations or completion."""

    def plan_developmental_goal(self, goal_id, actions=None):
        goal = (getattr(self, "developmental_goals", {}) or {}).get(goal_id)
        if not goal:
            return {"found": False, "reason": "목표를 찾을 수 없음"}
        if goal.get("status") == "completed":
            return {"found": True, "complete": True, "goal": dict(goal), "steps": []}
        kind, target = goal.get("kind"), goal.get("target")
        if kind == "stabilize_concept":
            concept = (getattr(self, "induced_concepts", {}) or {}).get(target)
            if not concept:
                return {"found": False, "reason": "개념 기억이 사라짐", "goal": dict(goal)}
            needed = max(0, 3 - int(concept.get("observations", 0)))
            steps = [{"operation": "seek_varied_observation", "concept_id": target,
                      "modality": concept.get("modality"),
                      "avoid_exact_repetition": True, "needed": needed}]
        elif kind == "explain_exception":
            rule = (getattr(self, "abstract_rules", {}) or {}).get(target)
            if not rule:
                return {"found": False, "reason": "규칙 기억이 사라짐", "goal": dict(goal)}
            steps = [{"operation": "compare_exception_contexts",
                      "action": rule.get("pattern", {}).get("action"),
                      "contexts": [item.get("value") for item in rule.get("contexts", [])],
                      "outcomes": [item.get("value") for item in rule.get("outcomes", {}).values()]}]
        elif kind == "verify_belief":
            target = target or {}
            plan = self.make_verification_plan(target.get("subject", ""),
                                               target.get("relation", "is_a"))
            steps = plan.get("steps", [])
        else:
            return {"found": False, "reason": "지원하지 않는 목표 종류", "goal": dict(goal)}
        return {"found": True, "complete": False, "goal": dict(goal),
                "steps": steps, "actions_available": list(actions or [])}

    def advance_developmental_goal(self, goal_id, evidence_provider=None):
        """Run verifiable work when possible; otherwise return the needed real-world step."""
        plan = self.plan_developmental_goal(goal_id)
        if not plan.get("found") or plan.get("complete"):
            return plan
        goal = plan["goal"]
        if goal.get("kind") == "verify_belief" and evidence_provider is not None:
            target = goal.get("target") or {}
            run = self.execute_verification(
                target.get("subject", ""), target.get("relation", "is_a"),
                evidence_provider=evidence_provider)
            completed = self.refresh_developmental_goals()
            return {"found": True, "executed": True, "run": run,
                    "completed": [item["id"] for item in completed], "plan": plan}
        return {"found": True, "executed": False,
                "reason": "실제 관찰 또는 실험 결과가 필요함", "plan": plan}
