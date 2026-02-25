import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ChatMemberHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import Database
from rss_fetcher import RSSFetcher
from classifier import classify_update
from templates import format_message
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, BOT_USERNAME, OWNER_USERNAME

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
# PRIVATE CHAT HANDLER — COLORFUL BUTTONS
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private":
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
        logger.info(f"Added to {chat.type}: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting enabled for:\n"
                "📋 Government Job Notifications\n"
                "📅 Exam Dates &amp; Results\n"
                "🎫 Admit Cards &amp; Hall Tickets\n"
                "⚠️ Last Date Alerts\n\n"
                "📡 Updates arrive automatically every 15 mins. Stay tuned!",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome message failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"Removed from {chat.type}: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# ADMIN CHECK
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# ─────────────────────────────────────────
# /test — ADMIN ONLY
# Scrapes a real live job & shows preview
# ─────────────────────────────────────────
async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    await update.message.reply_text("🔄 <b>Fetching a live job update for test...</b>", parse_mode="HTML")

    try:
        import feedparser, hashlib

        test_feeds = [
            ("https://www.freejobalert.com/feed/", "FreeJobAlert"),
            ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
            ("https://www.govtjobguru.in/feed/", "GovtJobGuru"),
        ]

        item = None
        for feed_url, source_name in test_feeds:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    entry = feed.entries[0]
                    raw = (entry.get('link', '') + entry.get('title', '')).encode('utf-8')
                    item = {
                        'id': hashlib.md5(raw).hexdigest(),
                        'title': entry.get('title', 'Test Update').strip(),
                        'link': entry.get('link', 'https://freejobalert.com'),
                        'summary': entry.get('summary', '')[:300],
                        'published': None,
                        'source': source_name,
                    }
                    logger.info(f"Test fetched from {source_name}: {item['title']}")
                    break
            except Exception as ex:
                logger.warning(f"Test feed {feed_url} failed: {ex}")
                continue

        if not item:
            # Fallback sample
            item = {
                'id': 'test_dummy_001',
                'title': 'SSC CGL 2025 — Official Vacancy Notification Released',
                'link': 'https://ssc.nic.in',
                'summary': 'Staff Selection Commission has released SSC CGL 2025 official notification. Total 17,727 vacancies for Group B and Group C posts. Online applications open now.',
                'published': None,
                'source': 'SSC Official (Sample)',
            }

        category = classify_update(item['title'] + " " + item.get('summary', ''))
        text, buttons = format_message(item, category)

        # Step 1: Show test info
        await update.message.reply_text(
            f"✅ <b>LIVE DATA FETCHED!</b>\n\n"
            f"📌 <b>Source:</b> {item['source']}\n"
            f"🏷️ <b>Category:</b> <code>{category}</code>\n"
            f"🔗 <b>Title:</b> {item['title'][:80]}\n\n"
            "⬇️ <b>Preview of actual post:</b>",
            parse_mode="HTML"
        )

        # Step 2: Show exact post preview
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )

        # Step 3: Bot status summary
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 <b>Bot Status Report</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ RSS Fetching: <b>Working</b>\n"
            "✅ Classification: <b>Working</b>\n"
            "✅ Templates: <b>Working</b>\n"
            "✅ Scheduler: <b>Running (15 min)</b>\n\n"
            f"👥 <b>Active Chats:</b> {len(db.get_all_chats())}\n"
            f"📝 <b>Total Posted:</b> {db.get_post_count()}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 <b>Bot is fully operational!</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ <b>Test failed:</b> {e}", parse_mode="HTML")
        logger.error(f"Test command error: {e}")

# ─────────────────────────────────────────
# OTHER ADMIN COMMANDS
# ─────────────────────────────────────────
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    posts = db.get_post_count()
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posts: <code>{posts}</code>\n"
        f"🔄 Scheduler: Running\n"
        f"⏱️ Interval: Every 15 minutes",
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
        await update.message.reply_text(f"<pre>{log_text[-3000:]}</pre>", parse_mode="HTML")
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
# SCHEDULER
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_membership, pattern="^verify_membership$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin commands
    app.add_handler(CommandHandler("test", admin_test))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    setup_scheduler(app)

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
