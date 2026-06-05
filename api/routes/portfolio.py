"""Portfolio + decision-log API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[2]

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/allocation")
async def allocation() -> dict:
    """Return the current portfolio allocation from the latest deployments."""
    deps_path = ROOT / "state" / "deployments.json"
    if deps_path.exists():
        deps = json.loads(deps_path.read_text())
    else:
        deps = {}

    return {
        "vault": deps.get("vault"),
        "tokens": deps.get("tokens", {}),
        "chainId": deps.get("chainId"),
    }


@router.get("/decisions")
async def decisions() -> dict:
    """Return the last 10 decision records."""
    from agent.db import load_decisions

    records = load_decisions()
    return {"decisions": records[-10:], "total": len(records)}
