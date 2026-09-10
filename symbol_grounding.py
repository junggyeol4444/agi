"""Ground heard symbols in self-induced concepts through repeated experience."""


class SymbolGroundingMixin:
    """Learn word meanings from concept co-occurrence, ambiguity, and counterexamples."""

    def observe_symbol(self, language, symbol, concept_id, matches=True, source="direct"):
        if not isinstance(getattr(self, "symbol_groundings", None), dict):
            self.symbol_groundings = {}
        language, symbol, concept_id = str(language), str(symbol), str(concept_id)
        symbol_key = f"{language}\u241f{symbol}"
        record = self.symbol_groundings.setdefault(symbol_key, {
            "language": language, "symbol": symbol, "concepts": {}, "observations": 0})
        candidate = record["concepts"].setdefault(concept_id, {
            "concept_id": concept_id, "support": 0, "oppose": 0, "sources": []})
        candidate["support" if matches else "oppose"] += 1
        if source not in candidate["sources"]:
            candidate["sources"].append(source)
            candidate["sources"] = candidate["sources"][-20:]
        record["observations"] += 1
        return self.meaning_of(language, symbol)

    def _grounding_candidates(self, record):
        candidates = []
        for item in record.get("concepts", {}).values():
            total = item.get("support", 0) + item.get("oppose", 0)
            confidence = ((item.get("support", 0) + 1) / (total + 2)
                          if total else 0.0)
            candidates.append({**item, "confidence": round(confidence, 6),
                               "evidence": total})
        candidates.sort(key=lambda item: (-item["confidence"],
                                          -item.get("support", 0), item["concept_id"]))
        return candidates

    def meaning_of(self, language, symbol, min_support=3, min_margin=0.2):
        record = (getattr(self, "symbol_groundings", {}) or {}).get(
            f"{language}\u241f{symbol}")
        if not record:
            return {"grounded": False, "reason": "이 기호를 경험한 적 없음",
                    "language": language, "symbol": symbol, "candidates": []}
        candidates = self._grounding_candidates(record)
        best = candidates[0] if candidates else None
        runner_confidence = candidates[1]["confidence"] if len(candidates) > 1 else 0.0
        margin = best["confidence"] - runner_confidence if best else 0.0
        grounded = bool(best and best.get("support", 0) >= min_support
                        and margin >= min_margin and best["confidence"] > 0.5)
        reason = ("반복 경험에서 한 개념이 다른 후보보다 충분히 우세함" if grounded else
                  "반복 근거가 부족하거나 여러 의미 후보가 경쟁 중")
        return {"grounded": grounded, "reason": reason,
                "language": language, "symbol": symbol,
                "concept_id": best["concept_id"] if grounded else None,
                "margin": round(margin, 6), "candidates": candidates}

    def symbols_for_concept(self, concept_id, language=None, grounded_only=True):
        results = []
        for record in (getattr(self, "symbol_groundings", {}) or {}).values():
            if language is not None and record.get("language") != language:
                continue
            meaning = self.meaning_of(record["language"], record["symbol"])
            candidate = next((item for item in meaning["candidates"]
                              if item["concept_id"] == str(concept_id)), None)
            if not candidate:
                continue
            if grounded_only and meaning.get("concept_id") != str(concept_id):
                continue
            results.append({"language": record["language"], "symbol": record["symbol"],
                            "grounded": meaning["grounded"], "candidate": candidate})
        return results
