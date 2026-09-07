import asyncio
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bridger.config import Config
from bridger.models import PermissionRequest
from bridger.opencode_client import OpencodeClient

logger = logging.getLogger(__name__)

pending_messages: dict[str, int] = {}
pending_by_session: dict[str, list[PermissionRequest]] = {}

# ponytail: parse_mode Markdown de Telegram rechaza _ * ` [ ] sin cerrar → escaparlos
def _esc_md(s: str) -> str:
    return re.sub(r"([_*`\[\]])", r"\\\1", s)


def _remove_pending(req_id: str) -> None:
    """Remove a resolved request and clean up empty session entries."""
    for sess_list in pending_by_session.values():
        sess_list[:] = [r for r in sess_list if r.id != req_id]
    for sid in list(pending_by_session):
        if not pending_by_session[sid]:
            del pending_by_session[sid]

def format_request(req: PermissionRequest) -> str:
    meta = req.metadata
    cmd = _esc_md(meta.get("command", ""))
    cwd = _esc_md(meta.get("cwd", ""))
    patterns = ", ".join(_esc_md(p) for p in req.patterns) if req.patterns else "(none)"
    return (
        f"🔐 **Permiso solicitado**\n"
        f"Tool: `{_esc_md(req.tool)}`\n"
        f"Patrones: {patterns}\n"
        f"Comando: `{cmd}`\n"
        f"Directorio: `{cwd}`\n"
        f"Session: `{_esc_md(req.session_id)}`\n"
        f"ID: `{_esc_md(req.id)}`\n\n"
        f"¿Aprobar?"
    )

async def run_bot(queue: asyncio.Queue, client: OpencodeClient, config: Config):
    async def send_permission(req: PermissionRequest):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{req.id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny:{req.id}"),
        ]])
        msg = await app.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=format_request(req),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        pending_messages[req.id] = msg.message_id
        pending_by_session.setdefault(req.session_id, []).append(req)

    async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, req_id = query.data.split(":", 1)
        reply = "once" if action == "approve" else "reject"
        try:
            await client.reply(req_id, reply, config.opencode_working_dir)
            _remove_pending(req_id)
            pending_messages.pop(req_id, None)
            await query.edit_message_text(
                text=f"{query.message.text}\n\n{'✅ Aprobado' if action == 'approve' else '❌ Denegado'}"
            )
        except Exception as e:
            logger.error("Failed to reply: %s", e)
            await query.edit_message_text(text=f"{query.message.text}\n\n⚠️ Error: {e}")

    async def on_approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /approve <request_id>")
            return
        req_id = context.args[0]
        try:
            await client.reply(req_id, "once", config.opencode_working_dir)
            _remove_pending(req_id)
            pending_messages.pop(req_id, None)
            await update.message.reply_text(f"✅ Aprobado: `{req_id}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")

    async def on_deny_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /deny <request_id>")
            return
        req_id = context.args[0]
        try:
            await client.reply(req_id, "reject", config.opencode_working_dir)
            _remove_pending(req_id)
            pending_messages.pop(req_id, None)
            await update.message.reply_text(f"❌ Denegado: `{req_id}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")

    async def on_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not pending_by_session:
            await update.message.reply_text("No hay permisos pendientes.")
            return
        lines = ["📋 **Permisos pendientes:**"]
        for sess_id, reqs in pending_by_session.items():
            for req in reqs:
                lines.append(f"  • `{req.id}` [{req.tool}] session={sess_id}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(CommandHandler("approve", on_approve_cmd))
    app.add_handler(CommandHandler("deny", on_deny_cmd))
    app.add_handler(CommandHandler("list", on_list_cmd))

    async def queue_consumer():
        while True:
            req = await queue.get()
            try:
                await send_permission(req)
            except Exception as e:
                logger.error("Failed to send permission %s: %s", req.id, e)

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    consumer_task = asyncio.create_task(queue_consumer())
    try:
        await consumer_task
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
