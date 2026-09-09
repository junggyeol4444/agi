"""A small global-workspace cycle that coordinates learned cognitive subsystems."""


class CognitiveCycleMixin:
    """Select one mode of thought instead of running every mechanism on every input."""

    def _remember_focus(self, focus):
        if not isinstance(getattr(self, "working_memory", None), list):
            self.working_memory = []
        self.working_memory.append(focus)
        self.working_memory = self.working_memory[-20:]

    def _record_cognitive_cycle(self, cycle):
        if not isinstance(getattr(self, "cognitive_cycles", None), list):
            self.cognitive_cycles = []
        self.cognitive_seq = int(getattr(self, "cognitive_seq", 0)) + 1
        cycle["id"] = self.cognitive_seq
        self.cognitive_cycles.append(cycle)
        self.cognitive_cycles = self.cognitive_cycles[-500:]
        return cycle

    def _attention_value(self, kind):
        stats = (getattr(self, "attention_learning", {}) or {}).get(kind, {})
        return float(stats.get("usefulness", 0.5))

    def cognitive_cycle(self, observation=None, goal=None, question=None,
                        actions=None, modality="workspace", perception=None):
        """Attend, choose one reasoning mode, and leave an auditable trace."""
        actions = list(actions or [])
        candidates = []
        if perception is not None:
            candidates.append({
                "kind": "perception",
                "priority": 0.45 + 0.25 * self._attention_value("perception"),
                "reason": "새 감각 구조" if perception.get("created") else "익숙한 감각 구조",
                "data": perception,
            })
        elif isinstance(observation, dict) and observation:
            perception = self.observe_features(modality, observation, source="direct")
            candidates.append({
                "kind": "perception",
                "priority": ((0.45 if perception["created"] else 0.1)
                             + 0.25 * self._attention_value("perception")),
                "reason": "새 감각 구조" if perception["created"] else "익숙한 감각 구조",
                "data": perception,
            })

        if question:
            thought = self.deliberate(str(question))
            priority = ((0.75 if thought.get("action") in ("investigate", "verify") else 0.4)
                        + 0.25 * self._attention_value("question"))
            candidates.append({"kind": "question", "priority": priority,
                               "reason": "근거가 필요한 질문", "data": thought})

        if goal is not None:
            state = observation if observation is not None else getattr(self, "last_signal", None)
            plan = self.plan_actions(state, goal, actions, max_depth=3)
            candidates.append({"kind": "goal",
                               "priority": 0.65 + 0.25 * self._attention_value("goal"),
                               "reason": "명시된 목표를 위한 계획", "data": plan})

        queue = self.verification_queue(1) if hasattr(self, "verification_queue") else []
        if queue:
            candidates.append({"kind": "verification",
                               "priority": 0.6 + 0.25 * self._attention_value("verification"),
                               "reason": "해결되지 않은 믿음 충돌", "data": queue[0]})

        if not candidates:
            candidates.append({"kind": "idle", "priority": 0.1,
                               "reason": "주의를 요구하는 입력 없음", "data": None})
        candidates.sort(key=lambda item: (-item["priority"], item["kind"]))
        focus = candidates[0]
        self._remember_focus({"kind": focus["kind"], "reason": focus["reason"],
                              "at": getattr(self, "lived", 0)})

        if focus["kind"] in ("question", "verification"):
            mode = "verify" if focus["data"].get("action") == "verify" else "reason"
        elif focus["kind"] == "goal":
            mode = "plan"
        elif focus["kind"] == "perception":
            mode = "learn" if focus["data"]["created"] else "recognize"
        else:
            mode = "rest"
        cycle = {
            "at": getattr(self, "lived", 0), "mode": mode, "focus": focus,
            "alternatives": candidates[1:], "perception": perception,
            "working_memory_size": len(self.working_memory),
        }
        return self._record_cognitive_cycle(cycle)

    def record_cognitive_outcome(self, cycle_id, useful, reason=None):
        """Learn which kinds of attention were useful from later observed outcomes."""
        cycle = next((item for item in reversed(getattr(self, "cognitive_cycles", []) or [])
                      if item.get("id") == cycle_id), None)
        if cycle is None:
            return {"updated": False, "reason": "사고 주기를 찾을 수 없음"}
        if not isinstance(getattr(self, "attention_learning", None), dict):
            self.attention_learning = {}
        kind = cycle["focus"]["kind"]
        stats = self.attention_learning.setdefault(
            kind, {"attempts": 0, "useful": 0, "usefulness": 0.5})
        stats["attempts"] += 1
        if bool(useful):
            stats["useful"] += 1
        stats["usefulness"] = round(stats["useful"] / stats["attempts"], 6)
        cycle["outcome"] = {"useful": bool(useful), "reason": reason}
        return {"updated": True, "focus_kind": kind, "stats": dict(stats)}
