"""
Regression test for the M3 finding: OrderRequest (a plain dataclass with no
isinstance()/type()-is checks on the send_order path) can safely be
subclassed. Mirrors the exact scenario walked through in the deep-dive
doc's §1.3 (子类身份和新增字段随 copy.copy() 一起流经 OffsetConverter 式的拆单逻辑).
"""

from __future__ import annotations

from copy import copy

from vnpy.trader.constant import Direction, Exchange, Offset, OrderType

from vnpy_agentbridge.order_request_ext import StopOrderRequest


def _make_stop_order_request() -> StopOrderRequest:
    return StopOrderRequest(
        symbol="700",
        exchange=Exchange.SEHK,
        direction=Direction.LONG,
        type=OrderType.LIMIT,
        volume=100,
        price=350.0,
        offset=Offset.OPEN,
        stop_price=340.0,
        trail_percent=1.5,
    )


def test_stop_order_request_is_an_order_request() -> None:
    from vnpy.trader.object import OrderRequest

    req = _make_stop_order_request()
    assert isinstance(req, OrderRequest)


def test_stop_order_request_inherited_post_init_runs() -> None:
    req = _make_stop_order_request()
    assert req.vt_symbol == "700.SEHK"


def test_stop_order_request_extra_fields_present() -> None:
    req = _make_stop_order_request()
    assert req.stop_price == 340.0
    assert req.trail_percent == 1.5
    assert req.trail_amount is None


def test_subclass_identity_and_fields_survive_shallow_copy() -> None:
    """Mirrors OffsetConverter's use of copy.copy(req) when splitting an order."""
    req = _make_stop_order_request()
    req_copy = copy(req)

    assert type(req_copy) is StopOrderRequest
    assert req_copy.stop_price == 340.0
    assert req_copy is not req
