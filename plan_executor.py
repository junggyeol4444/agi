"""Execute learned plans, compare outcomes, and replan after deviations."""


class PlanExecutionMixin:
    """Close the loop between planning, action, observation, and model revision."""

    def execute_action_plan(self, plan, perform_action, observe_state, available_actions,
                            goal=None, max_replans=2, learn_observations=True):
        if not callable(perform_action) or not callable(observe_state):
            raise TypeError("perform_action and observe_state must be callable")
        try:
            max_replans = max(0, min(10, int(max_replans)))
        except (TypeError, ValueError):
            max_replans = 2
        goal = plan.get("goal") if goal is None else goal
        current_plan = dict(plan)
        run = {"goal": goal, "started_at": getattr(self, "lived", 0),
               "steps": [], "replans": 0, "status": "running"}
        while True:
            actions = list(current_plan.get("actions") or [])
            expected_states = list(current_plan.get("states") or [])
            if not actions:
                run["status"] = ("completed" if self._goal_reached(observe_state(), goal)
                                 else "blocked")
                break
            deviated = False
            for index, action in enumerate(actions):
                before = observe_state()
                result = perform_action(action)
                after = observe_state()
                reward = result.get("external_reward", result.get("reward", 0.0)) \
                    if isinstance(result, dict) else 0.0
                if learn_observations:
                    self.learn_transition(before, action, after, reward)
                expected = expected_states[index + 1] if index + 1 < len(expected_states) else None
                matched = expected is None or after == expected
                run["steps"].append({"action": action, "before": before,
                                     "expected": expected, "actual": after,
                                     "matched": matched, "result": result})
                if self._goal_reached(after, goal):
                    run["status"] = "completed"
                    deviated = False
                    break
                if not matched:
                    deviated = True
                    break
            if run["status"] == "completed":
                break
            if not deviated or run["replans"] >= max_replans:
                run["status"] = "deviated" if deviated else "incomplete"
                break
            run["replans"] += 1
            current_plan = self.plan_actions(
                observe_state(), goal, available_actions,
                max_depth=current_plan.get("max_depth", 3))
            run.setdefault("replacement_plans", []).append(current_plan)
            if current_plan.get("status") != "planned":
                run["status"] = "blocked"
                break
        run["finished_at"] = getattr(self, "lived", 0)
        if not isinstance(getattr(self, "plan_runs", None), list):
            self.plan_runs = []
        self.plan_runs.append(run)
        self.plan_runs = self.plan_runs[-200:]
        return run
