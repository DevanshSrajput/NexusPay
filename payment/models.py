"""Dataclasses describing x402 payment terms and results."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentTerms:
    """Parsed from a 402 response's payment requirements."""

    price_usdc: float
    asset: str  # "USDC"
    network: str  # "eip155:84532"
    pay_to: str  # recipient address
    scheme: str  # "exact"


@dataclass
class PaymentResult:
    """Outcome of a single pay-for-resource attempt."""

    success: bool
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None
