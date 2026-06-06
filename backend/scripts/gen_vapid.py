"""Generate a VAPID keypair for Web Push.

Prints three lines ready to paste into the prod `.env`. Run it ON THE VPS
so the private key never leaves production:

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
      exec backend python -m scripts.gen_vapid

- VAPID_PUBLIC_KEY  : base64url uncompressed EC point — served to browsers
                      as the `applicationServerKey`.
- VAPID_PRIVATE_KEY : base64url raw P-256 scalar — signs each push JWT.
- VAPID_SUBJECT     : a real mailto:/https: contact (iOS rejects junk).

The format matches what `services/push.py` (pywebpush) consumes — verified
by `_self_check()` below, which signs a throwaway JWT before printing.
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _self_check(private_b64u: str) -> None:
    """Confirm pywebpush/py-vapid can load the key string and sign a JWT."""
    v = Vapid01.from_string(private_key=private_b64u)
    headers = v.sign({"aud": "https://web.push.apple.com", "sub": "mailto:test@example.com"})
    assert headers.get("Authorization"), "VAPID self-check failed: no Authorization header"


def main() -> None:
    vapid = Vapid01()
    vapid.generate_keys()

    private_value = vapid.private_key.private_numbers().private_value
    private_b64u = _b64u(private_value.to_bytes(32, "big"))
    public_point = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64u = _b64u(public_point)

    _self_check(private_b64u)

    print(f"VAPID_PUBLIC_KEY={public_b64u}")
    print(f"VAPID_PRIVATE_KEY={private_b64u}")
    print("VAPID_SUBJECT=mailto:aarohiluke@gmail.com")


if __name__ == "__main__":
    main()
