from agent.budget import BudgetManager


def make_manager() -> BudgetManager:
    return BudgetManager(daily_cap=1.00, per_query_cap=0.05)


def test_query_cap_allows_within_cap():
    bm = make_manager()
    decision = bm.check_query_cap(estimated_cost=0.03, max_spend=0.05)
    assert decision.allowed


def test_query_cap_rejects_over_per_query_cap():
    bm = make_manager()
    decision = bm.check_query_cap(estimated_cost=0.06, max_spend=0.05)
    assert not decision.allowed


def test_query_cap_respects_lower_request_max_spend():
    bm = make_manager()
    decision = bm.check_query_cap(estimated_cost=0.03, max_spend=0.02)
    assert not decision.allowed


def test_query_cap_boundary_is_allowed():
    bm = make_manager()
    decision = bm.check_query_cap(estimated_cost=0.05, max_spend=0.05)
    assert decision.allowed


def test_fits_daily_allows_under_cap():
    bm = make_manager()
    decision = bm.fits_daily(current_spent=0.90, additional_cost=0.05)
    assert decision.allowed


def test_fits_daily_rejects_over_cap():
    bm = make_manager()
    decision = bm.fits_daily(current_spent=0.98, additional_cost=0.05)
    assert not decision.allowed


def test_fits_daily_boundary_is_allowed():
    bm = make_manager()
    decision = bm.fits_daily(current_spent=0.95, additional_cost=0.05)
    assert decision.allowed


def test_remaining_never_negative():
    bm = make_manager()
    assert bm.remaining(current_spent=1.50) == 0.0
    assert bm.remaining(current_spent=0.25) == 0.75
