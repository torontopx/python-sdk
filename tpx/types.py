"""Data types for Toronto Protocol messages."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Login:
    api_key: bytes
    hmac_sig: bytes
    timestamp_ns: int
    last_exchange_seq: int = 0


@dataclass
class LoginAck:
    client_id: int
    timestamp_ns: int


@dataclass
class NewOrder:
    client_seq: int
    client_id: int
    contract_id: int
    side: str          # "buy" | "sell"
    outcome: str       # "yes" | "no"
    price: int         # 1–999 tenths of a cent
    quantity: int
    order_type: str    # "limit" | "ioc" | "fok"
    time_in_force: str  # "gtc" | "day"
    timestamp_ns: int


@dataclass
class CancelOrder:
    client_seq: int
    client_id: int
    order_id: int
    timestamp_ns: int


@dataclass
class OrderAck:
    exchange_seq: int
    order_id: int
    client_id: int
    contract_id: int
    price: int
    quantity: int
    side: str
    timestamp_ns: int


@dataclass
class Fill:
    exchange_seq: int
    order_id: int
    contra_order_id: int
    client_id: int
    contract_id: int
    side: str
    price: int
    fill_quantity: int
    timestamp_ns: int


@dataclass
class Reject:
    exchange_seq: int
    client_id: int
    order_id: int
    reason: str
    timestamp_ns: int


@dataclass
class Heartbeat:
    timestamp_ns: int


@dataclass
class DepthLevel:
    price: int
    quantity: int


@dataclass
class MarketSnapshot:
    contract_id: int
    best_bid: int
    best_ask: int
    last_trade_price: int
    volume_today: int
    bid_levels: list = field(default_factory=list)
    ask_levels: list = field(default_factory=list)
    timestamp_ns: int = 0
