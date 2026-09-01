"""Compress repeated successful action sequences into reusable procedural skills."""

import json


class SkillLearningMixin:
    """Learn macro-actions from execution history rather than predefined scripts."""

    def _skill_key(self, start, goal, actions):
        payload = {"start": start, "goal": goal, "actions": list(actions)}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def observe_skill_run(self, run, min_successes=2):
        if not isinstance(getattr(self, "skills", None), dict):
            self.skills = {}
        # 우회·재계획·예상 불일치가 포함된 실행은 그대로 기술로 굳히지 않는다.
        if run.get("replans", 0) or any(not step.get("matched", True)
                                        for step in run.get("steps", [])):
            return None
        actions = [step.get("action") for step in run.get("steps", [])
                   if step.get("action")]
        if not actions:
            return None
        key = self._skill_key(run.get("start"), run.get("goal"), actions)
        skill = self.skills.setdefault(key, {
            "id": key, "start": run.get("start"), "goal": run.get("goal"),
            "actions": actions, "attempts": 0, "successes": 0,
            "status": "candidate", "created_at": getattr(self, "lived", 0),
        })
        skill["attempts"] += 1
        if run.get("status") == "completed":
            skill["successes"] += 1
        skill["success_rate"] = round(skill["successes"] / skill["attempts"], 4)
        skill["last_used_at"] = getattr(self, "lived", 0)
        if skill["successes"] >= min_successes and skill["success_rate"] >= 0.7:
            skill["status"] = "learned"
        elif skill["attempts"] >= min_successes and skill["success_rate"] < 0.5:
            skill["status"] = "unreliable"
        return dict(skill)

    def recall_skill(self, start, goal, min_success_rate=0.7):
        matches = []
        for skill in (getattr(self, "skills", {}) or {}).values():
            if skill.get("status") != "learned":
                continue
            if skill.get("start") != start or skill.get("goal") != goal:
                continue
            if skill.get("success_rate", 0.0) < min_success_rate:
                continue
            matches.append(skill)
        if not matches:
            return None
        best = max(matches, key=lambda skill: (skill.get("success_rate", 0),
                                               skill.get("successes", 0),
                                               -len(skill.get("actions", []))))
        return dict(best)
