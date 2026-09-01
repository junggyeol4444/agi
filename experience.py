"""Structured episodic experience memory independent from language strings."""


class ExperienceMemoryMixin:
    """Record and query events as actors, actions, objects, outcomes, and context."""

    def record_event(self, kind, actor=None, action=None, obj=None, outcome=None,
                     context=None, source="direct", confidence=1.0, metadata=None):
        if not isinstance(getattr(self, "events", None), list):
            self.events = []
        self.event_seq = int(getattr(self, "event_seq", 0)) + 1
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5
        event = {
            "id": self.event_seq, "kind": str(kind), "actor": actor,
            "action": action, "object": obj, "outcome": outcome,
            "context": context or {}, "source": source,
            "confidence": confidence, "at": getattr(self, "lived", 0),
            "metadata": metadata or {},
        }
        self.events.append(event)
        self.events = self.events[-5000:]
        return dict(event)

    def recall_events(self, kind=None, actor=None, action=None, obj=None,
                      context=None, limit=50):
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 50
        matches = []
        for event in reversed(getattr(self, "events", []) or []):
            if kind is not None and event.get("kind") != kind:
                continue
            if actor is not None and event.get("actor") != actor:
                continue
            if action is not None and event.get("action") != action:
                continue
            if obj is not None and event.get("object") != obj:
                continue
            event_context = event.get("context") or {}
            if context and not all(event_context.get(k) == v for k, v in context.items()):
                continue
            matches.append(dict(event))
            if len(matches) >= limit:
                break
        return matches
