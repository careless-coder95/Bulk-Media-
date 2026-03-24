import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo
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
    COLLECTING_MEDIA,
    AWAITING_REPEAT,
    CONFIRM_PUBLISH,
) = range(6)

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_admin(user_id):
    return user_id in ADMIN_IDS

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Select Target", callback_data="select_target")],
        [InlineKeyboardButton("➕ Add Media to Album", callback_data="add_media")],
        [InlineKeyboardButton("👁 View Album", callback_data="view_album")],
        [InlineKeyboardButton("🗑 Clear Album", callback_data="clear_album")],
        [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
    ])

def album_summary(user_id):
    items = db.get_album(user_id)
    repeat = db.get_repeat(user_id)
    count = len(items)
    if count == 0:
        return "📸 Album: <i>Empty</i>"
    types = [i["type"].upper() for i in items]
    return f"📸 Album: <b>{count} item(s)</b> ({', '.join(types)}) × <b>{repeat}</b>"

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return ConversationHandler.END
    context.user_data.clear()
    target = db.get_target(user.id)
    target_text = f"🎯 Target: <b>{target['title']}</b>" if target else "🎯 Target: <i>Not selected</i>"
    await update.message.reply_html(
        f"👋 Hello <b>{user.first_name}</b>!\n\n"
        f"{target_text}\n"
        f"{album_summary(user.id)}\n\n"
        "What do you want to do?",
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
        f"{target_text}\n"
        f"{album_summary(user.id)}\n\n"
        "What do you want to do?",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

# ── Target ────────────────────────────────────────────────────────────────────

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
        "Send channel/group username or ID:\n\n"
        "• <code>@mychannel</code>\n"
        "• <code>-1001234567890</code>\n\n"
        "Or forward any message from that chat.",
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
        await update.message.reply_text("❌ Invalid. Send a valid username or ID.")
        return ADDING_TARGET_INPUT
    try:
        chat = await context.bot.get_chat(chat_id_input)
        db.save_target(user.id, chat.id, chat.title or str(chat.id))
        db.set_active_target(user.id, chat.id)
        await update.message.reply_html(
            f"✅ Target set: <b>{chat.title}</b>",
            reply_markup=main_menu_keyboard()
        )
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

# ── Album Building ────────────────────────────────────────────────────────────

async def add_media_prompt(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    current = db.get_album(user.id)
    count = len(current)

    if count >= 10:
        await query.edit_message_text(
            "⚠️ Album mein already 10 items hain — Telegram ki maximum limit!\n\n"
            "Pehle publish karo ya album clear karo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
                [InlineKeyboardButton("🗑 Clear Album", callback_data="clear_album")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
            ])
        )
        return MAIN_MENU

    remaining = 10 - count
    await query.edit_message_text(
        f"📸 Album mein abhi <b>{count}</b> item(s) hain.\n"
        f"Aur <b>{remaining}</b> add kar sakte ho.\n\n"
        "Photo ya Video bhejo:\n"
        "<i>(Ek ek karke bhejo, sab album mein add hote jayenge)</i>\n\n"
        "Jab sab add ho jayein toh Done dabao.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done — Set Repeat", callback_data="done_adding")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_main")],
        ])
    )
    return COLLECTING_MEDIA

async def receive_media(update, context):
    msg = update.message
    user = update.effective_user
    current = db.get_album(user.id)

    if len(current) >= 10:
        await msg.reply_text(
            "⚠️ Album full hai! Maximum 10 items.\n"
            "Done button dabao aur publish karo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Done — Set Repeat", callback_data="done_adding")],
                [InlineKeyboardButton("🗑 Clear & Start Over", callback_data="clear_album")],
            ])
        )
        return COLLECTING_MEDIA

    item = None
    if msg.photo:
        item = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.video:
        item = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    else:
        await msg.reply_text(
            "❌ Sirf Photo ya Video support hai album mein.\n"
            "Document aur text is mode mein nahi chalega.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Done — Set Repeat", callback_data="done_adding")],
                [InlineKeyboardButton("🔙 Cancel", callback_data="back_main")],
            ])
        )
        return COLLECTING_MEDIA

    db.add_to_album(user.id, item)
    new_count = len(db.get_album(user.id))
    remaining = 10 - new_count

    await msg.reply_text(
        f"✅ Added! [{item['type'].upper()}]\n"
        f"📸 Album mein abhi: <b>{new_count}</b> item(s)\n"
        f"{'⚠️ Album full! Done dabao.' if remaining == 0 else f'Aur {remaining} add kar sakte ho.'}\n\n"
        "Aur bhejo ya Done dabao.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done — Set Repeat", callback_data="done_adding")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_main")],
        ])
    )
    return COLLECTING_MEDIA

async def done_adding(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    items = db.get_album(user.id)

    if not items:
        await query.edit_message_text(
            "❌ Album empty hai! Pehle kuch add karo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
        )
        return MAIN_MENU

    types = [i["type"].upper() for i in items]
    await query.edit_message_text(
        f"✅ Album ready!\n"
        f"📸 <b>{len(items)}</b> items: {', '.join(types)}\n\n"
        "🔁 Ye album kitni baar bhejni hai?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1", callback_data="repeat_1"),
                InlineKeyboardButton("2", callback_data="repeat_2"),
                InlineKeyboardButton("3", callback_data="repeat_3"),
            ],
            [
                InlineKeyboardButton("5", callback_data="repeat_5"),
                InlineKeyboardButton("10", callback_data="repeat_10"),
                InlineKeyboardButton("Custom", callback_data="repeat_custom"),
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ])
    )
    return AWAITING_REPEAT

async def set_repeat(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "repeat_custom":
        await query.edit_message_text(
            "✏️ Kitni baar bhejni hai album? (1–500 likhो):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_main")]])
        )
        context.user_data["awaiting_custom_repeat"] = True
        return AWAITING_REPEAT
    repeat = int(query.data.replace("repeat_", ""))
    db.set_repeat(update.effective_user.id, repeat)
    await _show_repeat_confirmed(query, update.effective_user.id, repeat)
    return MAIN_MENU

async def receive_custom_repeat(update, context):
    if not context.user_data.get("awaiting_custom_repeat"):
        return AWAITING_REPEAT
    try:
        repeat = int(update.message.text.strip())
        if repeat < 1 or repeat > 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ 1 aur 500 ke beech number likho.")
        return AWAITING_REPEAT
    context.user_data["awaiting_custom_repeat"] = False
    db.set_repeat(update.effective_user.id, repeat)
    items = db.get_album(update.effective_user.id)
    await update.message.reply_html(
        f"✅ Set! Album <b>{repeat} baar</b> bhejoge.\n"
        f"📸 {len(items)} items ready.\n\n"
        "Ab Publish karo!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ])
    )
    return MAIN_MENU

async def _show_repeat_confirmed(query, user_id, repeat):
    items = db.get_album(user_id)
    await query.edit_message_text(
        f"✅ Set! Album <b>{repeat} baar</b> bhejoge.\n"
        f"📸 {len(items)} items ready.\n\n"
        "Ab Publish karo!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
            [InlineKeyboardButton("➕ Add More Media", callback_data="add_media")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ])
    )

# ── View / Clear Album ────────────────────────────────────────────────────────

async def view_album(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    items = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not items:
        await query.edit_message_text(
            "📭 Album empty hai.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
        )
        return MAIN_MENU

    lines = [f"📸 Album ({len(items)} items) × {repeat} baar:\n"]
    for i, item in enumerate(items):
        caption = item.get("caption", "")
        preview = caption[:25] + "..." if len(caption) > 25 else caption
        lines.append(f"{i+1}. [{item['type'].upper()}] {preview or '(no caption)'}")

    lines.append(f"\n📤 Total bhejega: <b>{len(items)} items × {repeat} = {repeat} albums</b>")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Publish", callback_data="publish")],
            [InlineKeyboardButton("🗑 Clear Album", callback_data="clear_album")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
        ])
    )
    return MAIN_MENU

async def clear_album(update, context):
    query = update.callback_query
    await query.answer()
    db.clear_album(update.effective_user.id)
    db.set_repeat(update.effective_user.id, 1)
    await query.edit_message_text(
        "🗑 Album clear ho gaya!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]])
    )
    return MAIN_MENU

# ── Publish ───────────────────────────────────────────────────────────────────

async def publish_confirm(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    target = db.get_target(user.id)
    items = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not target:
        await query.edit_message_text(
            "❌ Target select nahi kiya!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
        )
        return MAIN_MENU

    if not items:
        await query.edit_message_text(
            "❌ Album empty hai!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
        )
        return MAIN_MENU

    await query.edit_message_text(
        f"🚀 Publish karne wala hai!\n\n"
        f"🎯 Target: <b>{target['title']}</b>\n"
        f"📸 Album: <b>{len(items)} media</b>\n"
        f"🔁 Repeat: <b>{repeat} baar</b>\n\n"
        f"Matlab: <b>{repeat} baar</b> ek album jayega jisme <b>{len(items)} items</b> honge.\n\n"
        "Confirm?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Publish Now!", callback_data="confirm_publish"),
                InlineKeyboardButton("❌ Cancel", callback_data="back_main"),
            ]
        ])
    )
    return CONFIRM_PUBLISH

async def do_publish(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    target = db.get_target(user.id)
    items = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not target or not items:
        await query.edit_message_text("❌ Kuch galat ho gaya.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    await query.edit_message_text(
        f"⏳ Publish ho raha hai <b>{target['title']}</b> mein...\n"
        f"0 / {repeat} albums sent",
        parse_mode="HTML"
    )

    sent = 0
    errors = 0
    chat_id = target["chat_id"]

    # Build InputMedia list
    def build_media_group(items):
        media_group = []
        for idx, item in enumerate(items):
            caption = item.get("caption") or None
            # Only first item gets caption in album
            c = caption if idx == 0 else None
            if item["type"] == "photo":
                media_group.append(InputMediaPhoto(media=item["file_id"], caption=c))
            elif item["type"] == "video":
                media_group.append(InputMediaVideo(media=item["file_id"], caption=c))
        return media_group

    for i in range(repeat):
        try:
            media_group = build_media_group(items)
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            sent += 1
        except Exception as e:
            logger.error(f"Send error (round {i+1}): {e}")
            errors += 1

        await asyncio.sleep(2)

        # Progress update
        try:
            await query.edit_message_text(
                f"⏳ Publish ho raha hai...\n{sent} / {repeat} albums sent",
                parse_mode="HTML"
            )
        except Exception:
            pass

    db.clear_album(user.id)
    db.set_repeat(user.id, 1)

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            f"✅ <b>Publish complete!</b>\n\n"
            f"🎯 Target: <b>{target['title']}</b>\n"
            f"📸 Album sent: <b>{sent}/{repeat}</b>\n"
            f"❌ Errors: <b>{errors}</b>"
        ),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set! .env file check karo.")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(select_target_menu, pattern="^select_target$"),
                CallbackQueryHandler(add_media_prompt, pattern="^add_media$"),
                CallbackQueryHandler(view_album, pattern="^view_album$"),
                CallbackQueryHandler(clear_album, pattern="^clear_album$"),
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
            COLLECTING_MEDIA: [
                MessageHandler(
                    (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
                    receive_media
                ),
                CallbackQueryHandler(done_adding, pattern="^done_adding$"),
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
