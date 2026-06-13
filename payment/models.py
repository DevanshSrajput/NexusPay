from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentTerms:
    price_usdc: float
    asset: str
    network: str
    pay_to: str
    scheme: str


@dataclass
class PaymentResult:
    success: bool
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None
