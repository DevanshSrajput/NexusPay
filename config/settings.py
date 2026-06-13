"""Application configuration loaded from environment / .env.

Exposes a singleton ``settings`` object that every module imports.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # x402 wallet (testnet only — never hardcode real keys)
    agent_private_key: str = ""
    agent_wallet_address: str = ""

    # Network
    network: str = "eip155:84532"  # Base Sepolia
    facilitator_url: str = "https://facilitator.cdp.coinbase.com"

    # When true, the payment layer skips real on-chain signing and simulates
    # a successful x402 flow. Lets the demo run without a funded testnet wallet.
    mock_payments: bool = True

    # Budget caps (testnet USDC)
    daily_cap_usdc: float = 1.00
    per_query_cap_usdc: float = 0.05

    # Servers
    agent_port: int = 8000
    data_server_port: int = 8001
    data_server_base_url: str = "http://localhost:8001"

    # Address the mock data servers receive payment to
    data_server_pay_to: str = "0x000000000000000000000000000000000000dEaD"

    # Database
    db_path: str = "nexuspay.db"


settings = Settings()
