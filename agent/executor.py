"""Purchase executor: runs a plan, paying for each source within budget."""

import json
from dataclasses import dataclass

from agent.budget import budget_manager
from agent.planner import PurchasePlan
from agent.registry import registry
from db.queries import log_spend
from payment.client import pay_for_resource
from payment.models import PaymentResult


@dataclass
class ExecutionOutcome:
    results: list[PaymentResult]
    collected_data: list[dict]
    total_cost: float


def _preview(data: dict | None) -> str:
    if not data:
        return ""
    return json.dumps(data)[:200]


async def execute_plan(plan: PurchasePlan) -> ExecutionOutcome:
    results: list[PaymentResult] = []
    collected: list[dict] = []
    total_cost = 0.0

    # Track daily spend locally during execution to avoid a DB round-trip
    # between every payment while keeping each charge's check accurate.
    running_daily = await budget_manager.daily_spent()

    for source_id in plan.sources:
        source = registry.get_by_id(source_id)
        if source is None:
            continue

        decision = budget_manager.fits_daily(running_daily, source.price_usdc)
        if not decision.allowed:
            result = PaymentResult(
                success=False,
                endpoint=source.endpoint,
                cost_usdc=source.price_usdc,
                error=f"skipped_budget: {decision.reason}",
            )
            results.append(result)
            await log_spend(
                query_id=plan.query_id,
                endpoint=_path(source.endpoint),
                endpoint_url=source.endpoint,
                cost_usdc=source.price_usdc,
                txn_hash=None,
                success=False,
                error_message=result.error,
            )
            continue

        result = await pay_for_resource(source.endpoint, source.price_usdc)
        results.append(result)

        if result.success:
            running_daily += result.cost_usdc
            total_cost += result.cost_usdc
            if result.data:
                collected.append({"source_id": source_id, "data": result.data})

        await log_spend(
            query_id=plan.query_id,
            endpoint=_path(source.endpoint),
            endpoint_url=source.endpoint,
            cost_usdc=result.cost_usdc,
            txn_hash=result.txn_hash,
            success=result.success,
            error_message=result.error,
            data_preview=_preview(result.data),
        )

    return ExecutionOutcome(results, collected, round(total_cost, 6))


def _path(url: str) -> str:
    from httpx import URL
    return URL(url).path
