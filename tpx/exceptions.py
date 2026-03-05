"""Exception types for the TPX Python SDK."""


class TpxError(Exception):
    """Base exception for all TPX errors."""


class AuthError(TpxError):
    """Authentication failed (bad API key, HMAC, or expired timestamp)."""


class ConnectionError(TpxError):
    """Connection to the gateway was lost or could not be established."""


class RejectError(TpxError):
    """Order was rejected by the exchange."""

    def __init__(self, reason: str, order_id: int = 0):
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"order rejected: {reason}")


class TimeoutError(TpxError):
    """Operation timed out waiting for a response."""
