import unittest

from experience import ExperienceMemoryMixin
from rule_induction import RuleInductionMixin


class RuleHost(ExperienceMemoryMixin, RuleInductionMixin):
    def __init__(self):
        self.events = []
        self.event_seq = 0
        self.abstract_rules = {}
        self.lived = 0


class RuleInductionTests(unittest.TestCase):
    def test_shared_conditions_survive_context_generalization(self):
        host = RuleHost()
        for color in ("red", "blue", "green"):
            host.record_event("interaction", action="push", obj="block",
                              context={"surface": "smooth", "color": color},
                              outcome="moves")

        rule = host.induced_rules(general_only=True)[0]

        self.assertEqual(rule["common_context"], {"surface": "smooth"})
        self.assertEqual(rule["conclusion"], "moves")
        self.assertEqual(rule["distinct_contexts"], 3)

    def test_one_context_does_not_claim_general_rule(self):
        host = RuleHost()
        for _ in range(3):
            host.record_event("interaction", action="push",
                              context={"surface": "smooth"}, outcome="moves")

        self.assertEqual(host.induced_rules()[0]["status"], "candidate")

    def test_exception_keeps_rule_variable(self):
        host = RuleHost()
        host.record_event("interaction", action="push", context={"weight": 1},
                          outcome="moves")
        host.record_event("interaction", action="push", context={"weight": 2},
                          outcome="moves")
        host.record_event("interaction", action="push", context={"weight": 9},
                          outcome="stuck")

        rule = host.induced_rules()[0]

        self.assertEqual(rule["status"], "variable")
        self.assertEqual(len(rule["outcomes"]), 2)

    def test_repeated_testimony_is_not_promoted_as_experienced_rule(self):
        host = RuleHost()
        for place in ("a", "b", "c"):
            host.record_event("claim", action="hears", context={"place": place},
                              outcome="dragons exist", source="testimony")

        self.assertEqual(host.induced_rules()[0]["status"], "candidate")


if __name__ == "__main__":
    unittest.main()
