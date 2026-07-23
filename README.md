# vnpy_agentbridge

`IntentEngine` + MCP Bridge Server for AI-Agent-assisted trading on top of a
[VeighNa (vnpy)](https://github.com/vnpy/vnpy) fork. This package is
deliberately **not** part of the vnpy fork itself (see the "核心改动范围清单"
section of the deep-dive doc) — it is an independent, pip-installable app,
so syncing the fork with upstream never has to touch this code.

## Why this exists

An AI Agent that is allowed to read market/portfolio state and *suggest*
trades is useful. An AI Agent that can directly call
`MainEngine.send_order()` is a real-money incident waiting to happen —
prompt injection, a hallucinated parameter, or a bug in the Agent's own
reasoning loop turns straight into a live order with no human or rule
engine in the loop. This package exists to make "the Agent can propose,
never execute" a structural property of the system rather than a coding
convention someone has to remember to follow every time a new tool
function gets added.

## Two independent gates

1. **Structural (this package).** Every Agent-facing tool is exposed by
   `mcp_bridge.py`'s `FastMCP` server, which runs in the **same OS process
   as `MainEngine`**. The Agent's own process never imports
   `vnpy_agentbridge` and never holds a `main_engine`/`IntentEngine`
   reference — it only knows this server's URL (configured in the Agent's
   `.vnag/mcp_config.json`, see below) and reaches every tool over the MCP
   protocol. The one tool that writes anything,
   `order_submit_intent`, reaches `IntentEngine.create_intent()`
   exclusively; there is no tool on this server that calls
   `main_engine.send_order()` directly. Converting an approved intent into
   a real `OrderRequest` and calling `send_order()` happens only inside
   `IntentEngine.approve_intent()`.

2. **Mechanical (`vnpy_riskmanager`, reused unmodified).** Once
   `approve_intent()` calls `main_engine.send_order()`, that call runs
   through whatever `RiskEngine.patch_functions()` has installed — the
   same gate every other caller (GUI, CTA strategies) goes through. This
   package does not reimplement risk checks on `OrderRequest`; it adds a
   *different* tier, `IntentRuleTemplate` (see `template.py`), which
   inspects `OrderIntent` fields (`reasoning`, `confidence`) that
   `OrderRequest` does not carry and that `RiskEngine` therefore cannot
   see. **Load order matters**: `vnpy_riskmanager`'s `RiskEngine` must be
   added to `MainEngine` before any code has a chance to cache the
   original (unpatched) `main_engine.send_order` — add it as early as
   possible in your application's startup sequence.

## Package contents

| File | Purpose |
|---|---|
| `object.py` | `OrderIntent` / `IntentStatus` — never passed to `send_order()` directly |
| `order_request_ext.py` | `StopOrderRequest(OrderRequest)` — the M3-verified safe dataclass-subclassing extension pattern |
| `template.py` | `IntentRuleTemplate` — the Agent-intent-level rule tier |
| `rules/confidence_rule.py` | Example rule: reject empty reasoning / low-confidence intents |
| `engine.py` | `IntentEngine(BaseEngine)` — create/approve/reject/cancel lifecycle |
| `mcp_bridge.py` | `build_mcp_bridge()` — the FastMCP server exposing the Agent-facing tool surface |

## A note on `OrderType`

`OrderRequest` (a plain dataclass) can be safely subclassed — see
`order_request_ext.py` and `tests/test_order_request_ext.py`. `OrderType`
(a Python `Enum` that already defines members) **cannot** be extended the
same way; Python's `enum` module refuses to let an `Enum` with existing
members be subclassed to add new ones (`TypeError` at class-definition
time — a language rule, not a vnpy design choice).
`tests/test_enum_extension_blocked.py` encodes this as a permanent
regression test. If a genuinely new *structural* order type is ever
required (not just a new field), it has to be added to
`vnpy/trader/constant.py` in the fork itself — see the deep-dive doc's
"核心改动范围清单" section for exactly where and how small that change is.

## Running the tests

```bash
python -m pytest -q
```

Every test runs against a real `MainEngine`/`EventEngine` pair wired to a
`FakeGateway` (see `tests/conftest.py`) that records `OrderRequest`s
instead of sending them anywhere — no network access, no credentials, no
real orders, ever.

## Wiring this into a real application (not done by this package)

This package only provides the engine and the MCP server builder. Wiring
them into a running application means, roughly:

```python
main_engine = MainEngine(event_engine)
main_engine.add_engine(RiskEngine)      # vnpy_riskmanager — load this FIRST
intent_engine = main_engine.add_engine(IntentEngine)
intent_engine.add_rule(ConfidenceRule(min_confidence=0.6))

# ... add_gateway(...) for your real broker(s) ...

mcp = build_mcp_bridge(main_engine, intent_engine)
mcp.run(transport="http", host="127.0.0.1", port=8765)  # pick your own port/auth
```

The Agent process's `.vnag/mcp_config.json` would then point at
`http://127.0.0.1:8765/mcp` (or wherever this is actually served) — it
never imports this package.

Actually connecting a real broker gateway, exposing this server outside
localhost, and adding authentication are deliberately out of scope here —
none of that is safe to stand up without real credentials and an explicit
decision about who's allowed to approve intents, which is beyond what
this scaffold decides on its own.
