"""Mock x402-gated data servers.

Single FastAPI app hosting three priced endpoints. Each returns 402 with
payment terms when called without a valid X-PAYMENT header, and the mock data
payload once payment is verified.
"""

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config.settings import settings
from data_servers.middleware import payment_required_response, verify_payment

app = FastAPI(title="NexusPay Mock Data Servers")

_DATA_DIR = Path(__file__).resolve().parent / "data"

_ENDPOINTS = {
    "/news/breaking": ("breaking_news.json", 0.001),
    "/articles/deep": ("deep_articles.json", 0.005),
    "/sentiment": ("sentiment.json", 0.002),
}


def _load(filename: str) -> dict:
    return json.loads((_DATA_DIR / filename).read_text())


async def _gated(request: Request, resource: str) -> JSONResponse:
    filename, price = _ENDPOINTS[resource]
    result = await verify_payment(request, resource, price)
    if not result.ok:
        return payment_required_response(resource, price)

    payload = _load(filename)
    return JSONResponse(
        status_code=200,
        content=payload,
        headers={"X-PAYMENT-RESPONSE-TXN": result.txn_hash or ""},
    )


@app.get("/news/breaking")
async def news_breaking(request: Request):
    return await _gated(request, "/news/breaking")


@app.get("/articles/deep")
async def articles_deep(request: Request):
    return await _gated(request, "/articles/deep")


@app.get("/sentiment")
async def sentiment(request: Request):
    return await _gated(request, "/sentiment")


@app.get("/health")
async def health():
    return {"status": "ok", "mock_payments": settings.mock_payments}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.data_server_port)
