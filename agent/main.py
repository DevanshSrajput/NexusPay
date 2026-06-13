"""NexusPay agent server.

Wires planner -> budget -> executor -> synthesizer behind a /query endpoint,
plus observability endpoints for logs, budget and sources.

Run:  uvicorn agent.main:app --port 8000
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agent.budget import budget_manager
from agent.executor import execute_plan
from agent.models import (
    BudgetStatus,
    LogsResponse,
    QueryRequest,
    QueryResponse,
    SourcesResponse,
    SourceInfo,
    SourceUsed,
    SpendLog,
)
from agent.planner import plan_purchase
from agent.registry import registry
from agent.synthesizer import synthesize
from config.settings import settings
from db.database import init_db
from db.queries import create_query, get_all_logs, update_query
from payment.wallet import wallet


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    spent = await budget_manager.daily_spent()
    print(
        f"NexusPay agent ready. Wallet: {wallet.address} | "
        f"Daily budget: ${settings.daily_cap_usdc:.2f} | "
        f"Spent today: ${spent:.4f} | mock_payments={settings.mock_payments}"
    )
    yield


app = FastAPI(title="NexusPay Agent", lifespan=lifespan)


def _budget_error(status_spent: float, message: str, error: str) -> JSONResponse:
    remaining = budget_manager.remaining(status_spent)
    return JSONResponse(
        status_code=402,
        content={
            "error": error,
            "message": message,
            "daily_spent": round(status_spent, 4),
            "daily_cap": settings.daily_cap_usdc,
            "remaining": round(remaining, 4),
            "suggestion": f"Reduce max_spend to {remaining:.4f} or wait until tomorrow.",
        },
    )


@app.post("/query")
async def query(req: QueryRequest):
    query_id = f"q_{int(time.time())}"
    await create_query(query_id, req.query, req.max_spend)

    # Step 1: per-query cap pre-check on the requested ceiling.
    if req.max_spend > settings.per_query_cap_usdc + 1e-9:
        await update_query(query_id, status="failed", error_message="query_cap_exceeded")
        spent = await budget_manager.daily_spent()
        return _budget_error(
            spent,
            f"Requested max_spend ${req.max_spend:.4f} exceeds per-query cap "
            f"${settings.per_query_cap_usdc:.4f}.",
            "query_cap_exceeded",
        )

    # Step 2: LLM planning.
    await update_query(query_id, status="planning")
    try:
        plan = await plan_purchase(query_id, req.query, req.sources)
    except Exception as exc:
        await update_query(query_id, status="failed", error_message=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "planner_failed", "message": str(exc),
                     "suggestion": "Retry the query."},
        )

    # Validate estimated cost against caps.
    cap_decision = budget_manager.check_query_cap(plan.estimated_cost, req.max_spend)
    if not cap_decision.allowed:
        await update_query(query_id, status="failed", error_message=cap_decision.reason,
                           estimated_cost=plan.estimated_cost,
                           planner_reasoning=plan.reasoning)
        spent = await budget_manager.daily_spent()
        return _budget_error(spent, cap_decision.reason, "query_cap_exceeded")

    # Step 3: daily budget pre-check.
    daily_decision = await budget_manager.can_afford_daily(plan.estimated_cost)
    if not daily_decision.allowed:
        await update_query(query_id, status="failed", error_message=daily_decision.reason,
                           estimated_cost=plan.estimated_cost,
                           planner_reasoning=plan.reasoning)
        spent = await budget_manager.daily_spent()
        return _budget_error(spent, daily_decision.reason, "budget_exceeded")

    await update_query(
        query_id,
        status="executing",
        estimated_cost=plan.estimated_cost,
        sources_planned=_json(plan.sources),
        planner_reasoning=plan.reasoning,
    )

    # Step 4: execute purchases.
    outcome = await execute_plan(plan)

    sources_used = [
        SourceUsed(
            endpoint=_path(r.endpoint),
            cost_usdc=r.cost_usdc,
            txn_hash=r.txn_hash,
            data_preview=(_preview(r) ),
            success=r.success,
        )
        for r in outcome.results
    ]
    successful = [r for r in outcome.results if r.success]

    # Step 5: synthesis.
    await update_query(query_id, status="synthesizing",
                       sources_used=_json([c["source_id"] for c in outcome.collected_data]),
                       actual_cost=outcome.total_cost)
    synthesis = await synthesize(req.query, outcome.collected_data)

    status = "complete" if successful else "failed"
    if successful and len(successful) < len(plan.sources):
        status = "partial"

    await update_query(query_id, status=status if status != "partial" else "complete",
                       final_answer=synthesis.answer,
                       completed_at=None)

    # Step 6: assemble response.
    response = QueryResponse(
        answer=synthesis.answer,
        sources_used=sources_used,
        total_cost_usdc=outcome.total_cost,
        query_id=query_id,
        reasoning=plan.reasoning,
        status=status,
    )
    code = 200 if successful else 500
    return JSONResponse(status_code=code, content=response.model_dump())


@app.get("/logs", response_model=LogsResponse)
async def logs():
    rows = await get_all_logs()
    spent = await budget_manager.daily_spent()
    log_models = [
        SpendLog(
            id=r["id"],
            query_id=r["query_id"],
            endpoint=r["endpoint"],
            cost_usdc=r["cost_usdc"],
            txn_hash=r["txn_hash"],
            success=bool(r["success"]),
            data_preview=r["data_preview"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return LogsResponse(
        logs=log_models,
        total_spent_today=round(spent, 4),
        daily_cap=settings.daily_cap_usdc,
        count=len(log_models),
    )


@app.get("/budget", response_model=BudgetStatus)
async def budget():
    spent = await budget_manager.daily_spent()
    return BudgetStatus(
        daily_cap=settings.daily_cap_usdc,
        spent_today=round(spent, 4),
        remaining=round(budget_manager.remaining(spent), 4),
        per_query_cap=settings.per_query_cap_usdc,
        queries_today=await budget_manager.queries_today(),
    )


@app.get("/sources", response_model=SourcesResponse)
async def sources():
    return SourcesResponse(
        sources=[
            SourceInfo(
                id=s.id,
                endpoint=s.endpoint,
                price_usdc=s.price_usdc,
                data_type=s.data_type,
                quality_score=s.quality_score,
                description=s.description,
                tags=s.tags,
            )
            for s in registry.get_all()
        ]
    )


@app.get("/health")
async def health():
    return {"status": "ok", "wallet": wallet.address}


# --- small helpers ---------------------------------------------------------

def _json(value) -> str:
    import json

    return json.dumps(value)


def _path(url: str) -> str:
    from httpx import URL

    return URL(url).path


def _preview(result) -> str:
    if result.success and result.data:
        import json

        return json.dumps(result.data)[:200]
    return result.error or ""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.agent_port)
