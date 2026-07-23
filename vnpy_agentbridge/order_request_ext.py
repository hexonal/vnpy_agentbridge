"""
The M3-verified safe extension pattern: OrderRequest is a plain dataclass
with no isinstance()/type()-is checks anywhere on the send_order path
(MainEngine.send_order -> BaseGateway.send_order -> concrete gateway ->
OffsetConverter's copy(req)), so it can be safely subclassed to carry
broker-native fields the core OrderRequest does not have (stop price,
trailing amount/percent).

OrderType, by contrast, is a Python Enum that already defines members —
Python's enum module refuses to let such an Enum be subclassed to add new
members (TypeError at class-definition time; PEP 435 / Python 3.4+
language rule, not a vnpy design choice). See
tests/test_enum_extension_blocked.py, which encodes that finding as a
permanent regression test. Do not try to add new OrderType members via
subclassing here — extend vnpy/trader/constant.py directly if a new
*structural* order type is ever genuinely required.
"""

from __future__ import annotations

from dataclasses import dataclass

from vnpy.trader.object import OrderRequest


@dataclass
class StopOrderRequest(OrderRequest):
    """OrderRequest carrying broker-native stop / trailing-stop parameters."""

    stop_price: float | None = None
    trail_amount: float | None = None
    trail_percent: float | None = None
