"""FastAPI app — dashboard + portfolio + telegram webhook (wired day 4-7)."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="PrimeYield", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "primeyield"}


# Routers are mounted on days 4-7:
# from api.routes import portfolio, telegram
# app.include_router(portfolio.router)
# app.include_router(telegram.router)
