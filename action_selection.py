"""Resource-light action selection from learned effects and intrinsic information value."""

import math


class ActionSelectionMixin:
    """Choose actions from experience rather than an environment answer table."""

    def evaluate_actions(self, state, actions, action_costs=None, risk_weight=0.25):
        action_costs = action_costs or {}
        evaluations = []
        for action in actions:
            model = self.predict_effects(state, action)
            observations = int(model.get("observations", 0))
            if model.get("known"):
                information_value = model["uncertainty"] + 1.0 / math.sqrt(observations + 1)
                expected_value = float(model.get("expected_reward", 0.0))
                risk = float(model.get("uncertainty", 1.0))
            else:
                information_value = 1.0
                expected_value = 0.0
                risk = 1.0
            cost = max(0.0, float(action_costs.get(action, 0.0)))
            score = expected_value + information_value - risk_weight * risk - cost
            evaluations.append({
                "action": action, "score": round(score, 6),
                "expected_value": round(expected_value, 6),
                "information_value": round(information_value, 6),
                "risk": round(risk, 6), "cost": round(cost, 6),
                "observations": observations, "known": bool(model.get("known")),
            })
        return sorted(evaluations, key=lambda item: (-item["score"], item["action"]))

    def select_action(self, state, actions, action_costs=None, risk_weight=0.25):
        evaluations = self.evaluate_actions(state, actions, action_costs, risk_weight)
        if not evaluations:
            return {"action": None, "reason": "가능한 행동 없음", "evaluations": []}
        best_score = evaluations[0]["score"]
        tied = [item for item in evaluations if item["score"] == best_score]
        rng = getattr(getattr(self, "world", None), "rng", None)
        chosen = rng.choice(tied) if rng and len(tied) > 1 else tied[0]
        reason = ("아직 모르는 행동의 결과를 알아보기 위해 선택"
                  if not chosen["known"] else
                  "경험한 결과·정보가치·위험·비용을 비교해 선택")
        decision = {"action": chosen["action"], "reason": reason,
                    "chosen": dict(chosen), "evaluations": evaluations,
                    "at": getattr(self, "lived", 0)}
        if not isinstance(getattr(self, "action_decisions", None), list):
            self.action_decisions = []
        self.action_decisions.append(decision)
        self.action_decisions = self.action_decisions[-500:]
        return decision
