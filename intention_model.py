"""Infer tentative agent goals from repeated, observed state-changing actions."""

import json


class IntentionModelMixin:
    """Keep inferred intentions as revisable hypotheses, not observed facts."""

    def _intention_value_key(self, value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def observe_agent_action(self, agent, action, before, after, context=None,
                             event_id=None):
        if not isinstance(getattr(self, "intention_models", None), dict):
            self.intention_models = {}
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        changes = {key: value for key, value in after.items()
                   if key not in before or before[key] != value}
        record = self.intention_models.setdefault(str(agent), {
            "observations": 0, "outcomes": {}, "actions": {}, "history": []})
        record["observations"] += 1
        record["actions"][str(action)] = record["actions"].get(str(action), 0) + 1
        for attribute, value in changes.items():
            key = f"{attribute}\u241f{self._intention_value_key(value)}"
            outcome = record["outcomes"].setdefault(
                key, {"attribute": attribute, "value": value, "count": 0,
                      "actions": {}, "contexts": []})
            outcome["count"] += 1
            outcome["actions"][str(action)] = outcome["actions"].get(str(action), 0) + 1
            context_key = self._intention_value_key(context or {})
            if context_key not in outcome["contexts"]:
                outcome["contexts"].append(context_key)
                outcome["contexts"] = outcome["contexts"][-50:]
        record["history"].append({"at": getattr(self, "lived", 0), "action": action,
                                  "changes": changes, "context": context or {},
                                  "event_id": event_id})
        record["history"] = record["history"][-100:]
        return self.infer_agent_intention(agent)

    def infer_agent_intention(self, agent, min_observations=3, min_share=0.7):
        record = (getattr(self, "intention_models", {}) or {}).get(str(agent))
        if not record:
            return {"inferred": False, "agent": agent, "reason": "관찰한 행동 없음",
                    "candidates": []}
        total = max(1, record["observations"])
        candidates = []
        for outcome in record["outcomes"].values():
            candidates.append({
                "goal": {"attribute": outcome["attribute"], "value": outcome["value"]},
                "support": outcome["count"], "share": round(outcome["count"] / total, 6),
                "distinct_actions": len(outcome["actions"]),
                "distinct_contexts": len(outcome["contexts"]),
            })
        candidates.sort(key=lambda item: (-item["share"], -item["support"],
                                          self._intention_value_key(item["goal"])))
        best = candidates[0] if candidates else None
        second_share = candidates[1]["share"] if len(candidates) > 1 else 0.0
        inferred = bool(best and record["observations"] >= min_observations
                        and best["share"] >= min_share
                        and best["share"] > second_share)
        return {"inferred": inferred, "agent": agent,
                "goal_hypothesis": best["goal"] if inferred else None,
                "confidence": best["share"] if inferred else 0.0,
                "observations": record["observations"], "candidates": candidates,
                "reason": ("여러 행동 뒤 반복해서 만들어진 상태를 목표 후보로 추론"
                           if inferred else "행동 결과가 부족하거나 여러 목표 후보가 경쟁함"),
                "warning": "행동 결과로 추론한 가설이며 행위자가 직접 밝힌 의도는 아님"}

    def stated_intention(self, agent, goal, source=None):
        """Store stated intent separately; testimony does not overwrite behavioral inference."""
        if not isinstance(getattr(self, "stated_intentions", None), list):
            self.stated_intentions = []
        entry = {"agent": str(agent), "goal": goal, "source": source,
                 "at": getattr(self, "lived", 0)}
        self.stated_intentions.append(entry)
        self.stated_intentions = self.stated_intentions[-200:]
        return entry

    def compare_stated_and_inferred_intention(self, agent):
        inferred = self.infer_agent_intention(agent)
        stated = next((item for item in reversed(getattr(self, "stated_intentions", []) or [])
                       if item.get("agent") == str(agent)), None)
        if not stated or not inferred["inferred"]:
            status = "unknown"
        elif stated["goal"] == inferred["goal_hypothesis"]:
            status = "consistent"
        else:
            status = "different"
        return {"agent": agent, "status": status, "stated": stated,
                "inferred": inferred,
                "note": "다르다는 사실만으로 기만을 판정하지 않음"}
