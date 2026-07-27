"""
Regression test for the M3 finding: OrderType (a Python Enum that already
defines members) cannot be extended via subclassing — this is a Python
language rule (PEP 435, Python 3.4+), not a vnpy design choice, and it is
the reason StopOrderRequest (order_request_ext.py) adds fields on top of
OrderRequest rather than trying to add new OrderType members.

If a future vnpy upgrade ever changes OrderType to allow this (extremely
unlikely, since it would require CPython's enum module itself to change),
this test failing is exactly the signal that the constraint documented in
the fork's "核心改动范围清单" no longer holds and that section needs
revisiting.
"""

from __future__ import annotations

import pytest
from vnpy.trader.constant import OrderType


def test_ordertype_already_has_members() -> None:
    assert len(list(OrderType)) > 0


def test_subclassing_ordertype_to_add_members_raises_typeerror() -> None:
    with pytest.raises(TypeError):

        class ExtendedOrderType(OrderType):  # type: ignore[misc]
            AUCTION = "AUCTION"
            TRAILING_STOP = "TRAILING_STOP"
