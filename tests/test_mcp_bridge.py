"""
Smoke tests for the MCP Bridge Server: proves the expected tool surface is
registered and that a round trip through the server (not through
IntentEngine directly) still only ever reaches create_intent(), never
main_engine.send_order().

These do not start a network listener — FastMCP's in-process
list_tools()/call_tool() are used directly, which is sufficient to prove
the tool registrations and their wiring to IntentEngine are correct.
"""

from __future__ import annotations

import asyncio
import json

from vnpy.trader.constant import Direction, Exchange, Offset, OrderType

from vnpy_agentbridge.engine import IntentEngine
from vnpy_agentbridge.mcp_bridge import build_mcp_bridge
from vnpy_agentbridge.object import IntentStatus
from tests.conftest import FakeGateway

EXPECTED_TOOL_NAMES = {
    "screen_get_contract_pool",
    "timing_get_latest_tick",
    "risk_get_positions",
    "risk_get_account_balance",
    "risk_get_active_orders",
    "order_submit_intent",
    "order_query_intent_status",
}


def test_expected_tools_are_registered(main_engine, intent_engine: IntentEngine) -> None:
    mcp = build_mcp_bridge(main_engine, intent_engine)
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOL_NAMES <= names


def test_order_submit_intent_tool_reaches_intent_engine_not_send_order(
    main_engine, intent_engine: IntentEngine, fake_gateway: FakeGateway
) -> None:
    mcp = build_mcp_bridge(main_engine, intent_engine)

    result = asyncio.run(
        mcp.call_tool(
            "order_submit_intent",
            {
                "gateway_name": "FAKE",
                "symbol": "700",
                "exchange": Exchange.SEHK.value,
                "direction": Direction.LONG.value,
                "offset": Offset.OPEN.value,
                "order_type": OrderType.LIMIT.value,
                "volume": 100,
                "price": 350.0,
                "reasoning": "test via MCP tool call",
                "confidence": 0.9,
            },
        )
    )

    payload = json.loads(result.content[0].text)
    intent_id = payload["intent_id"]
    assert payload["status"] == IntentStatus.PENDING_REVIEW.value

    # Submitting an intent through the MCP tool must not have touched the gateway.
    assert fake_gateway.sent_requests == []

    # And IntentEngine (not some parallel state) is what actually holds it.
    intent = intent_engine.get_intent(intent_id)
    assert intent is not None
    assert intent.reasoning == "test via MCP tool call"


def test_order_query_intent_status_round_trip(main_engine, intent_engine: IntentEngine) -> None:
    mcp = build_mcp_bridge(main_engine, intent_engine)

    intent = intent_engine.create_intent(
        gateway_name="FAKE",
        symbol="700",
        exchange=Exchange.SEHK,
        direction=Direction.LONG,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        volume=100,
        price=350.0,
        reasoning="direct create for query test",
        confidence=0.9,
    )

    result = asyncio.run(mcp.call_tool("order_query_intent_status", {"intent_id": intent.intent_id}))
    payload = json.loads(result.content[0].text)
    assert payload["intent_id"] == intent.intent_id
    assert payload["status"] == IntentStatus.PENDING_REVIEW.value


def test_risk_get_positions_tool_is_read_only_and_reachable(main_engine, intent_engine: IntentEngine) -> None:
    mcp = build_mcp_bridge(main_engine, intent_engine)
    result = asyncio.run(mcp.call_tool("risk_get_positions", {}))
    payload = json.loads(result.content[0].text)
    assert payload == []  # no positions yet, but the call succeeded end to end
