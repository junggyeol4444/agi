"""Induce role order from already grounded utterances."""


class GrammarInductionMixin:
    """Learn compositional syntax from experience without a supplied language template."""

    def observe_grounded_utterance(self, language, tokens):
        if not isinstance(getattr(self, "grammar_memory", None), dict):
            self.grammar_memory = {}
        roles, evidence, unresolved = [], [], []
        for token in tokens:
            meaning = self.event_meaning(language, token)
            if not meaning.get("grounded"):
                unresolved.append(token)
                continue
            roles.append(meaning["role"])
            evidence.append({"token": token, "role": meaning["role"],
                             "confidence": meaning["confidence"]})
        if unresolved or len(roles) != len(tokens) or len(set(roles)) != len(roles):
            return {"learned": False, "reason": "모든 토큰의 서로 다른 역할이 먼저 필요함",
                    "roles": roles, "unresolved_tokens": unresolved, "evidence": evidence}
        memory = self.grammar_memory.setdefault(str(language),
                                                {"orders": {}, "observations": 0})
        order_key = "\u241f".join(roles)
        memory["orders"][order_key] = memory["orders"].get(order_key, 0) + 1
        memory["observations"] += 1
        return {"learned": True, "roles": roles, "unresolved_tokens": [],
                "evidence": evidence, "grammar": self.learned_role_order(language)}

    def learned_role_order(self, language, min_examples=3, min_dominance=0.75):
        memory = (getattr(self, "grammar_memory", {}) or {}).get(str(language))
        if not memory or not memory.get("orders"):
            return {"grounded": False, "language": language, "reason": "어순 경험 없음",
                    "orders": []}
        total = memory["observations"]
        orders = [{"roles": key.split("\u241f"), "count": count,
                   "frequency": round(count / total, 6)}
                  for key, count in memory["orders"].items()]
        orders.sort(key=lambda item: (-item["count"], item["roles"]))
        best = orders[0]
        grounded = total >= min_examples and best["frequency"] >= min_dominance
        return {"grounded": grounded, "language": language,
                "roles": best["roles"] if grounded else None,
                "confidence": best["frequency"] if grounded else 0.0,
                "observations": total, "orders": orders,
                "reason": ("반복된 완전 grounding 발화에서 역할 순서가 안정됨"
                           if grounded else "일관된 어순 경험이 더 필요함")}

    def compose_event_utterance(self, language, event):
        """Express roles in learned order and refuse unknown roles or words."""
        grammar = self.learned_role_order(language)
        if not grammar["grounded"]:
            return {"expressed": False, "tokens": [], "reason": grammar["reason"]}
        expected = grammar["roles"]
        if set(event or {}) != set(expected):
            return {"expressed": False, "tokens": [],
                    "reason": "학습한 문장 역할과 사건 역할이 다름",
                    "expected_roles": expected}
        tokens = []
        for role in expected:
            expression = self.express_event(language, {role: event[role]})
            if not expression.get("expressed"):
                return {"expressed": False, "tokens": [],
                        "reason": "역할에 필요한 기호를 아직 배우지 못함",
                        "missing": expression.get("missing")}
            tokens.extend(expression["tokens"])
        return {"expressed": True, "tokens": tokens, "roles": expected,
                "grammar_confidence": grammar["confidence"]}
