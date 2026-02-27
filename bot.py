import logging
import asyncio
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ChatMemberHandler, filters, MessageHandler
)
from database import Database
from rss_fetcher import RSSFetcher
from classifier import classify_update
from templates import format_message
from ai_extractor import ai_extract
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, BOT_USERNAME, OWNER_USERNAME, FETCH_INTERVAL_MINUTES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('bot.log')]
)
logger = logging.getLogger(__name__)

db = Database()
rss_fetcher = RSSFetcher()
INTERVAL_SECONDS = FETCH_INTERVAL_MINUTES * 60

# ─────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin in the group."""
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False

# ─────────────────────────────────────────
# CORE FETCH & POST WITH AI
# ─────────────────────────────────────────
async def do_fetch_and_post(bot):
    logger.info("⏰ Fetch cycle started!")
    try:
        new_items = rss_fetcher.fetch_new_items()
        logger.info(f"📦 {len(new_items)} new items found")

        chats = db.get_all_chats()
        if not chats:
            logger.info("⚠️ No chats registered.")
            return 0

        posted_total = 0
        for item in new_items:
            try:
                # 🤖 AI enrichment
                enriched = ai_extract(item)

                category = classify_update(enriched['title'] + " " + enriched.get('summary', ''))
                text, buttons = format_message(enriched, category)

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
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Item error: {e}")

        logger.info(f"🎯 Cycle done — {posted_total} messages sent")
        return posted_total
    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")
        return 0

# ─────────────────────────────────────────
# BACKGROUND SCHEDULER
# ─────────────────────────────────────────
def start_scheduler(bot, loop):
    logger.info("🕐 Scheduler thread started!")
    time.sleep(30)
    while True:
        logger.info("🔄 Scheduler running...")
        try:
            future = asyncio.run_coroutine_threadsafe(do_fetch_and_post(bot), loop)
            result = future.result(timeout=300)
            logger.info(f"🔄 Done — {result} posts")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        logger.info(f"😴 Next fetch in {FETCH_INTERVAL_MINUTES} min...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# /start — PRIVATE CHAT
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    bot_username = BOT_USERNAME.lstrip('@')
    owner = OWNER_USERNAME.lstrip('@')
    channel = CHANNEL_USERNAME.lstrip('@')

    keyboard = [
        [InlineKeyboardButton("📢 Join Official Channel 🔔", url=f"https://t.me/{channel}")],
        [
            InlineKeyboardButton("➕ Add Bot to Channel", url=f"https://t.me/{bot_username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"),
            InlineKeyboardButton("👑 Owner", url=f"https://t.me/{owner}")
        ],
        [InlineKeyboardButton("✅ Tap Here to Verify ✅", callback_data="verify_membership")],
    ]

    await update.message.reply_text(
        "🇮🇳 <b>Welcome to GovtJobs Alert Bot!</b> 🇮🇳\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 <b>Auto Updates Delivered Every 30 Min:</b>\n"
        "📋 Government Job Notifications\n"
        "📅 Exam Dates &amp; Schedules\n"
        "🏆 Results &amp; Merit Lists\n"
        "🎫 Admit Cards &amp; Hall Tickets\n"
        "⚠️ Last Date Alerts &amp; Reminders\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📖 <b>How to use this bot:</b>\n"
        "1️⃣ Join our official channel\n"
        "2️⃣ Tap Verify button below\n"
        "3️⃣ Add bot to your channel/group as Admin\n"
        "4️⃣ Bot auto-posts jobs every 30 minutes!\n\n"
        "🛠 <b>Group Admin Commands:</b>\n"
        "/forcefetch — Fetch jobs right now\n"
        "/test — Test bot is working\n"
        "/stats — View bot statistics\n\n"
        "⚠️ <b>Access Restricted!</b>\n"
        "👇 Join channel first, then tap Verify.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─────────────────────────────────────────
# VERIFY MEMBERSHIP
# ─────────────────────────────────────────
async def verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_username = BOT_USERNAME.lstrip('@')
    owner = OWNER_USERNAME.lstrip('@')
    channel = CHANNEL_USERNAME.lstrip('@')

    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, query.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            keyboard = [
                [InlineKeyboardButton("➕ Add Bot to Your Channel", url=f"https://t.me/{bot_username}?startchannel=true&admin=post_messages+edit_messages+delete_messages")],
                [InlineKeyboardButton("👑 Contact Owner", url=f"https://t.me/{owner}")]
            ]
            await query.edit_message_text(
                "✅ <b>Membership Verified!</b>\n\n"
                "🎉 Welcome! You're all set.\n\n"
                "📢 <b>To get live job updates:</b>\n"
                "➕ Add this bot to your channel/group as <b>Admin</b>\n"
                "📡 Bot will auto-post every 30 minutes!\n\n"
                "🛠 <b>Commands you can use in group:</b>\n"
                "/forcefetch — Get jobs instantly\n"
                "/test — Check bot status\n"
                "/stats — View statistics",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            raise Exception("Not member")
    except Exception:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("🔄 Try Again", callback_data="verify_membership")]
        ]
        await query.edit_message_text(
            "❌ <b>Not Verified!</b>\n\nJoin the channel first then verify.",
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
        logger.info(f"✅ Registered: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting every 30 min:\n"
                "📋 Govt Jobs | 📅 Exams | 🎫 Admit Cards | ⚠️ Alerts\n\n"
                "🤖 <b>AI-Powered</b> — Full details auto-filled!\n\n"
                "🛠 <b>Admin Commands:</b>\n"
                "/forcefetch — Fetch jobs now\n"
                "/test — Test bot\n"
                "/stats — Statistics",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome msg failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"❌ Removed: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# /addchat — ADMIN manually add channel
# ─────────────────────────────────────────
async def admin_add_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /addchat <chat_id> <title>\n\n"
            "To get channel ID:\n"
            "1. Forward a message from your channel to @userinfobot\n"
            "2. It will show the channel ID (negative number like -1001234567890)"
        )
        return
    try:
        chat_id = int(context.args[0])
        title = " ".join(context.args[1:]) if len(context.args) > 1 else "Manual"
        db.add_chat(chat_id, title, "channel")
        await update.message.reply_text(f"✅ Added: {title} ({chat_id})")
        # Test post
        try:
            await context.bot.send_message(chat_id, "✅ <b>GovtJobsBot connected!</b>\n\nAuto-posting activated 🎉", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Added to DB but test post failed: {e}\nMake sure bot is admin in channel.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────
# /forcefetch — GROUP ADMINS + BOT ADMIN
# ─────────────────────────────────────────
async def force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type

    # In private — only bot admin
    if chat_type == "private":
        if not is_admin(update.effective_user.id):
            return
    else:
        # In group/channel — group admins can use
        if not is_admin(update.effective_user.id) and not await is_group_admin(update, context):
            await update.message.reply_text("❌ Only group admins can use this command.")
            return

    msg = await update.message.reply_text("🔄 <b>Fetching jobs now... please wait</b>", parse_mode="HTML")
    count = await do_fetch_and_post(context.bot)
    await msg.edit_text(
        f"✅ <b>Done!</b>\n"
        f"📨 <b>{count}</b> new jobs posted!\n"
        f"👥 Active Chats: {len(db.get_all_chats())}",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /test — GROUP ADMINS + BOT ADMIN
# ─────────────────────────────────────────
async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type == "private":
        if not is_admin(update.effective_user.id):
            return
    else:
        if not is_admin(update.effective_user.id) and not await is_group_admin(update, context):
            await update.message.reply_text("❌ Only group admins can use this command.")
            return

    await update.message.reply_text("🔄 <b>Fetching live test job with AI...</b>", parse_mode="HTML")
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
                    raw = (e.get('link', '') + e.get('title', '')).encode()
                    summary = re.sub(r'<[^>]+>', '', e.get('summary', '') or '')[:400]
                    item = {
                        'id': hashlib.md5(raw).hexdigest(),
                        'title': e.get('title', '').strip(),
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
                'id': 'test_001',
                'title': 'SSC CGL 2025 — 17,727 Vacancies | Apply Online',
                'link': 'https://ssc.nic.in',
                'summary': 'SSC CGL 2025 notification released by Staff Selection Commission. 17,727 vacancies for Group B & C posts. Age limit 18-32 years. Fee: Rs 100 for General. Qualification: Graduation.',
                'published': None,
                'source': 'SSC (Sample)',
            }

        # AI enrich
        enriched = ai_extract(item)
        cat = classify_update(enriched['title'] + ' ' + enriched.get('summary', ''))
        text, buttons = format_message(enriched, cat)

        await update.message.reply_text(
            f"✅ <b>Source:</b> {item['source']} | <b>AI:</b> ✅ | <b>Category:</b> <code>{cat}</code>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )
        await update.message.reply_text(
            f"📊 <b>Status</b>\n"
            f"👥 Active Chats: <b>{len(db.get_all_chats())}</b>\n"
            f"📝 Total Posted: <b>{db.get_post_count()}</b>\n"
            f"⏱ Auto-interval: <b>{FETCH_INTERVAL_MINUTES} min</b>\n"
            f"🤖 AI: <b>Gemini + Groq</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        logger.error(f"Test error: {e}")

# ─────────────────────────────────────────
# /stats — GROUP ADMINS + BOT ADMIN
# ─────────────────────────────────────────
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type != "private":
        if not is_admin(update.effective_user.id) and not await is_group_admin(update, context):
            return

    chats = db.get_all_chats()
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posted: <code>{db.get_post_count()}</code>\n"
        f"⏱ Auto Interval: <b>{FETCH_INTERVAL_MINUTES} min</b>\n"
        f"🤖 AI: <b>Gemini + Groq ✅</b>\n"
        f"🔄 Scheduler: <b>Running ✅</b>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /broadcast — BOT ADMIN ONLY
# ─────────────────────────────────────────
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
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
        await update.message.reply_text("Usage: /removechat <chat_id>")
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

    # Commands usable by group admins too
    app.add_handler(CommandHandler("forcefetch", force_fetch))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    # Bot admin only
    app.add_handler(CommandHandler("addchat", admin_add_chat))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    # Start background scheduler
    loop = asyncio.get_event_loop()
    t = threading.Thread(target=start_scheduler, args=(app.bot, loop), daemon=True, name="Scheduler")
    t.start()
    logger.info("✅ Scheduler thread started!")

    logger.info("🤖 Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
