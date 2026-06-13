# Implementation Plan
## NexusPay — Autonomous NLP Data Acquisition Agent

**Version:** 1.0  
**Format:** Ongoing side project (flexible pace)

---

## Phase Overview

```
Phase 1 → Web3 + x402 Foundations        (Week 1–2)
Phase 2 → Mock Data Servers + Payment     (Week 3–4)
Phase 3 → Agent Core + LLM Integration   (Week 5–6)
Phase 4 → Budget + Logging               (Week 7)
Phase 5 → Polish + Portfolio Packaging   (Week 8+)
```

---

## Phase 1 — Web3 + x402 Foundations

**Goal:** Get x402 working end-to-end locally. Understand the payment flow before building anything complex.

### Tasks

**1.1 Environment Setup**
- [ ] Python 3.11+ virtualenv
- [ ] Install `primer-x402` or clone `BofAI/x402` Python SDK
- [ ] Create Coinbase CDP account → create testnet wallet
- [ ] Fund testnet wallet with Base Sepolia USDC from faucet
- [ ] Store private key in `.env`

**1.2 Run x402 Hello World**
- [ ] Build simplest possible x402-gated FastAPI endpoint (single file)
- [ ] Build simplest possible x402 client that pays it
- [ ] Confirm: 402 → sign → retry → 200 flow works end-to-end
- [ ] Log raw headers to understand protocol shape

**1.3 Understand the SDK**
- [ ] Read how `x402Middleware` / decorator works for FastAPI servers
- [ ] Read how `x402Fetch` / payment client works for payers
- [ ] Note what the facilitator URL is and how verification happens

**Deliverable:** A single script where client pays server $0.001 USDC (testnet) and receives `{"status": "paid"}`. Screenshot/terminal recording saved.

---

## Phase 2 — Mock Data Servers

**Goal:** Three x402-gated data endpoints running locally with realistic mock data.

### Tasks

**2.1 Mock Data Content**
- [ ] Create `data/breaking_news.json` — 10 fake news headlines with timestamps
- [ ] Create `data/deep_articles.json` — 3 fake long-form articles on AI/tech topics
- [ ] Create `data/sentiment.json` — Fake sentiment scores for 5 topics

**2.2 Data Server Implementation**
- [ ] `data_servers/server.py` — FastAPI app with 3 endpoints
- [ ] `data_servers/middleware.py` — x402 middleware applied to all endpoints
  - Returns 402 + payment terms if no `X-PAYMENT` header
  - Calls facilitator to verify payment if header present
  - Returns data JSON on successful verification
- [ ] Each endpoint returns different price: $0.001 / $0.002 / $0.005
- [ ] Test all three endpoints manually with curl + payment headers

**2.3 Source Registry Seed**
- [ ] `config/sources.json` — Registry of all 3 sources with metadata
- [ ] `registry.py` — Loads registry, exposes `get_all()`, `get_by_id()`, `get_by_tag()`

**Deliverable:** `uvicorn data_servers.server:app --port 8001` running. Manual curl test shows 402 on no payment, 200 + data on valid payment.

---

## Phase 3 — Agent Core + LLM Integration

**Goal:** Agent can take a query, decide what to buy, execute payments, return synthesized answer.

### Tasks

**3.1 LLM Planner**
- [ ] `agent/planner.py` — System prompt + user query → JSON purchase plan
- [ ] Prompt instructs Claude to output:
  ```json
  {
    "reasoning": "...",
    "sources": ["sentiment", "breaking_news"],
    "estimated_cost": 0.003
  }
  ```
- [ ] Parse and validate LLM output with Pydantic
- [ ] Handle LLM output errors gracefully (retry once, then fail)

**3.2 x402 Payment Client**
- [ ] `payment/wallet.py` — Load private key from env, create signer
- [ ] `payment/client.py` — `pay_for_resource(url, max_amount)` function
  - Fires GET to URL
  - Handles 402 response: parses payment terms
  - Signs EIP-3009 transfer authorization
  - Retries with `X-PAYMENT` header
  - Returns `PaymentResult` dataclass

**3.3 Executor**
- [ ] `agent/executor.py` — Runs purchase plan sequentially
  - For each source in plan:
    - Check budget (skip if over cap)
    - Call `payment/client.pay_for_resource()`
    - Collect data payload
    - Log result
  - Returns list of `PaymentResult`

**3.4 Synthesizer**
- [ ] `agent/synthesizer.py` — Takes original query + all purchased data → final answer
- [ ] Passes data payloads as context to Claude
- [ ] Claude returns: answer + confidence + which sources were most useful

**3.5 Main Agent Endpoint**
- [ ] `agent/main.py` — FastAPI app
  - `POST /query` → planner → executor → synthesizer → response
  - Wire all modules together
  - Full response schema from TRD

**Deliverable:** `curl -X POST localhost:8000/query -d '{"query":"latest news on LLMs"}'` returns full response with paid sources + synthesized answer.

---

## Phase 4 — Budget Enforcement + Spend Logging

**Goal:** Agent cannot overspend. Every payment is auditable.

### Tasks

**4.1 Database Setup**
- [ ] `db/database.py` — Create SQLite file, init tables on startup
- [ ] `db/queries.py`:
  - `log_spend(query_id, endpoint, cost, txn_hash)` 
  - `get_daily_total()` → float
  - `get_all_logs()` → list
  - `get_logs_by_query(query_id)` → list

**4.2 Budget Manager**
- [ ] `agent/budget.py` — `BudgetManager` class
  - `check_query_budget(estimated_cost)` → bool
  - `check_daily_budget(cost)` → bool
  - `record_spend(cost)` → updates running total
  - Reads daily total from DB on init
  - Resets at midnight (or first call of new day)

**4.3 Wire Budget Into Flow**
- [ ] Planner checks estimated cost vs per-query cap before execution
- [ ] Executor checks remaining daily budget before each payment call
- [ ] Returns 402 response with clear error if any cap exceeded

**4.4 Log Endpoints**
- [ ] `GET /logs` — returns all spend records
- [ ] `GET /budget` — returns current budget status
- [ ] `GET /sources` — returns source registry with call counts

**Deliverable:** Hit daily cap → agent returns 402 with `"error": "budget_exceeded"`. All spends visible in `/logs`.

---

## Phase 5 — Polish + Portfolio Packaging

**Goal:** Make it demo-able, readable, and impressive on GitHub.

### Tasks

**5.1 README**
- [ ] Project description with architecture diagram (ASCII or Mermaid)
- [ ] Prerequisites: Python 3.11, Coinbase CDP account, testnet USDC
- [ ] Setup steps: clone → `.env` → install → run
- [ ] Demo: single curl command + expected output
- [ ] Tech stack table
- [ ] "How x402 works" section (2 paragraphs, your own words)

**5.2 Demo Recording**
- [ ] Terminal recording (asciinema or screen record) showing:
  1. Start agent server + data servers
  2. POST query
  3. 402 → payment → data → answer in logs
  4. Hit budget cap

**5.3 Project Hardening**
- [ ] `Makefile` with: `make install`, `make run`, `make demo`
- [ ] `docker-compose.yml` — spins up agent + data servers together (optional)
- [ ] `.env.example` with placeholder values
- [ ] Basic pytest for budget manager and registry

**5.4 GitHub Setup**
- [ ] Repo: `DevanshSrajput/NexusPay`
- [ ] Description: "Autonomous NLP data acquisition agent with x402 pay-per-call payments"
- [ ] Topics: `x402`, `fastapi`, `ai-agent`, `stablecoin`, `autonomous-agent`, `nlp`
- [ ] Pinned to GitHub profile

---

## File Creation Order (for Claude Code)

When handing off to Claude Code, build in this exact order to avoid import errors:

```
1. config/settings.py          ← env vars, no dependencies
2. db/database.py              ← SQLite setup
3. db/queries.py               ← DB operations
4. agent/registry.py           ← source registry
5. payment/wallet.py           ← wallet loader
6. payment/client.py           ← x402 payment client
7. payment/models.py           ← dataclasses
8. data_servers/middleware.py  ← x402 server middleware
9. data_servers/server.py      ← mock data endpoints
10. agent/budget.py            ← budget manager
11. agent/planner.py           ← LLM planner
12. agent/executor.py          ← purchase executor
13. agent/synthesizer.py       ← LLM synthesizer
14. agent/main.py              ← FastAPI app (ties everything)
15. tests/test_budget.py       ← basic tests
16. Makefile + README          ← final polish
```

---

## Risks + Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| x402 Python SDK has breaking changes | Medium | Pin version, read changelog before install |
| Coinbase facilitator rejects testnet payments | Low | Use official Base Sepolia testnet, follow CDP docs exactly |
| LLM planner returns invalid JSON | Medium | Strict output schema prompt + Pydantic validation + retry |
| Budget state lost on restart | Low | Read from DB on startup, not in-memory only |
| Mock data too obviously fake for demo | Low | Write realistic news content in JSON files |
