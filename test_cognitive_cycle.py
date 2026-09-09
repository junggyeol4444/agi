import unittest

from cognitive_cycle import CognitiveCycleMixin
from concept_learning import ConceptLearningMixin


class CognitiveHost(CognitiveCycleMixin, ConceptLearningMixin):
    def __init__(self):
        self.induced_concepts = {}
        self.concept_seq = 0
        self.working_memory = []
        self.cognitive_cycles = []
        self.lived = 1

    def deliberate(self, question):
        return {"action": "investigate", "subject": question}

    def plan_actions(self, state, goal, actions, max_depth=3):
        return {"found": True, "state": state, "goal": goal, "actions": actions}

    def verification_queue(self, limit=1):
        return []


class CognitiveCycleTests(unittest.TestCase):
    def test_question_takes_attention_over_novel_perception(self):
        host = CognitiveHost()

        cycle = host.cognitive_cycle({"shape": "round"}, question="이게 뭐지?")

        self.assertEqual(cycle["mode"], "reason")
        self.assertEqual(cycle["focus"]["kind"], "question")
        self.assertTrue(any(item["kind"] == "perception"
                            for item in cycle["alternatives"]))

    def test_goal_uses_planning_only_when_requested(self):
        host = CognitiveHost()

        cycle = host.cognitive_cycle(observation="start", goal="finish",
                                     actions=["step"])

        self.assertEqual(cycle["mode"], "plan")
        self.assertTrue(cycle["focus"]["data"]["found"])

    def test_new_unlabelled_input_is_learned_when_it_is_the_focus(self):
        host = CognitiveHost()

        cycle = host.cognitive_cycle({"tone": "high"}, modality="sound")

        self.assertEqual(cycle["mode"], "learn")
        self.assertEqual(len(host.induced_concepts), 1)

    def test_working_memory_has_bounded_capacity(self):
        host = CognitiveHost()
        for index in range(30):
            host.cognitive_cycle({"value": index})

        self.assertEqual(len(host.working_memory), 20)
        self.assertEqual(len(host.cognitive_cycles), 30)


if __name__ == "__main__":
    unittest.main()
