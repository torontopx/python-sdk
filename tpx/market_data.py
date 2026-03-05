"""Multicast UDP receiver for TPX market data snapshots.

Joins the configured multicast group and decodes ``MarketSnapshot`` messages
published by ``tpx-feed``.  Pure Python — no external dependencies.
"""

import socket
import struct
import threading
from typing import Callable, Optional

from .protocol import _decode_market_snapshot, MSG_MARKET_SNAPSHOT, MSG_SIZES
from .types import MarketSnapshot


class TpxMarketDataReceiver:
    """Receives ``MarketSnapshot`` datagrams from the TPX multicast feed.

    Usage::

        receiver = TpxMarketDataReceiver()
        receiver.start(lambda snap: print(snap))
        # ... later ...
        receiver.stop()

    Or blocking one-at-a-time::

        receiver = TpxMarketDataReceiver()
        snap = receiver.recv_snapshot()
    """

    def __init__(
        self,
        multicast_group: str = "239.1.1.1",
        port: int = 5555,
        interface: str = "0.0.0.0",
    ):
        self.multicast_group = multicast_group
        self.port = port
        self.interface = interface

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _ensure_socket(self) -> socket.socket:
        if self._sock is not None:
            return self._sock

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind(("", self.port))

        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(self.multicast_group),
            socket.inet_aton(self.interface),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        self._sock = sock
        return sock

    def recv_snapshot(self, timeout: Optional[float] = None) -> MarketSnapshot:
        """Block until a ``MarketSnapshot`` datagram arrives and return it.

        Raises ``TimeoutError`` if *timeout* seconds elapse with no data.
        """
        sock = self._ensure_socket()
        sock.settimeout(timeout)

        expected_size = MSG_SIZES[MSG_MARKET_SNAPSHOT]
        data, _addr = sock.recvfrom(expected_size + 64)

        if len(data) < expected_size:
            raise ValueError(
                f"datagram too short: expected {expected_size}, got {len(data)}"
            )

        return _decode_market_snapshot(data[:expected_size])

    def start(self, callback: Callable[[MarketSnapshot], None]) -> None:
        """Start a background thread that invokes *callback* for each snapshot."""
        if self._thread is not None:
            raise RuntimeError("receiver already started")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._reader_loop, args=(callback,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background reader thread and close the socket."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _reader_loop(self, callback: Callable[[MarketSnapshot], None]) -> None:
        sock = self._ensure_socket()
        sock.settimeout(0.5)
        expected_size = MSG_SIZES[MSG_MARKET_SNAPSHOT]

        while not self._stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(expected_size + 64)
            except socket.timeout:
                continue
            except OSError:
                break

            if len(data) < expected_size:
                continue

            try:
                snap = _decode_market_snapshot(data[:expected_size])
                callback(snap)
            except (ValueError, struct.error):
                continue
