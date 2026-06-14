"""PrimeYield FastAPI application.

Serves:
  GET  /health               — liveness probe
  GET  /dashboard            — HTMX portfolio dashboard (Day 6-7)
  GET  /portfolio/allocation — current portfolio state (JSON)
  GET  /portfolio/decisions  — last 10 decision records
  POST /telegram/webhook     — Telegram approval callbacks

Run locally:
  uv run uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import dashboard, portfolio, telegram

log = logging.getLogger(__name__)

app = FastAPI(
    title="PrimeYield",
    version="0.1.0",
    description="RWA yield-rotation agent API + Telegram approval webhook",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telegram.router)
app.include_router(portfolio.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "primeyield"}
