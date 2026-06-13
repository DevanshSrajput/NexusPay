# Technical Requirements Document (TRD)
## NexusPay — Autonomous NLP Data Acquisition Agent

**Version:** 1.0  
**Author:** Devansh Singh  
**Date:** June 2026

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT                               │
│              curl / CLI / REST client                       │
└────────────────────────┬────────────────────────────────────┘
                         │ POST /query
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   NEXUSPAY AGENT SERVER                     │
│                    FastAPI (port 8000)                      │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ Query Router │──▶│ LLM Planner  │──▶│ Budget Manager │  │
│  └──────────────┘   │ (Claude API) │   └───────┬────────┘  │
│                     └──────────────┘           │           │
│                                                ▼           │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ Synthesizer  │◀──│  Data Cache  │◀──│  x402 Client   │  │
│  │ (Claude API) │   └──────────────┘   └───────┬────────┘  │
│  └──────────────┘                              │           │
│                                                ▼           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    Spend Logger (SQLite)              │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────-┘
                         │ x402 HTTP calls
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               MOCK DATA SERVERS (FastAPI, port 8001-8003)   │
│                                                             │
│  /news/breaking    → $0.001 USDC per call                   │
│  /articles/deep    → $0.005 USDC per call                   │
│  /sentiment        → $0.002 USDC per call                   │
│                                                             │
│  Each endpoint: returns 402 if no payment header            │
│                 returns JSON data if payment verified        │
└─────────────────────────────────────────────────────────────┘
                         │ facilitator verification
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               x402 FACILITATOR (Coinbase hosted)            │
│         Verifies USDC transfer auth on testnet              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Agent server | FastAPI (Python 3.11+) | Your primary stack |
| Mock data servers | FastAPI | Consistent stack |
| LLM | Anthropic Claude claude-sonnet-4-6 | Query planning + synthesis |
| Payment protocol | x402 Python SDK (`primer-x402` or `BofAI/x402`) | Official Python support |
| Wallet | Coinbase CDP testnet wallet | Free, no KYC for testnet |
| Blockchain | Base Sepolia testnet | x402 native, Coinbase facilitator |
| Stablecoin | USDC (testnet) | x402 default asset |
| Database | SQLite via `aiosqlite` | Zero config, portable |
| Config | `python-dotenv` | Secrets management |
| HTTP client | `httpx` (async) | FastAPI-native async HTTP |

---

## 3. x402 Payment Flow (Technical)

```
AGENT                      DATA SERVER                 FACILITATOR (Coinbase)
  │                              │                              │
  │── GET /sentiment ───────────▶│                              │
  │                              │                              │
  │◀── 402 Payment Required ─────│                              │
  │    Header: X-PAYMENT-REQUIRED                               │
  │    Body: {                                                   │
  │      price: "0.002",                                        │
  │      asset: "USDC",                                         │
  │      network: "eip155:84532",  ← Base Sepolia               │
  │      payTo: "0xDataServer...",                              │
  │      scheme: "exact"                                        │
  │    }                                                        │
  │                              │                              │
  │  [Agent checks budget]       │                              │
  │  [Agent signs EIP-3009 USDC transfer auth]                  │
  │                              │                              │
  │── GET /sentiment ───────────▶│                              │
  │   Header: X-PAYMENT: <signed_payload>                       │
  │                              │                              │
  │                              │── verify payment ──────────▶│
  │                              │◀── 200 OK confirmed ─────────│
  │                              │                              │
  │◀── 200 OK + data ────────────│                              │
  │    Body: { articles: [...] }                                │
  │                              │                              │
  │  [Agent logs txn to SQLite]  │                              │
```

---

## 4. Module Breakdown

### 4.1 `agent/` — Core Agent

```
agent/
├── main.py              # FastAPI app, /query endpoint
├── planner.py           # LLM call: parse query → source selection plan
├── executor.py          # Runs purchase plan, calls x402 client
├── synthesizer.py       # LLM call: purchased data → final answer
├── budget.py            # Budget tracking, cap enforcement
└── registry.py          # Source registry (in-memory + JSON file)
```

### 4.2 `payment/` — x402 Client Wrapper

```
payment/
├── client.py            # Wraps x402 SDK: pay_for_resource(url, max_amount)
├── wallet.py            # Loads wallet from env, exposes signer
└── models.py            # PaymentResult, PaymentError dataclasses
```

### 4.3 `data_servers/` — Mock x402-Gated Data Servers

```
data_servers/
├── server.py            # Single FastAPI app hosting all mock endpoints
├── middleware.py        # x402 middleware: returns 402, verifies payment
└── data/
    ├── breaking_news.json   # Static mock news payloads
    ├── deep_articles.json   # Static mock article payloads
    └── sentiment.json       # Static mock sentiment payloads
```

### 4.4 `db/` — Spend Logger

```
db/
├── database.py          # SQLite connection, table init
├── models.py            # SQLAlchemy or raw SQL table definitions
└── queries.py           # log_spend(), get_daily_total(), get_all_logs()
```

### 4.5 `config/` — Configuration

```
config/
├── settings.py          # Pydantic Settings: loads .env, validates
└── sources.json         # Source registry seed data
```

---

## 5. API Specification

### Agent Server (port 8000)

**POST `/query`**
```json
Request:
{
  "query": "What is the current sentiment around open source AI models?",
  "max_spend": 0.05,        // optional, overrides default
  "sources": ["sentiment", "breaking_news"]  // optional, force sources
}

Response 200:
{
  "answer": "Sentiment around open source AI models is...",
  "sources_used": [
    {
      "endpoint": "/sentiment",
      "cost_usdc": 0.002,
      "txn_hash": "0xabc...",
      "data_preview": "Sentiment score: +0.73"
    }
  ],
  "total_cost_usdc": 0.004,
  "query_id": "q_1718293847",
  "reasoning": "Selected sentiment + breaking_news endpoints because..."
}

Response 402:
{
  "error": "budget_exceeded",
  "message": "Daily cap of $1.00 USDC reached. Spent: $1.002.",
  "daily_spent": 1.002,
  "daily_cap": 1.00
}
```

**GET `/logs`**
```json
Response 200:
{
  "logs": [
    {
      "id": 1,
      "timestamp": "2026-06-13T10:23:11Z",
      "query_id": "q_1718293847",
      "endpoint": "/sentiment",
      "cost_usdc": 0.002,
      "txn_hash": "0xabc...",
      "quality_rating": null
    }
  ],
  "total_spent_today": 0.004,
  "daily_cap": 1.00
}
```

**GET `/budget`**
```json
Response 200:
{
  "daily_cap": 1.00,
  "spent_today": 0.004,
  "remaining": 0.996,
  "per_query_cap": 0.05
}
```

**GET `/sources`**
```json
Response 200:
{
  "sources": [
    {
      "id": "breaking_news",
      "endpoint": "http://localhost:8001/news/breaking",
      "price_usdc": 0.001,
      "data_type": "news",
      "quality_score": 0.8,
      "calls_today": 3
    }
  ]
}
```

### Mock Data Server (port 8001)

**GET `/news/breaking`**  
Returns 402 if no payment header. Returns mock news JSON if payment verified.

**GET `/articles/deep`**  
Returns 402 if no payment header. Returns mock article JSON if payment verified.

**GET `/sentiment`**  
Returns 402 if no payment header. Returns mock sentiment JSON if payment verified.

---

## 6. Data Models

### Source Registry Entry
```python
@dataclass
class DataSource:
    id: str                    # "breaking_news"
    endpoint: str              # "http://localhost:8001/news/breaking"
    price_usdc: float          # 0.001
    data_type: str             # "news" | "article" | "sentiment"
    quality_score: float       # 0.0 - 1.0
    description: str           # "Latest breaking news headlines"
    tags: list[str]            # ["news", "realtime", "headlines"]
```

### Purchase Plan (LLM Output)
```python
@dataclass
class PurchasePlan:
    query_id: str
    reasoning: str             # LLM's explanation of source selection
    sources: list[str]         # ordered list of source IDs to buy
    estimated_cost: float      # sum of source prices
```

### Payment Result
```python
@dataclass
class PaymentResult:
    success: bool
    endpoint: str
    cost_usdc: float
    txn_hash: str | None
    data: dict | None
    error: str | None
```

---

## 7. Environment Variables

```bash
# .env (never commit this)

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# x402 Wallet (testnet only)
AGENT_PRIVATE_KEY=0x...          # Testnet wallet private key
AGENT_WALLET_ADDRESS=0x...       # Corresponding address

# Network
NETWORK=eip155:84532             # Base Sepolia testnet
FACILITATOR_URL=https://facilitator.cdp.coinbase.com

# Budget
DAILY_CAP_USDC=1.00
PER_QUERY_CAP_USDC=0.05

# Server
AGENT_PORT=8000
DATA_SERVER_PORT=8001
```

---

## 8. Dependencies

```txt
# requirements.txt
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
anthropic==0.40.0
primer-x402==0.2.0          # x402 Python SDK (or BofAI/x402)
aiosqlite==0.20.0
python-dotenv==1.0.0
pydantic==2.9.0
pydantic-settings==2.5.0
```

---

## 9. Security Notes

- Private key loaded from `.env` only, never hardcoded
- `.env` in `.gitignore`
- Testnet keys only — if someone steals them, they get fake USDC
- No auth on agent server (portfolio project, run locally)
- Mock data servers validate payment via Coinbase facilitator (real x402 flow, fake funds)

---

## 10. Error Handling

| Error | HTTP Code | Behavior |
|-------|-----------|----------|
| Budget daily cap exceeded | 402 | Return error JSON, log attempt |
| Budget per-query cap exceeded | 402 | Return error JSON before any calls |
| x402 payment rejected by facilitator | 500 | Log failure, skip source, try next |
| LLM planner fails | 500 | Return error, suggest retry |
| All sources fail payment | 500 | Return partial results or error |
| Source returns empty data | 200 | Include in synthesis, flag in log |
