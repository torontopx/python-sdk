"""Toronto Protocol binary codec — CRC-16 and fixed-size message encode/decode.

Wire format: msg_type (1B) | payload | crc16 (2B), all little-endian.
Message sizes are fixed per type and must match the Rust wire structs exactly.
"""

import struct
from typing import Union

from .types import (
    NewOrder,
    CancelOrder,
    OrderAck,
    Fill,
    Reject,
    Heartbeat,
    Login,
    LoginAck,
    MarketSnapshot,
    DepthLevel,
)

# ── Message type tags ────────────────────────────────────────────────────────

MSG_NEW_ORDER = 0x01
MSG_CANCEL_ORDER = 0x02
MSG_ORDER_ACK = 0x10
MSG_FILL = 0x11
MSG_REJECT = 0x12
MSG_MARKET_SNAPSHOT = 0x20
MSG_RESOLVE_CONTRACT = 0x30
MSG_CREATE_CONTRACT = 0x31
MSG_TRANSITION_CONTRACT = 0x32
MSG_ADMIN_ACK = 0x33
MSG_HEARTBEAT = 0xF0
MSG_LOGIN = 0xF1
MSG_LOGIN_ACK = 0xF2

# ── Wire sizes (must match Rust repr(C, packed) structs) ─────────────────────

MSG_SIZES = {
    MSG_NEW_ORDER: 37,
    MSG_CANCEL_ORDER: 31,
    MSG_ORDER_ACK: 42,
    MSG_FILL: 50,
    MSG_REJECT: 32,
    MSG_MARKET_SNAPSHOT: 145,
    MSG_HEARTBEAT: 11,
    MSG_LOGIN: 67,
    MSG_LOGIN_ACK: 15,
    MSG_RESOLVE_CONTRACT: 8,
    MSG_CREATE_CONTRACT: 7,
    MSG_TRANSITION_CONTRACT: 8,
    MSG_ADMIN_ACK: 8,
}

# ── CRC-16/CCITT-FALSE ──────────────────────────────────────────────────────

_POLY = 0x1021
_INIT = 0xFFFF


def _generate_crc_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        table.append(crc)
    return table


_CRC_TABLE = _generate_crc_table()


def crc16(data: bytes) -> int:
    """Compute CRC-16/CCITT-FALSE over *data*."""
    crc = _INIT
    for b in data:
        idx = ((crc >> 8) ^ b) & 0xFF
        crc = ((crc << 8) ^ _CRC_TABLE[idx]) & 0xFFFF
    return crc


def _append_crc(buf: bytearray) -> bytes:
    c = crc16(bytes(buf))
    buf += struct.pack("<H", c)
    return bytes(buf)


def _check_crc(data: bytes) -> None:
    payload = data[:-2]
    wire_crc = struct.unpack_from("<H", data, len(data) - 2)[0]
    computed = crc16(payload)
    if wire_crc != computed:
        raise ValueError(f"CRC mismatch: expected 0x{computed:04X}, got 0x{wire_crc:04X}")


# ── Side / Outcome / OrderType / TimeInForce maps ───────────────────────────

SIDE_MAP = {"buy": 1, "sell": 2}
SIDE_REVERSE = {1: "buy", 2: "sell"}

OUTCOME_MAP = {"yes": 1, "no": 2}
OUTCOME_REVERSE = {1: "yes", 2: "no"}

ORDER_TYPE_MAP = {"limit": 1, "ioc": 2, "fok": 3}
ORDER_TYPE_REVERSE = {1: "limit", 2: "ioc", 3: "fok"}

TIF_MAP = {"gtc": 1, "day": 2}
TIF_REVERSE = {1: "gtc", 2: "day"}

REJECT_REASON_REVERSE = {
    0x01: "unknown_contract",
    0x02: "contract_not_open",
    0x03: "invalid_price",
    0x04: "invalid_quantity",
    0x05: "position_limit",
    0x06: "duplicate_sequence",
    0x07: "unknown_order",
    0x08: "auth_failed",
}

Message = Union[NewOrder, CancelOrder, OrderAck, Fill, Reject, Heartbeat, Login, LoginAck, MarketSnapshot]


# ── Encoders ─────────────────────────────────────────────────────────────────

def encode_login(msg: Login) -> bytes:
    buf = bytearray()
    buf += struct.pack("<B", MSG_LOGIN)
    buf += msg.api_key
    buf += msg.hmac_sig
    buf += struct.pack("<Q", msg.timestamp_ns)
    buf += struct.pack("<Q", msg.last_exchange_seq)
    return _append_crc(buf)


def encode_new_order(msg: NewOrder) -> bytes:
    buf = bytearray()
    buf += struct.pack("<B", MSG_NEW_ORDER)
    buf += struct.pack("<Q", msg.client_seq)
    buf += struct.pack("<I", msg.client_id)
    buf += struct.pack("<I", msg.contract_id)
    buf += struct.pack("<B", SIDE_MAP[msg.side])
    buf += struct.pack("<B", OUTCOME_MAP[msg.outcome])
    buf += struct.pack("<H", msg.price)
    buf += struct.pack("<I", msg.quantity)
    buf += struct.pack("<B", ORDER_TYPE_MAP[msg.order_type])
    buf += struct.pack("<B", TIF_MAP[msg.time_in_force])
    buf += struct.pack("<Q", msg.timestamp_ns)
    return _append_crc(buf)


def encode_cancel_order(msg: CancelOrder) -> bytes:
    buf = bytearray()
    buf += struct.pack("<B", MSG_CANCEL_ORDER)
    buf += struct.pack("<Q", msg.client_seq)
    buf += struct.pack("<I", msg.client_id)
    buf += struct.pack("<Q", msg.order_id)
    buf += struct.pack("<Q", msg.timestamp_ns)
    return _append_crc(buf)


def encode_heartbeat(msg: Heartbeat) -> bytes:
    buf = bytearray()
    buf += struct.pack("<B", MSG_HEARTBEAT)
    buf += struct.pack("<Q", msg.timestamp_ns)
    return _append_crc(buf)


def encode(msg: Message) -> bytes:
    if isinstance(msg, Login):
        return encode_login(msg)
    if isinstance(msg, NewOrder):
        return encode_new_order(msg)
    if isinstance(msg, CancelOrder):
        return encode_cancel_order(msg)
    if isinstance(msg, Heartbeat):
        return encode_heartbeat(msg)
    raise TypeError(f"cannot encode {type(msg).__name__}")


# ── Decoders ─────────────────────────────────────────────────────────────────

def _decode_order_ack(data: bytes) -> OrderAck:
    _check_crc(data)
    (_, exchange_seq, order_id, client_id, contract_id, price, quantity, side, ts) = struct.unpack_from(
        "<BQQIIHIB Q", data
    )
    return OrderAck(
        exchange_seq=exchange_seq,
        order_id=order_id,
        client_id=client_id,
        contract_id=contract_id,
        price=price,
        quantity=quantity,
        side=SIDE_REVERSE[side],
        timestamp_ns=ts,
    )


def _decode_fill(data: bytes) -> Fill:
    _check_crc(data)
    (_, exchange_seq, order_id, contra_order_id, client_id, contract_id, side, price, fill_qty, ts) = struct.unpack_from(
        "<BQQQ II B H I Q", data
    )
    return Fill(
        exchange_seq=exchange_seq,
        order_id=order_id,
        contra_order_id=contra_order_id,
        client_id=client_id,
        contract_id=contract_id,
        side=SIDE_REVERSE[side],
        price=price,
        fill_quantity=fill_qty,
        timestamp_ns=ts,
    )


def _decode_reject(data: bytes) -> Reject:
    _check_crc(data)
    (_, exchange_seq, client_id, order_id, reason, ts) = struct.unpack_from(
        "<BQ I Q B Q", data
    )
    return Reject(
        exchange_seq=exchange_seq,
        client_id=client_id,
        order_id=order_id,
        reason=REJECT_REASON_REVERSE.get(reason, f"unknown({reason})"),
        timestamp_ns=ts,
    )


def _decode_login_ack(data: bytes) -> LoginAck:
    _check_crc(data)
    (_, client_id, ts) = struct.unpack_from("<B I Q", data)
    return LoginAck(client_id=client_id, timestamp_ns=ts)


def _decode_heartbeat(data: bytes) -> Heartbeat:
    _check_crc(data)
    (_, ts) = struct.unpack_from("<B Q", data)
    return Heartbeat(timestamp_ns=ts)


def _decode_market_snapshot(data: bytes) -> MarketSnapshot:
    _check_crc(data)
    offset = 0
    (_, contract_id, best_bid, best_ask, last_trade_price, volume_today) = struct.unpack_from(
        "<BIHHHI", data, offset
    )
    offset = 1 + 4 + 2 + 2 + 2 + 4  # 15 bytes

    bid_levels = []
    for _ in range(10):
        (price, qty) = struct.unpack_from("<HI", data, offset)
        bid_levels.append(DepthLevel(price=price, quantity=qty))
        offset += 6

    ask_levels = []
    for _ in range(10):
        (price, qty) = struct.unpack_from("<HI", data, offset)
        ask_levels.append(DepthLevel(price=price, quantity=qty))
        offset += 6

    (ts,) = struct.unpack_from("<Q", data, offset)

    return MarketSnapshot(
        contract_id=contract_id,
        best_bid=best_bid,
        best_ask=best_ask,
        last_trade_price=last_trade_price,
        volume_today=volume_today,
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        timestamp_ns=ts,
    )


def decode(data: bytes) -> Message:
    """Decode a complete wire message (including msg_type byte and CRC)."""
    if not data:
        raise ValueError("empty buffer")
    msg_type = data[0]
    expected_size = MSG_SIZES.get(msg_type)
    if expected_size is None:
        raise ValueError(f"unknown message type: 0x{msg_type:02X}")
    if len(data) < expected_size:
        raise ValueError(f"buffer too short: expected {expected_size}, got {len(data)}")
    data = data[:expected_size]

    if msg_type == MSG_ORDER_ACK:
        return _decode_order_ack(data)
    if msg_type == MSG_FILL:
        return _decode_fill(data)
    if msg_type == MSG_REJECT:
        return _decode_reject(data)
    if msg_type == MSG_LOGIN_ACK:
        return _decode_login_ack(data)
    if msg_type == MSG_HEARTBEAT:
        return _decode_heartbeat(data)
    if msg_type == MSG_MARKET_SNAPSHOT:
        return _decode_market_snapshot(data)
    raise ValueError(f"decoder not implemented for 0x{msg_type:02X}")


def read_message(sock) -> Message:
    """Read one framed Toronto Protocol message from a socket."""
    type_byte = _recv_exact(sock, 1)
    msg_type = type_byte[0]
    size = MSG_SIZES.get(msg_type)
    if size is None:
        raise ValueError(f"unknown message type: 0x{msg_type:02X}")
    rest = _recv_exact(sock, size - 1)
    return decode(type_byte + rest)


def _recv_exact(sock, n: int) -> bytes:
    """Read exactly *n* bytes from *sock*, raising on short read."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf += chunk
    return buf
