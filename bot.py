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

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
OWNER_ID   = int(os.environ.get("OWNER_ID", "0"))

db = Database()

(
    MAIN_MENU,
    SELECTING_TARGET,
    ADDING_TARGET_INPUT,
    COLLECTING_MEDIA,
    AWAITING_REPEAT,
    CONFIRM_PUBLISH,
) = range(6)

# ═══════════════════════════════════════════════════════════
#  ACCESS CONTROL
# ═══════════════════════════════════════════════════════════

def is_owner(uid):   return uid == OWNER_ID
def is_sudo(uid):    return is_owner(uid) or db.is_sudo(uid)

# ═══════════════════════════════════════════════════════════
#  UI HELPERS
# ═══════════════════════════════════════════════════════════

DIVIDER = "─" * 20

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯  Select Target",     callback_data="select_target")],
        [InlineKeyboardButton("📸  Add Media to Album", callback_data="add_media")],
        [InlineKeyboardButton("👁  View Album",         callback_data="view_album")],
        [InlineKeyboardButton("🗑  Clear Album",        callback_data="clear_album")],
        [InlineKeyboardButton("🚀  Publish Now",        callback_data="publish")],
    ])

def back_btn(dest="back_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data=dest)]])

def album_summary(user_id):
    items  = db.get_album(user_id)
    repeat = db.get_repeat(user_id)
    if not items:
        return "📂  Album  ›  <i>empty</i>"
    types = " · ".join(i["type"].upper() for i in items)
    return f"📂  Album  ›  <b>{len(items)} item(s)</b>  ·  {types}\n🔁  Repeat  ›  <b>{repeat}×</b>"

def home_text(user):
    target     = db.get_target(user.id)
    tgt_line   = f"<b>{target['title']}</b>" if target else "<i>not selected</i>"
    return (
        f"┌─────────────────────────\n"
        f"│  📡  <b>Bulk Media Bot</b>\n"
        f"└─────────────────────────\n\n"
        f"👤  <b>{user.first_name}</b>\n\n"
        f"🎯  Target  ›  {tgt_line}\n"
        f"{album_summary(user.id)}\n\n"
        f"<i>Select an option below 👇</i>"
    )

# ═══════════════════════════════════════════════════════════
#  /start  &  menu refresh
# ═══════════════════════════════════════════════════════════

async def start(update, context):
    user = update.effective_user
    if not is_sudo(user.id):
        await update.message.reply_text("⛔  Access denied.")
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_html(home_text(user), reply_markup=main_menu_keyboard())
    return MAIN_MENU

async def menu_refresh(update, context):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    await q.edit_message_text(home_text(user), parse_mode="HTML", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ═══════════════════════════════════════════════════════════
#  SUDO COMMANDS  (owner only)
# ═══════════════════════════════════════════════════════════

async def cmd_addsudo(update, context):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_html("⛔  Sirf <b>owner</b> yeh command use kar sakta hai.")
        return

    if not context.args:
        await update.message.reply_html(
            "╔══════════════════════\n"
            "║  ⚙️  <b>Add Sudo User</b>\n"
            "╚══════════════════════\n\n"
            "Usage:\n"
            "<code>/addsudo [user_id]</code>\n\n"
            "Example:\n"
            "<code>/addsudo 123456789</code>"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_html("❌  Invalid user ID. Numbers only likhो.")
        return

    if target_id == OWNER_ID:
        await update.message.reply_html("ℹ️  Owner already has full access.")
        return

    # Try to get name from Telegram
    name = f"<code>{target_id}</code>"
    try:
        chat = await context.bot.get_chat(target_id)
        name = f"<b>{chat.full_name}</b>"
    except Exception:
        pass

    db.add_sudo(target_id)
    await update.message.reply_html(
        f"╔══════════════════════\n"
        f"║  ✅  <b>Sudo Granted</b>\n"
        f"╚══════════════════════\n\n"
        f"👤  User  ›  {name}\n"
        f"🆔  ID  ›  <code>{target_id}</code>\n"
        f"🔑  Access  ›  <b>Granted</b>"
    )

async def cmd_rmsudo(update, context):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_html("⛔  Sirf <b>owner</b> yeh command use kar sakta hai.")
        return

    if not context.args:
        await update.message.reply_html(
            "╔══════════════════════\n"
            "║  ⚙️  <b>Remove Sudo User</b>\n"
            "╚══════════════════════\n\n"
            "Usage:\n"
            "<code>/rmsudo [user_id]</code>\n\n"
            "Example:\n"
            "<code>/rmsudo 123456789</code>"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_html("❌  Invalid user ID.")
        return

    if target_id == OWNER_ID:
        await update.message.reply_html("⚠️  Owner ka access remove nahi ho sakta.")
        return

    if not db.is_sudo(target_id):
        await update.message.reply_html(
            f"ℹ️  <code>{target_id}</code> already sudo list mein nahi hai."
        )
        return

    name = f"<code>{target_id}</code>"
    try:
        chat = await context.bot.get_chat(target_id)
        name = f"<b>{chat.full_name}</b>"
    except Exception:
        pass

    db.remove_sudo(target_id)
    await update.message.reply_html(
        f"╔══════════════════════\n"
        f"║  🗑  <b>Sudo Removed</b>\n"
        f"╚══════════════════════\n\n"
        f"👤  User  ›  {name}\n"
        f"🆔  ID  ›  <code>{target_id}</code>\n"
        f"🔑  Access  ›  <b>Revoked</b>"
    )

async def cmd_sudolist(update, context):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_html("⛔  Sirf <b>owner</b> yeh command use kar sakta hai.")
        return

    sudo_users = db.list_sudo()

    lines = [
        "╔══════════════════════",
        "║  👑  <b>Sudo Users List</b>",
        "╚══════════════════════\n",
        f"👑  <b>Owner</b>  ›  <code>{OWNER_ID}</code>\n",
        f"{DIVIDER}",
    ]

    if not sudo_users:
        lines.append("\n<i>No sudo users added yet.</i>")
        lines.append(f"\nUse <code>/addsudo [id]</code> to add someone.")
    else:
        lines.append(f"\n<b>Sudo Users ({len(sudo_users)})</b>\n")
        for i, su in enumerate(sudo_users, 1):
            name_part = f"  ·  {su['name']}" if su.get("name") else ""
            lines.append(f"  <b>{i}.</b>  <code>{su['user_id']}</code>{name_part}")

    lines.append(f"\n{DIVIDER}")
    lines.append(f"📊  Total access  ›  <b>{len(sudo_users) + 1}</b> (including owner)")

    await update.message.reply_html("\n".join(lines))

# ═══════════════════════════════════════════════════════════
#  TARGET SELECTION
# ═══════════════════════════════════════════════════════════

async def select_target_menu(update, context):
    q = update.callback_query
    await q.answer()
    saved   = db.list_saved_targets(update.effective_user.id)
    buttons = [
        [InlineKeyboardButton(f"📢  {t['title']}", callback_data=f"settarget_{t['chat_id']}")]
        for t in saved
    ]
    buttons.append([InlineKeyboardButton("➕  Add new channel / group", callback_data="add_new_target")])
    buttons.append([InlineKeyboardButton("‹ Back", callback_data="back_main")])
    await q.edit_message_text(
        "╔══════════════════════\n"
        "║  🎯  <b>Select Target</b>\n"
        "╚══════════════════════\n\n"
        "<i>Bot must be admin with\n'Send Messages' permission.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECTING_TARGET

async def add_new_target(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "╔══════════════════════\n"
        "║  ➕  <b>Add New Target</b>\n"
        "╚══════════════════════\n\n"
        "Channel/group ka username ya ID bhejo:\n\n"
        "•  <code>@mychannel</code>\n"
        "•  <code>-1001234567890</code>\n\n"
        "<i>Ya us chat ka koi bhi message forward karo.</i>",
        parse_mode="HTML",
        reply_markup=back_btn()
    )
    return ADDING_TARGET_INPUT

async def receive_target_input(update, context):
    user = update.effective_user
    text = update.message.text.strip() if update.message.text else None
    fwd  = update.message.forward_origin
    chat_id_input = None
    if fwd and hasattr(fwd, "chat"):
        chat_id_input = fwd.chat.id
    elif text:
        chat_id_input = text
    if not chat_id_input:
        await update.message.reply_text("❌  Valid username ya ID bhejo.")
        return ADDING_TARGET_INPUT
    try:
        chat = await context.bot.get_chat(chat_id_input)
        db.save_target(user.id, chat.id, chat.title or str(chat.id))
        db.set_active_target(user.id, chat.id)
        await update.message.reply_html(
            f"✅  Target set!\n\n"
            f"📢  <b>{chat.title}</b>\n"
            f"🆔  <code>{chat.id}</code>",
            reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU
    except Exception as e:
        await update.message.reply_text(
            f"❌  Error: {e}\n\nBot ko us chat mein admin banao.",
            reply_markup=back_btn()
        )
        return ADDING_TARGET_INPUT

async def set_saved_target(update, context):
    q = update.callback_query
    await q.answer()
    chat_id = int(q.data.replace("settarget_", ""))
    db.set_active_target(update.effective_user.id, chat_id)
    target = db.get_target(update.effective_user.id)
    await q.edit_message_text(
        f"✅  Target set!\n\n🎯  <b>{target['title']}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Main Menu", callback_data="back_main")]])
    )
    return MAIN_MENU

# ═══════════════════════════════════════════════════════════
#  ALBUM BUILDING
# ═══════════════════════════════════════════════════════════

async def add_media_prompt(update, context):
    q    = update.callback_query
    await q.answer()
    user = update.effective_user
    count     = len(db.get_album(user.id))
    remaining = 10 - count

    if count >= 10:
        await q.edit_message_text(
            "⚠️  Album mein already <b>10 items</b> hain — Telegram ki max limit!\n\n"
            "Pehle publish karo ya album clear karo.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀  Publish",      callback_data="publish")],
                [InlineKeyboardButton("🗑  Clear Album",  callback_data="clear_album")],
                [InlineKeyboardButton("‹ Back",           callback_data="back_main")],
            ])
        )
        return MAIN_MENU

    await q.edit_message_text(
        f"╔══════════════════════\n"
        f"║  📸  <b>Add Media</b>\n"
        f"╚══════════════════════\n\n"
        f"📂  Items so far   ›  <b>{count}</b>\n"
        f"➕  Aur add kar sakte ho  ›  <b>{remaining}</b>\n\n"
        f"Photo ya Video bhejo — ek ek karke.\n"
        f"<i>Sab ek album mein jata hai.</i>\n\n"
        f"Jab ho jaye toh <b>Done</b> dabao 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅  Done — Set Repeat", callback_data="done_adding")],
            [InlineKeyboardButton("‹ Cancel",              callback_data="back_main")],
        ])
    )
    return COLLECTING_MEDIA

async def receive_media(update, context):
    msg  = update.message
    user = update.effective_user
    current = db.get_album(user.id)

    if len(current) >= 10:
        await msg.reply_html(
            "⚠️  Album full hai! Max <b>10 items</b>.\n\nDone dabao.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅  Done — Set Repeat", callback_data="done_adding")],
                [InlineKeyboardButton("🗑  Clear & Start Over", callback_data="clear_album")],
            ])
        )
        return COLLECTING_MEDIA

    item = None
    if msg.photo:
        item = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.video:
        item = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    else:
        await msg.reply_html(
            "❌  Sirf <b>Photo</b> ya <b>Video</b> support hai album mein.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅  Done — Set Repeat", callback_data="done_adding")],
                [InlineKeyboardButton("‹ Cancel",              callback_data="back_main")],
            ])
        )
        return COLLECTING_MEDIA

    db.add_to_album(user.id, item)
    new_count = len(db.get_album(user.id))
    remaining = 10 - new_count
    full_note = "⚠️  <b>Album full!</b> Done dabao." if remaining == 0 else f"Aur <b>{remaining}</b> add kar sakte ho."

    await msg.reply_html(
        f"✅  Added!  [{item['type'].upper()}]\n\n"
        f"📂  Album  ›  <b>{new_count} item(s)</b>\n"
        f"{full_note}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅  Done — Set Repeat", callback_data="done_adding")],
            [InlineKeyboardButton("‹ Cancel",              callback_data="back_main")],
        ])
    )
    return COLLECTING_MEDIA

async def done_adding(update, context):
    q     = update.callback_query
    await q.answer()
    items = db.get_album(update.effective_user.id)

    if not items:
        await q.edit_message_text(
            "❌  Album empty hai! Pehle kuch add karo.",
            reply_markup=back_btn()
        )
        return MAIN_MENU

    types = "  ·  ".join(i["type"].upper() for i in items)
    await q.edit_message_text(
        f"╔══════════════════════\n"
        f"║  🔁  <b>Set Repeat Count</b>\n"
        f"╚══════════════════════\n\n"
        f"📂  Album ready  ›  <b>{len(items)} item(s)</b>\n"
        f"📋  Types  ›  {types}\n\n"
        f"<i>Yeh album kitni baar bhejni hai?</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1×",  callback_data="repeat_1"),
                InlineKeyboardButton("2×",  callback_data="repeat_2"),
                InlineKeyboardButton("3×",  callback_data="repeat_3"),
            ],
            [
                InlineKeyboardButton("5×",  callback_data="repeat_5"),
                InlineKeyboardButton("10×", callback_data="repeat_10"),
                InlineKeyboardButton("✏️ Custom", callback_data="repeat_custom"),
            ],
            [InlineKeyboardButton("‹ Back", callback_data="back_main")]
        ])
    )
    return AWAITING_REPEAT

async def set_repeat(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "repeat_custom":
        await q.edit_message_text(
            "✏️  Kitni baar bhejni hai album?\n\n"
            "<i>1 se 500 ke beech number likho:</i>",
            parse_mode="HTML",
            reply_markup=back_btn()
        )
        context.user_data["awaiting_custom_repeat"] = True
        return AWAITING_REPEAT
    repeat = int(q.data.replace("repeat_", ""))
    db.set_repeat(update.effective_user.id, repeat)
    await _show_repeat_confirmed(q, update.effective_user.id, repeat)
    return MAIN_MENU

async def receive_custom_repeat(update, context):
    if not context.user_data.get("awaiting_custom_repeat"):
        return AWAITING_REPEAT
    try:
        repeat = int(update.message.text.strip())
        if repeat < 1 or repeat > 500:
            raise ValueError
    except ValueError:
        await update.message.reply_html("❌  <b>1 aur 500</b> ke beech number likho.")
        return AWAITING_REPEAT
    context.user_data["awaiting_custom_repeat"] = False
    db.set_repeat(update.effective_user.id, repeat)
    items = db.get_album(update.effective_user.id)
    await update.message.reply_html(
        f"✅  Set!  Album  <b>{repeat}×</b>  bhejoge.\n"
        f"📂  {len(items)} items ready.\n\n"
        "<i>Ab publish karo 👇</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀  Publish Now",      callback_data="publish")],
            [InlineKeyboardButton("🏠  Main Menu",         callback_data="back_main")],
        ])
    )
    return MAIN_MENU

async def _show_repeat_confirmed(q, user_id, repeat):
    items = db.get_album(user_id)
    await q.edit_message_text(
        f"✅  Set!  Album  <b>{repeat}×</b>  bhejoge.\n"
        f"📂  {len(items)} items ready.\n\n"
        "<i>Ab publish karo 👇</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀  Publish Now",       callback_data="publish")],
            [InlineKeyboardButton("➕  Add More Media",    callback_data="add_media")],
            [InlineKeyboardButton("🏠  Main Menu",          callback_data="back_main")],
        ])
    )

# ═══════════════════════════════════════════════════════════
#  VIEW / CLEAR ALBUM
# ═══════════════════════════════════════════════════════════

async def view_album(update, context):
    q     = update.callback_query
    await q.answer()
    user  = update.effective_user
    items = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not items:
        await q.edit_message_text(
            "📭  Album empty hai.",
            reply_markup=back_btn()
        )
        return MAIN_MENU

    lines = [
        "╔══════════════════════",
        "║  📂  <b>Album Preview</b>",
        "╚══════════════════════\n",
    ]
    for i, item in enumerate(items):
        cap = item.get("caption", "")
        preview = (cap[:22] + "…") if len(cap) > 22 else cap
        icon = "🖼" if item["type"] == "photo" else "🎬"
        lines.append(f"  {icon}  <b>{i+1}.</b>  {item['type'].upper()}  {('· ' + preview) if preview else ''}")

    lines += [
        f"\n{DIVIDER}",
        f"🔁  Repeat  ›  <b>{repeat}×</b>",
        f"📤  Total sends  ›  <b>{repeat} album(s)</b>",
    ]

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀  Publish",      callback_data="publish")],
            [InlineKeyboardButton("🗑  Clear Album",  callback_data="clear_album")],
            [InlineKeyboardButton("‹ Back",           callback_data="back_main")],
        ])
    )
    return MAIN_MENU

async def clear_album(update, context):
    q = update.callback_query
    await q.answer()
    db.clear_album(update.effective_user.id)
    db.set_repeat(update.effective_user.id, 1)
    await q.edit_message_text(
        "🗑  Album clear ho gaya!",
        reply_markup=back_btn()
    )
    return MAIN_MENU

# ═══════════════════════════════════════════════════════════
#  PUBLISH
# ═══════════════════════════════════════════════════════════

async def publish_confirm(update, context):
    q      = update.callback_query
    await q.answer()
    user   = update.effective_user
    target = db.get_target(user.id)
    items  = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not target:
        await q.edit_message_text("❌  Target select nahi kiya!", reply_markup=back_btn())
        return MAIN_MENU
    if not items:
        await q.edit_message_text("❌  Album empty hai!", reply_markup=back_btn())
        return MAIN_MENU

    await q.edit_message_text(
        f"╔══════════════════════\n"
        f"║  🚀  <b>Confirm Publish</b>\n"
        f"╚══════════════════════\n\n"
        f"🎯  Target   ›  <b>{target['title']}</b>\n"
        f"📸  Album    ›  <b>{len(items)} media</b>\n"
        f"🔁  Repeat   ›  <b>{repeat}×</b>\n\n"
        f"{DIVIDER}\n"
        f"📤  Bot bhejega  <b>{repeat} album(s)</b>\n"
        f"    har album mein  <b>{len(items)} item(s)</b>\n"
        f"{DIVIDER}\n\n"
        f"<i>Confirm karo?</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅  Publish Now!",  callback_data="confirm_publish"),
                InlineKeyboardButton("✕  Cancel",         callback_data="back_main"),
            ]
        ])
    )
    return CONFIRM_PUBLISH

async def do_publish(update, context):
    q      = update.callback_query
    await q.answer()
    user   = update.effective_user
    target = db.get_target(user.id)
    items  = db.get_album(user.id)
    repeat = db.get_repeat(user.id)

    if not target or not items:
        await q.edit_message_text("❌  Kuch galat ho gaya.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    await q.edit_message_text(
        f"⏳  Publishing…\n\n"
        f"🎯  <b>{target['title']}</b>\n"
        f"0 / {repeat} albums sent",
        parse_mode="HTML"
    )

    sent   = 0
    errors = 0
    chat_id = target["chat_id"]

    def build_media_group():
        group = []
        for idx, item in enumerate(items):
            cap = (item.get("caption") or None) if idx == 0 else None
            if item["type"] == "photo":
                group.append(InputMediaPhoto(media=item["file_id"], caption=cap))
            elif item["type"] == "video":
                group.append(InputMediaVideo(media=item["file_id"], caption=cap))
        return group

    for i in range(repeat):
        try:
            await context.bot.send_media_group(chat_id=chat_id, media=build_media_group())
            sent += 1
        except Exception as e:
            logger.error(f"Round {i+1} error: {e}")
            errors += 1
        await asyncio.sleep(2)
        try:
            await q.edit_message_text(
                f"⏳  Publishing…\n\n"
                f"🎯  <b>{target['title']}</b>\n"
                f"{'▓' * sent}{'░' * (repeat - sent)}  {sent}/{repeat}",
                parse_mode="HTML"
            )
        except Exception:
            pass

    db.clear_album(user.id)
    db.set_repeat(user.id, 1)

    status = "✅  Sab kuch chala gaya!" if errors == 0 else f"⚠️  {errors} error(s) aaye."
    await context.bot.send_message(
        chat_id=user.id,
        text=(
            f"╔══════════════════════\n"
            f"║  📤  <b>Publish Complete</b>\n"
            f"╚══════════════════════\n\n"
            f"🎯  Target   ›  <b>{target['title']}</b>\n"
            f"✅  Sent     ›  <b>{sent}</b> album(s)\n"
            f"❌  Errors   ›  <b>{errors}</b>\n\n"
            f"{status}"
        ),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU

# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set!")
    if not OWNER_ID:
        raise ValueError("OWNER_ID not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    # Sudo commands (outside conversation)
    app.add_handler(CommandHandler("addsudo",  cmd_addsudo))
    app.add_handler(CommandHandler("rmsudo",   cmd_rmsudo))
    app.add_handler(CommandHandler("sudolist", cmd_sudolist))

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(select_target_menu, pattern="^select_target$"),
                CallbackQueryHandler(add_media_prompt,   pattern="^add_media$"),
                CallbackQueryHandler(view_album,         pattern="^view_album$"),
                CallbackQueryHandler(clear_album,        pattern="^clear_album$"),
                CallbackQueryHandler(publish_confirm,    pattern="^publish$"),
                CallbackQueryHandler(menu_refresh,       pattern="^back_main$"),
            ],
            SELECTING_TARGET: [
                CallbackQueryHandler(add_new_target,  pattern="^add_new_target$"),
                CallbackQueryHandler(set_saved_target, pattern="^settarget_"),
                CallbackQueryHandler(menu_refresh,    pattern="^back_main$"),
            ],
            ADDING_TARGET_INPUT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_target_input),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            COLLECTING_MEDIA: [
                MessageHandler((filters.PHOTO | filters.VIDEO) & ~filters.COMMAND, receive_media),
                CallbackQueryHandler(done_adding,  pattern="^done_adding$"),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            AWAITING_REPEAT: [
                CallbackQueryHandler(set_repeat, pattern="^repeat_\\d+$"),
                CallbackQueryHandler(set_repeat, pattern="^repeat_custom$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_repeat),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
            CONFIRM_PUBLISH: [
                CallbackQueryHandler(do_publish,   pattern="^confirm_publish$"),
                CallbackQueryHandler(menu_refresh, pattern="^back_main$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    app.add_handler(conv)
    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
