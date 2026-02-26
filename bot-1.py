import os
import logging
import asyncio
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ChatMemberHandler
)
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

INTERVAL_SECONDS = 30 * 60  # 30 minutes

# ─────────────────────────────────────────
# CORE FETCH & POST FUNCTION
# ─────────────────────────────────────────
async def do_fetch_and_post(bot):
    logger.info("⏰ Auto-fetch triggered!")
    try:
        new_items = rss_fetcher.fetch_new_items()
        logger.info(f"📦 Found {len(new_items)} new items")

        chats = db.get_all_chats()
        if not chats:
            logger.info("⚠️ No chats registered.")
            return 0

        posted_total = 0
        for item in new_items:
            try:
                category = classify_update(item['title'] + " " + item.get('summary', ''))
                text, buttons = format_message(item, category)

                for chat in chats:
                    try:
                        await bot.send_message(
                            chat_id=chat['chat_id'],
                            text=text,
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
                            disable_web_page_preview=True
                        )
                        posted_total += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        err = str(e).lower()
                        logger.warning(f"Post failed {chat['chat_id']}: {e}")
                        if any(x in err for x in ["kicked", "not found", "deactivated", "blocked", "forbidden"]):
                            db.remove_chat(chat['chat_id'])

                db.mark_posted(item['id'], item.get('title', ''), item.get('link', ''))
                logger.info(f"✅ Posted: {item['title'][:60]}")
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Item error: {e}")

        logger.info(f"🎯 Cycle done — {posted_total} messages sent to {len(chats)} chats")
        return posted_total

    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")
        return 0

# ─────────────────────────────────────────
# BACKGROUND THREAD — runs every 30 min
# ─────────────────────────────────────────
def start_scheduler(bot, loop):
    """Runs in a separate daemon thread — never stops."""
    logger.info("🕐 Scheduler thread started!")

    # First run after 60 seconds
    time.sleep(60)

    while True:
        logger.info(f"🔄 Scheduler: Starting fetch cycle...")
        try:
            future = asyncio.run_coroutine_threadsafe(do_fetch_and_post(bot), loop)
            result = future.result(timeout=300)  # 5 min timeout
            logger.info(f"🔄 Scheduler: Cycle done, {result} posts sent")
        except Exception as e:
            logger.error(f"🔄 Scheduler error: {e}")

        logger.info(f"😴 Sleeping {INTERVAL_SECONDS // 60} minutes...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# START COMMAND
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
                "📢 Add this bot to your group/channel to get live updates!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            raise Exception("Not member")
    except Exception:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel Now 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Try Again", callback_data="verify_membership")]
        ]
        await query.edit_message_text(
            "❌ <b>Not Verified!</b>\n\nJoin the channel first, then verify.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ─────────────────────────────────────────
# BOT ADDED TO CHAT
# ─────────────────────────────────────────
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    chat = result.chat
    new_status = result.new_chat_member.status

    if new_status in ["member", "administrator"]:
        db.add_chat(chat.id, chat.title or "", chat.type)
        logger.info(f"✅ Added: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ I will auto-post every 30 minutes:\n"
                "📋 Govt Job Notifications\n"
                "📅 Exam Dates &amp; Results\n"
                "🎫 Admit Cards\n"
                "⚠️ Last Date Alerts\n\n"
                "📡 Next auto-update in 30 minutes!",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome msg failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"❌ Removed: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# ADMIN CHECK
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# ─────────────────────────────────────────
# /forcefetch — immediate fetch
# ─────────────────────────────────────────
async def admin_force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 Fetching now... please wait.")
    count = await do_fetch_and_post(context.bot)
    await update.message.reply_text(
        f"✅ <b>Done!</b>\n📨 {count} messages posted to {len(db.get_all_chats())} chats.",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /test — admin only
# ─────────────────────────────────────────
async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 <b>Fetching live test job...</b>", parse_mode="HTML")
    try:
        import feedparser, hashlib, re
        item = None
        for feed_url, sname in [
            ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
            ("https://aglasem.com/feed/", "AglaSem"),
            ("https://testbook.com/blog/feed/", "Testbook"),
        ]:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    e = feed.entries[0]
                    raw = (e.get('link','') + e.get('title','')).encode()
                    summary = re.sub(r'<[^>]+>', '', e.get('summary','') or '')[:300]
                    item = {
                        'id': hashlib.md5(raw).hexdigest(),
                        'title': e.get('title','').strip(),
                        'link': e.get('link', feed_url),
                        'summary': summary,
                        'published': None,
                        'source': sname,
                    }
                    break
            except Exception:
                continue

        if not item:
            item = {
                'id': 'test_dummy',
                'title': 'SSC CGL 2025 — 17,727 Vacancies Notification Released',
                'link': 'https://ssc.nic.in',
                'summary': 'SSC CGL 2025 official notification released. Apply online for Group B & C posts.',
                'published': None,
                'source': 'SSC (Sample)',
            }

        cat = classify_update(item['title'] + ' ' + item.get('summary', ''))
        text, buttons = format_message(item, cat)

        await update.message.reply_text(
            f"✅ Source: <b>{item['source']}</b> | Category: <code>{cat}</code>\n⬇️ Preview:",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )
        await update.message.reply_text(
            f"📊 Active Chats: <b>{len(db.get_all_chats())}</b>\n"
            f"📝 Total Posted: <b>{db.get_post_count()}</b>\n"
            f"⏱ Auto-interval: <b>30 minutes</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────
# /stats
# ─────────────────────────────────────────
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    await update.message.reply_text(
        f"📊 <b>Bot Stats</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posted: <code>{db.get_post_count()}</code>\n"
        f"⏱ Auto Interval: <b>30 minutes</b>\n"
        f"🔄 Scheduler: <b>✅ Running (background thread)</b>",
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
    ok = 0
    for chat in chats:
        try:
            await context.bot.send_message(chat['chat_id'], f"📢 <b>Broadcast</b>\n\n{msg}", parse_mode="HTML")
            ok += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Sent to {ok}/{len(chats)} chats.")

async def admin_list_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text("⚠️ No chats registered.")
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
    await update.message.reply_text("✅ Removed.")

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        with open("bot.log", "r") as f:
            lines = f.readlines()[-40:]
        await update.message.reply_text(f"<pre>{''.join(lines)[-3500:]}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_membership, pattern="^verify_membership$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin commands
    app.add_handler(CommandHandler("test", admin_test))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    # Get event loop and start background scheduler thread
    loop = asyncio.get_event_loop()
    scheduler_thread = threading.Thread(
        target=start_scheduler,
        args=(app.bot, loop),
        daemon=True,
        name="SchedulerThread"
    )
    scheduler_thread.start()
    logger.info("✅ Background scheduler thread started!")

    logger.info("🤖 Bot polling started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
