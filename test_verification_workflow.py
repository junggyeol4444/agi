import unittest

from verification_workflow import VerificationWorkflowMixin


class WorkflowHost(VerificationWorkflowMixin):
    def __init__(self):
        self.verification_tasks = {}
        self.curiosity = []
        self.lived = 3

    def belief_about(self, subject, relation="is_a", context=None):
        return []

    def verify_belief(self, subject, relation="is_a", context=None):
        return {"verified": False}

    def _context_key(self, subject, relation, context):
        return f"{subject}|{relation}|{sorted(context.items())}"

    def _wonder(self, subject):
        self.curiosity.append(subject)


class StandaloneVerificationWorkflowTests(unittest.TestCase):
    def test_unknown_subject_becomes_persistent_work(self):
        host = WorkflowHost()

        thought = host.deliberate("미지의대상")

        self.assertEqual(thought["action"], "investigate")
        self.assertIn(host._verification_key("미지의대상", "is_a"),
                      host.verification_tasks)


if __name__ == "__main__":
    unittest.main()
