"""High-level trading client for the Toronto Prediction Exchange.

Connects via TCP, authenticates with HMAC-SHA256, sends orders, and
streams fills/acks in a background reader thread. A heartbeat thread
keeps the session alive.
"""

import socket
import threading
import time
from typing import Callable, Optional

from .auth import compute_hmac
from .exceptions import AuthError, RejectError
from .protocol import (
    encode,
    read_message,
    MSG_SIZES,
)
from .types import (
    CancelOrder,
    Fill,
    Heartbeat,
    Login,
    LoginAck,
    NewOrder,
    OrderAck,
    Reject,
)


def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


class TpxClient:
    """Synchronous trading client for the Toronto Prediction Exchange.

    Usage::

        client = TpxClient(
            host="127.0.0.1",
            port=9000,
            api_key=bytes.fromhex("123123"),
            secret=bytes.fromhex("123123"),
        )
        client.connect()
        ack = client.place_order(contract_id=1, side="buy", outcome="yes", price=500, quantity=10)
        client.disconnect()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        api_key: bytes = b"",
        secret: bytes = b"",
        heartbeat_interval: float = 0.5,
        response_timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.secret = secret
        self.heartbeat_interval = heartbeat_interval
        self.response_timeout = response_timeout

        self._sock: Optional[socket.socket] = None
        self._client_seq = 0
        self._client_id = 0
        self._write_lock = threading.Lock()
        self._connected = False

        self._reader_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._pending: dict[int, threading.Event] = {}
        self._responses: dict[int, object] = {}
        self._response_lock = threading.Lock()

        self._on_fill: Optional[Callable[[Fill], None]] = None
        self._on_reject: Optional[Callable[[Reject], None]] = None
        self._on_ack: Optional[Callable[[OrderAck], None]] = None

    def on_fill(self, callback: Callable[[Fill], None]) -> None:
        """Register a callback invoked for each Fill received."""
        self._on_fill = callback

    def on_reject(self, callback: Callable[[Reject], None]) -> None:
        """Register a callback invoked for each Reject received."""
        self._on_reject = callback

    def on_ack(self, callback: Callable[[OrderAck], None]) -> None:
        """Register a callback invoked for each OrderAck received."""
        self._on_ack = callback

    def connect(self) -> LoginAck:
        """Connect to the gateway, perform the HMAC login, and start
        background heartbeat/reader threads.

        Returns the ``LoginAck`` on success.
        Raises ``AuthError`` if the server rejects the login.
        """
        self._sock = socket.create_connection((self.host, self.port), timeout=self.response_timeout)
        self._sock.settimeout(self.response_timeout)

        ts = _now_ns()
        hmac_sig = compute_hmac(self.secret, self.api_key, ts)
        login = Login(api_key=self.api_key, hmac_sig=hmac_sig, timestamp_ns=ts)
        self._send(login)

        resp = read_message(self._sock)
        if isinstance(resp, LoginAck):
            self._client_id = resp.client_id
            self._connected = True
            self._stop_event.clear()
            self._sock.settimeout(1.0)  # non-blocking-ish for reader
            self._start_threads()
            return resp
        if isinstance(resp, Reject):
            self._sock.close()
            raise AuthError(f"login rejected: {resp.reason}")
        self._sock.close()
        raise AuthError(f"unexpected response: {type(resp).__name__}")

    def disconnect(self) -> None:
        """Stop background threads and close the connection."""
        self._connected = False
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def place_order(
        self,
        contract_id: int,
        side: str,
        outcome: str,
        price: int,
        quantity: int,
        order_type: str = "limit",
        time_in_force: str = "gtc",
    ) -> OrderAck:
        """Send a NewOrder and block until an OrderAck or Reject is received.

        Returns ``OrderAck`` on success.
        Raises ``RejectError`` if the order is rejected.
        Raises ``TimeoutError`` if no response within ``response_timeout``.
        """
        self._client_seq += 1
        seq = self._client_seq

        event = threading.Event()
        with self._response_lock:
            self._pending[seq] = event

        order = NewOrder(
            client_seq=seq,
            client_id=0,
            contract_id=contract_id,
            side=side,
            outcome=outcome,
            price=price,
            quantity=quantity,
            order_type=order_type,
            time_in_force=time_in_force,
            timestamp_ns=_now_ns(),
        )
        self._send(order)

        if not event.wait(timeout=self.response_timeout):
            with self._response_lock:
                self._pending.pop(seq, None)
            from .exceptions import TimeoutError
            raise TimeoutError(f"no response for client_seq={seq}")

        with self._response_lock:
            resp = self._responses.pop(seq, None)
            self._pending.pop(seq, None)

        if isinstance(resp, OrderAck):
            return resp
        if isinstance(resp, Reject):
            raise RejectError(resp.reason, resp.order_id)
        raise RuntimeError(f"unexpected response type: {type(resp)}")

    def cancel_order(self, order_id: int) -> OrderAck:
        """Send a CancelOrder and block until an ack or reject is received.

        Returns ``OrderAck`` with quantity=0 on success.
        Raises ``RejectError`` if the cancel fails (e.g., unknown order).
        """
        self._client_seq += 1
        seq = self._client_seq

        event = threading.Event()
        with self._response_lock:
            self._pending[seq] = event

        cancel = CancelOrder(
            client_seq=seq,
            client_id=0,
            order_id=order_id,
            timestamp_ns=_now_ns(),
        )
        self._send(cancel)

        if not event.wait(timeout=self.response_timeout):
            with self._response_lock:
                self._pending.pop(seq, None)
            from .exceptions import TimeoutError
            raise TimeoutError(f"no response for cancel client_seq={seq}")

        with self._response_lock:
            resp = self._responses.pop(seq, None)
            self._pending.pop(seq, None)

        if isinstance(resp, OrderAck):
            return resp
        if isinstance(resp, Reject):
            raise RejectError(resp.reason, resp.order_id)
        raise RuntimeError(f"unexpected response type: {type(resp)}")

    # ── Internal ─────────────────────────────────────────────────────────

    def _send(self, msg) -> None:
        data = encode(msg)
        with self._write_lock:
            self._sock.sendall(data)

    def _start_threads(self) -> None:
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.heartbeat_interval)
            if self._stop_event.is_set():
                break
            try:
                self._send(Heartbeat(timestamp_ns=_now_ns()))
            except OSError:
                break

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = read_message(self._sock)
            except socket.timeout:
                continue
            except (ConnectionError, OSError, ValueError):
                break

            self._dispatch(msg)

    def _dispatch(self, msg) -> None:
        if isinstance(msg, OrderAck):
            if self._on_ack:
                self._on_ack(msg)
            self._resolve_first_pending(msg)

        elif isinstance(msg, Fill):
            if self._on_fill:
                self._on_fill(msg)

        elif isinstance(msg, Reject):
            if self._on_reject:
                self._on_reject(msg)
            self._resolve_first_pending(msg)

    def _resolve_first_pending(self, msg) -> None:
        """Resolve the oldest pending request with this response.

        The exchange doesn't echo back ``client_seq``, so we resolve
        requests in FIFO order.
        """
        with self._response_lock:
            if not self._pending:
                return
            seq = min(self._pending.keys())
            event = self._pending.get(seq)
            if event:
                self._responses[seq] = msg
                event.set()
