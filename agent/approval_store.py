"""In-process approval state registry.

Bridges the LangGraph request_approval node (which creates an asyncio.Event
and awaits it) with the FastAPI Telegram webhook handler (which fires the
event when the user clicks Approve or Reject on their phone).

Keyed by decision_id (a UUID generated per rebalance cycle).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

# decision_id -> asyncio.Event
_events: dict[str, asyncio.Event] = {}

# decision_id -> "approved" | "rejected"
_outcomes: dict[str, str] = {}


def register(decision_id: str) -> asyncio.Event:
    """Register a pending approval; return the asyncio.Event to await."""
    event = asyncio.Event()
    _events[decision_id] = event
    log.debug("approval_store: registered %s", decision_id)
    return event


def resolve(decision_id: str, status: str) -> None:
    """Resolve a pending approval with `status` (approved/rejected).

    Called by the Telegram webhook handler.
    """
    _outcomes[decision_id] = status
    if decision_id in _events:
        _events[decision_id].set()
        log.info("approval_store: %s resolved as %s", decision_id, status)
    else:
        log.warning("approval_store: unknown decision_id %s (status=%s)", decision_id, status)


def get_status(decision_id: str) -> Optional[str]:
    """Return the resolved status, or None if still pending."""
    return _outcomes.get(decision_id)


def cleanup(decision_id: str) -> None:
    """Remove a decision_id from the registry after it has been processed."""
    _events.pop(decision_id, None)
    _outcomes.pop(decision_id, None)
