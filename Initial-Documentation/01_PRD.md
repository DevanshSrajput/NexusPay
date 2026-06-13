# Product Requirements Document (PRD)
## NexusPay — Autonomous NLP Data Acquisition Agent

**Version:** 1.0  
**Author:** Devansh Singh  
**Date:** June 2026  
**Status:** Draft

---

## 1. Overview

### 1.1 Problem Statement

AI agents that need real-time NLP data (news, articles, sentiment) today either:
- Call a single hardcoded API with a monthly subscription
- Require a human to approve each data purchase
- Have no budget awareness — they overspend or underspend

There is no autonomous, pay-per-call, budget-aware data acquisition layer for NLP agents.

### 1.2 Solution

**NexusPay** is an AI agent that:
1. Accepts a natural language query (e.g. "What is the sentiment around NVIDIA this week?")
2. Autonomously decides which data sources to purchase from based on cost, quality, and relevance
3. Pays per-call using the x402 HTTP payment protocol with testnet USDC
4. Synthesizes the purchased data into a coherent response
5. Logs every spend decision with reasoning for auditability

No human approval needed. No monthly subscriptions. Pay only for what the agent actually uses.

### 1.3 Target Users

- **Primary:** Portfolio reviewers / interviewers evaluating ML/AI + Web3 engineering depth
- **Secondary:** Developers building agentic data pipelines who want a reference implementation

---

## 2. Goals

| Goal | Metric |
|------|--------|
| Agent operates fully autonomously | Zero human approvals per query |
| Budget enforcement works | Agent never exceeds daily cap |
| Payment flow is observable | Every purchase logged with txn hash |
| Demo-able in under 2 minutes | Single query → paid response in <10s |
| Portfolio-ready | README + architecture diagram + live demo GIF |

---

## 3. Non-Goals

- Real money / mainnet deployment (testnet only for now)
- Building a front-end UI (v1 is API + CLI)
- Multi-agent orchestration (single agent, multiple data sources)
- ERC-8004 identity/reputation (out of scope for v1)
- Production-grade security (portfolio project)

---

## 4. Features

### 4.1 Core Features (MVP)

**F1 — Query Intake**
Agent accepts a natural language query via REST API or CLI. Query is passed to an LLM (Claude via Anthropic API) which determines: what data is needed, which sources to buy from, in what order.

**F2 — Source Registry**
A local registry of x402-gated data endpoints with metadata:
- Endpoint URL
- Price per call (in USDC)
- Data type (breaking news / deep article / sentiment)
- Quality score (static seed, updated after use)

**F3 — Autonomous Purchase Decision**
Agent ranks sources by a simple scoring function:
```
score = (relevance_weight * relevance) + (quality_weight * quality) - (cost_weight * cost)
```
Agent selects top N sources within budget.

**F4 — x402 Payment Execution**
Agent uses the x402 Python SDK to:
- Detect 402 response from data server
- Sign USDC transfer authorization (EIP-3009)
- Retry request with payment header
- Receive data payload

**F5 — Budget Enforcement**
- Per-query cap: configurable max spend per single query (default $0.05 testnet USDC)
- Daily cap: configurable max daily spend (default $1.00 testnet USDC)
- Hard stop: agent refuses to call any endpoint if budget exhausted

**F6 — Data Synthesis**
Purchased data payloads are passed back to the LLM to synthesize a final answer. Response includes: answer, sources used, total cost, reasoning trace.

**F7 — Spend Log**
Every transaction recorded to SQLite:
- Timestamp, endpoint, cost, txn hash, query ID, data quality rating

### 4.2 V2 Features (Post-MVP)

- React dashboard showing spend log and agent decisions
- Dynamic quality scoring (agent rates data after use, updates registry)
- Multiple agent wallets with different budget profiles
- ERC-8004 identity registration for the agent

---

## 5. User Stories

```
As a developer querying NexusPay,
I want to ask a natural language question,
So that the agent autonomously buys the right data and answers me.

As a developer reviewing spend,
I want to see a full audit log of every payment,
So that I can verify the agent's decision-making.

As a demo viewer,
I want to see the payment happen in real time (402 → pay → data),
So that I understand the x402 protocol in action.

As a portfolio reviewer,
I want to see budget cap enforcement trigger,
So that I trust the agent won't overspend.
```

---

## 6. Constraints

- **Testnet only:** Avalanche Fuji or Base Sepolia testnet USDC
- **No real keys in code:** All private keys via `.env`, never committed
- **Python + FastAPI only:** No Node.js in the agent core
- **Offline-first data servers:** Mock data servers run locally; no dependency on third-party paid APIs
- **LLM:** Anthropic Claude (via API) for query parsing and synthesis

---

## 7. Success Criteria

MVP is complete when:
1. Single `curl` or CLI command triggers full flow: query → LLM decision → x402 payment → data → synthesized answer
2. Budget cap triggers correctly when exceeded
3. SQLite spend log records every transaction
4. A 90-second screen recording can demo the entire flow clearly
