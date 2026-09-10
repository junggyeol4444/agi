"""Learn compositional event language from utterance/event co-occurrence."""

import json


class EventLanguageMixin:
    """Map symbols to event roles without next-token generation or supplied alignment."""

    def _event_value_key(self, value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def observe_utterance_event(self, language, tokens, event):
        if not isinstance(getattr(self, "event_lexicon", None), dict):
            self.event_lexicon = {}
        language = str(language)
        tokens = [str(token) for token in tokens if str(token)]
        roles = {str(role): value for role, value in (event or {}).items()
                 if value is not None}
        language_memory = self.event_lexicon.setdefault(language, {})
        for token in tokens:
            record = language_memory.setdefault(token, {"observations": 0, "candidates": {}})
            record["observations"] += 1
            for role, value in roles.items():
                key = f"{role}\u241f{self._event_value_key(value)}"
                candidate = record["candidates"].setdefault(
                    key, {"role": role, "value": value, "count": 0})
                candidate["count"] += 1
        return {token: self.event_meaning(language, token) for token in tokens}

    def event_meaning(self, language, token, min_support=2, min_margin=0.25):
        record = (getattr(self, "event_lexicon", {}) or {}).get(
            str(language), {}).get(str(token))
        if not record:
            return {"grounded": False, "language": language, "token": token,
                    "candidates": [], "reason": "사건과 함께 들은 적 없음"}
        total = max(1, record["observations"])
        candidates = [{**candidate, "confidence": round(candidate["count"] / total, 6)}
                      for candidate in record["candidates"].values()]
        candidates.sort(key=lambda item: (-item["confidence"], -item["count"],
                                          item["role"], self._event_value_key(item["value"])))
        best = candidates[0]
        second = candidates[1]["confidence"] if len(candidates) > 1 else 0.0
        margin = best["confidence"] - second
        grounded = best["count"] >= min_support and margin >= min_margin
        return {"grounded": grounded, "language": language, "token": token,
                "role": best["role"] if grounded else None,
                "value": best["value"] if grounded else None,
                "confidence": best["confidence"] if grounded else 0.0,
                "margin": round(margin, 6), "candidates": candidates,
                "reason": ("여러 사건에서 다른 요소가 바뀌어도 같은 역할·값과 연결됨"
                           if grounded else "역할 후보를 구분할 다양한 사건이 더 필요함")}

    def understand_event_utterance(self, language, tokens):
        """Build a partial event only from grounded token meanings."""
        event, evidence, conflicts = {}, [], []
        for token in tokens:
            meaning = self.event_meaning(language, token)
            if not meaning["grounded"]:
                continue
            role = meaning["role"]
            if role in event and event[role] != meaning["value"]:
                conflicts.append({"role": role, "existing": event[role],
                                  "candidate": meaning["value"], "token": token})
                continue
            event[role] = meaning["value"]
            evidence.append({"token": token, "role": role,
                             "confidence": meaning["confidence"]})
        return {"understood": bool(event) and not conflicts, "event": event,
                "evidence": evidence, "conflicts": conflicts,
                "unresolved_tokens": [token for token in tokens
                                      if not self.event_meaning(language, token)["grounded"]]}

    def express_event(self, language, event):
        """Recall learned symbols for event roles; do not invent missing words."""
        selected = []
        for role, value in (event or {}).items():
            matches = []
            for token in (getattr(self, "event_lexicon", {}) or {}).get(language, {}):
                meaning = self.event_meaning(language, token)
                if meaning.get("grounded") and meaning.get("role") == role \
                        and meaning.get("value") == value:
                    matches.append((meaning["confidence"], token))
            if not matches:
                return {"expressed": False, "tokens": [],
                        "missing": {"role": role, "value": value}}
            selected.append(max(matches)[1])
        return {"expressed": True, "tokens": selected, "missing": None}
