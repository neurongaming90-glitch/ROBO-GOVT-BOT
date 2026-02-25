import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import Database
from rss_fetcher import RSSFetcher
from classifier import classify_update
from templates import format_message
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

db = Database()
rss_fetcher = RSSFetcher()

# ─────────────────────────────────────────
# PRIVATE CHAT HANDLER
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        return

    keyboard = [
        [InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("🔄 Verify Membership", callback_data="verify_membership")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ *Access Restricted*\n\n"
        "This bot delivers live Indian Government Exam & Job Updates.\n\n"
        "📌 Please join our official update channel to continue.\n\n"
        "After joining, tap *Verify Membership* below.",
        parse_mode="Markdown",
        reply_markup=markup
    )

async def verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "administrator", "creator"]:
            await query.edit_message_text(
                "✅ *Membership Verified!*\n\n"
                "Welcome! You now have access to all features.\n\n"
                "📢 This bot auto-posts updates to groups & channels.\n"
                "➕ Add me to your group/channel to get updates!",
                parse_mode="Markdown"
            )
        else:
            raise Exception("Not a member")
    except Exception:
        keyboard = [
            [InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Try Again", callback_data="verify_membership")]
        ]
        await query.edit_message_text(
            "❌ *Not Verified*\n\n"
            "You have not joined our channel yet.\n\n"
            "Please join the channel first, then verify.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ─────────────────────────────────────────
# BOT ADDED TO GROUP/CHANNEL
# ─────────────────────────────────────────
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    chat = result.chat
    new_status = result.new_chat_member.status

    if new_status in ["member", "administrator"]:
        db.add_chat(chat.id, chat.title or "", chat.type)
        logger.info(f"Added to {chat.type}: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 *GovtJobsBot Activated!*\n\n"
                "✅ I'll now auto-post:\n"
                "• Government Job Notifications\n"
                "• Exam Dates & Results\n"
                "• Admit Cards & Alerts\n"
                "• Last Date Reminders\n\n"
                "📡 Updates will arrive automatically. Stay tuned!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Welcome message failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"Removed from {chat.type}: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    posts = db.get_post_count()
    await update.message.reply_text(
        f"📊 *Bot Statistics*\n\n"
        f"👥 Active Chats: `{len(chats)}`\n"
        f"📝 Total Posts: `{posts}`\n"
        f"🔄 Scheduler: Running",
        parse_mode="Markdown"
    )

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    chats = db.get_all_chats()
    success = 0
    for chat in chats:
        try:
            await context.bot.send_message(chat['chat_id'], f"📢 *Broadcast*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {success}/{len(chats)} chats.")

async def admin_force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 Force fetching updates...")
    await fetch_and_post(context.application)
    await update.message.reply_text("✅ Done!")

async def admin_list_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text("No active chats.")
        return
    text = "📋 *Active Chats:*\n\n"
    for c in chats[:20]:
        text += f"• `{c['chat_id']}` — {c['title']} ({c['chat_type']})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def admin_remove_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removechat <chat_id>")
        return
    chat_id = int(context.args[0])
    db.remove_chat(chat_id)
    await update.message.reply_text(f"✅ Chat {chat_id} removed.")

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        with open("bot.log", "r") as f:
            lines = f.readlines()[-30:]
        log_text = "".join(lines)
        await update.message.reply_text(f"```\n{log_text[-3000:]}\n```", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ─────────────────────────────────────────
# CORE: FETCH & POST UPDATES
# ─────────────────────────────────────────
async def fetch_and_post(app):
    logger.info("Starting RSS fetch cycle...")
    try:
        new_items = rss_fetcher.fetch_new_items()
        logger.info(f"Found {len(new_items)} new items")

        chats = db.get_all_chats()
        if not chats:
            logger.info("No chats registered yet.")
            return

        for item in new_items:
            try:
                category = classify_update(item['title'] + " " + item.get('summary', ''))
                text, buttons = format_message(item, category)

                posted_count = 0
                for chat in chats:
                    try:
                        await app.bot.send_message(
                            chat_id=chat['chat_id'],
                            text=text,
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
                            disable_web_page_preview=True
                        )
                        posted_count += 1
                        await asyncio.sleep(0.05)
                    except Exception as e:
                        logger.warning(f"Failed to post to {chat['chat_id']}: {e}")
                        if "kicked" in str(e) or "not found" in str(e) or "deactivated" in str(e):
                            db.remove_chat(chat['chat_id'])

                db.mark_posted(item['id'])
                logger.info(f"Posted '{item['title'][:50]}' to {posted_count} chats")

            except Exception as e:
                logger.error(f"Error processing item: {e}")

    except Exception as e:
        logger.error(f"RSS fetch error: {e}")

# ─────────────────────────────────────────
# SCHEDULER SETUP
# ─────────────────────────────────────────
def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        fetch_and_post,
        'interval',
        minutes=15,
        args=[app],
        id='rss_fetch',
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started — fetching every 15 minutes")
    return scheduler

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_membership, pattern="^verify_membership$"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_my_chat_member))

    # Admin commands
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    # Track bot being added/removed from chats
    from telegram.ext import ChatMemberHandler
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Start scheduler
    scheduler = setup_scheduler(app)

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
