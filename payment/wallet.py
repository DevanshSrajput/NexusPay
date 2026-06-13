"""Wallet loader: derives an EIP-3009 signer from the env private key."""

from typing import TYPE_CHECKING, Optional

from config.settings import settings

if TYPE_CHECKING:
    from eth_account.signers.local import LocalAccount


class Wallet:
    def __init__(self) -> None:
        self._account = None
        self._address: Optional[str] = settings.agent_wallet_address or None

        key = settings.agent_private_key.strip()
        if key:
            try:
                from eth_account import Account

                self._account = Account.from_key(key)
                self._address = self._account.address
            except Exception as exc:
                if not settings.mock_payments:
                    raise RuntimeError(f"Failed to load wallet from key: {exc}") from exc

    @property
    def address(self) -> str:
        return self._address or "0xMOCK000000000000000000000000000000000000"

    @property
    def account(self) -> 'Optional[LocalAccount]':
        return self._account

    def is_ready(self) -> bool:
        return self._account is not None

    def sign_message_hash(self, message_hash: bytes) -> str:
        if self._account is None:
            raise RuntimeError("No signer loaded; cannot sign in live mode")
        from eth_account.messages import encode_defunct

        signed = self._account.sign_message(encode_defunct(primitive=message_hash))
        return signed.signature.hex()


wallet = Wallet()
