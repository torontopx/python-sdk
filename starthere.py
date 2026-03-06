from tpx import TpxClient, TpxQueryClient, TpxMarketDataReceiver

# ── Configuration ─────────────────────────────────────────────────────────────
# Edit these variables, then run: python starthere.py

# Gateway (TCP trading connection)
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9000

# Credentials (hex-encoded; get yours via `tpx-admin create-api-key`)
API_KEY = "123123"
SECRET  = "123123"

# Engine HTTP query API
QUERY_API_URL = "http://127.0.0.1:9002"

# Market data multicast feed
MARKET_DATA_GROUP = "239.1.1.1"
MARKET_DATA_PORT  = 5555

# ──────────────────────────────────────────────────────────────────────────────

client = TpxClient(
    host=GATEWAY_HOST,
    port=GATEWAY_PORT,
    api_key=bytes.fromhex(API_KEY),
    secret=bytes.fromhex(SECRET),
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

# ── Query API usage (uncomment to try) ────────────────────────────────────────
#
# qc = TpxQueryClient(base_url=QUERY_API_URL, api_key=API_KEY)
# orders = qc.get_orders(contract_id=1)
# for o in orders:
#     print(f"{o.side} {o.outcome} {o.remaining_quantity}@{o.price}")

qc = TpxQueryClient(base_url=QUERY_API_URL, api_key=API_KEY)
book = qc.get_book(contract_id=1)
print(f"Buy Yes:  {[(l.price, l.quantity) for l in book.buy_yes]}")
print(f"Sell Yes: {[(l.price, l.quantity) for l in book.sell_yes]}")
print(f"Buy No:   {[(l.price, l.quantity) for l in book.buy_no]}")
print(f"Sell No:  {[(l.price, l.quantity) for l in book.sell_no]}")

# ── Market data usage (uncomment to try) ──────────────────────────────────────
#
# receiver = TpxMarketDataReceiver(
#     multicast_group=MARKET_DATA_GROUP,
#     port=MARKET_DATA_PORT,
# )
# snap = receiver.recv_snapshot(timeout=5.0)
# print(f"contract={snap.contract_id} bid={snap.best_bid} ask={snap.best_ask}")
