"""
End-to-end IntentEngine lifecycle tests: create -> (rule evaluation) ->
approve/reject/cancel, exercised against a real MainEngine wired to the
FakeGateway from conftest.py (no network access, no credentials).
"""

from __future__ import annotations

import pytest
from vnpy.trader.constant import Direction, Exchange, Offset, OrderType

from tests.conftest import FakeGateway
from vnpy_agentbridge.engine import IntentEngine
from vnpy_agentbridge.object import IntentStatus
from vnpy_agentbridge.rules.confidence_rule import ConfidenceRule


def _submit(intent_engine: IntentEngine, **overrides) -> str:
    params = dict(
        gateway_name="FAKE",
        symbol="700",
        exchange=Exchange.SEHK,
        direction=Direction.LONG,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        volume=100,
        price=350.0,
        reasoning="RSI oversold bounce",
        confidence=0.8,
    )
    params.update(overrides)
    intent = intent_engine.create_intent(**params)
    return intent.intent_id


def test_create_intent_defaults_to_pending_review(intent_engine: IntentEngine) -> None:
    intent_id = _submit(intent_engine)
    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.PENDING_REVIEW
    assert intent.vt_symbol == "700.SEHK"


def test_create_intent_never_calls_send_order(
    intent_engine: IntentEngine, fake_gateway: FakeGateway
) -> None:
    _submit(intent_engine)
    assert fake_gateway.sent_requests == []


def test_approve_intent_sends_a_real_order_request(
    intent_engine: IntentEngine, fake_gateway: FakeGateway
) -> None:
    intent_id = _submit(intent_engine)

    vt_orderid = intent_engine.approve_intent(intent_id, approver="tester")

    assert len(fake_gateway.sent_requests) == 1
    sent = fake_gateway.sent_requests[0]
    assert sent.symbol == "700"
    assert sent.volume == 100
    assert vt_orderid == "FAKE.fake1"

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.SENT
    assert intent.vt_orderid == vt_orderid


def test_approve_intent_with_stop_price_sends_stop_order_request(
    intent_engine: IntentEngine, fake_gateway: FakeGateway
) -> None:
    from vnpy_agentbridge.order_request_ext import StopOrderRequest

    intent_id = _submit(intent_engine, stop_price=340.0)
    intent_engine.approve_intent(intent_id)

    sent = fake_gateway.sent_requests[0]
    assert isinstance(sent, StopOrderRequest)
    assert sent.stop_price == 340.0


def test_cannot_approve_an_already_sent_intent_twice(intent_engine: IntentEngine) -> None:
    intent_id = _submit(intent_engine)
    intent_engine.approve_intent(intent_id)

    with pytest.raises(ValueError):
        intent_engine.approve_intent(intent_id)


def test_reject_intent(intent_engine: IntentEngine, fake_gateway: FakeGateway) -> None:
    intent_id = _submit(intent_engine)
    intent_engine.reject_intent(intent_id, reason="position limit reached", approver="tester")

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.MANUAL_REJECTED
    assert "position limit reached" in intent.reject_reason
    assert fake_gateway.sent_requests == []


def test_cancel_intent(intent_engine: IntentEngine, fake_gateway: FakeGateway) -> None:
    intent_id = _submit(intent_engine)
    intent_engine.cancel_intent(intent_id)

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.CANCELLED
    assert fake_gateway.sent_requests == []


def test_unknown_intent_id_raises_keyerror(intent_engine: IntentEngine) -> None:
    with pytest.raises(KeyError):
        intent_engine.approve_intent("does-not-exist")


# --- IntentRuleTemplate integration (ConfidenceRule) -----------------------


def test_confidence_rule_auto_rejects_low_confidence_intent(
    intent_engine: IntentEngine, fake_gateway: FakeGateway
) -> None:
    intent_engine.add_rule(ConfidenceRule(min_confidence=0.6))

    intent_id = _submit(intent_engine, confidence=0.3)

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.AUTO_REJECTED
    assert "confidence" in intent.reject_reason


def test_confidence_rule_auto_rejects_empty_reasoning(intent_engine: IntentEngine) -> None:
    intent_engine.add_rule(ConfidenceRule())

    intent_id = _submit(intent_engine, reasoning="   ")

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.AUTO_REJECTED


def test_auto_rejected_intent_cannot_be_approved(intent_engine: IntentEngine) -> None:
    intent_engine.add_rule(ConfidenceRule(min_confidence=0.6))
    intent_id = _submit(intent_engine, confidence=0.1)

    with pytest.raises(ValueError):
        intent_engine.approve_intent(intent_id)


def test_high_confidence_intent_passes_the_rule(intent_engine: IntentEngine) -> None:
    intent_engine.add_rule(ConfidenceRule(min_confidence=0.6))
    intent_id = _submit(intent_engine, confidence=0.9)

    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.PENDING_REVIEW
