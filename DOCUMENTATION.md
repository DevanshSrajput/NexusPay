# NexusPay — Project Documentation

A complete walkthrough of **what** NexusPay is, **why** it exists, **how** every
file works, the **algorithms** behind it, and the **reasoning** for each design
decision. Read this top-to-bottom and you will understand the entire codebase.

---

## Table of contents

1. [The idea](#1-the-idea)
2. [Mental model: how the pieces fit](#2-mental-model-how-the-pieces-fit)
3. [Request lifecycle (end to end)](#3-request-lifecycle-end-to-end)
4. [The x402 payment protocol, as implemented here](#4-the-x402-payment-protocol-as-implemented-here)
5. [File-by-file reference](#5-file-by-file-reference)
6. [The algorithms](#6-the-algorithms)
7. [Data models](#7-data-models)
8. [Database schema](#8-database-schema)
9. [Configuration](#9-configuration)
10. [Error handling](#10-error-handling)
11. [Design decisions & trade-offs](#11-design-decisions--trade-offs)
12. [Testing](#12-testing)
13. [How to extend it](#13-how-to-extend-it)
14. [Glossary](#14-glossary)

---

## 1. The idea

Modern AI agents that need real-time data (news, articles, sentiment) usually hit
**one hardcoded API behind a monthly subscription**, or they require a human to
approve every data purchase. Neither scales to autonomous agents that should be
able to decide *for themselves* what data is worth buying, pay for exactly that,
and stay inside a budget.

**NexusPay is a reference implementation of the missing piece: an autonomous,
pay-per-call, budget-aware data acquisition layer.**

It demonstrates four ideas working together:

| Idea | How NexusPay shows it |
|------|------------------------|
| **Autonomous decisioning** | An LLM reads your query and the source catalog, then picks which sources to buy. |
| **Machine-native payments** | Each purchase is settled over the x402 HTTP payment protocol with (testnet) USDC. |
| **Spend discipline** | Per-query and daily budget caps are enforced *before* any money moves. |
| **Auditability** | Every payment attempt — success or failure — is written to SQLite with its reasoning. |

The whole thing is designed to run **locally with simulated payments**, so the
concepts are demonstrable without a funded crypto wallet.

---

## 2. Mental model: how the pieces fit

There are **two independent servers**:

```
┌──────────────────────────────┐        x402 over HTTP        ┌──────────────────────────────┐
│  AGENT SERVER  (:8000)       │ ───────────────────────────▶ │  DATA SERVERS  (:8001)       │
│  agent/main.py               │   GET → 402 → pay → 200      │  data_servers/server.py      │
│                              │                              │                              │
│  planner → budget → executor │                              │  3 priced, x402-gated        │
│   → synthesizer → spend log  │                              │  endpoints + mock JSON       │
└──────────────────────────────┘                              └──────────────────────────────┘
        the "buyer"                                                    the "seller"
```

They run on **different ports on purpose** — the agent is the *buyer*, the data
servers are the *sellers*. Keeping them separate makes the payment boundary real:
the agent genuinely makes HTTP calls, receives `402`s, and pays to cross them.

The supporting packages:

| Package          | Role                                                            |
|------------------|----------------------------------------------------------------|
| `config/`        | Settings (from `.env`) and the source catalog seed.            |
| `db/`            | SQLite connection, schema, and all query helpers.              |
| `agent/`         | The brain: planning, budgeting, execution, synthesis, the API. |
| `payment/`       | The x402 *client* — wallet + the pay-for-resource flow.        |
| `data_servers/`  | The x402 *server* — middleware + the mock endpoints.           |
| `streamlit_app.py` | The web UI — a two-section (Control center / About) Streamlit app that runs the data server in a thread and drives `agent/pipeline.py`. |
| `docs/` | Documentation-site generator (`build.py` + theme) that renders this Markdown into a static, SPA, AI-ready website; deployed to GitHub Pages. |

---

## 3. Request lifecycle (end to end)

A single `POST /query` travels through six steps. This is the spine of the whole
project — every file exists to serve one of these steps.

```
POST /query {query, max_spend, sources?}
        │
        ▼
STEP 1 ── Intake & per-query cap         agent/main.py
        │   • generate a unique query_id
        │   • record the query row (status: pending)
        │   • reject if max_spend > PER_QUERY_CAP            → 402
        ▼
STEP 2 ── Planning                        agent/planner.py
        │   • Gemini (or keyword fallback) selects sources
        │   • output validated by Pydantic
        │   • we recompute estimated_cost from the registry
        │   • reject if estimated_cost > caps               → 402
        ▼
STEP 3 ── Daily budget pre-check          agent/budget.py
        │   • read today's spend from SQLite
        │   • reject if daily_spent + estimate > DAILY_CAP  → 402
        ▼
STEP 4 ── Execution                       agent/executor.py
        │   for each source:
        │     • re-check the daily cap for THIS charge
        │     • pay_for_resource() over x402
        │     • collect data, log the spend
        ▼
STEP 5 ── Synthesis                       agent/synthesizer.py
        │   • Gemini turns purchased data into one answer
        │   • (fallback: structured summary)
        ▼
STEP 6 ── Response assembly               agent/main.py
            • answer + sources_used + total_cost + reasoning → 200
```

> **Why budget checks happen three times** (step 1 ceiling, step 2 estimate,
> step 4 per-charge): each guards a different failure mode. Step 1 stops an
> obviously-too-large request before we spend an LLM call. Step 2 validates the
> *actual* plan the LLM produced. Step 4 protects against the daily cap being
> hit *mid-plan* (e.g. an earlier source already pushed us to the edge).

---

## 4. The x402 payment protocol, as implemented here

x402 reuses the dormant HTTP `402 Payment Required` status code as a structured
payment handshake. Here is the exact exchange NexusPay performs:

```
AGENT (payment/client.py)                      DATA SERVER (data_servers/)
        │
        │   1.  GET /sentiment                       (no payment)
        │ ─────────────────────────────────────────▶
        │
        │   2.  402 Payment Required
        │       body: { "accepts": [{                 ◀───────────── built by
        │         "scheme": "exact",                                payment_required_response()
        │         "network": "eip155:84532",
        │         "maxAmountRequired": "0.002",
        │         "asset": "USDC",
        │         "payTo": "0x…"
        │       }] }
        │ ◀─────────────────────────────────────────
        │
        │   [ parse terms · check price ≤ max_amount · build X-PAYMENT ]
        │
        │   3.  GET /sentiment
        │       header: X-PAYMENT: <base64 envelope>
        │ ─────────────────────────────────────────▶
        │                                            [ verify_payment():
        │                                              mock → decode + check amount
        │                                              live → POST to facilitator ]
        │   4.  200 OK
        │       header: X-PAYMENT-RESPONSE-TXN: 0x…
        │       body: { "topics": [ … ] }
        │ ◀─────────────────────────────────────────
        │
        │   [ return PaymentResult(success, txn_hash, data) ]
```

### The X-PAYMENT envelope

The client and server agree on a wire format: a **base64-encoded JSON envelope**
that mirrors a real x402 payment header.

```json
{
  "x402Version": 1,
  "scheme": "exact",
  "network": "eip155:84532",
  "payload": {
    "from": "0xAgent…",
    "to": "0xPayTo…",
    "value": "0.002",
    "asset": "USDC",
    "nonce": "0x…",
    "signature": "0x…",
    "validBefore": 1781362736,
    "resource": "/sentiment"
  }
}
```

### Two modes — controlled by `MOCK_PAYMENTS`

| Mode | `MOCK_PAYMENTS` | What `signature` is | What the server checks |
|------|-----------------|---------------------|------------------------|
| **Mock** (default) | `true` | a random token (`0xmock…`) | decodes envelope, confirms `asset == USDC` and `value ≥ price` |
| **Live** | `false` | a real EIP-3009 signature from `eth-account` | delegates to the Coinbase facilitator's `/verify` |

This is the key design lever: **mock mode preserves the full protocol shape**
(real 402s, real headers, real retries) while removing the need for funds. The
flow you demo locally is byte-for-byte the same flow that would run on testnet —
only the signature source and the verification backend change.

---

## 5. File-by-file reference

### `config/settings.py` — single source of truth for configuration

- **`Settings(BaseSettings)`** — a pydantic-settings model that loads every
  config value from `.env` (or environment variables), with sensible defaults.
- **`settings`** — a module-level singleton imported everywhere. Importing the
  same object everywhere means there's exactly one place config can come from.

Key fields: `gemini_api_key`, `gemini_model`, `mock_payments`, `daily_cap_usdc`,
`per_query_cap_usdc`, `network`, `facilitator_url`, `data_server_pay_to`,
`db_path`.

> **Reasoning:** secrets must never be hardcoded. `BaseSettings` gives validation
> + `.env` loading for free, and `extra="ignore"` means extra env vars won't
> crash startup.

---

### `config/sources.json` — the source catalog (seed data)

A static JSON list of the buyable data sources, each with `id`, `endpoint`,
`price_usdc`, `data_type`, `quality_score`, `description`, and `tags`. This is
the "menu" the planner reads from. Read-only at runtime in v1.

---

### `db/database.py` — connection + schema

- **`SCHEMA`** — the `CREATE TABLE IF NOT EXISTS` DDL for `spend_logs` and
  `queries`, plus their indexes.
- **`get_connection()`** — opens an `aiosqlite` connection with
  `row_factory = aiosqlite.Row` so rows behave like dicts.
- **`init_db()`** — runs the schema once on startup (idempotent).

> **Reasoning:** SQLite is zero-config and portable, ideal for a self-contained
> portfolio project. `IF NOT EXISTS` makes startup safe to run repeatedly.

---

### `db/queries.py` — all database operations

Every SQL statement lives here so the rest of the app never writes raw SQL.

| Function | Purpose |
|----------|---------|
| `log_spend(...)` | Insert one payment attempt (success or failure); accepts an optional `quality_rating`. |
| `get_daily_total()` | `SUM(cost_usdc)` of **successful** spends for today (UTC). The number the budget cap is measured against. |
| `get_all_logs(limit)` | Recent spend logs, newest first. |
| `get_logs_by_query(query_id)` | All logs for one query, oldest first. |
| `count_queries_today()` | How many queries were submitted today. |
| `create_query(...)` | Insert a new top-level query row (`status='pending'`). |
| `update_query(query_id, **fields)` | Patch **whitelisted** columns (`_UPDATABLE_QUERY_COLUMNS`); rejects unknown keys with `ValueError`; auto-sets `completed_at` when status becomes terminal (`complete`/`partial`/`failed`). |

> **Reasoning:** the daily total is read from the DB (not held in memory) so a
> process restart can never reset the budget — a deliberate safety property.
> `update_query` whitelists column names so an injected/arbitrary identifier can
> never reach the SQL string.

---

### `agent/registry.py` — the source catalog, in memory

- **`DataSource`** — a dataclass for one catalog entry.
- **`SourceRegistry`** — loads `sources.json` and exposes:
  - `get_all(enabled_only=True)`
  - `get_by_id(id)`
  - `get_by_tag(tag)`
- **`registry`** — singleton loaded at import.

> **Reasoning:** loading the JSON once into typed objects gives the planner and
> executor a fast, validated lookup without re-reading files.

---

### `payment/models.py` — payment dataclasses

- **`PaymentTerms`** — what the server demands (`price_usdc`, `asset`,
  `network`, `pay_to`, `scheme`), parsed from a `402`.
- **`PaymentResult`** — the outcome of one purchase (`success`, `endpoint`,
  `cost_usdc`, `txn_hash`, `data`, `error`).

> **Reasoning:** dataclasses make the payment boundary explicit and typed; the
> executor branches purely on `PaymentResult.success`.

---

### `payment/wallet.py` — the signer

- **`Wallet`** — wraps an `eth-account` signer derived from
  `AGENT_PRIVATE_KEY`. Works **without** a real key in mock mode (so the demo
  runs), but raises in live mode if the key is missing.
  - `address` — the agent's wallet address (or a mock placeholder).
  - `is_ready()` — `True` only when a real signer is loaded.
  - `sign_message_hash(hash)` — signs a digest (used for live EIP-3009 auth).
- **`wallet`** — singleton.

> **Reasoning:** isolating key handling in one class keeps secrets out of the
> request path and makes the mock/live distinction a single `is_ready()` check.

---

### `payment/client.py` — the x402 buyer

The heart of the payment flow.

- **`pay_for_resource(url, max_amount)`** — the public entry point:
  1. `GET url` (no payment). `200` → free resource. `402` → continue. Anything
     else → error.
  2. `_parse_terms()` reads the `accepts[0]` block from the 402 body.
  3. Refuse if `terms.price_usdc > max_amount` — **never overpay**.
  4. `_build_payment_header()` constructs the base64 X-PAYMENT envelope (mock
     signature or real EIP-3009 signature).
  5. Retry the `GET` with the `X-PAYMENT` header.
  6. On `200`, read the `X-PAYMENT-RESPONSE-TXN` header and return a successful
     `PaymentResult` with the data.
- **`_parse_terms`, `_build_payment_header`, `_safe_json`** — helpers.

> **Reasoning:** the price-ceiling check (step 3) happens *before any signing*,
> so a misbehaving or expensive server can never trick the agent into paying
> more than the per-call budget it was handed.

---

### `data_servers/middleware.py` — the x402 seller's gatekeeper

- **`payment_required_response(resource, price)`** — builds the `402` with the
  `accepts` terms block.
- **`verify_payment(request, resource, price)`** — the dispatcher:
  - mock → `_verify_mock()`: base64-decode the envelope, confirm
    `asset == "USDC"` and `value ≥ price` and a signature is present, then mint a
    txn hash.
  - live → `_verify_live()`: `POST` the header to the facilitator's `/verify`.
- **`_mint_txn_hash(nonce, resource)`** — deterministic-ish fake hash:
  `0x` + `sha256(nonce | resource | time)`. Gives the demo realistic, unique
  transaction hashes.
- **`VerifyResult`** — `(ok, txn_hash, error)`.

> **Reasoning:** keeping all payment-enforcement logic in middleware means the
> actual endpoints stay trivially simple — they just call one function.

---

### `data_servers/server.py` — the mock data endpoints

- **`_ENDPOINTS`** — maps each path to `(json file, price)`:
  `/news/breaking → $0.001`, `/articles/deep → $0.005`, `/sentiment → $0.002`.
- **`_gated(request, resource)`** — the shared handler: verify payment, return
  `402` on failure, otherwise load the JSON and return `200` with the
  `X-PAYMENT-RESPONSE-TXN` header.
- Three thin route functions + `/health`.

> **Reasoning:** one shared `_gated` helper guarantees all three endpoints
> enforce payment identically — no copy-paste drift.

---

### `agent/models.py` — API request/response schemas

Pydantic models that define and validate the HTTP contract:
`QueryRequest` (with `min_length`/`max_length`/range validators), `QueryResponse`,
`SourceUsed`, `BudgetError`, `BudgetStatus`, `SpendLog`, `LogsResponse`,
`SourceInfo`, `SourcesResponse`.

> **Reasoning:** validation at the edge means malformed requests are rejected by
> FastAPI before any business logic runs.

---

### `agent/budget.py` — spend discipline

- **`BudgetDecision`** — `(allowed, reason)`.
- **`BudgetManager`**:
  - *Pure, synchronous checks* (trivially unit-testable, no DB):
    - `check_query_cap(estimated_cost, max_spend)` — estimate must fit under
      `min(per_query_cap, max_spend)`.
    - `fits_daily(current_spent, additional_cost)` — one charge must fit under
      the daily cap.
    - `remaining(current_spent)` — never negative.
  - *Async, DB-backed wrappers*:
    - `daily_spent()`, `queries_today()`, `can_afford_daily(cost)`.
- **`budget_manager`** — singleton.

> **Reasoning:** the pure functions take `current_spent` as an argument instead
> of reading the DB themselves. That single decision makes the budget math
> unit-testable without a database — see `tests/test_budget.py`.

---

### `agent/planner.py` — the decision-maker

- **`PlannerOutput`** — Pydantic model of the LLM's JSON
  (`reasoning`, `sources`, `estimated_cost`). A `field_validator` **drops any
  source id that isn't in the registry** and errors if none remain — this is the
  hallucination guard.
- **`PurchasePlan`** — the validated, cost-corrected plan the executor consumes.
- **`_call_gemini(query)`** — calls Gemini with `response_mime_type=
  "application/json"`, parses, validates; **retries once** on bad JSON.
- **`_keyword_fallback(query)`** — deterministic selection: tokenizes the query
  and matches each token against source tags via `registry.get_by_tag()` (plus a
  data-type match), falling back to the cheapest source so the flow always runs.
  Used when there's no API key or the LLM fails.
- **`plan_purchase(query_id, query, forced_sources)`** — orchestrates: forced
  sources > Gemini > fallback, then **recomputes `estimated_cost` from the
  registry** rather than trusting the model's arithmetic.

> **Reasoning:** LLMs hallucinate. Two guards make their output safe to act on:
> (1) Pydantic + a registry whitelist on `sources`, and (2) we never trust the
> model's cost math — we sum real prices ourselves.

---

### `agent/executor.py` — the purchaser

- **`execute_plan(plan)`** — the loop:
  1. Read today's spend **once**, then track increments locally (avoids a DB
     round-trip between every payment).
  2. For each source: re-check the daily cap → if it would breach, log a
     `skipped_budget` failure and continue.
  3. Otherwise `pay_for_resource()`, accumulate cost/data on success, and
     `log_spend()` either way.
- **`ExecutionOutcome`** — `(results, collected_data, total_cost)`.

> **Reasoning:** sources are bought **sequentially** so the running budget is
> always accurate before the next charge — parallel buys could collectively blow
> the cap. Failures are logged and skipped, never fatal (partial results still
> produce an answer).

---

### `agent/synthesizer.py` — the answer-writer

- **`synthesize(query, collected)`** — feeds the original query + all purchased
  JSON to Gemini and returns a `Synthesis(answer, key_sources, confidence)`.
- **`_fallback(query, collected)`** — when there's no key or the call fails,
  returns a structured summary of what was bought (so the endpoint always
  produces output).

> **Reasoning:** graceful degradation. The agent's *value* is in buying the
> right data; rendering it with an LLM is an enhancement, not a hard dependency.

---

### `agent/main.py` — the FastAPI app

- **`lifespan`** — on startup: `init_db()` then log the wallet, daily cap, and
  today's spend.
- **`POST /query`** — implements the six-step lifecycle from §3, updating the
  `queries` row's status at each stage (`pending → planning → executing →
  synthesizing → complete/partial/failed`). A run where some sources succeed and
  others fail is stored as `partial` (not collapsed to `complete`).
- **`GET /logs`**, **`GET /budget`**, **`GET /sources`**, **`GET /health`** —
  observability endpoints.
- **`_budget_error(...)`** — builds the consistent `402` budget error body.
- **`query_id = f"q_{int(time.time())}_{secrets.token_hex(3)}"`** — timestamp +
  random suffix guarantees uniqueness even for rapid-fire requests (the
  timestamp-only version collided on the primary key).

> **Reasoning:** `main.py` is pure orchestration — it owns no business logic, it
> just sequences the other modules and shapes HTTP responses. That keeps each
> stage independently testable.

---

### `agent/pipeline.py` — the reusable, staged flow

Exposes the query flow as discrete awaitable stages — `plan_stage()`,
`execute_stage()`, `synthesize_stage()`, plus `budget_snapshot()` and
`new_query_id()` — so a non-HTTP caller (the Streamlit UI) can render each stage
as it happens. It records the same `queries` rows and status transitions the API
does. `agent/main.py` keeps its own thin HTTP glue; this module is the shared
core for the UI.

> **Reasoning:** the UI wants to show planning, paying, and synthesizing as
> separate animated steps. Splitting the flow into stages here keeps that logic
> out of the view layer and reusable.

---

### `streamlit_app.py` — the web UI

A single-process Streamlit "control center" (dark OLED theme, Fira Code/Sans,
green accent, custom-CSS animations):

- **`bootstrap()`** (`@st.cache_resource`) — starts the mock data server in a
  **daemon thread** and runs `init_db()` exactly once. This is what makes the
  whole app deployable as a single process (e.g. Streamlit Cloud): the buyer
  (agent flow, in-process) and seller (data server, background thread) coexist,
  and x402 calls go over real HTTP to `127.0.0.1:8001`.
- **`_run_async()`** — runs the pipeline's coroutines from Streamlit's sync
  context.
- **Secrets bridge** — copies `st.secrets` into `os.environ` *before* importing
  `settings`, so the same code reads `.env` locally and Streamlit Cloud secrets
  in the cloud.
- **Two sections** behind a prominent segmented switcher (`st.tabs`):
  - **Control center** (`tab_app`) — the persistent header (logo + live status
    pills for payment mode, LLM, wallet, network), the query box with clickable
    example chips, the animated pipeline, the x402 settlement cards, and the
    spend log / session stats. The budget gauge and spend controls live in the
    sidebar (Mission Control), visible from either section.
  - **About** (`tab_about`) — what the project is and does, a guide to every UI
    component (including the green/amber/red meaning of settlement cards), the
    author (Devansh Singh), and `st.link_button`s to the GitHub repo and issue
    tracker (`GITHUB_URL` / `ISSUES_URL`).
- **`run_pipeline()`** — drives `agent/pipeline.py` stage by stage, animating the
  plan, each x402 settlement (with its txn hash), and the final answer. It is
  wrapped in a `try/except` that renders a clean styled error card instead of a
  raw traceback.
- **`_use_example()`** — an `on_click` callback (runs before the text-area widget
  is instantiated) that fills the query box from an example chip. Doing this in a
  callback avoids Streamlit's "cannot modify a widget-keyed value after the
  widget exists" error.

`.streamlit/config.toml` carries the matching dark theme and sets
`showErrorDetails = "none"` so unexpected errors stay aesthetic.

> **Reasoning:** running the data server in a thread (rather than requiring a
> second deployed service) is the key trick that lets the two-server x402
> architecture deploy as one Streamlit app while keeping the payment boundary a
> real HTTP hop.

---

## 6. The algorithms

### 6.1 Source selection (planning)

Two strategies, same output shape:

**LLM strategy** — Gemini receives the query and a formatted catalog
(`id | price | type | quality | tags | description`) and a strict system prompt
demanding JSON of `{reasoning, sources, estimated_cost}`. We force
`response_mime_type="application/json"`, validate with Pydantic, whitelist source
ids against the registry, and retry once on failure.

**Keyword fallback** — for each source, select it if any of its `tags` (or its
`data_type`) appears as a substring of the lowercased query. If nothing matches,
default to the **cheapest** source so the flow still runs.

The PRD describes a scoring function
`score = w_r·relevance + w_q·quality − w_c·cost`; in this implementation the LLM
performs that relevance/quality/cost trade-off in natural language, and the
keyword matcher is the deterministic stand-in.

### 6.2 Budget enforcement

Two independent caps, checked with floating-point tolerance (`1e-9`) to avoid
spurious rejections from float arithmetic:

```
per-query:  estimated_cost ≤ min(PER_QUERY_CAP, request.max_spend)
daily:      daily_spent + charge ≤ DAILY_CAP        (re-checked per charge)
```

`daily_spent` is **always read from SQLite**, never cached across requests, so
the cap survives restarts.

### 6.3 The x402 handshake

`GET → 402 → parse terms → price-check → sign → retry with X-PAYMENT → 200`.
Detailed in §4. The price-check-before-signing is the safety invariant.

### 6.4 Transaction-hash minting (mock mode)

`txn_hash = "0x" + sha256(f"{nonce}|{resource}|{time.time()}")`. The per-call
nonce + timestamp makes every fake hash unique and realistic-looking for the
demo, without any chain interaction.

### 6.5 Cost recomputation

The planner **never trusts the LLM's `estimated_cost`**. After source selection,
`_recompute_cost()` sums `price_usdc` straight from the registry. This closes the
gap between what the model *claims* a plan costs and what it *actually* costs.

---

## 7. Data models

| Model | File | Kind | Role |
|-------|------|------|------|
| `Settings` | `config/settings.py` | pydantic-settings | App config from `.env`. |
| `DataSource` | `agent/registry.py` | dataclass | One catalog entry. |
| `PaymentTerms` | `payment/models.py` | dataclass | Parsed 402 demands. |
| `PaymentResult` | `payment/models.py` | dataclass | Outcome of a purchase. |
| `PlannerOutput` | `agent/planner.py` | Pydantic | Validated LLM JSON. |
| `PurchasePlan` | `agent/planner.py` | dataclass | The plan to execute. |
| `BudgetDecision` | `agent/budget.py` | dataclass | allow/deny + reason. |
| `ExecutionOutcome` | `agent/executor.py` | dataclass | Results + data + cost. |
| `Synthesis` | `agent/synthesizer.py` | dataclass | Final answer bundle. |
| `QueryRequest` / `QueryResponse` / … | `agent/models.py` | Pydantic | HTTP contract. |

---

## 8. Database schema

### `spend_logs` — every payment attempt
`id`, `query_id`, `endpoint`, `endpoint_url`, `cost_usdc`, `txn_hash`,
`success` (0/1), `error_message`, `data_preview` (first 200 chars), `quality_rating`
(writable via `log_spend()`; populated by the v2 scoring feature), `created_at`
(UTC). Indexed on `created_at` and `query_id`.

The daily-total query — the budget's source of truth:

```sql
SELECT COALESCE(SUM(cost_usdc), 0) FROM spend_logs
WHERE success = 1 AND DATE(created_at) = DATE('now', 'utc');
```

### `queries` — every top-level request
`id`, `query_text`, `status`, `max_spend`, `estimated_cost`, `actual_cost`,
`sources_planned`/`sources_used` (JSON arrays), `planner_reasoning`,
`final_answer`, `error_message`, `created_at`, `completed_at`. Indexed on `status`.

The `status` column traces the request lifecycle:
`pending → planning → executing → synthesizing → complete | partial | failed`.

---

## 9. Configuration

All via `.env` (template in `.env.example`). The notable ones:

- **`MOCK_PAYMENTS=true`** — keep this for free, fake payments. Set `false` only
  with a funded testnet wallet.
- **`GEMINI_API_KEY`** — empty is fine; the agent falls back to keyword planning
  and summary synthesis. Provide one to unlock real reasoning.
- **`DAILY_CAP_USDC` / `PER_QUERY_CAP_USDC`** — the two budget ceilings.
- **`AGENT_PRIVATE_KEY` / `AGENT_WALLET_ADDRESS`** — only used in live mode.

See the table in the [README](README.md#configuration) for the full list.

---

## 10. Error handling

| Situation | Where | Response |
|-----------|-------|----------|
| `max_spend` over per-query cap | Step 1 | `402` `query_cap_exceeded` |
| Plan estimate over cap | Step 2 | `402` `query_cap_exceeded` |
| Daily cap would be exceeded | Step 3 | `402` `budget_exceeded` |
| LLM produces invalid JSON | Planner | retry once → keyword fallback |
| Server asks more than `max_amount` | Client | refuse, `PaymentResult.error` |
| One source's payment fails | Executor | log, skip, continue (partial) |
| No data collected at all | Synthesizer | fallback "no data" answer, `500` |
| Planner raises | Step 2 | `500` `planner_failed` + retry hint |

The guiding principle: **a single source failing never aborts the query** — the
agent degrades to partial results and still answers.

---

## 11. Design decisions & trade-offs

- **Mock payments by default.** Preserves the entire x402 protocol shape while
  removing the need for funds. The demo flow == the testnet flow, minus the
  signature backend. *Trade-off:* mock verification is structural, not
  cryptographic.
- **Two separate servers.** Makes the buyer/seller payment boundary real rather
  than an in-process function call. *Trade-off:* you run two processes.
- **Recompute cost server-side.** Never trust LLM arithmetic. *Trade-off:* the
  model's `estimated_cost` is effectively advisory.
- **Pure budget functions.** Decisions take `current_spent` as input → unit
  tests need no database. *Trade-off:* callers must fetch the spend first.
- **Sequential purchasing.** Keeps the running budget exact. *Trade-off:* higher
  latency than parallel buys (acceptable at these volumes).
- **Graceful LLM degradation.** The agent works with no API key at all.
  *Trade-off:* fallback answers are plainer than Gemini's.
- **SQLite as budget source of truth.** Survives restarts. *Trade-off:* not
  built for high-concurrency multi-writer workloads (fine for this scope).

---

## 12. Testing

`tests/test_budget.py` covers the pure budget logic — the most safety-critical
code — including boundary cases (spend exactly at the cap), the per-query vs.
request-`max_spend` interaction, and the "never negative" remaining guarantee.

```bash
make test        # or: venv/bin/pytest -q
```

Because the budget checks are pure functions, these tests run instantly with no
database, no servers, and no network.

---

## 13. How to extend it

- **Add a data source:** add an entry to `config/sources.json`, a JSON payload
  under `data_servers/data/`, and a route + `_ENDPOINTS` entry in
  `data_servers/server.py`.
- **Go live on testnet:** set `MOCK_PAYMENTS=false`, fund a Base Sepolia wallet,
  set `AGENT_PRIVATE_KEY`, and confirm `FACILITATOR_URL`.
- **Dynamic quality scoring (v2):** rate purchased data after synthesis and
  write `quality_rating` back to `spend_logs`; feed scores into planning.
- **Swap the LLM:** the planner and synthesizer are the only LLM touch-points;
  both isolate the provider call behind one function.
- **Extend the UI:** add a section by adding a tab to `st.tabs([...])` in
  `streamlit_app.py`; reuse the existing CSS classes (`np-card`, `np-eyebrow`,
  `np-pill`, …) to stay on-theme.

---

## 14. Glossary

- **x402** — an open protocol that turns HTTP `402 Payment Required` into a real
  pay-per-request payment handshake.
- **EIP-3009** — "transfer with authorization"; lets a wallet sign a USDC
  transfer that someone else submits, enabling gasless, header-based payments.
- **Facilitator** — a service (e.g. Coinbase's) that verifies an x402 payment
  authorization on-chain on the server's behalf.
- **Base Sepolia** — an Ethereum L2 testnet (`eip155:84532`) where the testnet
  USDC lives. Free, no real value.
- **USDC** — a USD-pegged stablecoin; x402's default settlement asset.
