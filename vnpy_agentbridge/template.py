"""
Base class for pluggable Agent-intent-level rules.

This is a distinct rule tier from vnpy_riskmanager's RuleTemplate:
vnpy_riskmanager checks *OrderRequest* objects at the main_engine.send_order
boundary, a point every caller shares (GUI, CTA strategies, this package's
IntentEngine.approve_intent). IntentRuleTemplate checks *OrderIntent*
objects instead, which carry Agent-specific fields (reasoning/confidence)
that OrderRequest does not have and that RuleTemplate therefore cannot see.
The two tiers run at different points in the pipeline and are not
substitutes for one another — see the architecture note in engine.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .object import OrderIntent


class IntentRuleTemplate(ABC):
    """Evaluated by IntentEngine.check_rules() before an intent leaves PENDING_REVIEW."""

    active: bool = True

    @abstractmethod
    def check_allowed(self, intent: OrderIntent) -> tuple[bool, str]:
        """Return (allowed, reason); reason is only meaningful when allowed is False."""
        raise NotImplementedError
