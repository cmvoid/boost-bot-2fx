"""Telegram bot to send boosting services through an SMM panel.

Main commands:
  /start, /help             - welcome message and guide
  /id                       - show the chat id and user id (useful for setup)
  /balance                  - show the panel balance
  /services                 - list the services configured in the bot
  /panelservices <search>   - search raw services from the panel
  /status <order_id>        - status of an order
  /<service> <link> <qty>   - place an order (e.g. /members https://t.me/channel 1000)
  /order <service> <link> <qty> - generic form
"""

from __future__ import annotations

import html
import logging
from functools import partial
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import Config
from services import BoostService, SERVICES, services_by_command
from smm_api import Balance, SmmApiError, SmmClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("boost-bot")

CONFIG: Config = Config.load()
SMM = SmmClient(CONFIG.smm_api_url, CONFIG.smm_api_key)
SERVICE_MAP = services_by_command()

# Flag used to avoid spamming the low-balance alert.
LOW_BALANCE_KEY = "low_balance_alerted"


# --------------------------------------------------------------------------- #
# Access control helpers
# --------------------------------------------------------------------------- #
UNAUTHORIZED_MESSAGE = "You are not authorized to use this bot."


def _user_authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in CONFIG.authorized_user_ids)


async def _guard(update: Update) -> bool:
    """Return True if the user is authorized; otherwise reply and return False."""
    if not _user_authorized(update):
        if update.effective_message:
            await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return False
    return True


def fmt_balance(b: Balance) -> str:
    return f"{b.amount:.2f} {b.currency}".strip()


# --------------------------------------------------------------------------- #
# Basic commands
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.effective_message.reply_text(_help_text(), parse_mode=ParseMode.HTML)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    chat = update.effective_chat
    user = update.effective_user
    lines = [
        "<b>Chat info</b>",
        f"Your user id: <code>{user.id}</code>" if user else "Your user id: n/a",
        f"Chat id: <code>{chat.id}</code>" if chat else "",
        f"Chat type: <code>{chat.type}</code>" if chat else "",
    ]
    text = "\n".join(l for l in lines if l)
    text += (
        "\n\nTo authorize a user, add their <b>user id</b> to the "
        "<code>AUTHORIZED_USER_IDS</code> field of the .env file."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.effective_message.reply_text("Checking balance...")
    try:
        balance = await SMM.get_balance()
    except SmmApiError as exc:
        await msg.edit_text(f"Error fetching balance:\n{exc}")
        return
    await msg.edit_text(f"Current panel balance: <b>{fmt_balance(balance)}</b>",
                        parse_mode=ParseMode.HTML)


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not SERVICES:
        await update.effective_message.reply_text(
            "No services configured. Edit the services.py file."
        )
        return
    lines = ["<b>Available services</b>", ""]
    for s in SERVICES:
        configured = "" if s.service_id else "  ⚠️ <i>service_id not set</i>"
        lines.append(
            f"• /{s.command} — {html.escape(s.label)}{configured}\n"
            f"   usage: <code>/{s.command} &lt;link&gt; &lt;quantity&gt;</code>"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_panelservices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search raw services from the panel (useful to find the service_id)."""
    if not await _guard(update):
        return
    query = " ".join(context.args).strip().lower() if context.args else ""
    msg = await update.effective_message.reply_text("Fetching services from the panel...")
    try:
        services = await SMM.get_services()
    except SmmApiError as exc:
        await msg.edit_text(f"Error: {exc}")
        return

    matches = []
    for svc in services:
        name = str(svc.get("name", ""))
        if not query or query in name.lower():
            matches.append(svc)

    if not matches:
        await msg.edit_text(f"No service found for '{query}'.")
        return

    lines = [f"<b>Services from the panel</b> (first 30 of {len(matches)})", ""]
    for svc in matches[:30]:
        lines.append(
            f"ID <code>{svc.get('service')}</code> — {html.escape(str(svc.get('name','')))}\n"
            f"   rate: {svc.get('rate')} | min: {svc.get('min')} | max: {svc.get('max')}"
        )
    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /status <order_id>")
        return
    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("The order id must be a number.")
        return
    msg = await update.effective_message.reply_text("Checking status...")
    try:
        status = await SMM.get_status(order_id)
    except SmmApiError as exc:
        await msg.edit_text(f"Error: {exc}")
        return
    text = (
        f"<b>Order {order_id}</b>\n"
        f"Status: <b>{html.escape(str(status.get('status', 'n/a')))}</b>\n"
        f"Start count: {status.get('start_count', 'n/a')}\n"
        f"Remaining: {status.get('remains', 'n/a')}\n"
        f"Charge: {status.get('charge', 'n/a')}"
    )
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
async def _place_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service: BoostService,
    args: list[str],
) -> None:
    if not await _guard(update):
        return

    if len(args) < 2:
        await update.effective_message.reply_text(
            f"Usage: /{service.command} <link> <quantity>\n"
            f"Example: /{service.command} https://t.me/your_channel 1000"
        )
        return

    link = args[0].strip()
    qty_raw = args[1].strip()

    if not (link.startswith("http://") or link.startswith("https://") or link.startswith("t.me/") or link.startswith("@")):
        await update.effective_message.reply_text(
            "The link does not look valid. Enter the channel/post link "
            "(e.g. https://t.me/your_channel)."
        )
        return

    try:
        quantity = int(qty_raw)
    except ValueError:
        await update.effective_message.reply_text("The quantity must be an integer.")
        return

    if service.service_id <= 0:
        await update.effective_message.reply_text(
            f"The service '{service.label}' does not have a valid service_id yet.\n"
            "Set the correct ID in services.py (you can find it with /panelservices)."
        )
        return

    if quantity < service.min_quantity or quantity > service.max_quantity:
        await update.effective_message.reply_text(
            f"Quantity out of range for {service.label}: "
            f"min {service.min_quantity}, max {service.max_quantity}."
        )
        return

    msg = await update.effective_message.reply_text(
        f"Placing order: {service.label}\nLink: {link}\nQuantity: {quantity}..."
    )

    try:
        order = await SMM.add_order(service.service_id, link, quantity)
    except SmmApiError as exc:
        await msg.edit_text(f"❌ Order failed:\n{exc}")
        await _maybe_alert_insufficient_funds(context, str(exc))
        return

    await msg.edit_text(
        f"✅ Order created!\n"
        f"Service: {service.label}\n"
        f"Link: {link}\n"
        f"Quantity: {quantity}\n"
        f"Order id: {order.order_id}\n\n"
        f"Check the status with /status {order.order_id}"
    )

    # After each order, check the balance to alert in time.
    await _check_balance_and_alert(context)


async def cmd_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generic form: /order <service> <link> <quantity>."""
    if not await _guard(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /order <service> <link> <quantity>\n"
            "Services: " + ", ".join(SERVICE_MAP.keys())
        )
        return
    key = context.args[0].lower()
    service = SERVICE_MAP.get(key)
    if not service:
        await update.effective_message.reply_text(
            f"Service '{key}' not found. Available: " + ", ".join(SERVICE_MAP.keys())
        )
        return
    await _place_order(update, context, service, context.args[1:])


async def _service_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service: BoostService
) -> None:
    await _place_order(update, context, service, context.args or [])


# --------------------------------------------------------------------------- #
# Balance notifications
# --------------------------------------------------------------------------- #
async def _notify_authorized(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Send a private notification to every authorized user."""
    if not CONFIG.authorized_user_ids:
        logger.warning("No authorized users set: cannot send notification.")
        return
    for user_id in CONFIG.authorized_user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id, text=text, parse_mode=ParseMode.HTML
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to notify user %s: %s", user_id, exc)


async def _maybe_alert_insufficient_funds(
    context: ContextTypes.DEFAULT_TYPE, error_text: str
) -> None:
    lowered = error_text.lower()
    if any(k in lowered for k in ("balance", "funds", "insufficient")):
        await _notify_authorized(
            context,
            "🔴 <b>SMM panel balance depleted!</b>\n"
            "An order was rejected due to insufficient funds.\n"
            "Top up the balance to keep delivering services.",
        )


async def _check_balance_and_alert(context: ContextTypes.DEFAULT_TYPE) -> Optional[Balance]:
    try:
        balance = await SMM.get_balance()
    except SmmApiError as exc:
        logger.error("Balance check failed: %s", exc)
        return None

    already_alerted = context.bot_data.get(LOW_BALANCE_KEY, False)

    if balance.amount <= CONFIG.balance_low_threshold:
        if not already_alerted:
            context.bot_data[LOW_BALANCE_KEY] = True
            await _notify_authorized(
                context,
                f"⚠️ <b>Panel balance almost depleted</b>\n"
                f"Current balance: <b>{fmt_balance(balance)}</b>\n"
                f"Alert threshold: {CONFIG.balance_low_threshold:.2f}\n\n"
                f"Top up the balance to avoid interrupting the services.",
            )
    else:
        # Balance back above threshold: reset the alert.
        if already_alerted:
            context.bot_data[LOW_BALANCE_KEY] = False
            await _notify_authorized(
                context,
                f"✅ Balance topped up: <b>{fmt_balance(balance)}</b>. All good.",
            )
    return balance


async def job_check_balance(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check_balance_and_alert(context)


# --------------------------------------------------------------------------- #
# Help text
# --------------------------------------------------------------------------- #
def _help_text() -> str:
    lines = [
        "👋 <b>Boost Bot</b> — send Telegram boosting services.",
        "",
        "<b>Service commands:</b>",
    ]
    for s in SERVICES:
        lines.append(f"• <code>/{s.command} &lt;link&gt; &lt;quantity&gt;</code> — {html.escape(s.label)}")
    lines += [
        "",
        "<b>Other commands:</b>",
        "• /balance — panel balance",
        "• /services — bot service list",
        "• /status &lt;order_id&gt; — status of an order",
        "• /id — id of this chat (for setup)",
        "",
        "Example: <code>/members https://t.me/your_channel 1000</code>",
    ]
    return "\n".join(lines)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.effective_message.reply_text(_help_text(), parse_mode=ParseMode.HTML)


# --------------------------------------------------------------------------- #
# Application setup
# --------------------------------------------------------------------------- #
def build_application() -> Application:
    app = Application.builder().token(CONFIG.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("panelservices", cmd_panelservices))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("order", cmd_order))

    # One command per configured service.
    for service in SERVICES:
        app.add_handler(
            CommandHandler(service.command, partial(_service_command, service=service))
        )

    # Periodic balance-check job.
    if app.job_queue is not None:
        interval = CONFIG.balance_check_interval_min * 60
        app.job_queue.run_repeating(job_check_balance, interval=interval, first=10)
    else:
        logger.warning(
            "JobQueue not available: install python-telegram-bot[job-queue]."
        )

    return app


def main() -> None:
    logger.info("Starting Boost Bot...")
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
