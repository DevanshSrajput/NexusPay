"""x402 server-side payment enforcement for the mock data servers.

Builds 402 responses advertising payment terms and verifies X-PAYMENT headers
(mock: decode + check amount/asset; live: delegate to the configured facilitator).
The wire format mirrors ``payment/client.py``.
"""

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from config.settings import settings

X402_VERSION = 1


@dataclass
class VerifyResult:
    ok: bool
    txn_hash: Optional[str] = None
    error: Optional[str] = None


def payment_required_response(resource: str, price_usdc: float) -> JSONResponse:
    body = {
        "x402Version": X402_VERSION,
        "error": "payment required",
        "accepts": [
            {
                "scheme": "exact",
                "network": settings.network,
                "maxAmountRequired": str(price_usdc),
                "asset": "USDC",
                "payTo": settings.data_server_pay_to,
                "resource": resource,
                "description": f"Access to {resource}",
            }
        ],
    }
    return JSONResponse(status_code=402, content=body)


def _mint_txn_hash(nonce: str, resource: str) -> str:
    digest = hashlib.sha256(f"{nonce}|{resource}|{time.time()}".encode()).hexdigest()
    return "0x" + digest


async def _verify_live(header_value: str) -> VerifyResult:
    url = settings.facilitator_url.rstrip("/") + "/verify"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(url, json={"payment": header_value})
    except httpx.HTTPError as exc:
        return VerifyResult(False, error=f"facilitator_unreachable: {exc}")

    if resp.status_code != 200:
        return VerifyResult(False, error=f"facilitator_status: {resp.status_code}")
    body = resp.json()
    if not body.get("valid"):
        return VerifyResult(False, error="facilitator_rejected")
    return VerifyResult(True, txn_hash=body.get("txnHash"))


def _verify_mock(header_value: str, resource: str, price_usdc: float) -> VerifyResult:
    try:
        envelope = json.loads(base64.b64decode(header_value))
    except Exception:
        return VerifyResult(False, error="malformed_payment_header")

    payload = envelope.get("payload", {})
    try:
        value = float(payload.get("value"))
    except (TypeError, ValueError):
        return VerifyResult(False, error="invalid_payment_value")

    if payload.get("asset") != "USDC":
        return VerifyResult(False, error="unsupported_asset")
    if value + 1e-9 < price_usdc:
        return VerifyResult(False, error="insufficient_payment")
    if not payload.get("signature"):
        return VerifyResult(False, error="missing_signature")

    nonce = payload.get("nonce", "")
    return VerifyResult(True, txn_hash=_mint_txn_hash(nonce, resource))


async def verify_payment(
    request: Request, resource: str, price_usdc: float
) -> VerifyResult:
    header_value = request.headers.get("X-PAYMENT")
    if not header_value:
        return VerifyResult(False, error="no_payment_header")

    if settings.mock_payments:
        return _verify_mock(header_value, resource, price_usdc)
    return await _verify_live(header_value)
