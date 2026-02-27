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
# CORE FETCH & POST
# ─────────────────────────────────────────
async def do_fetch_and_post(bot):
    logger.info("⏰ Fetch cycle started!")
    try:
        new_items = rss_fetcher.fetch_new_items()
        logger.info(f"📦 {len(new_items)} new items")

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

        logger.info(f"🎯 Done — {posted_total} messages sent")
        return posted_total
    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")
        return 0

# ─────────────────────────────────────────
# BACKGROUND SCHEDULER THREAD
# ─────────────────────────────────────────
def start_scheduler(bot, loop):
    logger.info("🕐 Scheduler thread started!")
    time.sleep(30)
    while True:
        logger.info("🔄 Scheduler: running fetch...")
        try:
            future = asyncio.run_coroutine_threadsafe(do_fetch_and_post(bot), loop)
            result = future.result(timeout=300)
            logger.info(f"🔄 Scheduler: {result} posts sent")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        logger.info(f"😴 Next fetch in {FETCH_INTERVAL_MINUTES} minutes...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# ADMIN CHECK
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# ─────────────────────────────────────────
# /start — WELCOME MESSAGE
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        # Group mein /start — show help
        await update.message.reply_text(
            f"👋 <b>Hello {user.first_name}!</b>\n\n"
            "📋 <b>Available Commands:</b>\n\n"
            "🔄 /forcefetch — Abhi turant jobs fetch karo\n"
            "📊 /stats — Bot ki stats dekho\n"
            "📋 /listchats — Registered chats dekho\n"
            "🧪 /test — Bot test karo\n"
            "📢 /broadcast — Sab chats mein msg bhejo\n\n"
            "🤖 Bot har 30 min mein auto-post karta hai!",
            parse_mode="HTML"
        )
        return

    # Private chat welcome
    keyboard = [
        [InlineKeyboardButton("📢 Join Official Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [
            InlineKeyboardButton("➕ Add Bot to Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startadmin"),
            InlineKeyboardButton("👑 @ethicalrobo", url=f"https://t.me/ethicalrobo")
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
# /help — GROUP COMMANDS HELP
# ─────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>GovtJobs Bot — Command Guide</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Admin Commands:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 /forcefetch — Turant RSS fetch karke post karo\n"
        "📊 /stats — Active chats, total posts dekho\n"
        "📋 /listchats — Saare registered chats\n"
        "➕ /addchat — Is chat ko manually register karo\n"
        "❌ /removechat &lt;id&gt; — Chat remove karo\n"
        "📢 /broadcast &lt;msg&gt; — Sabko message bhejo\n"
        "🧪 /test — Bot working hai check karo\n"
        "📝 /logs — Recent bot logs dekho\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ <b>Auto Schedule:</b> Har 30 minute mein\n"
        "🤖 <b>AI:</b> Gemini + Groq se full details\n"
        "━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# VERIFY MEMBERSHIP
# ─────────────────────────────────────────
async def verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, query.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            keyboard = [
                [InlineKeyboardButton("➕ Add Bot to Your Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startadmin")],
                [InlineKeyboardButton("👑 Contact @ethicalrobo", url="https://t.me/ethicalrobo")]
            ]
            await query.edit_message_text(
                "✅ <b>Membership Verified!</b>\n\n"
                "🎉 Welcome! You're all set.\n\n"
                "📢 Add bot to your channel/group as Admin to get live updates!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            raise Exception("Not member")
    except Exception:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Try Again", callback_data="verify_membership")]
        ]
        await query.edit_message_text(
            "❌ <b>Not Verified!</b>\n\nJoin the channel first then tap verify.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ─────────────────────────────────────────
# BOT ADDED TO CHAT — AUTO REGISTER
# ─────────────────────────────────────────
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    chat = result.chat
    new_status = result.new_chat_member.status
    if new_status in ["member", "administrator"]:
        db.add_chat(chat.id, chat.title or "", chat.type)
        logger.info(f"✅ Auto-registered: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting every 30 minutes:\n"
                "📋 Govt Jobs | 📅 Exams | 🎫 Admit Cards | ⚠️ Alerts\n\n"
                "🤖 AI-powered full details on every post!\n"
                "Type /help for all commands.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome msg failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"❌ Removed: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# /addchat — manually register current chat
# ─────────────────────────────────────────
async def add_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin use kar sakta hai.")
        return
    chat = update.effective_chat
    db.add_chat(chat.id, chat.title or "Private", chat.type)
    await update.message.reply_text(
        f"✅ <b>Chat registered!</b>\n\n"
        f"📋 Name: {chat.title or 'Private'}\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"📂 Type: {chat.type}\n\n"
        "Bot ab is chat mein auto-post karega! 🎉",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /forcefetch
# ─────────────────────────────────────────
async def admin_force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin use kar sakta hai.")
        return
    await update.message.reply_text(
        "🔄 <b>Fetching now...</b>\n"
        "🤖 AI se full details extract ho rahi hain.\n"
        "⏳ 1-2 minute lag sakte hain...",
        parse_mode="HTML"
    )
    count = await do_fetch_and_post(context.bot)
    chats = db.get_all_chats()
    await update.message.reply_text(
        f"✅ <b>Done!</b>\n\n"
        f"📨 Messages posted: <b>{count}</b>\n"
        f"👥 Active chats: <b>{len(chats)}</b>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /test
# ─────────────────────────────────────────
async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin use kar sakta hai.")
        return
    await update.message.reply_text("🔄 <b>AI se live job fetch ho rahi hai...</b>", parse_mode="HTML")
    try:
        import feedparser, hashlib, re
        from ai_extractor import ai_extract

        item = None
        for feed_url, sname in [
            ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
            ("https://aglasem.com/feed/", "AglaSem"),
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
                'title': 'SSC CGL 2025 — 17,727 Vacancies',
                'link': 'https://ssc.nic.in',
                'summary': 'SSC CGL 2025 notification released.',
                'published': None,
                'source': 'SSC',
            }

        await update.message.reply_text("🤖 AI page scrape kar raha hai...")
        item = ai_extract(item)

        cat = classify_update(item['title'] + ' ' + item.get('summary', ''))
        text, buttons = format_message(item, cat)

        ai_status = "✅ AI Enriched" if item.get('ai_enriched') else "⚠️ Raw Data"

        await update.message.reply_text(
            f"📌 Source: <b>{item['source']}</b>\n"
            f"🏷 Category: <code>{cat}</code>\n"
            f"🤖 AI Status: {ai_status}\n\n"
            "⬇️ <b>Preview:</b>",
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
            f"⏱ Auto Interval: <b>{FETCH_INTERVAL_MINUTES} min</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────
# /stats
# ─────────────────────────────────────────
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin use kar sakta hai.")
        return
    chats = db.get_all_chats()
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posted: <code>{db.get_post_count()}</code>\n"
        f"⏱ Auto Interval: <b>{FETCH_INTERVAL_MINUTES} minutes</b>\n"
        f"🤖 AI: <b>Gemini + Groq</b>\n"
        f"🔄 Scheduler: <b>✅ Running</b>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# /broadcast
# ─────────────────────────────────────────
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

# ─────────────────────────────────────────
# /listchats
# ─────────────────────────────────────────
async def admin_list_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text("⚠️ No chats registered.\n\nBot ko group/channel mein Admin banao ya /addchat use karo.")
        return
    text = "📋 <b>Active Chats:</b>\n\n"
    for c in chats[:20]:
        text += f"• <code>{c['chat_id']}</code> — {c['title']} ({c['chat_type']})\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ─────────────────────────────────────────
# /removechat
# ─────────────────────────────────────────
async def admin_remove_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removechat &lt;chat_id&gt;", parse_mode="HTML")
        return
    db.remove_chat(int(context.args[0]))
    await update.message.reply_text("✅ Chat removed.")

# ─────────────────────────────────────────
# /logs
# ─────────────────────────────────────────
async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        with open("bot.log", "r") as f:
            lines = f.readlines()[-40:]
        await update.message.reply_text(
            f"<pre>{''.join(lines)[-3500:]}</pre>", parse_mode="HTML"
        )
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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(verify_membership, pattern="^verify_membership$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin commands
    app.add_handler(CommandHandler("addchat", add_chat))
    app.add_handler(CommandHandler("test", admin_test))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    # Background scheduler thread
    loop = asyncio.get_event_loop()
    scheduler_thread = threading.Thread(
        target=start_scheduler,
        args=(app.bot, loop),
        daemon=True,
        name="SchedulerThread"
    )
    scheduler_thread.start()
    logger.info("✅ Scheduler thread started!")

    logger.info("🤖 Bot polling started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
