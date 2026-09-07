"""Learn action effects from interventions instead of temporal coincidence."""

import json


class InterventionLearningMixin:
    """Compare intentional actions under the same context before claiming effects."""

    def _intervention_key(self, value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def record_intervention(self, context, action, outcome):
        """Record one deliberate action; passive sequence observations do not enter here."""
        if not isinstance(getattr(self, "intervention_trials", None), dict):
            self.intervention_trials = {}
        context_key = self._intervention_key(context)
        action_key = str(action)
        outcome_key = self._intervention_key(outcome)
        context_entry = self.intervention_trials.setdefault(
            context_key, {"context": context, "actions": {}})
        action_entry = context_entry["actions"].setdefault(
            action_key, {"action": action, "trials": 0, "outcomes": {}})
        outcome_entry = action_entry["outcomes"].setdefault(
            outcome_key, {"outcome": outcome, "count": 0})
        outcome_entry["count"] += 1
        action_entry["trials"] += 1
        return self.intervention_effect(context, action)

    def intervention_effect(self, context, action, min_trials=2):
        """Contrast an action with other actions tried in the same context."""
        context_entry = (getattr(self, "intervention_trials", {}) or {}).get(
            self._intervention_key(context))
        action_entry = ((context_entry or {}).get("actions", {}) or {}).get(str(action))
        if not action_entry:
            return {"known": False, "reason": "이 행동을 개입으로 시험한 적 없음",
                    "context": context, "action": action}

        alternatives = [entry for key, entry in context_entry["actions"].items()
                        if key != str(action)]
        action_trials = action_entry["trials"]
        baseline_trials = sum(entry["trials"] for entry in alternatives)
        if action_trials < min_trials or baseline_trials < min_trials:
            return {"known": False, "reason": "같은 조건의 개입과 비교 행동이 더 필요함",
                    "context": context, "action": action,
                    "action_trials": action_trials,
                    "baseline_trials": baseline_trials}

        baseline_counts = {}
        baseline_values = {}
        for entry in alternatives:
            for key, outcome in entry["outcomes"].items():
                baseline_counts[key] = baseline_counts.get(key, 0) + outcome["count"]
                baseline_values[key] = outcome["outcome"]
        action_counts = {key: item["count"]
                         for key, item in action_entry["outcomes"].items()}
        outcome_values = {key: item["outcome"]
                          for key, item in action_entry["outcomes"].items()}
        outcome_values.update(baseline_values)
        effects = []
        for key in set(action_counts) | set(baseline_counts):
            with_action = action_counts.get(key, 0) / action_trials
            without_action = baseline_counts.get(key, 0) / baseline_trials
            effects.append({
                "outcome": outcome_values[key],
                "with_action": round(with_action, 6),
                "with_alternatives": round(without_action, 6),
                "difference": round(with_action - without_action, 6),
            })
        effects.sort(key=lambda item: (-abs(item["difference"]),
                                       self._intervention_key(item["outcome"])))
        return {"known": True, "context": context, "action": action,
                "action_trials": action_trials, "baseline_trials": baseline_trials,
                "effects": effects,
                "strongest_effect": effects[0] if effects else None}

    def propose_intervention(self, context, actions, min_trials=2):
        """Choose the least-tested comparison needed to distinguish action effects."""
        context_entry = (getattr(self, "intervention_trials", {}) or {}).get(
            self._intervention_key(context), {"actions": {}})
        candidates = []
        for action in actions:
            trials = context_entry["actions"].get(str(action), {}).get("trials", 0)
            if trials < min_trials:
                candidates.append({"action": action, "trials": trials,
                                   "needed": min_trials - trials})
        candidates.sort(key=lambda item: (item["trials"], str(item["action"])))
        return {"context": context, "complete": not candidates,
                "next_action": candidates[0]["action"] if candidates else None,
                "comparisons_needed": candidates,
                "reason": ("같은 조건에서 비교 행동을 반복해 우연과 행동 효과를 구분"
                           if candidates else "모든 비교 행동의 최소 반복을 충족")}
