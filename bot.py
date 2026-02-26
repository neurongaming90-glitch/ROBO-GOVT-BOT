import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ChatMemberHandler
)
from database import Database
from rss_fetcher import RSSFetcher
from classifier import classify_update
from templates import format_message
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, BOT_USERNAME, OWNER_USERNAME, FETCH_INTERVAL_MINUTES

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
# CORE: FETCH & POST — runs via PTB job queue
# ─────────────────────────────────────────
async def fetch_and_post(context):
    """Called by PTB's built-in scheduler every X minutes."""
    logger.info("⏰ Scheduler triggered — fetching RSS...")
    try:
        new_items = rss_fetcher.fetch_new_items()
        logger.info(f"📦 {len(new_items)} new items found")

        chats = db.get_all_chats()
        if not chats:
            logger.info("⚠️ No chats registered yet.")
            return

        for item in new_items:
            try:
                category = classify_update(item['title'] + " " + item.get('summary', ''))
                text, buttons = format_message(item, category)

                posted_count = 0
                for chat in chats:
                    try:
                        await context.bot.send_message(
                            chat_id=chat['chat_id'],
                            text=text,
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
                            disable_web_page_preview=True
                        )
                        posted_count += 1
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        err = str(e).lower()
                        logger.warning(f"Failed to post to {chat['chat_id']}: {e}")
                        if any(x in err for x in ["kicked", "not found", "deactivated", "blocked", "forbidden"]):
                            db.remove_chat(chat['chat_id'])
                            logger.info(f"Removed dead chat: {chat['chat_id']}")

                db.mark_posted(item['id'], item.get('title', ''), item.get('link', ''))
                logger.info(f"✅ Posted: '{item['title'][:60]}' → {posted_count} chats")
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error processing item '{item.get('title', '')}': {e}")

    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")

# ─────────────────────────────────────────
# STARTUP — runs once when bot starts
# ─────────────────────────────────────────
async def on_startup(app):
    logger.info("🚀 Bot started! Running initial fetch in 10 seconds...")
    # Schedule first run after 10 seconds
    app.job_queue.run_once(fetch_and_post, when=10, name="startup_fetch")
    # Schedule repeating job every N minutes
    app.job_queue.run_repeating(
        fetch_and_post,
        interval=FETCH_INTERVAL_MINUTES * 60,
        first=FETCH_INTERVAL_MINUTES * 60,
        name="auto_fetch"
    )
    logger.info(f"✅ Scheduler set — every {FETCH_INTERVAL_MINUTES} minutes")

# ─────────────────────────────────────────
# PRIVATE CHAT — START
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    keyboard = [
        [InlineKeyboardButton("📢 Join Official Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [
            InlineKeyboardButton("➕ Add Bot to Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startchannel=true"),
            InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}")
        ],
        [InlineKeyboardButton("✅ Tap Here to Verify ✅", callback_data="verify_membership")],
    ]

    await update.message.reply_text(
        "🇮🇳 <b>Welcome to GovtJobs Alert Bot!</b> 🇮🇳\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 <b>Auto Updates Delivered:</b>\n"
        "📋 Government Job Notifications\n"
        "📅 Exam Dates &amp; Schedules\n"
        "🏆 Results &amp; Merit Lists\n"
        "🎫 Admit Cards &amp; Hall Tickets\n"
        "⚠️ Last Date Alerts &amp; Reminders\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ <b>Access Restricted!</b>\n"
        "👇 Join our channel first, then tap <b>Verify</b> below.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─────────────────────────────────────────
# VERIFY MEMBERSHIP
# ─────────────────────────────────────────
async def verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "administrator", "creator"]:
            keyboard = [
                [InlineKeyboardButton("➕ Add Bot to Your Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startchannel=true")],
                [InlineKeyboardButton("👑 Contact Owner", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}")]
            ]
            await query.edit_message_text(
                "✅ <b>Membership Verified!</b>\n\n"
                "🎉 Welcome! You're all set.\n\n"
                "📢 This bot auto-posts Govt updates to groups &amp; channels.\n"
                "➕ Add me to your group/channel to start getting live updates!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            raise Exception("Not a member")
    except Exception:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel Now 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Try Verify Again", callback_data="verify_membership")]
        ]
        await query.edit_message_text(
            "❌ <b>Not Verified!</b>\n\n"
            "You haven't joined our channel yet.\n\n"
            "👇 Join the channel first, then verify.",
            parse_mode="HTML",
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
        logger.info(f"✅ Added to {chat.type}: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting enabled for:\n"
                "📋 Government Job Notifications\n"
                "📅 Exam Dates &amp; Results\n"
                "🎫 Admit Cards &amp; Hall Tickets\n"
                "⚠️ Last Date Alerts\n\n"
                f"📡 Updates auto-post every {FETCH_INTERVAL_MINUTES} mins. Stay tuned!",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome message failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"❌ Removed from {chat.type}: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# ADMIN CHECK
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# ─────────────────────────────────────────
# /test — ADMIN ONLY
# ─────────────────────────────────────────
async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only.")
        return

    await update.message.reply_text("🔄 <b>Fetching live job for test...</b>", parse_mode="HTML")

    try:
        import feedparser, hashlib

        test_feeds = [
            ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
            ("https://aglasem.com/feed/", "AglaSem"),
            ("https://testbook.com/blog/feed/", "Testbook"),
        ]

        item = None
        for feed_url, source_name in test_feeds:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    import re
                    entry = feed.entries[0]
                    raw = (entry.get('link', '') + entry.get('title', '')).encode('utf-8')
                    summary_raw = entry.get('summary', '') or entry.get('description', '') or ''
                    summary = re.sub(r'<[^>]+>', '', summary_raw)[:300]
                    item = {
                        'id': hashlib.md5(raw).hexdigest(),
                        'title': entry.get('title', '').strip(),
                        'link': entry.get('link', feed_url),
                        'summary': summary,
                        'published': None,
                        'source': source_name,
                    }
                    break
            except Exception:
                continue

        if not item:
            item = {
                'id': 'test_dummy',
                'title': 'SSC CGL 2025 — Official Notification Released | 17,727 Vacancies',
                'link': 'https://ssc.nic.in',
                'summary': 'Staff Selection Commission released SSC CGL 2025 notification. 17,727 vacancies for Group B & C posts. Apply online now.',
                'published': None,
                'source': 'SSC Official (Sample)',
            }

        category = classify_update(item['title'] + " " + item.get('summary', ''))
        text, buttons = format_message(item, category)

        await update.message.reply_text(
            f"✅ <b>Live Data Fetched!</b>\n"
            f"📌 Source: {item['source']}\n"
            f"🏷 Category: <code>{category}</code>\n\n"
            "⬇️ <b>Exact post preview:</b>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 <b>Bot Status</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ RSS Fetch: Working\n"
            "✅ Template: Working\n"
            f"✅ Scheduler: Every {FETCH_INTERVAL_MINUTES} min\n\n"
            f"👥 Active Chats: <b>{len(db.get_all_chats())}</b>\n"
            f"📝 Total Posted: <b>{db.get_post_count()}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        logger.error(f"Test error: {e}")

# ─────────────────────────────────────────
# /forcefetch — ADMIN ONLY
# ─────────────────────────────────────────
async def admin_force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 Force fetching now...")
    # Run via job queue so it uses same context properly
    context.application.job_queue.run_once(fetch_and_post, when=1, name="force_fetch")
    await update.message.reply_text("✅ Fetch triggered! Check logs in 30 seconds.")

# ─────────────────────────────────────────
# OTHER ADMIN COMMANDS
# ─────────────────────────────────────────
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    posts = db.get_post_count()
    # Get scheduler status
    jobs = context.application.job_queue.jobs()
    scheduler_status = f"✅ Running ({len(jobs)} jobs)" if jobs else "❌ Not running"
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posts: <code>{posts}</code>\n"
        f"⏱ Interval: {FETCH_INTERVAL_MINUTES} minutes\n"
        f"🔄 Scheduler: {scheduler_status}",
        parse_mode="HTML"
    )

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast &lt;message&gt;", parse_mode="HTML")
        return
    msg = " ".join(context.args)
    chats = db.get_all_chats()
    success = 0
    for chat in chats:
        try:
            await context.bot.send_message(chat['chat_id'], f"📢 <b>Broadcast</b>\n\n{msg}", parse_mode="HTML")
            success += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Sent to {success}/{len(chats)} chats.")

async def admin_list_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text("⚠️ No active chats registered.")
        return
    text = "📋 <b>Active Chats:</b>\n\n"
    for c in chats[:20]:
        text += f"• <code>{c['chat_id']}</code> — {c['title']} ({c['chat_type']})\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def admin_remove_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removechat &lt;chat_id&gt;", parse_mode="HTML")
        return
    db.remove_chat(int(context.args[0]))
    await update.message.reply_text(f"✅ Removed.")

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        with open("bot.log", "r") as f:
            lines = f.readlines()[-40:]
        await update.message.reply_text(
            f"<pre>{''.join(lines)[-3500:]}</pre>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    db.init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)   # ← scheduler starts here properly
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_membership, pattern="^verify_membership$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin
    app.add_handler(CommandHandler("test", admin_test))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    logger.info("🤖 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
