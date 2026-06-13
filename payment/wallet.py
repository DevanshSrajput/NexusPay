"""Wallet loader: derives an EIP-3009 signer from the env private key.

Never hardcode keys — the key comes from settings (which loads .env).
In mock mode a real key is not required.
"""

from typing import Optional

from config.settings import settings


class Wallet:
    """Thin wrapper around an eth-account signer.

    When ``settings.mock_payments`` is true, the wallet works without a real
    key so the demo can run without funded testnet USDC.
    """

    def __init__(self) -> None:
        self._account = None
        self._address: Optional[str] = settings.agent_wallet_address or None

        key = settings.agent_private_key.strip()
        if key:
            try:
                from eth_account import Account

                self._account = Account.from_key(key)
                self._address = self._account.address
            except Exception as exc:  # pragma: no cover - depends on env/deps
                if not settings.mock_payments:
                    raise RuntimeError(f"Failed to load wallet from key: {exc}") from exc

    @property
    def address(self) -> str:
        return self._address or "0xMOCK000000000000000000000000000000000000"

    @property
    def account(self):
        """The underlying eth-account object, or None in mock mode."""
        return self._account

    def is_ready(self) -> bool:
        """True if a real signer is loaded (required for live payments)."""
        return self._account is not None

    def sign_message_hash(self, message_hash: bytes) -> str:
        """Sign a 32-byte hash, returning the hex signature.

        Used by the x402 client to authorize an EIP-3009 transfer.
        """
        if self._account is None:
            raise RuntimeError("No signer loaded; cannot sign in live mode")
        from eth_account.messages import encode_defunct

        signed = self._account.sign_message(encode_defunct(primitive=message_hash))
        return signed.signature.hex()


wallet = Wallet()
