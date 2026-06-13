# NexusPay

Autonomous NLP data acquisition agent with x402 pay-per-call payments.

NexusPay takes a natural-language query, lets Claude decide which paid data
sources to buy, pays for each one over the [x402](https://x402.org) HTTP payment
protocol (testnet USDC on Base Sepolia), and synthesizes the purchased data into
a final answer — all within a hard budget cap, with every spend logged for audit.

## Architecture

```
client ──POST /query──▶ Agent (FastAPI :8000)
                          │  planner (Claude)  → which sources to buy
                          │  budget manager    → per-query + daily caps
                          │  executor          → x402 payments
                          │  synthesizer (Claude) → final answer
                          │  spend logger (SQLite)
                          ▼
                        Mock data servers (FastAPI :8001)
                          /news/breaking   $0.001
                          /articles/deep   $0.005
                          /sentiment       $0.002
                        Each returns 402 until payment is verified.
```

## How x402 works here

When the agent requests a gated endpoint without paying, the data server replies
`402 Payment Required` and advertises terms (price, asset, network, recipient).
The agent checks the price against its budget, signs an EIP-3009 USDC transfer
authorization, and retries the request with an `X-PAYMENT` header. The server
verifies the payment (via the Coinbase facilitator in live mode) and returns the
data plus a transaction hash. No subscriptions, no human approval — the agent
pays per call, only for what it uses.

By default the project runs in `MOCK_PAYMENTS=true` mode, which simulates the
full 402 → sign → verify → 200 handshake locally so you can demo it without a
funded testnet wallet. Set `MOCK_PAYMENTS=false` and provide a funded
`AGENT_PRIVATE_KEY` to run real on-chain testnet payments.

## Setup

```bash
python -m venv venv
make install                 # installs requirements.txt into venv
cp .env.example .env         # fill in ANTHROPIC_API_KEY (optional for mock demo)
```

Without an `ANTHROPIC_API_KEY`, the planner falls back to keyword/tag matching
and the synthesizer returns a structured data summary, so the end-to-end flow
still runs.

## Run

```bash
make data-server   # terminal 1: mock data servers on :8001
make agent         # terminal 2: agent on :8000
make demo          # fire a sample query
```

Or directly:

```bash
curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the sentiment around open source LLMs?","max_spend":0.05}'
```

## Endpoints

| Method | Path       | Description                                  |
|--------|------------|----------------------------------------------|
| POST   | `/query`   | Run the full plan → pay → synthesize flow    |
| GET    | `/logs`    | Spend log + today's total                    |
| GET    | `/budget`  | Daily cap, spent today, remaining            |
| GET    | `/sources` | Registered data sources                      |
| GET    | `/health`  | Liveness + wallet address                    |

## Budget enforcement

- **Per-query cap** (`PER_QUERY_CAP_USDC`, default $0.05): checked before any
  LLM or payment call.
- **Daily cap** (`DAILY_CAP_USDC`, default $1.00): read from SQLite on every
  request so a restart cannot reset it. Exceeding either cap returns `402` with
  a `budget_exceeded` / `query_cap_exceeded` error.

## Tests

```bash
make test
```

## Tech stack

Python 3.11+, FastAPI, httpx, aiosqlite, Anthropic Claude, eth-account,
Pydantic v2 / pydantic-settings.
