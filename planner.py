"""Bounded multi-step planning over learned world-model transitions."""


class PlannerMixin:
    """Search short action sequences without a hard-coded solution path."""

    def _goal_reached(self, state, goal):
        if callable(goal):
            return bool(goal(state))
        if isinstance(goal, dict) and isinstance(state, dict):
            return all(state.get(key) == value for key, value in goal.items())
        return state == goal

    def plan_actions(self, state, goal, actions, max_depth=3, beam_width=20,
                     action_costs=None):
        action_costs = action_costs or {}
        max_depth = max(0, min(8, int(max_depth)))
        beam_width = max(1, min(200, int(beam_width)))
        if self._goal_reached(state, goal):
            return {"status": "achieved", "actions": [], "states": [state],
                    "confidence": 1.0, "reason": "이미 목표 상태"}
        frontier = [{"state": state, "actions": [], "states": [state],
                     "confidence": 1.0, "value": 0.0, "cost": 0.0}]
        best = None
        visited = set()
        for _ in range(max_depth):
            expanded = []
            for node in frontier:
                for action in actions:
                    model = self.predict_effects(node["state"], action)
                    if not model.get("known"):
                        continue
                    for outcome in model.get("outcomes", []):
                        next_state = outcome["state"]
                        confidence = node["confidence"] * outcome["probability"]
                        step_cost = max(0.0, float(action_costs.get(action, 0)))
                        cost = node["cost"] + step_cost
                        value = node["value"] + float(model.get("expected_reward", 0)) - step_cost
                        child = {"state": next_state,
                                 "actions": node["actions"] + [action],
                                 "states": node["states"] + [next_state],
                                 "confidence": confidence, "value": value,
                                 "cost": cost}
                        if self._goal_reached(next_state, goal):
                            if best is None or (confidence, value) > (best["confidence"], best["value"]):
                                best = child
                        marker = (self._state_key(next_state), len(child["actions"]))
                        if marker not in visited:
                            visited.add(marker)
                            expanded.append(child)
            if best is not None:
                break
            expanded.sort(key=lambda node: (-node["confidence"], -node["value"],
                                            node["cost"], len(node["actions"])))
            frontier = expanded[:beam_width]
            if not frontier:
                break
        if best is None:
            result = {"status": "insufficient_model", "actions": [],
                      "states": [state], "confidence": 0.0,
                      "reason": "경험한 전이만으로 목표까지 이어지는 경로를 찾지 못함"}
        else:
            result = {"status": "planned", "actions": best["actions"],
                      "states": best["states"],
                      "confidence": round(best["confidence"], 6),
                      "expected_value": round(best["value"], 6),
                      "cost": round(best["cost"], 6),
                      "reason": "학습한 행동 결과를 여러 단계 연결함"}
        stored_goal = ({"predicate": getattr(goal, "__name__", "callable")}
                       if callable(goal) else goal)
        result.update({"start": state, "goal": stored_goal, "max_depth": max_depth,
                       "at": getattr(self, "lived", 0)})
        if not isinstance(getattr(self, "plans", None), list):
            self.plans = []
        self.plans.append(result)
        self.plans = self.plans[-300:]
        return result
