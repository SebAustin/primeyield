"""Portfolio + decision-log API routes — implemented day 6-7."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# day 6-7: GET /portfolio/allocation, GET /portfolio/decisions, GET /dashboard
