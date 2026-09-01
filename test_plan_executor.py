import unittest

from plan_executor import PlanExecutionMixin
from metacognition import MetacognitionMixin
from planner import PlannerMixin
from world_model import WorldModelMixin


class ExecutionHost(PlanExecutionMixin, PlannerMixin, MetacognitionMixin,
                    WorldModelMixin):
    def __init__(self):
        self.transition_model = {}
        self.plans = []
        self.plan_runs = []
        self.calibration_records = []
        self.lived = 1


class PlanExecutorTests(unittest.TestCase):
    def test_executes_plan_until_goal(self):
        host = ExecutionHost()
        state = {"value": "room"}

        def observe():
            return dict(state)

        def perform(action):
            state["value"] = "hall" if action == "open" else "garden"
            return {"external_reward": 0.0}

        plan = {"actions": ["open", "walk"],
                "states": [{"value": "room"}, {"value": "hall"},
                           {"value": "garden"}],
                "goal": {"value": "garden"}, "max_depth": 3}
        run = host.execute_action_plan(plan, perform, observe, ["open", "walk"])

        self.assertEqual(run["status"], "completed")
        self.assertEqual([step["action"] for step in run["steps"]], ["open", "walk"])
        self.assertTrue(run["calibration"]["succeeded"])
        self.assertEqual(host.calibration_report("plan")["count"], 1)

    def test_deviation_updates_model_and_replans(self):
        host = ExecutionHost()
        host.learn_transition("detour", "walk", "goal", 0.0)
        state = "start"

        def observe():
            return state

        def perform(action):
            nonlocal state
            state = "detour" if state == "start" else "goal"
            return {}

        original = {"actions": ["open"], "states": ["start", "hall"],
                    "goal": "goal", "max_depth": 2}
        run = host.execute_action_plan(original, perform, observe, ["walk"])

        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["replans"], 1)
        learned = host.predict_effects("start", "open")
        self.assertEqual(learned["outcomes"][0]["state"], "detour")


if __name__ == "__main__":
    unittest.main()
