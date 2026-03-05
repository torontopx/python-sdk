"""HTTP query client for the TPX engine market data API.

Provides read-only access to resting orders, trade history (including
marriages and divorces), positions, contracts, and full order book depth.
Uses the engine's HTTP API (default port 9002) — no Toronto Protocol
connection or authentication required.

Pure Python — only uses ``urllib`` from the standard library.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RestingOrder:
    order_id: int
    client_id: int
    contract_id: int
    side: str
    outcome: str
    price: int
    quantity: int
    filled_quantity: int
    remaining_quantity: int
    order_type: str
    time_in_force: str
    timestamp_ns: int


@dataclass
class Trade:
    exchange_seq: int
    timestamp_ns: int
    incoming_order_id: int
    resting_order_id: int
    incoming_client_id: int
    resting_client_id: int
    contract_id: int
    side: str
    price: int
    quantity: int
    match_type: str  # "normal" | "marriage" | "divorce"


@dataclass
class Position:
    client_id: int
    contract_id: int
    net_yes_qty: int
    cost_basis: int
    unrealized_pnl: int


@dataclass
class Contract:
    id: int
    status: str
    outcome: Optional[str] = None


@dataclass
class BookLevel:
    price: int
    quantity: int
    order_count: int


@dataclass
class BookDepth:
    contract_id: int
    buy_yes: list = field(default_factory=list)
    sell_yes: list = field(default_factory=list)
    buy_no: list = field(default_factory=list)
    sell_no: list = field(default_factory=list)


class TpxQueryClient:
    """Read-only HTTP client for the TPX engine query API.

    Usage::

        qc = TpxQueryClient()  # default http://127.0.0.1:9002
        orders = qc.get_orders(contract_id=1)
        trades = qc.get_trades(match_type="marriage")
        positions = qc.get_positions(client_id=1)
        contracts = qc.get_contracts()
        book = qc.get_book(contract_id=1)
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9002",
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_orders(
        self,
        contract_id: Optional[int] = None,
        client_id: Optional[int] = None,
    ) -> list[RestingOrder]:
        """Fetch resting orders, optionally filtered by contract or client."""
        params = {}
        if contract_id is not None:
            params["contract_id"] = contract_id
        if client_id is not None:
            params["client_id"] = client_id
        data = self._get("/api/v1/orders", params)
        return [RestingOrder(**o) for o in data]

    def get_trades(
        self,
        contract_id: Optional[int] = None,
        match_type: Optional[str] = None,
    ) -> list[Trade]:
        """Fetch trade history, optionally filtered by contract or match type.

        ``match_type`` can be ``"normal"``, ``"marriage"``, or ``"divorce"``.
        """
        params = {}
        if contract_id is not None:
            params["contract_id"] = contract_id
        if match_type is not None:
            params["match_type"] = match_type
        data = self._get("/api/v1/trades", params)
        return [Trade(**t) for t in data]

    def get_positions(
        self,
        client_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> list[Position]:
        """Fetch positions, optionally filtered by client or contract."""
        params = {}
        if client_id is not None:
            params["client_id"] = client_id
        if contract_id is not None:
            params["contract_id"] = contract_id
        data = self._get("/api/v1/positions", params)
        return [Position(**p) for p in data]

    def get_contracts(self) -> list[Contract]:
        """Fetch all contracts with their current status."""
        data = self._get("/api/v1/contracts")
        return [Contract(**c) for c in data]

    def get_book(self, contract_id: int) -> BookDepth:
        """Fetch the full order book depth for a contract (all 4 quadrants)."""
        data = self._get(f"/api/v1/book/{contract_id}")
        return BookDepth(
            contract_id=data["contract_id"],
            buy_yes=[BookLevel(**l) for l in data.get("buy_yes", [])],
            sell_yes=[BookLevel(**l) for l in data.get("sell_yes", [])],
            buy_no=[BookLevel(**l) for l in data.get("buy_no", [])],
            sell_no=[BookLevel(**l) for l in data.get("sell_no", [])],
        )

    def _get(self, path: str, params: Optional[dict] = None) -> object:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"cannot reach engine at {self.base_url}: {e.reason}") from e
