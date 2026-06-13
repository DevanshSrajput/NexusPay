"""Request/response Pydantic models for the agent API."""

from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500)
    max_spend: float = Field(default=0.05, ge=0.0, le=10.0)
    sources: Optional[list[str]] = None  # force specific sources


class SourceUsed(BaseModel):
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str] = None
    data_preview: str
    success: bool


class QueryResponse(BaseModel):
    answer: str
    sources_used: list[SourceUsed]
    total_cost_usdc: float
    query_id: str
    reasoning: str
    status: str  # "complete" | "partial" | "failed"


class BudgetError(BaseModel):
    error: str  # "budget_exceeded" | "query_cap_exceeded"
    message: str
    daily_spent: float
    daily_cap: float
    remaining: float
    suggestion: Optional[str] = None


class BudgetStatus(BaseModel):
    daily_cap: float
    spent_today: float
    remaining: float
    per_query_cap: float
    queries_today: int


class SpendLog(BaseModel):
    id: int
    query_id: str
    endpoint: str
    cost_usdc: float
    txn_hash: Optional[str] = None
    success: bool
    data_preview: Optional[str] = None
    created_at: str


class LogsResponse(BaseModel):
    logs: list[SpendLog]
    total_spent_today: float
    daily_cap: float
    count: int


class SourceInfo(BaseModel):
    id: str
    endpoint: str
    price_usdc: float
    data_type: str
    quality_score: float
    description: str
    tags: list[str]


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]
