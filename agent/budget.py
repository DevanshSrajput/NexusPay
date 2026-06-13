"""Budget enforcement.

Budget checks must run BEFORE any LLM or payment call. The running daily total
is read from SQLite so a restart cannot reset the cap.

The pure decision functions take the current spend as an argument, which keeps
them trivially unit-testable without a database.
"""

from dataclasses import dataclass

from config.settings import settings
from db.queries import count_queries_today, get_daily_total


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str = ""


class BudgetManager:
    def __init__(
        self,
        daily_cap: float | None = None,
        per_query_cap: float | None = None,
    ) -> None:
        self.daily_cap = settings.daily_cap_usdc if daily_cap is None else daily_cap
        self.per_query_cap = (
            settings.per_query_cap_usdc if per_query_cap is None else per_query_cap
        )

    def check_query_cap(self, estimated_cost: float, max_spend: float) -> BudgetDecision:
        effective_cap = min(self.per_query_cap, max_spend)
        if estimated_cost > effective_cap + 1e-9:
            return BudgetDecision(
                False,
                f"Estimated cost ${estimated_cost:.4f} exceeds per-query cap "
                f"${effective_cap:.4f}.",
            )
        return BudgetDecision(True)

    def fits_daily(self, current_spent: float, additional_cost: float) -> BudgetDecision:
        if current_spent + additional_cost > self.daily_cap + 1e-9:
            return BudgetDecision(
                False,
                f"Daily cap of ${self.daily_cap:.2f} USDC reached. "
                f"Spent: ${current_spent:.4f} today.",
            )
        return BudgetDecision(True)

    def remaining(self, current_spent: float) -> float:
        return max(0.0, self.daily_cap - current_spent)

    async def daily_spent(self) -> float:
        return await get_daily_total()

    async def queries_today(self) -> int:
        return await count_queries_today()

    async def can_afford_daily(self, additional_cost: float) -> BudgetDecision:
        spent = await self.daily_spent()
        return self.fits_daily(spent, additional_cost)


budget_manager = BudgetManager()
