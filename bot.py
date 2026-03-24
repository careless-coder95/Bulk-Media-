import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
from database import Database

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(","))) if os.environ.get("ADMIN_IDS") else []

db = Database()

(
    MAIN_MENU,
    SELECTING_TARGET,
    ADDING_TARGET_INPUT,
    BUILDING_QUEUE,
    AWAITING_MEDIA,
    AWAITING_REPEAT,
    CONFIRM_PUBLISH,
) = range(7)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Select Target", callback_data="select_target")],
        [InlineKeyboardButton("➕ Add to Queue", callback_data="add_queue")],
        [InlineKeyboardButton("👁 View Queue", callback_data="view_queue")],
        [InlineKeyboardButton("🗑 Clear Queue", callback_data="clear_queue")],
        [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
    ])

def queue_item_text(item, idx):
    kind = item["type"].upper()
    caption = item.get("caption") or item.get("text", "")
    preview = caption[:30] + "..." if len(caption) > 30 else caption
    return f"{idx+1}. [{kind}] {preview or '(no caption)'} × {item['repeat']}"

async def start(update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ You are not authorized.")
        return ConversationHandler.END
    context.user_data.clear()
    target = db.get_target(user.id)
    target_text = f"🎯 Target: <b>{target['title']}</b>" if target else "🎯 Target: <i>Not selected</i>"
    await update.message.reply_html(
        f"👋 Hello <b>{user.first_name}</b>!\n\n{target_text}\n"
        f"📦 Queue: <b>{db.queue_count(user.id)}</b> items\n\nWhat do you want to do?",
        reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

async def menu_refresh(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    target = db.get_target(user.id)
    target_text = f"🎯 Target: <b>{target['title']}</b>" if target else "🎯 Target: <i>Not selected</i>"
    await query.edit_message_text(
        f"{target_text}\n📦 Queue: <b>{db.queue_count(user.id)}</b> items\n\nWhat do you want to do?",
        parse_mode="HTML", reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

async def select_target_menu(update, context):
    query = update.callback_query
    await query.answer()
    saved = db.list_saved_targets(update.effective_user.id)
    buttons = [[InlineKeyboardButton(f"📢 {t['title']}", callback_data=f"settarget_{t['chat_id']}")] for t in saved]
    buttons.append([InlineKeyboardButton("➕ Add new channel/group", callback_data="add_new_target")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    await query.edit_message_text(
        "Select target:\n\n<i>Bot must be admin with Send Messages permission.</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECTING_TARGET

async def add_new_target(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Send channel/group username or ID:\n\n• <code>@mychannel</code>\n• <code>-1001234567890</code>\n\nOr forward any message from that chat.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_main")]])
    )
    return ADDING_TARGET_INPUT

async def receive_target_input(update, context):
    user = update.effective_user
    text = update.message.text.strip() if update.message.text else None
    fwd = update.message.forward_origin
    chat_id_input = None
    if fwd and hasattr(fwd, "chat"):
        chat_id_input = fwd.chat.id
    elif text:
        chat_id_input = text
    if not chat_id_input:
        await update.message.reply_text("❌ Invalid. Send a username or ID.")
        return ADDING_TARGET_INPUT
    try:
        chat = await context.bot.get_chat(chat_id_input)
        db.save_target(user.id, chat.id, chat.title or str(chat.id))
        db.set_active_target(user.id, chat.id)
        await update.message.reply_html(f"✅ Target set: <b>{chat.title}</b>", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error: {e}\n\nMake sure bot is admin there.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
        )
        return ADDING_TARGET_INPUT

async def set_saved_target(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.replace("settarget_", ""))
    db.set_active_target(update.effective_user.id, chat_id)
    target = db.get_target(update.effective_user.id)
    await query.edit_message_text(
        f"✅ Target set: <b>{target['title']}</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]])
    )
    return MAIN_MENU

async def add_queue_prompt(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📨 Send content to add to queue:\n\n• Text\n• Photo\n• Video\n• Document\n\n<i>One item at a time.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_main")]])
    )
    return AWAITING_MEDIA

async def receive_media(update, context):
    msg = update.message
    item = {}
    if msg.photo:
        item = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.video:
        item = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    elif msg.document:
        item = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
    elif msg.text:
        item = {"type": "text", "text": msg.text}
    else:
        await msg.reply_text("❌ Unsupported type. Send text, photo, video, or document.")
        return AWAITING_MEDIA
    context.user_data["pending_item"] = item
    preview = (item.get("caption") or item.get("text", ""))[:40]
    await msg.reply_text(
        f"✅ Got it! [{item['type'].upper()}] {preview}\n\n🔁 How many times to send?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1", callback_data="repeat_1"), InlineKeyboardButton("2", callback_data="repeat_2"), InlineKeyboardButton("3", callback_data="repeat_3")],
            [InlineKeyboardButton("5", callback_data="repeat_5"), InlineKeyboardButton("10", callback_data="repeat_10"), InlineKeyboardButton("Custom", callback_data="repeat_custom")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_main")]
        ])
    )
    return AWAITING_REPEAT

async def set_repeat(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "repeat_custom":
        await query.edit_message_text(
            "✏️ Type repeat count (1–500):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_main")]])
        )
        context.user_data["awaiting_custom_repeat"] = True
        return AWAITING_REPEAT
    repeat = int(query.data.replace("repeat_", ""))
    await _save_queue_item(update, context, repeat)
    return MAIN_MENU

async def receive_custom_repeat(update, context):
    if not context.user_data.get("awaiting_custom_repeat"):
        return AWAITING_REPEAT
    try:
        repeat = int(update.message.text.strip())
        if repeat < 1 or repeat > 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter a number between 1 and 500.")
        return AWAITING_REPEAT
    context.user_data["awaiting_custom_repeat"] = False
    await _save_queue_item(update, context, repeat)
    return MAIN_MENU

async def _save_queue_item(update, context, repeat):
    user = update.effective_user
    item = context.user_data.pop("pending_item", None)
    if not item:
        return
    item["repeat"] = repeat
    db.add_to_queue(user.id, item)
    count = db.queue_count(user.id)
    text = f"✅ Added! Repeat: <b>{repeat}×</b>\n📦 Queue total: <b>{count}</b> items\n\nAdd more or Publish."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add More", callback_data="add_queue")],
        [InlineKeyboardButton("👁 View Queue", callback_data="view_queue")],
        [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_html(text, reply_markup=kb)

async def view_queue(update, context):
    query = update.callback_query
    await query.answer()
    items = db.get_queue(update.effective_user.id)
    if not items:
        await query.edit_message_text("📭 Queue is empty.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return MAIN_MENU
    lines = [f"📦 Queue ({len(items)} items):\n"]
    total_sends = 0
    for i, item in enumerate(items):
        lines.append(queue_item_text(item, i))
        total_sends += item["repeat"]
    lines.append(f"\n📤 Total sends: <b>{total_sends}</b>")
    await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
        [InlineKeyboardButton("🗑 Clear Queue", callback_data="clear_queue")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ]))
    return MAIN_MENU

async def clear_queue(update, context):
    query = update.callback_query
    await query.answer()
    db.clear_queue(update.effective_user.id)
    await query.edit_message_text("🗑 Queue cleared!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]]))
    return MAIN_MENU

async def publish_confirm(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    target = db.get_target(user.id)
    items = db.get_queue(user.id)
    if not target:
        await query.edit_message_text("❌ No target selected!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return MAIN_MENU
    if not items:
        await query.edit_message_text("❌ Queue is empty!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return MAIN_MENU
    total_sends = sum(item["repeat"] for item in items)
    await query.edit_message_text(
        f"🚀 Ready to publish!\n\n🎯 Target: <b>{target['title']}</b>\n📦 Items: <b>{len(items)}</b>\n📤 Total sends: <b>{total_sends}</b>\n\nConfirm?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Publish Now!", callback_data="confirm_publish"), InlineKeyboardButton("❌ Cancel", callback_data="back_main")]])
    )
    return CONFIRM_PUBLISH

async def do_publish(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    target = db.get_target(user.id)
    items = db.get_queue(user.id)
    if not target or not items:
        await query.edit_message_text("❌ Something went wrong.", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    total_sends = sum(item["repeat"] for item in items)
    await query.edit_message_text(f"⏳ Publishing to <b>{target['title']}</b>...\n0 / {total_sends} sent", parse_mode="HTML")
    sent = 0
    errors = 0
    chat_id = target["chat_id"]
    for item in items:
        for _ in range(item["repeat"]):
            try:
                if item["type"] == "text":
                    await context.bot.send_message(chat_id=chat_id, text=item["text"])
                elif item["type"] == "photo":
                    await context.bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=item.get("caption") or None)
                elif item["type"] == "video":
                    await context.bot.send_video(chat_id=chat_id, video=item["file_id"], caption=item.get("caption") or None)
                elif item["type"] == "document":
                    await context.bot.send_document(chat_id=chat_id, document=item["file_id"], caption=item.get("caption") or None)
                sent += 1
            except Exception as e:
                logger.error(f"Send error: {e}")
                errors += 1
            await asyncio.sleep(1.5)
            if sent % 5 == 0:
                try:
                    await query.edit_message_text(f"⏳ Publishing...\n{sent} / {total_sends} sent", parse_mode="HTML")
                except Exception:
                    pass
    db.clear_queue(user.id)
    await context.bot.send_message(
        chat_id=user.id,
        text=f"✅ <b>Done!</b>\n\n🎯 Target: <b>{target['title']}</b>\n📤 Sent: <b>{sent}</b>\n❌ Errors: <b>{errors}</b>",
        parse_mode="HTML", reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set! .env file check karo.")
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(select_target_menu, pattern="^select_target$"),
                CallbackQueryHandler(add_queue_prompt, pattern="^add_queue$"),
                CallbackQueryHandler(view_queue, pattern="^view_queue$"),
                CallbackQueryHandler(clear_queue, pattern="^clear_queue$"),
                CallbackQueryHandler(publish_confirm, pattern="^publish$"),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            SELECTING_TARGET: [
                CallbackQueryHandler(add_new_target, pattern="^add_new_target$"),
                CallbackQueryHandler(set_saved_target, pattern="^settarget_"),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            ADDING_TARGET_INPUT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_target_input),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            AWAITING_MEDIA: [
                MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, receive_media),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            AWAITING_REPEAT: [
                CallbackQueryHandler(set_repeat, pattern="^repeat_\\d+$"),
                CallbackQueryHandler(set_repeat, pattern="^repeat_custom$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_repeat),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            CONFIRM_PUBLISH: [
                CallbackQueryHandler(do_publish, pattern="^confirm_publish$"),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    app.add_handler(conv)
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
