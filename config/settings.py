from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # x402 wallet (testnet only)
    agent_private_key: str = ""
    agent_wallet_address: str = ""

    # Network
    network: str = "eip155:84532"
    facilitator_url: str = "https://facilitator.cdp.coinbase.com"

    mock_payments: bool = True

    # Budget caps (testnet USDC)
    daily_cap_usdc: float = 1.00
    per_query_cap_usdc: float = 0.05

    # Servers
    agent_port: int = 8000
    data_server_port: int = 8001
    data_server_base_url: str = "http://localhost:8001"

    data_server_pay_to: str = "0x000000000000000000000000000000000000dEaD"

    # Database
    db_path: str = "nexuspay.db"


settings = Settings()
