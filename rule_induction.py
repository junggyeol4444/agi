"""Induce reusable rules by comparing structured experiences across contexts."""

import json


class RuleInductionMixin:
    """Generalize only what remains common across multiple direct experiences."""

    def _rule_key(self, event):
        pattern = {name: event.get(name) for name in
                   ("kind", "actor", "action", "object")}
        return json.dumps(pattern, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def _rule_value_key(self, value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def absorb_abstraction(self, event):
        """Update one abstract rule candidate from one structured event."""
        if not isinstance(getattr(self, "abstract_rules", None), dict):
            self.abstract_rules = {}
        key = self._rule_key(event)
        entry = self.abstract_rules.setdefault(key, {
            "pattern": {name: event.get(name) for name in
                        ("kind", "actor", "action", "object")},
            "observations": 0, "contexts": [], "common_context": None,
            "outcomes": {}, "supporting_event_ids": [], "status": "candidate",
            "direct_observations": 0,
        })
        context = event.get("context") or {}
        if entry["common_context"] is None:
            entry["common_context"] = dict(context)
        else:
            entry["common_context"] = {
                name: value for name, value in entry["common_context"].items()
                if name in context and context[name] == value
            }
        context_key = self._rule_value_key(context)
        if all(item["key"] != context_key for item in entry["contexts"]):
            entry["contexts"].append({"key": context_key, "value": context})
            entry["contexts"] = entry["contexts"][-50:]
        outcome_key = self._rule_value_key(event.get("outcome"))
        outcome = entry["outcomes"].setdefault(
            outcome_key, {"value": event.get("outcome"), "count": 0})
        outcome["count"] += 1
        entry["observations"] += 1
        if event.get("source") in ("direct", "experiment"):
            entry["direct_observations"] = entry.get("direct_observations", 0) + 1
        if event.get("id") is not None:
            entry["supporting_event_ids"].append(event["id"])
            entry["supporting_event_ids"] = entry["supporting_event_ids"][-50:]

        dominant = max(entry["outcomes"].values(), key=lambda item: item["count"])
        entry["conclusion"] = dominant["value"]
        entry["reliability"] = round(dominant["count"] / entry["observations"], 6)
        distinct_contexts = len(entry["contexts"])
        if (entry.get("direct_observations", 0) >= 3 and distinct_contexts >= 2
                and entry["reliability"] >= 0.8):
            entry["status"] = "general_rule"
        elif len(entry["outcomes"]) > 1:
            entry["status"] = "variable"
        else:
            entry["status"] = "candidate"
        entry["updated_at"] = getattr(self, "lived", 0)
        return self._public_rule(entry)

    def _public_rule(self, entry):
        result = dict(entry)
        result["distinct_contexts"] = len(entry.get("contexts", []))
        return result

    def induced_rules(self, action=None, obj=None, general_only=False, limit=50):
        """Return learned rules, including variability rather than hiding exceptions."""
        rules = []
        for entry in (getattr(self, "abstract_rules", {}) or {}).values():
            pattern = entry.get("pattern", {})
            if action is not None and pattern.get("action") != action:
                continue
            if obj is not None and pattern.get("object") != obj:
                continue
            if general_only and entry.get("status") != "general_rule":
                continue
            rules.append(self._public_rule(entry))
        rules.sort(key=lambda item: (-item.get("reliability", 0.0),
                                     -item.get("observations", 0)))
        try:
            size = max(0, int(limit))
        except (TypeError, ValueError):
            size = 50
        return rules[:size]
