"""Telegram approval webhook — implemented day 4-5.

POST /telegram/webhook receives Update objects; handles the approve/reject
CallbackQuery from the inline keyboard and resumes/ends the graph.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/telegram", tags=["telegram"])

# day 4-5: POST /telegram/webhook -> handle CallbackQuery (approve/reject)
