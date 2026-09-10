"""Execution loop for turning verification plans into recorded evidence."""


class VerificationExecutorMixin:
    """Execute queued verification work through an injected evidence provider.

    The provider receives one task and returns observation dictionaries accepted by
    ``observe_belief``.  Keeping acquisition injectable separates reasoning from web,
    sensors, experiments, or a human teacher.
    """

    def execute_verification(self, evidence_provider, limit=1):
        if not callable(evidence_provider):
            raise TypeError("evidence_provider must be callable")
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 1
        if not isinstance(getattr(self, "verification_runs", None), list):
            self.verification_runs = []
        results = []
        for task in self.verification_queue(limit=limit):
            task_id = task["id"]
            stored = self.verification_tasks.get(task_id, task)
            stored["status"] = "running"
            run = {"task_id": task_id, "subject": task["subject"],
                   "started_at": self.lived, "observations": 0}
            try:
                observations = evidence_provider(dict(task)) or []
                if isinstance(observations, dict):
                    observations = [observations]
                for observation in observations:
                    if not isinstance(observation, dict) or not observation.get("object"):
                        continue
                    self.observe_belief(
                        task["subject"], task.get("relation", "is_a"),
                        observation["object"], source=observation.get("source"),
                        supports=observation.get("supports", True),
                        evidence=observation.get("evidence"),
                        kind=observation.get("kind", "testimony"),
                        reliability=observation.get("reliability", 1.0),
                        context=observation.get("context", task.get("context")),
                        evidence_id=observation.get("evidence_id"),
                        independence_group=observation.get("independence_group"),
                    )
                    run["observations"] += 1
                verdict = self.verify_belief(
                    task["subject"], task.get("relation", "is_a"),
                    context=task.get("context") or None,
                )
                run["verdict"] = verdict
                if not verdict.get("verified") and stored.get("status") == "running":
                    stored["status"] = "open" if run["observations"] else "blocked"
                stored["last_run_at"] = self.lived
                stored["attempts"] = stored.get("attempts", 0) + 1
            except Exception as exc:
                stored["status"] = "blocked"
                stored["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
                run["error"] = stored["last_error"]
            run["finished_at"] = self.lived
            self.verification_runs.append(run)
            results.append(run)
        self.verification_runs = self.verification_runs[-200:]
        return results
