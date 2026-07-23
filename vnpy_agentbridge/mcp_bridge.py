"""
MCP Bridge Server: the single place where Agent-facing MCP tools are
registered and the only component (besides IntentEngine itself) that holds
a live main_engine/intent_engine reference.

Architectural rule (see engine.py and the deep-dive doc's corrected §5.1):
this module runs in the SAME OS process as MainEngine. The Agent's own
process never imports vnpy_agentbridge — it only holds this server's URL
in its `.vnag/mcp_config.json` (see README.md) and reaches every tool
below over the MCP protocol. That process boundary, not a coding
convention, is what makes "the Agent can't reach send_order() directly" a
structural guarantee rather than a promise a function author could break
by accident.

Every tool that only reads MainEngine-resident state (positions, active
orders, contracts, ticks) is exposed here rather than as a vnag LocalTool,
because that state only exists inside this process — a LocalTool running
inside the Agent's process could not reach it even if it tried. Read-only
tools whose data comes from outside this process (news, static reference
data, an Agent's own cached factors) are a legitimate candidate for a
LocalTool instead; none are implemented in this scaffold.

order_submit_intent is the only tool that writes anything, and it calls
IntentEngine.create_intent() exclusively — never main_engine.send_order().
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from vnpy.trader.constant import Direction, Exchange, Offset, OrderType
from vnpy.trader.engine import MainEngine

from .engine import IntentEngine


def build_mcp_bridge(main_engine: MainEngine, intent_engine: IntentEngine) -> FastMCP:
    """Build (but do not run) the FastMCP server exposing this package's Agent-facing tools."""

    mcp: FastMCP = FastMCP("vnpy-agentbridge")

    @mcp.tool
    def screen_get_contract_pool(product: str | None = None, exchange: str | None = None) -> str:
        """List known contracts, optionally filtered by product type and/or exchange."""
        rows = [
            {
                "vt_symbol": c.vt_symbol,
                "symbol": c.symbol,
                "exchange": c.exchange.value,
                "name": c.name,
                "product": c.product.value,
                "size": c.size,
                "pricetick": c.pricetick,
            }
            for c in main_engine.get_all_contracts()
            if (product is None or c.product.value == product)
            and (exchange is None or c.exchange.value == exchange)
        ]
        return json.dumps(rows, ensure_ascii=False)

    @mcp.tool
    def timing_get_latest_tick(vt_symbol: str) -> str:
        """Return the latest cached tick for vt_symbol, or {} if none is cached yet."""
        tick = main_engine.get_tick(vt_symbol)
        if tick is None:
            return json.dumps({})
        return json.dumps(
            {
                "vt_symbol": tick.vt_symbol,
                "last_price": tick.last_price,
                "volume": tick.volume,
                "datetime": tick.datetime.isoformat() if tick.datetime else None,
            },
            ensure_ascii=False,
        )

    @mcp.tool
    def risk_get_positions(vt_symbol: str | None = None) -> str:
        """Return current positions, optionally filtered to one vt_symbol. Read-only."""
        rows = [
            {
                "vt_symbol": p.vt_symbol,
                "direction": p.direction.value,
                "volume": p.volume,
                "frozen": p.frozen,
                "price": p.price,
                "pnl": p.pnl,
                "yd_volume": p.yd_volume,
            }
            for p in main_engine.get_all_positions()
            if vt_symbol is None or p.vt_symbol == vt_symbol
        ]
        return json.dumps(rows, ensure_ascii=False)

    @mcp.tool
    def risk_get_account_balance(accountid: str | None = None) -> str:
        """Return account balances, optionally filtered to one accountid. Read-only."""
        rows = [
            {"accountid": a.accountid, "balance": a.balance, "frozen": a.frozen}
            for a in main_engine.get_all_accounts()
            if accountid is None or a.accountid == accountid
        ]
        return json.dumps(rows, ensure_ascii=False)

    @mcp.tool
    def risk_get_active_orders(vt_symbol: str | None = None) -> str:
        """Return currently active (not yet finished) orders. Read-only."""
        rows = [
            {
                "vt_orderid": o.vt_orderid,
                "vt_symbol": o.vt_symbol,
                "direction": o.direction.value,
                "status": o.status.value,
                "volume": o.volume,
                "traded": o.traded,
            }
            for o in main_engine.get_all_active_orders()
            if vt_symbol is None or o.vt_symbol == vt_symbol
        ]
        return json.dumps(rows, ensure_ascii=False)

    @mcp.tool
    def order_submit_intent(
        gateway_name: str,
        symbol: str,
        exchange: str,
        direction: str,
        offset: str,
        order_type: str,
        volume: float,
        price: float,
        reasoning: str,
        confidence: float,
        stop_price: float | None = None,
    ) -> str:
        """
        Submit an order intent for rule evaluation / human approval.

        This does NOT place a real order. It only reaches
        IntentEngine.create_intent(); there is no tool on this server that
        calls main_engine.send_order() directly. `reasoning` and
        `confidence` are required and audited — do not call this with an
        empty reasoning string.
        """
        intent = intent_engine.create_intent(
            gateway_name=gateway_name,
            symbol=symbol,
            exchange=Exchange(exchange),
            direction=Direction(direction),
            offset=Offset(offset),
            order_type=OrderType(order_type),
            volume=volume,
            price=price,
            reasoning=reasoning,
            confidence=confidence,
            stop_price=stop_price,
        )
        return json.dumps({"intent_id": intent.intent_id, "status": intent.status.value}, ensure_ascii=False)

    @mcp.tool
    def order_query_intent_status(intent_id: str) -> str:
        """Query the current status of a previously submitted order intent."""
        intent = intent_engine.get_intent(intent_id)
        if intent is None:
            return json.dumps({"error": "unknown intent_id"})
        return json.dumps(
            {
                "intent_id": intent.intent_id,
                "status": intent.status.value,
                "reject_reason": intent.reject_reason,
                "vt_orderid": intent.vt_orderid,
            },
            ensure_ascii=False,
        )

    return mcp
