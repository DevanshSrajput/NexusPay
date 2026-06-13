# App Flow Document
## NexusPay — Autonomous NLP Data Acquisition Agent

---

## 1. Primary Flow: Query → Purchase → Synthesize

```
USER / CLIENT
     │
     │  POST /query
     │  { "query": "What's the latest news on open source LLMs?",
     │    "max_spend": 0.05 }
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: QUERY INTAKE                                         │
│ agent/main.py                                                │
│                                                              │
│ - Validate request schema                                    │
│ - Generate query_id (timestamp-based)                        │
│ - Check per-query budget cap (0.05 USDC)                     │
│   → If max_spend > PER_QUERY_CAP: reject immediately         │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: LLM PLANNING                                         │
│ agent/planner.py                                             │
│                                                              │
│ System prompt:                                               │
│   "You are a data purchasing agent. Given a query and a      │
│   list of available data sources with prices, select the     │
│   best sources to answer the query within budget.            │
│   Return ONLY valid JSON."                                   │
│                                                              │
│ Input to Claude:                                             │
│   query + source registry (all sources + prices + tags)      │
│                                                              │
│ Output (JSON):                                               │
│   {                                                          │
│     "reasoning": "Need sentiment + recent news for LLMs",   │
│     "sources": ["breaking_news", "sentiment"],               │
│     "estimated_cost": 0.003                                  │
│   }                                                          │
│                                                              │
│ Validation:                                                  │
│   - Pydantic validates JSON shape                            │
│   - estimated_cost ≤ max_spend (else: reject with reason)   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: BUDGET PRE-CHECK                                     │
│ agent/budget.py                                              │
│                                                              │
│ - Load today's total spent from SQLite                       │
│ - Check: daily_spent + estimated_cost ≤ DAILY_CAP           │
│   → If exceeded: return 402 with budget_exceeded error       │
│   → If OK: proceed                                           │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: SEQUENTIAL PURCHASE EXECUTION                        │
│ agent/executor.py                                            │
│                                                              │
│ For each source in plan.sources:                             │
│                                                              │
│   4a. Lookup endpoint URL + price from registry              │
│   4b. Check remaining budget for this call                   │
│       → Skip source if insufficient budget                   │
│   4c. Call payment/client.pay_for_resource(url, price)       │
│       → See Payment Sub-Flow below                           │
│   4d. If PaymentResult.success:                              │
│       - Append data payload to collected_data[]              │
│       - Log spend to SQLite                                  │
│   4e. If PaymentResult.error:                                │
│       - Log failure, continue to next source                 │
│                                                              │
│ End result: collected_data = list of purchased payloads      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: DATA SYNTHESIS                                       │
│ agent/synthesizer.py                                         │
│                                                              │
│ Input to Claude:                                             │
│   original query + all collected_data payloads               │
│                                                              │
│ Output:                                                      │
│   {                                                          │
│     "answer": "Open source LLMs are trending upward...",    │
│     "key_sources": ["breaking_news"],                        │
│     "confidence": "high"                                     │
│   }                                                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: RESPONSE ASSEMBLY + RETURN                           │
│ agent/main.py                                                │
│                                                              │
│ Assemble final response:                                     │
│   {                                                          │
│     "answer": "...",                                         │
│     "sources_used": [{endpoint, cost, txn_hash, preview}],  │
│     "total_cost_usdc": 0.003,                               │
│     "query_id": "q_1718293847",                             │
│     "reasoning": "LLM's source selection reasoning"         │
│   }                                                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Payment Sub-Flow (Step 4c Detail)

```
payment/client.py

CALL: pay_for_resource(url="http://localhost:8001/news/breaking", max_amount=0.001)

┌─────────────────────────────────────────────────────────────┐
│ 1. INITIAL REQUEST                                          │
│    httpx.get(url)  ← no payment header                      │
│    → Expect 402 response                                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PARSE 402 RESPONSE                                       │
│    response.status_code == 402                              │
│    Parse X-PAYMENT-REQUIRED header:                         │
│    {                                                        │
│      "price": "0.001",                                      │
│      "asset": "USDC",                                       │
│      "network": "eip155:84532",                             │
│      "payTo": "0xDataServer...",                            │
│      "scheme": "exact"                                      │
│    }                                                        │
│                                                             │
│    Validate: price ≤ max_amount                             │
│    → If price > max_amount: return PaymentResult(error)     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. SIGN PAYMENT                                             │
│    x402 SDK: create_payment_header(                         │
│      signer=wallet.signer,                                  │
│      payment_terms=parsed_terms                             │
│    )                                                        │
│    Returns: signed EIP-3009 transfer authorization          │
│    (This is the crypto part — SDK handles all signing)      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. RETRY WITH PAYMENT                                       │
│    httpx.get(url, headers={"X-PAYMENT": signed_payload})   │
│                                                             │
│    Data server receives request:                            │
│    → Sends X-PAYMENT to Coinbase facilitator               │
│    → Facilitator verifies on-chain USDC authorization       │
│    → Returns 200 + verification to data server              │
│    → Data server returns 200 + data JSON to agent           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. RETURN PaymentResult                                     │
│    PaymentResult(                                           │
│      success=True,                                          │
│      endpoint=url,                                          │
│      cost_usdc=0.001,                                       │
│      txn_hash="0xabc...",                                   │
│      data={"articles": [...]}                               │
│    )                                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Budget Exceeded Flow

```
POST /query  { "query": "...", "max_spend": 0.05 }
     │
     ▼
Budget Check: daily_spent ($0.98) + estimated ($0.05) > DAILY_CAP ($1.00)
     │
     ▼
Return immediately:
{
  "error": "budget_exceeded",
  "message": "Daily cap of $1.00 USDC reached. Spent: $0.98 today.",
  "daily_spent": 0.98,
  "daily_cap": 1.00,
  "remaining": 0.02,
  "suggestion": "Reduce max_spend to 0.02 or wait until tomorrow."
}
HTTP 402
```

---

## 4. Data Server Flow (from server's perspective)

```
Incoming request to /news/breaking

Has X-PAYMENT header?
     │
  NO │                     YES │
     ▼                         ▼
Return 402               Send to Coinbase facilitator:
X-PAYMENT-REQUIRED       POST https://facilitator.cdp.coinbase.com/verify
header with:                  { payment: X-PAYMENT header value }
{                                    │
  price: "0.001",         Facilitator returns:
  asset: "USDC",             { valid: true, txnHash: "0x..." }
  network: "eip155:84532",            │
  payTo: "0xServer...",   Return 200 + data:
  scheme: "exact"         {
}                           "articles": [
                              {
                                "title": "Meta releases LLaMA 4...",
                                "content": "...",
                                "published_at": "2026-06-13T09:00:00Z"
                              }
                            ]
                          }
```

---

## 5. State at Each Step

| Step | State Changes |
|------|--------------|
| Query intake | query_id created, request validated |
| LLM planning | purchase_plan created in memory |
| Budget pre-check | daily_total read from DB |
| Payment execution | USDC balance decreases (testnet), data collected |
| Spend logging | New row in `spend_logs` table |
| Synthesis | Final answer generated |
| Response | All state returned to caller |

---

## 6. Startup Flow

```
uvicorn agent.main:app --port 8000

1. Load .env → validate all required vars present
2. Initialize SQLite DB → create tables if not exist
3. Load source registry from config/sources.json
4. Initialize BudgetManager → load today's spend from DB
5. Initialize x402 wallet → load from AGENT_PRIVATE_KEY
6. Log startup: "NexusPay agent ready. Wallet: 0x... | Daily budget: $1.00 | Spent today: $0.00"
7. FastAPI ready to accept requests
```

---

## 7. Error States

| Error State | Where Triggered | Response |
|-------------|----------------|----------|
| Per-query cap exceeded | Step 1 | 402 + error JSON |
| LLM planner fails | Step 2 | 500 + retry suggestion |
| LLM returns invalid JSON | Step 2 | 500 + retry once |
| Daily cap exceeded | Step 3 | 402 + budget status |
| Payment rejected by facilitator | Step 4 | Skip source, log failure, continue |
| All sources fail | Step 4 | 500 + partial data if any |
| No data collected | Step 5 | 500 + "no data purchased" error |
| Synthesizer LLM fails | Step 5 | 500 + raw data returned instead |
