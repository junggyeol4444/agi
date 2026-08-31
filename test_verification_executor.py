import unittest

from belief_system import EvidenceBeliefMixin


class ExecutorHost(EvidenceBeliefMixin):
    def __init__(self):
        self.isa = {}
        self.doubts = {}
        self.beliefs = {}
        self.belief_revisions = []
        self.answer_history = []
        self.verification_tasks = {}
        self.verification_runs = []
        self.contextual_conclusions = {}
        self.lived = 1

    def _wonder(self, subject):
        pass

    def _j(self, word, with_batchim, without_batchim):
        return f"{word}{with_batchim}"


class VerificationExecutorTests(unittest.TestCase):
    def test_execution_closes_plan_with_acquired_evidence(self):
        host = ExecutorHost()
        host.make_verification_plan("펭귄")

        def provider(task):
            return [
                {"object": "조류", "source": "관찰-A"},
                {"object": "조류", "source": "관찰-B"},
            ]

        runs = host.execute_verification(provider)

        self.assertEqual(host.isa["펭귄"], "조류")
        self.assertTrue(runs[0]["verdict"]["verified"])
        task = host.verification_tasks[host._verification_key("펭귄", "is_a")]
        self.assertEqual(task["status"], "resolved")
        self.assertEqual(task["attempts"], 1)

    def test_failed_acquisition_blocks_task_without_inventing_evidence(self):
        host = ExecutorHost()
        host.make_verification_plan("미지")

        runs = host.execute_verification(lambda task: [])

        self.assertEqual(runs[0]["observations"], 0)
        self.assertEqual(host.beliefs, {})
        task = host.verification_tasks[host._verification_key("미지", "is_a")]
        self.assertEqual(task["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
