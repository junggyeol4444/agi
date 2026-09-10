"""Small experience-driven action/outcome world model."""

import json


class WorldModelMixin:
    """Learn state-action effects without using next-token language generation."""

    def _state_key(self, state):
        return json.dumps(state, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def learn_transition(self, state, action, next_state, reward=0.0):
        if not isinstance(getattr(self, "transition_model", None), dict):
            self.transition_model = {}
        key = f"{self._state_key(state)}\u241f{action}"
        entry = self.transition_model.setdefault(key, {
            "state": state, "action": action, "count": 0,
            "outcomes": {}, "reward_sum": 0.0,
        })
        outcome_key = self._state_key(next_state)
        outcome = entry["outcomes"].setdefault(
            outcome_key, {"state": next_state, "count": 0})
        outcome["count"] += 1
        entry["count"] += 1
        entry["reward_sum"] += float(reward)
        return self.predict_effects(state, action)

    def predict_effects(self, state, action):
        """Recall learned action effects only when planning or checking an action."""
        key = f"{self._state_key(state)}\u241f{action}"
        entry = (getattr(self, "transition_model", {}) or {}).get(key)
        if not entry or not entry.get("count"):
            return {"known": False, "state": state, "action": action,
                    "outcomes": [], "uncertainty": 1.0}
        total = entry["count"]
        outcomes = [{"state": item["state"],
                     "probability": round(item["count"] / total, 4),
                     "observations": item["count"]}
                    for item in entry["outcomes"].values()]
        outcomes.sort(key=lambda item: -item["probability"])
        return {"known": True, "state": state, "action": action,
                "observations": total, "outcomes": outcomes,
                "expected_reward": round(entry["reward_sum"] / total, 4),
                "uncertainty": round(1.0 - outcomes[0]["probability"], 4)}
