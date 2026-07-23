"""
Data structures for the Agent order-intent bridge.

An OrderIntent is deliberately NOT an OrderRequest: it carries the extra
provenance/audit fields (reasoning, confidence, source agent/session) that
vnpy's OrderRequest does not have, and — unlike OrderRequest — it is never
passed to MainEngine.send_order() directly. Converting an approved
OrderIntent into a real OrderRequest is the sole responsibility of
IntentEngine.approve_intent() (see engine.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from vnpy.trader.constant import Direction, Exchange, Offset, OrderType


class IntentStatus(Enum):
    """Lifecycle status of an OrderIntent."""

    PENDING_REVIEW = "pending_review"
    AUTO_REJECTED = "auto_rejected"
    MANUAL_REJECTED = "manual_rejected"
    SENT = "sent"
    CANCELLED = "cancelled"


@dataclass
class OrderIntent:
    """An Agent-generated order intent, queued for rule evaluation and/or human approval."""

    intent_id: str
    gateway_name: str
    symbol: str
    exchange: Exchange
    direction: Direction
    offset: Offset
    order_type: OrderType
    volume: float
    price: float
    reasoning: str
    confidence: float

    stop_price: float | None = None
    trail_amount: float | None = None
    trail_percent: float | None = None

    source_agent_id: str = ""
    source_session_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: IntentStatus = IntentStatus.PENDING_REVIEW
    reject_reason: str = ""
    vt_orderid: str = ""

    def __post_init__(self) -> None:
        self.vt_symbol: str = f"{self.symbol}.{self.exchange.value}"
