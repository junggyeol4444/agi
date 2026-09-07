import unittest

from experience import ExperienceMemoryMixin
from memory_consolidation import MemoryConsolidationMixin


class MemoryHost(ExperienceMemoryMixin, MemoryConsolidationMixin):
    def __init__(self):
        self.events = []
        self.event_seq = 0
        self.semantic_memory = {}
        self.lived = 0


class MemoryConsolidationTests(unittest.TestCase):
    def test_repeated_episodes_become_a_regular_rule(self):
        host = MemoryHost()
        for _ in range(3):
            host.record_event("interaction", actor="self", action="open",
                              outcome="open", context={"door": "closed"})

        recalled = host.semantic_recall(action="open", reliable_only=True)

        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["dominant_outcome"], "open")
        self.assertEqual(recalled[0]["reliability"], 1.0)

    def test_conflicting_episode_is_preserved_as_variability(self):
        host = MemoryHost()
        host.record_event("interaction", action="push", outcome="moves")
        host.record_event("interaction", action="push", outcome="stuck")
        host.record_event("interaction", action="push", outcome="moves")

        report = host.consolidate_memory()

        self.assertEqual(len(report["variable"]), 1)
        self.assertEqual(len(host.events), 3)

    def test_unrelated_patterns_are_updated_locally(self):
        host = MemoryHost()
        host.record_event("interaction", action="push", outcome="moves")
        host.record_event("interaction", action="pull", outcome="moves")

        self.assertEqual(len(host.semantic_memory), 2)


if __name__ == "__main__":
    unittest.main()
