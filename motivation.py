"""Intrinsic learning signals derived from the agent's own experience."""


class IntrinsicMotivationMixin:
    """Create learning pressure without encoding a correct action lookup table."""

    DEFAULT_DRIVE_WEIGHTS = {
        "novelty": 0.45,
        "uncertainty_reduction": 0.35,
        "goal_progress": 0.20,
    }

    def intrinsic_motivation(self, novelty=0.0, uncertainty_before=1.0,
                             uncertainty_after=1.0, goal_progress=0.0):
        weights = dict(self.DEFAULT_DRIVE_WEIGHTS)
        weights.update(getattr(self, "drive_weights", {}) or {})
        components = {
            "novelty": max(0.0, min(1.0, float(novelty))),
            "uncertainty_reduction": max(
                0.0, min(1.0, float(uncertainty_before) - float(uncertainty_after))),
            "goal_progress": max(-1.0, min(1.0, float(goal_progress))),
        }
        total = sum(weights[name] * value for name, value in components.items())
        return {"total": round(total, 6), "components": components,
                "weights": weights}
