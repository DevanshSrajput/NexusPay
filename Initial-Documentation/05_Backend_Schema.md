# Backend Schema
## NexusPay — Autonomous NLP Data Acquisition Agent

---

## 1. Database: SQLite (`nexuspay.db`)

### Table: `spend_logs`

Tracks every payment attempt made by the agent.

```sql
CREATE TABLE IF NOT EXISTS spend_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id        TEXT NOT NULL,              -- e.g. "q_1718293847"
    endpoint        TEXT NOT NULL,              -- e.g. "/news/breaking"
    endpoint_url    TEXT NOT NULL,              -- full URL called
    cost_usdc       REAL NOT NULL,              -- e.g. 0.001
    txn_hash        TEXT,                       -- onchain txn hash (null if failed)
    success         INTEGER NOT NULL DEFAULT 0, -- 1 = paid + got data, 0 = failed
    error_message   TEXT,                       -- null if success
    data_preview    TEXT,                       -- first 200 chars of response (for logs UI)
    quality_rating  REAL,                       -- null until rated (0.0 - 1.0), v2 feature
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Index for daily total lookups (most frequent query)
CREATE INDEX IF NOT EXISTS idx_spend_logs_date
    ON spend_logs (created_at);

-- Index for query-specific lookups
CREATE INDEX IF NOT EXISTS idx_spend_logs_query
    ON spend_logs (query_id);
```

**Common Queries:**

```sql
-- Daily total spent
SELECT COALESCE(SUM(cost_usdc), 0)
FROM spend_logs
WHERE success = 1
  AND DATE(created_at) = DATE('now', 'utc');

-- All logs for a specific query
SELECT * FROM spend_logs
WHERE query_id = 'q_1718293847'
ORDER BY created_at ASC;

-- All logs today
SELECT * FROM spend_logs
WHERE DATE(created_at) = DATE('now', 'utc')
ORDER BY created_at DESC;

-- Total spent per endpoint (useful for analytics)
SELECT endpoint, COUNT(*) as calls, SUM(cost_usdc) as total_spent
FROM spend_logs
WHERE success = 1
GROUP BY endpoint
ORDER BY total_spent DESC;
```

---

### Table: `queries`

Tracks each top-level query submitted to the agent.

```sql
CREATE TABLE IF NOT EXISTS queries (
    id              TEXT PRIMARY KEY,           -- e.g. "q_1718293847"
    query_text      TEXT NOT NULL,              -- original user query
    status          TEXT NOT NULL DEFAULT 'pending',
                                                -- 'pending' | 'planning' | 'executing'
                                                -- | 'synthesizing' | 'complete' | 'failed'
    max_spend       REAL NOT NULL,              -- per-query budget cap
    estimated_cost  REAL,                       -- from LLM planner
    actual_cost     REAL,                       -- sum of successful payments
    sources_planned TEXT,                       -- JSON array: ["breaking_news","sentiment"]
    sources_used    TEXT,                       -- JSON array: actually paid for
    planner_reasoning TEXT,                     -- LLM's explanation of source selection
    final_answer    TEXT,                       -- synthesized response
    error_message   TEXT,                       -- null if complete
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    completed_at    TEXT                        -- null until done
);

CREATE INDEX IF NOT EXISTS idx_queries_status
    ON queries (status);
```

**Common Queries:**

```sql
-- Latest queries
SELECT id, query_text, status, actual_cost, created_at
FROM queries
ORDER BY created_at DESC
LIMIT 20;

-- Failed queries today
SELECT * FROM queries
WHERE status = 'failed'
  AND DATE(created_at) = DATE('now', 'utc');

-- Average cost per successful query
SELECT AVG(actual_cost) as avg_cost
FROM queries
WHERE status = 'complete';
```

---

## 2. In-Memory / JSON: Source Registry

Stored in `config/sources.json`. Loaded into memory on startup. No writes at runtime in v1.

```json
{
  "sources": [
    {
      "id": "breaking_news",
      "endpoint": "http://localhost:8001/news/breaking",
      "price_usdc": 0.001,
      "data_type": "news",
      "quality_score": 0.80,
      "description": "Latest breaking technology and AI news headlines with timestamps",
      "tags": ["news", "realtime", "headlines", "technology", "ai"],
      "enabled": true
    },
    {
      "id": "deep_articles",
      "endpoint": "http://localhost:8001/articles/deep",
      "price_usdc": 0.005,
      "data_type": "article",
      "quality_score": 0.92,
      "description": "In-depth long-form articles on AI, ML, and technology trends",
      "tags": ["article", "analysis", "longform", "ai", "ml", "technology"],
      "enabled": true
    },
    {
      "id": "sentiment",
      "endpoint": "http://localhost:8001/sentiment",
      "price_usdc": 0.002,
      "data_type": "sentiment",
      "quality_score": 0.75,
      "description": "NLP sentiment scores for topics: positive/negative/neutral with confidence",
      "tags": ["sentiment", "nlp", "opinion", "score", "analysis"],
      "enabled": true
    }
  ]
}
```

---

## 3. Pydantic Models (Python)

### Request / Response Models

```python
# agent/models.py

from pydantic import BaseModel, Field
from typing import Optional
import time

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500)
    max_spend: float = Field(default=0.05, ge=0.0, le=10.0)
    sources: Optional[list[str]] = None  # force specific sources

class SourceUsed(BaseModel):
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str]
    data_preview: str
    success: bool

class QueryResponse(BaseModel):
    answer: str
    sources_used: list[SourceUsed]
    total_cost_usdc: float
    query_id: str
    reasoning: str
    status: str  # "complete" | "partial" | "failed"

class BudgetError(BaseModel):
    error: str  # "budget_exceeded" | "query_cap_exceeded"
    message: str
    daily_spent: float
    daily_cap: float
    remaining: float
    suggestion: Optional[str]

class BudgetStatus(BaseModel):
    daily_cap: float
    spent_today: float
    remaining: float
    per_query_cap: float
    queries_today: int

class SpendLog(BaseModel):
    id: int
    query_id: str
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str]
    success: bool
    data_preview: Optional[str]
    created_at: str

class LogsResponse(BaseModel):
    logs: list[SpendLog]
    total_spent_today: float
    daily_cap: float
    count: int
```

### Internal Models

```python
# payment/models.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class PaymentTerms:
    price_usdc: float
    asset: str           # "USDC"
    network: str         # "eip155:84532"
    pay_to: str          # "0xDataServer..."
    scheme: str          # "exact"

@dataclass
class PaymentResult:
    success: bool
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str]
    data: Optional[dict]
    error: Optional[str]

# agent/planner.py

@dataclass
class PurchasePlan:
    query_id: str
    reasoning: str
    sources: list[str]       # ordered list of source IDs
    estimated_cost: float

# registry.py

@dataclass
class DataSource:
    id: str
    endpoint: str
    price_usdc: float
    data_type: str
    quality_score: float
    description: str
    tags: list[str]
    enabled: bool
```

---

## 4. Config / Settings

```python
# config/settings.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str

    # x402 Wallet
    agent_private_key: str
    agent_wallet_address: str

    # Network
    network: str = "eip155:84532"               # Base Sepolia
    facilitator_url: str = "https://facilitator.cdp.coinbase.com"

    # Budget
    daily_cap_usdc: float = 1.00
    per_query_cap_usdc: float = 0.05

    # Server
    agent_port: int = 8000
    data_server_port: int = 8001

    # DB
    db_path: str = "nexuspay.db"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 5. Mock Data Payloads

### `/news/breaking` response payload

```json
{
  "source": "NexusPay Mock News",
  "fetched_at": "2026-06-13T10:23:11Z",
  "articles": [
    {
      "id": "n001",
      "title": "Meta releases LLaMA 4 Scout with 10M token context window",
      "summary": "Meta's latest open source model targets long-document reasoning tasks.",
      "published_at": "2026-06-13T08:00:00Z",
      "sentiment_hint": "positive",
      "tags": ["llm", "open-source", "meta", "ai"]
    },
    {
      "id": "n002",
      "title": "Mistral AI raises $1B Series C, eyes enterprise market",
      "summary": "European AI startup targets Fortune 500 clients with on-premise deployment.",
      "published_at": "2026-06-12T15:30:00Z",
      "sentiment_hint": "positive",
      "tags": ["startup", "funding", "open-source", "enterprise"]
    },
    {
      "id": "n003",
      "title": "EU AI Act enforcement begins: first compliance audits underway",
      "summary": "Regulators begin auditing high-risk AI systems deployed across member states.",
      "published_at": "2026-06-11T11:00:00Z",
      "sentiment_hint": "neutral",
      "tags": ["regulation", "eu", "compliance", "policy"]
    }
  ]
}
```

### `/articles/deep` response payload

```json
{
  "source": "NexusPay Mock Articles",
  "fetched_at": "2026-06-13T10:23:11Z",
  "articles": [
    {
      "id": "a001",
      "title": "The State of Open Source LLMs in 2026",
      "content": "Open source language models have undergone a dramatic shift in 2025-2026. Where proprietary models once dominated benchmark rankings, the gap has narrowed substantially. LLaMA 4, Mistral Large 3, and Qwen 3 now compete directly with GPT-5 and Claude on most standard benchmarks. Enterprise adoption has followed: 40% of Fortune 500 companies now run at least one open source LLM in production, up from 12% in 2024. The key drivers are cost, data privacy, and customization. On-premise deployment eliminates data egress concerns, while fine-tuning on proprietary datasets creates competitive moats that closed models cannot replicate.",
      "author": "Mock Author",
      "published_at": "2026-06-10T09:00:00Z",
      "word_count": 1200,
      "tags": ["llm", "open-source", "enterprise", "benchmarks"]
    }
  ]
}
```

### `/sentiment` response payload

```json
{
  "source": "NexusPay Mock Sentiment",
  "fetched_at": "2026-06-13T10:23:11Z",
  "topic": "open source LLMs",
  "sentiment": {
    "overall_score": 0.73,
    "label": "positive",
    "confidence": 0.88,
    "breakdown": {
      "positive": 0.73,
      "neutral": 0.20,
      "negative": 0.07
    }
  },
  "trend": "rising",
  "trend_30d_delta": +0.12,
  "sample_size": 4821,
  "analyzed_at": "2026-06-13T06:00:00Z"
}
```

---

## 6. Directory Structure (Complete)

```
NexusPay/
├── agent/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── planner.py           # LLM source selection
│   ├── executor.py          # Payment execution loop
│   ├── synthesizer.py       # LLM answer synthesis
│   ├── budget.py            # Budget enforcement
│   ├── registry.py          # Source registry loader
│   └── models.py            # Request/response Pydantic models
│
├── payment/
│   ├── __init__.py
│   ├── client.py            # x402 payment client
│   ├── wallet.py            # Wallet / signer loader
│   └── models.py            # PaymentResult, PaymentTerms
│
├── data_servers/
│   ├── __init__.py
│   ├── server.py            # Mock data FastAPI app
│   ├── middleware.py        # x402 server middleware
│   └── data/
│       ├── breaking_news.json
│       ├── deep_articles.json
│       └── sentiment.json
│
├── db/
│   ├── __init__.py
│   ├── database.py          # SQLite init, connection
│   └── queries.py           # All DB operations
│
├── config/
│   ├── __init__.py
│   ├── settings.py          # Pydantic settings
│   └── sources.json         # Source registry seed
│
├── tests/
│   ├── test_budget.py
│   ├── test_registry.py
│   └── test_payment_client.py
│
├── .env                     # ← never commit
├── .env.example             # ← commit this
├── .gitignore
├── requirements.txt
├── Makefile
└── README.md
```
