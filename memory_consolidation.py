"""Incrementally compress episodes into reusable semantic regularities."""

import json


class MemoryConsolidationMixin:
    """Extract recurring event rules while preserving conflicting exceptions."""

    def _semantic_key(self, event):
        identity = {
            "kind": event.get("kind"), "actor": event.get("actor"),
            "action": event.get("action"), "object": event.get("object"),
            "context": event.get("context") or {},
        }
        return json.dumps(identity, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def absorb_episode(self, event):
        """Update only the semantic entry related to one new episode."""
        if not isinstance(getattr(self, "semantic_memory", None), dict):
            self.semantic_memory = {}
        key = self._semantic_key(event)
        entry = self.semantic_memory.setdefault(key, {
            "pattern": {name: event.get(name) for name in
                        ("kind", "actor", "action", "object")},
            "context": event.get("context") or {}, "observations": 0,
            "outcomes": {}, "example_event_ids": [], "status": "candidate",
        })
        outcome_key = json.dumps(event.get("outcome"), ensure_ascii=False,
                                 sort_keys=True, separators=(",", ":"), default=str)
        outcome = entry["outcomes"].setdefault(
            outcome_key, {"value": event.get("outcome"), "count": 0})
        outcome["count"] += 1
        entry["observations"] += 1
        if event.get("id") is not None:
            entry["example_event_ids"].append(event["id"])
            entry["example_event_ids"] = entry["example_event_ids"][-20:]
        dominant = max(entry["outcomes"].values(), key=lambda item: item["count"])
        entry["dominant_outcome"] = dominant["value"]
        entry["reliability"] = round(dominant["count"] / entry["observations"], 6)
        if entry["observations"] >= 3 and entry["reliability"] >= 0.8:
            entry["status"] = "regularity"
        elif len(entry["outcomes"]) > 1:
            entry["status"] = "variable"
        entry["updated_at"] = getattr(self, "lived", 0)
        return dict(entry)

    def semantic_recall(self, kind=None, actor=None, action=None, obj=None,
                        context=None, reliable_only=False, limit=50):
        """Recall compressed regularities instead of replaying all raw episodes."""
        context = context or {}
        matches = []
        for entry in (getattr(self, "semantic_memory", {}) or {}).values():
            pattern = entry.get("pattern", {})
            if kind is not None and pattern.get("kind") != kind:
                continue
            if actor is not None and pattern.get("actor") != actor:
                continue
            if action is not None and pattern.get("action") != action:
                continue
            if obj is not None and pattern.get("object") != obj:
                continue
            if context and not all(entry.get("context", {}).get(k) == v
                                   for k, v in context.items()):
                continue
            if reliable_only and entry.get("status") != "regularity":
                continue
            matches.append(dict(entry))
        matches.sort(key=lambda item: (-item.get("reliability", 0.0),
                                       -item.get("observations", 0)))
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 50
        return matches[:limit]

    def consolidate_memory(self, min_observations=3):
        """Report stable rules and unresolved exceptions without erasing episodes."""
        try:
            minimum = max(1, int(min_observations))
        except (TypeError, ValueError):
            minimum = 3
        entries = list((getattr(self, "semantic_memory", {}) or {}).values())
        stable = [dict(item) for item in entries
                  if item.get("observations", 0) >= minimum
                  and item.get("status") == "regularity"]
        variable = [dict(item) for item in entries
                    if item.get("observations", 0) >= minimum
                    and item.get("status") == "variable"]
        return {"stable": stable, "variable": variable,
                "episodes": len(getattr(self, "events", []) or []),
                "semantic_patterns": len(entries)}
