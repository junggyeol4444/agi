"""Compress repeated successful action sequences into reusable procedural skills."""

import json


class SkillLearningMixin:
    """Learn macro-actions from execution history rather than predefined scripts."""

    def _skill_key(self, start, goal, actions):
        # 시작 상태는 여러 성공 사례에서 공통 적용 조건으로 학습한다.
        payload = {"goal": goal, "actions": list(actions)}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def _derive_preconditions(self, examples):
        if not examples:
            return None
        if all(isinstance(example, dict) for example in examples):
            common = dict(examples[0])
            for example in examples[1:]:
                common = {key: value for key, value in common.items()
                          if key in example and example[key] == value}
            if common:
                return {"kind": "mapping", "required": common}
            return {"kind": "examples", "required": list(examples)}
        first = examples[0]
        if all(example == first for example in examples):
            return {"kind": "exact", "required": first}
        return {"kind": "examples", "required": list(examples)}

    def _preconditions_match(self, preconditions, state):
        if not preconditions:
            return False
        kind = preconditions.get("kind")
        required = preconditions.get("required")
        if kind == "mapping" and isinstance(state, dict):
            return all(state.get(key) == value for key, value in required.items())
        if kind == "exact":
            return state == required
        return state in (required or [])

    def observe_skill_run(self, run, min_successes=2):
        if not isinstance(getattr(self, "skills", None), dict):
            self.skills = {}
        existing_id = run.get("skill_id")
        if existing_id and run.get("status") != "completed":
            return self.record_skill_failure(existing_id, run.get("start"))
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
            "start_examples": [], "excluded_states": [],
            "status": "candidate", "created_at": getattr(self, "lived", 0),
        })
        skill["attempts"] += 1
        if run.get("status") == "completed":
            skill["successes"] += 1
            if run.get("start") not in skill["start_examples"]:
                skill["start_examples"].append(run.get("start"))
                skill["start_examples"] = skill["start_examples"][-50:]
            skill["preconditions"] = self._derive_preconditions(skill["start_examples"])
        skill["success_rate"] = round(skill["successes"] / skill["attempts"], 4)
        skill["last_used_at"] = getattr(self, "lived", 0)
        if skill["successes"] >= min_successes and skill["success_rate"] >= 0.7:
            skill["status"] = "learned"
        elif skill["attempts"] >= min_successes and skill["success_rate"] < 0.5:
            skill["status"] = "unreliable"
        return dict(skill)

    def record_skill_failure(self, skill_id, state):
        skill = (getattr(self, "skills", {}) or {}).get(skill_id)
        if not skill:
            return None
        skill["attempts"] += 1
        skill["success_rate"] = round(skill["successes"] / skill["attempts"], 4)
        if state not in skill.setdefault("excluded_states", []):
            skill["excluded_states"].append(state)
            skill["excluded_states"] = skill["excluded_states"][-50:]
        if skill["success_rate"] < 0.7:
            skill["status"] = "unreliable"
        return dict(skill)

    def recall_skill(self, start, goal, min_success_rate=0.7):
        matches = []
        for skill in (getattr(self, "skills", {}) or {}).values():
            if skill.get("status") != "learned":
                continue
            if skill.get("goal") != goal:
                continue
            if start in skill.get("excluded_states", []):
                continue
            if not self._preconditions_match(skill.get("preconditions"), start):
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
