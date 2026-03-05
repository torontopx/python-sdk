"""HMAC-SHA256 authentication matching the Toronto Protocol login handshake.

The HMAC is computed over: api_key (16 bytes) || timestamp_ns (8 bytes LE)
using the shared_secret as the HMAC key.
"""

import hmac
import hashlib
import struct


def compute_hmac(shared_secret: bytes, api_key: bytes, timestamp_ns: int) -> bytes:
    """Compute the HMAC-SHA256 signature for a Login message.

    Returns 32 bytes matching the Rust ``compute_hmac`` function.
    """
    msg = api_key + struct.pack("<Q", timestamp_ns)
    return hmac.new(shared_secret, msg, hashlib.sha256).digest()
