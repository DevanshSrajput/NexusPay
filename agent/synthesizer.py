"""Synthesizer: turns purchased data into a final answer via Gemini.

Falls back to a deterministic summary when no API key is configured so the
end-to-end flow still produces output.
"""

import json
from dataclasses import dataclass

from config.settings import settings

_SYSTEM_PROMPT = """You are a research assistant. Answer the user's query using \
only the provided purchased data. Be concise and specific. If the data is \
insufficient, say so. Cite which source ids were most useful."""


@dataclass
class Synthesis:
    answer: str
    key_sources: list[str]
    confidence: str


def _fallback(query: str, collected: list[dict]) -> Synthesis:
    if not collected:
        return Synthesis(
            answer="No data was purchased, so no answer could be synthesized.",
            key_sources=[],
            confidence="low",
        )
    used = [c["source_id"] for c in collected]
    bits = []
    for item in collected:
        bits.append(f"From {item['source_id']}: {json.dumps(item['data'])[:300]}")
    answer = (
        f"Based on {len(collected)} purchased source(s) for the query "
        f"\"{query}\":\n\n" + "\n\n".join(bits)
    )
    return Synthesis(answer=answer, key_sources=used, confidence="medium")


async def synthesize(query: str, collected: list[dict]) -> Synthesis:
    if not collected:
        return _fallback(query, collected)

    if not settings.gemini_api_key:
        return _fallback(query, collected)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        data_block = json.dumps(collected, indent=2)
        user_msg = (
            f"User query: {query}\n\n"
            f"Purchased data (JSON):\n{data_block}\n\n"
            "Write the answer now."
        )
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=1024,
                temperature=0.3,
            ),
        )
        answer = (resp.text or "").strip()
        return Synthesis(
            answer=answer or _fallback(query, collected).answer,
            key_sources=[c["source_id"] for c in collected],
            confidence="high",
        )
    except Exception:
        return _fallback(query, collected)
