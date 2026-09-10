import unittest

from symbol_grounding import SymbolGroundingMixin


class GroundingHost(SymbolGroundingMixin):
    def __init__(self):
        self.symbol_groundings = {}


class SymbolGroundingTests(unittest.TestCase):
    def test_single_hearing_does_not_define_meaning(self):
        host = GroundingHost()

        meaning = host.observe_symbol("ko", "공", "concept-round")

        self.assertFalse(meaning["grounded"])

    def test_repeated_cooccurrence_grounds_symbol_in_own_concept(self):
        host = GroundingHost()
        for _ in range(3):
            meaning = host.observe_symbol("ko", "공", "concept-round")

        self.assertTrue(meaning["grounded"])
        self.assertEqual(meaning["concept_id"], "concept-round")

    def test_ambiguous_symbol_is_withheld(self):
        host = GroundingHost()
        for _ in range(3):
            host.observe_symbol("ko", "저것", "concept-a")
            meaning = host.observe_symbol("ko", "저것", "concept-b")

        self.assertFalse(meaning["grounded"])
        self.assertEqual(len(meaning["candidates"]), 2)

    def test_counterexample_can_retract_grounding(self):
        host = GroundingHost()
        for _ in range(3):
            host.observe_symbol("ko", "공", "concept-round")
        for _ in range(4):
            meaning = host.observe_symbol(
                "ko", "공", "concept-round", matches=False)

        self.assertFalse(meaning["grounded"])


if __name__ == "__main__":
    unittest.main()
