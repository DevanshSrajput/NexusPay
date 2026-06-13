"""LLM planner: turns a natural-language query into a purchase plan.

Gemini is given the query and the source registry and must return JSON naming
which sources to buy. The output is validated with Pydantic before use because
LLMs can emit malformed or hallucinated JSON. One retry is attempted, then a
deterministic keyword fallback keeps the agent functional without a working
API key.
"""

import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError, field_validator

from agent.registry import registry
from config.settings import settings

_SYSTEM_PROMPT = """You are a data-purchasing agent. Given a user query and a \
list of available paid data sources, select the minimal set of sources that \
best answers the query within budget.

Return ONLY valid JSON, no prose, in exactly this shape:
{
  "reasoning": "<one or two sentences explaining your choice>",
  "sources": ["<source_id>", ...],
  "estimated_cost": <number>
}

Rules:
- "sources" must only contain ids from the provided list.
- Order sources by importance (most useful first).
- "estimated_cost" must equal the sum of the chosen sources' prices.
- Prefer fewer sources when one or two already answer the query."""


class PlannerOutput(BaseModel):
    reasoning: str
    sources: list[str]
    estimated_cost: float

    @field_validator("sources")
    @classmethod
    def known_sources_only(cls, value: list[str]) -> list[str]:
        valid_ids = {s.id for s in registry.get_all()}
        filtered = [s for s in value if s in valid_ids]
        if not filtered:
            raise ValueError("no valid sources selected")
        return filtered


@dataclass
class PurchasePlan:
    query_id: str
    reasoning: str
    sources: list[str]
    estimated_cost: float


def _registry_for_prompt() -> str:
    lines = []
    for s in registry.get_all():
        lines.append(
            f"- id: {s.id} | price_usdc: {s.price_usdc} | type: {s.data_type} | "
            f"quality: {s.quality_score} | tags: {', '.join(s.tags)} | {s.description}"
        )
    return "\n".join(lines)


def _recompute_cost(source_ids: list[str]) -> float:
    total = 0.0
    for sid in source_ids:
        src = registry.get_by_id(sid)
        if src:
            total += src.price_usdc
    return round(total, 6)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in response")
    return json.loads(match.group(0))


def _keyword_fallback(query: str) -> PlannerOutput:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    chosen: list[str] = []
    for source in registry.get_all():
        tag_hit = any(source in registry.get_by_tag(token) for token in tokens)
        if tag_hit or source.data_type in tokens:
            chosen.append(source.id)
    if not chosen:
        cheapest = sorted(registry.get_all(), key=lambda s: s.price_usdc)
        chosen = [cheapest[0].id] if cheapest else []
    return PlannerOutput(
        reasoning="Selected sources by matching query keywords against source tags "
        "(LLM planner unavailable).",
        sources=chosen,
        estimated_cost=_recompute_cost(chosen),
    )


async def _call_gemini(query: str) -> PlannerOutput:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    user_msg = (
        f"Available data sources:\n{_registry_for_prompt()}\n\n"
        f"User query: {query}\n\nReturn the JSON plan."
    )
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        max_output_tokens=512,
        temperature=0.2,
        response_mime_type="application/json",
    )

    last_error: Exception | None = None
    for _ in range(2):
        try:
            resp = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=user_msg,
                config=config,
            )
            return PlannerOutput(**_extract_json(resp.text or ""))
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            continue
    raise RuntimeError(f"planner failed to produce valid JSON: {last_error}")


async def plan_purchase(query_id: str, query: str, forced_sources: list[str] | None = None) -> PurchasePlan:
    if forced_sources:
        valid = [s for s in forced_sources if registry.get_by_id(s)]
        output = PlannerOutput(
            reasoning="Sources explicitly specified in the request.",
            sources=valid or forced_sources,
            estimated_cost=_recompute_cost(valid),
        )
    elif settings.gemini_api_key:
        try:
            output = await _call_gemini(query)
        except Exception:
            output = _keyword_fallback(query)
    else:
        output = _keyword_fallback(query)

    estimated = _recompute_cost(output.sources)
    return PurchasePlan(
        query_id=query_id,
        reasoning=output.reasoning,
        sources=output.sources,
        estimated_cost=estimated,
    )
