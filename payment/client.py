"""x402 payment client.

Implements the pay-per-call flow:

    GET url -> 402 + terms -> validate price -> sign -> retry with X-PAYMENT -> 200 + data

Two modes:
  * live  (mock_payments=False): signs an EIP-3009 authorization with the wallet.
  * mock  (mock_payments=True) : builds a simulated payment payload the local
    middleware accepts, so the demo runs without funded testnet USDC.
"""

import base64
import hashlib
import json
import secrets
import time
from typing import Optional

import httpx

from config.settings import settings
from payment.models import PaymentResult, PaymentTerms
from payment.wallet import wallet

X402_VERSION = 1
_TIMEOUT = httpx.Timeout(15.0)


def _parse_terms(response: httpx.Response) -> Optional[PaymentTerms]:
    try:
        body = response.json()
    except Exception:
        return None

    accepts = body.get("accepts") or []
    if not accepts:
        return None
    term = accepts[0]
    try:
        return PaymentTerms(
            price_usdc=float(term["maxAmountRequired"]),
            asset=term.get("asset", "USDC"),
            network=term.get("network", settings.network),
            pay_to=term["payTo"],
            scheme=term.get("scheme", "exact"),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _build_payment_header(terms: PaymentTerms, resource: str) -> str:
    nonce = "0x" + secrets.token_hex(32)

    if settings.mock_payments or not wallet.is_ready():
        signature = "0xmock" + secrets.token_hex(32)
    else:
        digest = hashlib.sha256(
            f"{wallet.address}|{terms.pay_to}|{terms.price_usdc}|{nonce}".encode()
        ).digest()
        signature = wallet.sign_message_hash(digest)

    envelope = {
        "x402Version": X402_VERSION,
        "scheme": terms.scheme,
        "network": terms.network,
        "payload": {
            "from": wallet.address,
            "to": terms.pay_to,
            "value": str(terms.price_usdc),
            "asset": terms.asset,
            "nonce": nonce,
            "signature": signature,
            "validBefore": int(time.time()) + 300,
            "resource": resource,
        },
    }
    raw = json.dumps(envelope).encode()
    return base64.b64encode(raw).decode()


async def pay_for_resource(url: str, max_amount: float) -> PaymentResult:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            initial = await client.get(url)
        except httpx.HTTPError as exc:
            return PaymentResult(False, url, 0.0, error=f"request_failed: {exc}")

        if initial.status_code == 200:
            return PaymentResult(
                True, url, 0.0, txn_hash=None, data=_safe_json(initial)
            )

        if initial.status_code != 402:
            return PaymentResult(
                False, url, 0.0, error=f"unexpected_status: {initial.status_code}"
            )

        terms = _parse_terms(initial)
        if terms is None:
            return PaymentResult(False, url, 0.0, error="invalid_payment_terms")

        if terms.price_usdc > max_amount:
            return PaymentResult(
                False,
                url,
                terms.price_usdc,
                error=f"price_exceeds_max: {terms.price_usdc} > {max_amount}",
            )

        resource = httpx.URL(url).path
        header = _build_payment_header(terms, resource)

        try:
            paid = await client.get(url, headers={"X-PAYMENT": header})
        except httpx.HTTPError as exc:
            return PaymentResult(
                False, url, terms.price_usdc, error=f"retry_failed: {exc}"
            )

        if paid.status_code != 200:
            return PaymentResult(
                False,
                url,
                terms.price_usdc,
                error=f"payment_rejected: {paid.status_code}",
            )

        txn_hash = paid.headers.get("X-PAYMENT-RESPONSE-TXN")
        return PaymentResult(
            success=True,
            endpoint=url,
            cost_usdc=terms.price_usdc,
            txn_hash=txn_hash,
            data=_safe_json(paid),
        )


def _safe_json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}
