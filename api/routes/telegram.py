"""Telegram approval webhook.

POST /telegram/webhook receives Update objects sent by Telegram's server.
Handles the approve/reject CallbackQuery from the inline keyboard and
fires the asyncio.Event in agent.approval_store so the request_approval
graph node can resume.

Setup (run once, then Telegram will POST every update to your server):
  curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
       -d "url=https://<your-domain>/telegram/webhook"
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from agent import approval_store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receive an Update from Telegram and resolve the pending approval."""
    try:
        from telegram import Bot, Update

        from agent.config import get_settings

        settings = get_settings()
        if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("123456"):
            return {"ok": True, "note": "bot not configured"}

        bot = Bot(token=settings.telegram_bot_token)
        data = await request.json()
        update = Update.de_json(data, bot)

        if update.callback_query:
            query = update.callback_query
            callback_data = query.data or ""

            if ":" in callback_data:
                action, decision_id = callback_data.split(":", 1)
                status = "approved" if action == "approve" else "rejected"
                approval_store.resolve(decision_id, status)

                # Acknowledge the callback to remove the loading spinner.
                await query.answer(
                    text="✅ Approved — executing rebalance"
                    if status == "approved"
                    else "❌ Rejected"
                )
                # Edit the original message to show the outcome.
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                    await bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"Decision `{decision_id}` *{status.upper()}*",
                        parse_mode="Markdown",
                    )
                except Exception:  # noqa: BLE001
                    pass

                log.info("telegram_webhook: %s -> %s", decision_id, status)
            else:
                log.warning("telegram_webhook: unexpected callback_data %r", callback_data)
                await query.answer()

    except Exception as exc:  # noqa: BLE001
        log.error("telegram_webhook error: %s", exc, exc_info=True)

    return {"ok": True}


@router.get("/status/{decision_id}")
async def approval_status(decision_id: str) -> dict:
    """Poll endpoint: check the current approval status of a decision_id."""
    status = approval_store.get_status(decision_id)
    return {
        "decision_id": decision_id,
        "status": status or "pending",
    }
