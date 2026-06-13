"""Staged agent pipeline, shared by the Streamlit UI.

Exposes the query flow as discrete awaitable stages so a UI can render each one
as it happens (plan → budget → execute → synthesize). The FastAPI server
(`agent/main.py`) keeps its own HTTP glue; this module is the reusable core for
non-HTTP callers.
"""

import json
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from agent.budget import budget_manager
from agent.executor import ExecutionOutcome, execute_plan
from agent.planner import PurchasePlan, plan_purchase
from agent.registry import registry
from agent.synthesizer import Synthesis, synthesize
from config.settings import settings
from db.queries import create_query, update_query
from httpx import URL


@dataclass
class BudgetSnapshot:
    daily_cap: float
    spent_today: float
    remaining: float
    per_query_cap: float


@dataclass
class StageError:
    error: str
    message: str
    daily_spent: float = 0.0
    daily_cap: float = 0.0
    remaining: float = 0.0


@dataclass
class PlanStage:
    plan: Optional[PurchasePlan] = None
    error: Optional[StageError] = None


def new_query_id() -> str:
    return f"q_{int(time.time())}_{secrets.token_hex(3)}"


async def budget_snapshot() -> BudgetSnapshot:
    spent = await budget_manager.daily_spent()
    return BudgetSnapshot(
        daily_cap=settings.daily_cap_usdc,
        spent_today=round(spent, 6),
        remaining=round(budget_manager.remaining(spent), 6),
        per_query_cap=settings.per_query_cap_usdc,
    )


async def plan_stage(
    query_id: str, query: str, max_spend: float, forced: Optional[list[str]]
) -> PlanStage:
    await create_query(query_id, query, max_spend)

    if max_spend > settings.per_query_cap_usdc + 1e-9:
        snap = await budget_snapshot()
        await update_query(query_id, status="failed", error_message="query_cap_exceeded")
        return PlanStage(error=StageError(
            "query_cap_exceeded",
            f"Requested max spend ${max_spend:.4f} exceeds the per-query cap "
            f"${settings.per_query_cap_usdc:.4f}.",
            snap.spent_today, snap.daily_cap, snap.remaining,
        ))

    await update_query(query_id, status="planning")
    plan = await plan_purchase(query_id, query, forced)

    cap = budget_manager.check_query_cap(plan.estimated_cost, max_spend)
    if not cap.allowed:
        snap = await budget_snapshot()
        await update_query(query_id, status="failed", error_message=cap.reason,
                           estimated_cost=plan.estimated_cost,
                           planner_reasoning=plan.reasoning)
        return PlanStage(error=StageError(
            "query_cap_exceeded", cap.reason,
            snap.spent_today, snap.daily_cap, snap.remaining,
        ))

    daily = await budget_manager.can_afford_daily(plan.estimated_cost)
    if not daily.allowed:
        snap = await budget_snapshot()
        await update_query(query_id, status="failed", error_message=daily.reason,
                           estimated_cost=plan.estimated_cost,
                           planner_reasoning=plan.reasoning)
        return PlanStage(error=StageError(
            "budget_exceeded", daily.reason,
            snap.spent_today, snap.daily_cap, snap.remaining,
        ))

    await update_query(query_id, status="executing",
                       estimated_cost=plan.estimated_cost,
                       planner_reasoning=plan.reasoning)
    return PlanStage(plan=plan)


async def execute_stage(plan: PurchasePlan) -> ExecutionOutcome:
    outcome = await execute_plan(plan)
    await update_query(plan.query_id, status="synthesizing",
                       actual_cost=outcome.total_cost,
                       sources_used=json.dumps(
                           [c["source_id"] for c in outcome.collected_data]))
    return outcome


async def synthesize_stage(
    query_id: str, query: str, outcome: ExecutionOutcome, source_count: int
) -> tuple[Synthesis, str]:
    synthesis = await synthesize(query, outcome.collected_data)
    successful = [r for r in outcome.results if r.success]
    status = "complete" if successful else "failed"
    if successful and len(successful) < source_count:
        status = "partial"
    await update_query(query_id, status=status, final_answer=synthesis.answer)
    return synthesis, status


def endpoint_path(url: str) -> str:
    return URL(url).path


def source_label(source_id: str) -> str:
    src = registry.get_by_id(source_id)
    return src.data_type if src else source_id
