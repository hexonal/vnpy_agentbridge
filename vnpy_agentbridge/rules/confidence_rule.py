"""Example IntentRuleTemplate: rejects empty reasoning or low-confidence intents."""

from __future__ import annotations

from ..object import OrderIntent
from ..template import IntentRuleTemplate


class ConfidenceRule(IntentRuleTemplate):
    """Reject an intent whose reasoning is empty or whose confidence is below a threshold."""

    def __init__(self, min_confidence: float = 0.6) -> None:
        self.min_confidence = min_confidence

    def check_allowed(self, intent: OrderIntent) -> tuple[bool, str]:
        if not intent.reasoning.strip():
            return False, "reasoning field is empty"
        if intent.confidence < self.min_confidence:
            return False, f"confidence {intent.confidence} below threshold {self.min_confidence}"
        return True, ""
