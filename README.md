# TPX Python SDK

Python client library for the Toronto Prediction Exchange (TPX). Implements the Toronto Protocol binary codec, HMAC-SHA256 authentication, and a high-level trading client.

**Pure Python** — no external dependencies beyond the standard library.

## Installation

```bash
pip install -e sdk/python
```

Or copy the `tpx/` directory into your project.

## Quick Start

```python
from tpx import TpxClient

client = TpxClient(
    host="127.0.0.1",
    port=9000,
    api_key=bytes.fromhex("01" * 16),
    secret=bytes.fromhex("aa" * 32),
)

# Connect and authenticate
login_ack = client.connect()
print(f"Logged in as client_id={login_ack.client_id}")

# Place a limit order: Buy 10 Yes contracts at 50.0¢
ack = client.place_order(
    contract_id=1,
    side="buy",
    outcome="yes",
    price=500,       # tenths of a cent (500 = 50.0¢)
    quantity=10,
    order_type="limit",
    time_in_force="gtc",
)
print(f"Order placed: order_id={ack.order_id}")

# Register callbacks for fills
client.on_fill(lambda fill: print(f"Fill: {fill.fill_quantity} @ {fill.price}"))

# Cancel the order
cancel_ack = client.cancel_order(order_id=ack.order_id)
print("Order cancelled")

# Disconnect
client.disconnect()
```

## Market Data

Receive real-time `MarketSnapshot` messages published by `tpx-feed` over UDP multicast:

```python
from tpx import TpxMarketDataReceiver

receiver = TpxMarketDataReceiver(
    multicast_group="239.1.1.1",
    port=5555,
)

# Blocking — receive a single snapshot
snap = receiver.recv_snapshot(timeout=5.0)
print(f"contract={snap.contract_id} bid={snap.best_bid} ask={snap.best_ask}")
print(f"last_trade={snap.last_trade_price} volume={snap.volume_today}")
for lvl in snap.bid_levels[:3]:
    print(f"  bid {lvl.price}: {lvl.quantity}")

# Or stream snapshots in a background thread
receiver.start(lambda snap: print(f"tick: bid={snap.best_bid} ask={snap.best_ask}"))
# ... later ...
receiver.stop()
```

### `TpxMarketDataReceiver`

| Method                                     | Description                                            |
| ------------------------------------------ | ------------------------------------------------------ |
| `recv_snapshot(timeout) -> MarketSnapshot` | Block until a snapshot arrives. Raises `TimeoutError`. |
| `start(callback)`                          | Start a background thread that calls `callback(snap)`. |
| `stop()`                                   | Stop the background thread and close the socket.       |

### Constructor Parameters

| Parameter         | Default       | Description               |
| ----------------- | ------------- | ------------------------- |
| `multicast_group` | `"239.1.1.1"` | Multicast group address   |
| `port`            | `5555`        | UDP port                  |
| `interface`       | `"0.0.0.0"`   | Network interface to bind |

### `MarketSnapshot` Fields

| Field              | Type               | Description                                   |
| ------------------ | ------------------ | --------------------------------------------- |
| `contract_id`      | `int`              | Contract identifier                           |
| `best_bid`         | `int`              | Best bid price (tenths of a cent)             |
| `best_ask`         | `int`              | Best ask price (tenths of a cent)             |
| `last_trade_price` | `int`              | Last trade price (tenths of a cent)           |
| `volume_today`     | `int`              | Cumulative volume traded today                |
| `bid_levels`       | `list[DepthLevel]` | Top 10 bid levels (price + quantity)          |
| `ask_levels`       | `list[DepthLevel]` | Top 10 ask levels (price + quantity)          |
| `timestamp_ns`     | `int`              | Exchange timestamp in nanoseconds since epoch |

## Engine Query API

Query live exchange state — resting orders, trade history (including marriages and divorces), positions, contracts, and full order book depth — via the engine's HTTP API. No authentication or Toronto Protocol connection required.

```python
from tpx import TpxQueryClient

qc = TpxQueryClient()  # default http://127.0.0.1:9002

# Resting orders (optionally filter by contract_id or client_id)
orders = qc.get_orders(contract_id=1)
for o in orders:
    print(f"{o.side} {o.outcome} {o.remaining_quantity}@{o.price}")

# Trade history — all trades, or filter by match_type
all_trades = qc.get_trades()
marriages = qc.get_trades(match_type="marriage")
divorces = qc.get_trades(match_type="divorce")

# Positions
positions = qc.get_positions(client_id=1)
for p in positions:
    print(f"contract={p.contract_id} net_yes={p.net_yes_qty} cost={p.cost_basis}")

# Contracts and their lifecycle status
contracts = qc.get_contracts()
for c in contracts:
    print(f"contract {c.id}: {c.status}")

# Full order book depth (all 4 quadrants, all levels)
book = qc.get_book(contract_id=1)
for lvl in book.buy_yes:
    print(f"  BID YES {lvl.quantity}@{lvl.price} ({lvl.order_count} orders)")
for lvl in book.sell_yes:
    print(f"  ASK YES {lvl.quantity}@{lvl.price} ({lvl.order_count} orders)")
```

### `TpxQueryClient`

| Method                                                       | Description                                                       |
| ------------------------------------------------------------ | ----------------------------------------------------------------- |
| `get_orders(contract_id?, client_id?) -> list[RestingOrder]` | Resting orders in the book                                        |
| `get_trades(contract_id?, match_type?) -> list[Trade]`       | Trade history (match_type: `"normal"`, `"marriage"`, `"divorce"`) |
| `get_positions(client_id?, contract_id?) -> list[Position]`  | Position ledger                                                   |
| `get_contracts() -> list[Contract]`                          | All contracts with status                                         |
| `get_book(contract_id) -> BookDepth`                         | Full order book depth                                             |

### Constructor Parameters

| Parameter  | Default                   | Description                |
| ---------- | ------------------------- | -------------------------- |
| `base_url` | `"http://127.0.0.1:9002"` | Engine HTTP query API URL  |
| `timeout`  | `5.0`                     | Request timeout in seconds |

### Key Types

| Type           | Fields                                                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RestingOrder` | `order_id`, `client_id`, `contract_id`, `side`, `outcome`, `price`, `quantity`, `filled_quantity`, `remaining_quantity`, `order_type`, `time_in_force`, `timestamp_ns`       |
| `Trade`        | `exchange_seq`, `timestamp_ns`, `incoming_order_id`, `resting_order_id`, `incoming_client_id`, `resting_client_id`, `contract_id`, `side`, `price`, `quantity`, `match_type` |
| `Position`     | `client_id`, `contract_id`, `net_yes_qty`, `cost_basis`, `unrealized_pnl`                                                                                                    |
| `Contract`     | `id`, `status`, `outcome`                                                                                                                                                    |
| `BookDepth`    | `contract_id`, `buy_yes`, `sell_yes`, `buy_no`, `sell_no` (each a list of `BookLevel`)                                                                                       |
| `BookLevel`    | `price`, `quantity`, `order_count`                                                                                                                                           |

## Getting Your API Key

Ask your exchange administrator to generate credentials using the admin CLI:

```bash
tpx-admin create-api-key
# Output:
# client_id: 3
# api_key:   a3f8c1...  (32 hex chars = 16 bytes)
# secret:    c7b1e2...  (64 hex chars = 32 bytes)
```

Use the hex-encoded values:

```python
client = TpxClient(
    api_key=bytes.fromhex("a3f8c1..."),
    secret=bytes.fromhex("c7b1e2..."),
)
```

## API Reference

### `TpxClient`

| Method                               | Description                                                       |
| ------------------------------------ | ----------------------------------------------------------------- |
| `connect() -> LoginAck`              | Connect and authenticate. Starts heartbeat and reader threads.    |
| `disconnect()`                       | Stop threads and close the connection.                            |
| `place_order(...) -> OrderAck`       | Send a NewOrder, block until ack. Raises `RejectError` on reject. |
| `cancel_order(order_id) -> OrderAck` | Send a CancelOrder, block until ack.                              |
| `on_fill(callback)`                  | Register a callback for Fill messages.                            |
| `on_ack(callback)`                   | Register a callback for OrderAck messages.                        |
| `on_reject(callback)`                | Register a callback for Reject messages.                          |

### Constructor Parameters

| Parameter            | Default       | Description                         |
| -------------------- | ------------- | ----------------------------------- |
| `host`               | `"127.0.0.1"` | Gateway hostname                    |
| `port`               | `9000`        | Gateway TCP port                    |
| `api_key`            | `b""`         | 16-byte API key                     |
| `secret`             | `b""`         | 32-byte shared secret               |
| `heartbeat_interval` | `0.5`         | Seconds between heartbeats          |
| `response_timeout`   | `5.0`         | Seconds to wait for order responses |

### Order Parameters

| Parameter       | Values                      | Description                                                    |
| --------------- | --------------------------- | -------------------------------------------------------------- |
| `side`          | `"buy"`, `"sell"`           | Order side                                                     |
| `outcome`       | `"yes"`, `"no"`             | Contract outcome                                               |
| `price`         | 1–999                       | Price in tenths of a cent. Yes + No prices always sum to 1000. |
| `order_type`    | `"limit"`, `"ioc"`, `"fok"` | Limit, Immediate-or-Cancel, Fill-or-Kill                       |
| `time_in_force` | `"gtc"`, `"day"`            | Good-til-Cancel or Day                                         |

## Protocol Details

The SDK implements the full Toronto Protocol binary wire format:

- Fixed-size messages with `msg_type (1B) | payload | crc16 (2B)`
- CRC-16/CCITT-FALSE integrity check
- HMAC-SHA256 login: `HMAC(secret, api_key || timestamp_ns_le)`
- Heartbeats sent every 500ms to keep the session alive
- Background reader thread dispatches fills and acks
