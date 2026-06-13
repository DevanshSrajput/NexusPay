<div align="center">

# 🛰️ NexusPay

### An autonomous AI agent that buys the data it needs, pays per call with x402, and answers you.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![x402](https://img.shields.io/badge/x402-pay--per--call-6E56CF)](https://x402.org)
[![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Tests](https://img.shields.io/badge/tests-passing-success)](tests/)

</div>

---

## What is this?

**NexusPay** is a budget-aware autonomous agent. You ask it a natural-language
question. It uses an LLM to decide *which paid data sources are worth buying*,
pays for each one over the **x402** HTTP payment protocol (testnet USDC on Base
Sepolia), and then synthesizes everything it bought into a single answer.

No subscriptions. No human clicking "approve" on every purchase. No overspending —
the agent enforces a per-query cap and a daily cap, and logs every transaction
for audit.

> 💡 **Runs out of the box with fake payments.** By default `MOCK_PAYMENTS=true`
> simulates the entire `402 → sign → verify → 200` handshake locally, so you can
> demo the whole thing without a wallet, without funds, and without spending a cent.

---

## The flow in one picture

```
                 POST /query  { "query": "...", "max_spend": 0.05 }
                       │
                       ▼
   ┌───────────────────────────────────────────────────────────┐
   │  NexusPay Agent  (FastAPI · :8000)                         │
   │                                                            │
   │   1. Planner     ── Gemini picks which sources to buy      │
   │   2. Budget      ── per-query + daily caps (BEFORE paying) │
   │   3. Executor    ── pays each source via x402              │
   │   4. Synthesizer ── Gemini turns data into the answer      │
   │   5. Spend log   ── every payment → SQLite                 │
   └───────────────────────────────┬───────────────────────────┘
                                   │ x402 (HTTP 402 → pay → 200)
                                   ▼
   ┌───────────────────────────────────────────────────────────┐
   │  Mock Data Servers  (FastAPI · :8001)                      │
   │    /news/breaking   $0.001     /articles/deep   $0.005     │
   │    /sentiment       $0.002                                 │
   │    → return 402 until a valid X-PAYMENT header arrives     │
   └───────────────────────────────────────────────────────────┘
```

---

## How x402 works (in 30 seconds)

The HTTP `402 Payment Required` status code has sat unused in the spec for
decades. [x402](https://x402.org) revives it as a real, structured payment
handshake:

1. The agent requests a gated endpoint **without paying**.
2. The server replies `402` and advertises terms — price, asset, network, recipient.
3. The agent checks the price against its budget, **signs a USDC transfer
   authorization** (EIP-3009), and retries with an `X-PAYMENT` header.
4. The server verifies the payment and returns the data plus a transaction hash.

The result is a machine-native commerce layer where **budgets, not API keys,
govern access** — perfect for autonomous agents that pay per call.

---

## Quickstart

```bash
# 1. Create and activate a virtualenv (repo ships with venv/ already)
python -m venv venv

# 2. Install dependencies
make install

# 3. Create your .env (optional for the mock demo)
cp .env.example .env
```

Add a free **Gemini API key** to `.env` to unlock real LLM reasoning
(grab one at <https://aistudio.google.com/apikey>):

```bash
GEMINI_API_KEY=your-key-here
```

> Without a key, the agent still runs end-to-end: the planner falls back to
> keyword/tag matching and the synthesizer returns a structured data summary.

### Run it

```bash
make data-server   # terminal 1 → mock data on :8001
make agent         # terminal 2 → agent API on :8000
make demo          # terminal 3 → fire a sample query
```

Or call it directly:

```bash
curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the sentiment around open source LLMs?","max_spend":0.05}'
```

```json
{
  "answer": "Sentiment around open source LLMs is strongly positive...",
  "sources_used": [
    { "endpoint": "/news/breaking", "cost_usdc": 0.001, "txn_hash": "0x…", "success": true },
    { "endpoint": "/sentiment",     "cost_usdc": 0.002, "txn_hash": "0x…", "success": true }
  ],
  "total_cost_usdc": 0.003,
  "query_id": "q_1781362436_a1b2c3",
  "reasoning": "Selected news + sentiment to cover both events and mood.",
  "status": "complete"
}
```

---

## API

| Method | Path       | Description                                       |
|--------|------------|---------------------------------------------------|
| `POST` | `/query`   | Plan → pay → synthesize. Returns the full answer. |
| `GET`  | `/logs`    | Every spend record + today's total.               |
| `GET`  | `/budget`  | Daily cap, spent today, remaining, per-query cap. |
| `GET`  | `/sources` | The registered data sources.                      |
| `GET`  | `/health`  | Liveness + agent wallet address.                  |

---

## Budget enforcement

Spend discipline is a first-class feature, not an afterthought:

- **Per-query cap** (`PER_QUERY_CAP_USDC`, default `$0.05`) — checked *before*
  any LLM or payment call.
- **Daily cap** (`DAILY_CAP_USDC`, default `$1.00`) — read from SQLite on every
  request, so restarting the process can never reset the limit.

Exceeding either returns `HTTP 402` with a `budget_exceeded` /
`query_cap_exceeded` error and a suggested remaining spend.

---

## Configuration

Everything is driven by `.env` (see [`.env.example`](.env.example)):

| Variable             | Default                  | Meaning                                              |
|----------------------|--------------------------|------------------------------------------------------|
| `GEMINI_API_KEY`     | *(empty)*                | Google Gemini key. Empty → keyword/summary fallback. |
| `GEMINI_MODEL`       | `gemini-2.5-flash`       | Model used for planning + synthesis.                 |
| `MOCK_PAYMENTS`      | `true`                   | **Keep `true` for fake, free payments.**             |
| `DAILY_CAP_USDC`     | `1.00`                   | Hard daily spend ceiling.                            |
| `PER_QUERY_CAP_USDC` | `0.05`                   | Max spend for a single query.                        |
| `NETWORK`            | `eip155:84532`           | Base Sepolia testnet.                                |
| `AGENT_PRIVATE_KEY`  | *(empty)*                | Only needed when `MOCK_PAYMENTS=false`.              |

---

## Tests

```bash
make test
```

---

## Tech stack

| Layer            | Choice                                  |
|------------------|-----------------------------------------|
| Web framework    | FastAPI (async)                         |
| HTTP client      | httpx                                   |
| LLM              | Google Gemini (`google-genai`)          |
| Payments         | x402 protocol + `eth-account` signing   |
| Database         | SQLite via `aiosqlite`                   |
| Config / models  | Pydantic v2 + pydantic-settings         |

---

## Project documentation

For a deep dive — the idea, every file's role, the algorithms, the major
functions, and the reasoning behind each decision — see
**[DOCUMENTATION.md](DOCUMENTATION.md)**.

---

<div align="center">
Built as a reference implementation for autonomous, pay-per-call agentic data pipelines.
</div>
