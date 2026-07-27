"""
IntentEngine: the structural first gate for Agent-originated order intents.

Two independent gates protect every order that originates from an Agent:

  1. STRUCTURAL (this module). Agent-facing tool functions (exposed over
     MCP by mcp_bridge.py, running in this same process) can call
     IntentEngine.create_intent() and nothing else. create_intent() only
     queues an OrderIntent and evaluates it against IntentRuleTemplate
     rules — it never calls MainEngine.send_order(). Converting an
     approved intent into a real OrderRequest and calling send_order() is
     done exclusively by approve_intent(), below. The Agent's own process
     never imports this module and never holds a reference to it or to
     MainEngine — it only knows the MCP Bridge Server's URL (see
     mcp_bridge.py / README.md), so there is no in-process path for a
     compromised or hallucinating Agent to reach send_order() directly.

  2. MECHANICAL (vnpy_riskmanager, reused unmodified). Once approve_intent()
     calls main_engine.send_order(), that call runs through whatever
     RiskEngine.patch_functions() has installed — the same gate every
     other caller (GUI, CTA strategies) goes through. This package does
     not reimplement that; it just relies on vnpy_riskmanager being loaded
     (see README.md for load-order requirements).

These two gates check different things at different points and are not
substitutes for one another: IntentRuleTemplate (template.py) inspects
Agent-specific fields (reasoning/confidence) that OrderRequest does not
carry and that RiskEngine therefore cannot see; RiskEngine's rules inspect
the OrderRequest that every caller — Agent-approved or not — ultimately
produces.
"""

from __future__ import annotations

import uuid

from vnpy.event import Event, EventEngine
from vnpy.trader.constant import Direction, Exchange, Offset, OrderType
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.object import OrderRequest

from .object import IntentStatus, OrderIntent
from .order_request_ext import StopOrderRequest
from .template import IntentRuleTemplate

APP_NAME = "AgentBridge"

EVENT_INTENT_CREATED = "eIntentCreated."
EVENT_INTENT_APPROVED = "eIntentApproved."
EVENT_INTENT_REJECTED = "eIntentRejected."
EVENT_INTENT_CANCELLED = "eIntentCancelled."


class IntentEngine(BaseEngine):
    """Queues Agent-generated OrderIntents; only approve_intent() may call send_order()."""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        super().__init__(main_engine, event_engine, APP_NAME)

        self.intents: dict[str, OrderIntent] = {}
        self.rules: list[IntentRuleTemplate] = []

    def add_rule(self, rule: IntentRuleTemplate) -> None:
        self.rules.append(rule)

    def check_rules(self, intent: OrderIntent) -> tuple[bool, str]:
        for rule in self.rules:
            if not rule.active:
                continue
            allowed, reason = rule.check_allowed(intent)
            if not allowed:
                return False, reason
        return True, ""

    def create_intent(
        self,
        gateway_name: str,
        symbol: str,
        exchange: Exchange,
        direction: Direction,
        offset: Offset,
        order_type: OrderType,
        volume: float,
        price: float,
        reasoning: str,
        confidence: float,
        stop_price: float | None = None,
        trail_amount: float | None = None,
        trail_percent: float | None = None,
        source_agent_id: str = "",
        source_session_id: str = "",
    ) -> OrderIntent:
        """Create and evaluate a new OrderIntent. Never calls main_engine.send_order()."""
        intent = OrderIntent(
            intent_id=str(uuid.uuid4()),
            gateway_name=gateway_name,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            offset=offset,
            order_type=order_type,
            volume=volume,
            price=price,
            reasoning=reasoning,
            confidence=confidence,
            stop_price=stop_price,
            trail_amount=trail_amount,
            trail_percent=trail_percent,
            source_agent_id=source_agent_id,
            source_session_id=source_session_id,
        )

        self.intents[intent.intent_id] = intent
        self._put_event(EVENT_INTENT_CREATED, intent)

        allowed, reason = self.check_rules(intent)
        if not allowed:
            intent.status = IntentStatus.AUTO_REJECTED
            intent.reject_reason = reason
            self._put_event(EVENT_INTENT_REJECTED, intent)

        return intent

    def get_intent(self, intent_id: str) -> OrderIntent | None:
        return self.intents.get(intent_id)

    def get_all_intents(self) -> list[OrderIntent]:
        return list(self.intents.values())

    def _require_pending(self, intent_id: str) -> OrderIntent:
        intent = self.intents.get(intent_id)
        if intent is None:
            raise KeyError(f"unknown intent_id: {intent_id}")
        if intent.status != IntentStatus.PENDING_REVIEW:
            raise ValueError(
                f"intent {intent_id} is not pending review (status={intent.status.value})"
            )
        return intent

    def approve_intent(self, intent_id: str, approver: str = "") -> str:
        """
        The only method in this package that builds a real OrderRequest and
        calls main_engine.send_order(). Requires the intent to still be
        PENDING_REVIEW (i.e. not already auto-rejected by check_rules()).
        """
        intent = self._require_pending(intent_id)

        req: OrderRequest
        if (
            intent.stop_price is not None
            or intent.trail_amount is not None
            or intent.trail_percent is not None
        ):
            req = StopOrderRequest(
                symbol=intent.symbol,
                exchange=intent.exchange,
                direction=intent.direction,
                type=intent.order_type,
                volume=intent.volume,
                price=intent.price,
                offset=intent.offset,
                stop_price=intent.stop_price,
                trail_amount=intent.trail_amount,
                trail_percent=intent.trail_percent,
            )
        else:
            req = OrderRequest(
                symbol=intent.symbol,
                exchange=intent.exchange,
                direction=intent.direction,
                type=intent.order_type,
                volume=intent.volume,
                price=intent.price,
                offset=intent.offset,
            )

        vt_orderid = self.main_engine.send_order(req, intent.gateway_name)

        intent.status = IntentStatus.SENT
        intent.vt_orderid = vt_orderid
        intent.reject_reason = f"approved by {approver}" if approver else "approved"
        self._put_event(EVENT_INTENT_APPROVED, intent)
        return vt_orderid

    def reject_intent(self, intent_id: str, reason: str, approver: str = "") -> None:
        intent = self._require_pending(intent_id)
        intent.status = IntentStatus.MANUAL_REJECTED
        intent.reject_reason = f"{reason} (rejected by {approver})" if approver else reason
        self._put_event(EVENT_INTENT_REJECTED, intent)

    def cancel_intent(self, intent_id: str) -> None:
        intent = self._require_pending(intent_id)
        intent.status = IntentStatus.CANCELLED
        self._put_event(EVENT_INTENT_CANCELLED, intent)

    def _put_event(self, event_type: str, intent: OrderIntent) -> None:
        self.event_engine.put(Event(event_type, intent))
        self.event_engine.put(Event(event_type + intent.vt_symbol, intent))
