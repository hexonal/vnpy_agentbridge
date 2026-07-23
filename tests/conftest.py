"""
Shared fixtures: a real MainEngine/EventEngine pair wired to a minimal fake
gateway that records send_order() calls instead of talking to any real
broker. Used by every test that needs to exercise the full
create_intent -> approve_intent -> main_engine.send_order path without
network access or credentials.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.engine import MainEngine
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import CancelRequest, OrderRequest

from vnpy_agentbridge.engine import IntentEngine


class FakeGateway(BaseGateway):
    """Records every OrderRequest it receives instead of sending it anywhere real."""

    default_name = "FAKE"
    exchanges = [Exchange.SEHK, Exchange.SMART]

    def __init__(self, event_engine: EventEngine, gateway_name: str) -> None:
        super().__init__(event_engine, gateway_name)
        self.sent_requests: list[OrderRequest] = []
        self._next_orderid = 0

    def connect(self, setting: dict) -> None:
        return

    def close(self) -> None:
        return

    def subscribe(self, req) -> None:  # noqa: ANN001
        return

    def send_order(self, req: OrderRequest) -> str:
        self.sent_requests.append(req)
        self._next_orderid += 1
        orderid = f"fake{self._next_orderid}"
        return f"{self.gateway_name}.{orderid}"

    def cancel_order(self, req: CancelRequest) -> None:
        return

    def query_account(self) -> None:
        return

    def query_position(self) -> None:
        return


@pytest.fixture()
def event_engine() -> EventEngine:
    # Not started here: MainEngine.__init__ starts the event engine it is
    # given, and MainEngine.close() stops it — starting/stopping it again
    # here would double-start the same background thread.
    return EventEngine()


@pytest.fixture()
def main_engine(event_engine: EventEngine) -> Iterator[MainEngine]:
    engine = MainEngine(event_engine)
    engine.add_gateway(FakeGateway, "FAKE")
    yield engine
    engine.close()


@pytest.fixture()
def fake_gateway(main_engine: MainEngine) -> FakeGateway:
    gateway = main_engine.get_gateway("FAKE")
    assert isinstance(gateway, FakeGateway)
    return gateway


@pytest.fixture()
def intent_engine(main_engine: MainEngine) -> IntentEngine:
    # add_engine() takes the class and constructs it internally with
    # (main_engine, event_engine) — matches vnpy_riskmanager's own pattern.
    return main_engine.add_engine(IntentEngine)
