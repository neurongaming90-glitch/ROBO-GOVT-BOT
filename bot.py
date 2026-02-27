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
            logger.info(f"🔄 {result} posts sent")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        logger.info(f"😴 Next fetch in {FETCH_INTERVAL_MINUTES} min...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# ADMIN CHECK
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# ─────────────────────────────────────────
# CHECK IF USER JOINED CHANNEL
# ─────────────────────────────────────────
async def check_member(bot, user_id) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# ─────────────────────────────────────────
# WELCOME MESSAGE (after verification)
# ─────────────────────────────────────────
async def send_welcome(update_or_query, context, edit=False):
    """Send full welcome message with 3 buttons."""
    keyboard = [
        [
            InlineKeyboardButton("📖 Help & Commands", callback_data="show_help"),
        ],
        [
            InlineKeyboardButton("➕ Add to Your Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startadmin"),
            InlineKeyboardButton("👑 @ethicalrobo", url="https://t.me/ethicalrobo"),
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🇮🇳 <b>GovtJobs Alert Bot — Activated!</b> 🇮🇳\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Ye bot kya karta hai?</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Har 30 minute mein automatically fetch karta hai:\n\n"
        "📋 Government Job Notifications\n"
        "📅 Exam Dates &amp; Schedules\n"
        "🏆 Results &amp; Merit Lists\n"
        "🎫 Admit Cards &amp; Hall Tickets\n"
        "⚠️ Last Date Alerts &amp; Reminders\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>Special Features:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 AI-Powered — Gemini + Groq se\n"
        "   full job details auto-fill hoti hain\n"
        "🌐 16+ RSS Sources monitor karta hai\n"
        "🚫 Duplicate posts kabhi nahi aate\n"
        "⚡ Real-time alerts with buttons\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Help button dabao — saari commands dekho!</b>"
    )

    if edit:
        await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

# ─────────────────────────────────────────
# /start
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # Group/channel mein /start
    if chat.type != "private":
        await update.message.reply_text(
            f"👋 <b>Hello {user.first_name}!</b>\n\n"
            "Type /help for all commands.",
            parse_mode="HTML"
        )
        return

    # Private chat — check channel membership first
    is_member = await check_member(context.bot, user.id)

    if not is_member:
        # Step 1: Not joined — show join button only
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("✅ Already Joined? Verify Karo", callback_data="verify_start")],
        ]
        await update.message.reply_text(
            "🇮🇳 <b>Welcome to GovtJobs Alert Bot!</b> 🇮🇳\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Pehle Channel Join Karo!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Is bot ka use karne ke liye\n"
            "humara official channel join karna zaroori hai.\n\n"
            "👇 Neeche button dabao aur join karo:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Already joined — directly show welcome
        await send_welcome(update, context, edit=False)

# ─────────────────────────────────────────
# VERIFY BUTTON (after joining channel)
# ─────────────────────────────────────────
async def verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking...")
    user_id = query.from_user.id

    is_member = await check_member(context.bot, user_id)

    if is_member:
        # Verified — show full welcome
        await send_welcome(query, context, edit=True)
    else:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Verify Again", callback_data="verify_start")],
        ]
        await query.edit_message_text(
            "❌ <b>Abhi Tak Join Nahi Kiya!</b>\n\n"
            "Pehle channel join karo phir verify karo.\n\n"
            "👇 Channel join karo:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ─────────────────────────────────────────
# HELP BUTTON CALLBACK — Full A to Z details
# ─────────────────────────────────────────
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🔙 Back to Home", callback_data="back_home")],
    ]

    text = (
        "📖 <b>GovtJobs Bot — Complete Guide</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Bot Kaise Kaam Karta Hai?</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ 16+ govt job websites monitor karta hai\n"
        "2️⃣ Har 30 min mein naye jobs fetch karta hai\n"
        "3️⃣ AI (Gemini + Groq) se full details nikalta hai\n"
        "4️⃣ Automatically channel/group mein post karta hai\n"
        "5️⃣ Duplicates kabhi post nahi karta\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Admin Commands:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 /forcefetch\n"
        "   → Abhi turant jobs fetch karke post karo\n\n"
        "📊 /stats\n"
        "   → Active chats, total posts, scheduler status\n\n"
        "📋 /listchats\n"
        "   → Saare registered groups/channels ki list\n\n"
        "➕ /addchat\n"
        "   → Is chat ko manually register karo\n\n"
        "❌ /removechat &lt;id&gt;\n"
        "   → Kisi chat ko remove karo\n\n"
        "📢 /broadcast &lt;message&gt;\n"
        "   → Saare chats mein ek saath message bhejo\n\n"
        "🧪 /test\n"
        "   → Live job fetch karke preview dekho\n\n"
        "📝 /logs\n"
        "   → Recent bot logs dekho (errors/info)\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>Bot Features A to Z:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Auto RSS Fetching — 16+ sources\n"
        "✅ AI Enrichment — Gemini + Groq\n"
        "✅ 5 Premium Templates\n"
        "✅ Smart Classification\n"
        "   (Job/Result/Admit Card/Alert/General)\n"
        "✅ Duplicate Prevention\n"
        "✅ Auto Dead Chat Cleanup\n"
        "✅ Channel Membership Verification\n"
        "✅ 30 Min Auto Schedule\n"
        "✅ Broadcast System\n"
        "✅ Live Logs\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📡 <b>Sources Monitored:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "SarkariNaukri • AglaSem • Testbook\n"
        "Adda247 • BankersAdda • SSCAdda\n"
        "CareerPower • IBPS • Jagran Josh\n"
        "Employment News • FreshersLive\n"
        "ExamPundit • OliveBoard • FreeJobAlert\n"
        "SarkariResult • SarkariJobFind\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Bot Add Karne Ka Tarika:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1. Channel/Group Settings kholo\n"
        "2. Administrators → Add Admin\n"
        "3. Bot username search karo\n"
        "4. Post Messages permission ON karo\n"
        "5. Bot automatically register ho jayega!\n\n"

        "👑 Support: @ethicalrobo"
    )

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ─────────────────────────────────────────
# BACK TO HOME BUTTON
# ─────────────────────────────────────────
async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_welcome(query, context, edit=True)

# ─────────────────────────────────────────
# /help COMMAND (for groups)
# ─────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>GovtJobs Bot — Commands</b>\n\n"
        "🔄 /forcefetch — Turant fetch &amp; post\n"
        "📊 /stats — Bot statistics\n"
        "📋 /listchats — Registered chats\n"
        "➕ /addchat — Is chat register karo\n"
        "❌ /removechat &lt;id&gt; — Chat remove karo\n"
        "📢 /broadcast &lt;msg&gt; — Sabko message\n"
        "🧪 /test — Bot test karo\n"
        "📝 /logs — Logs dekho\n\n"
        "⏱ Auto post: Har <b>30 minutes</b>\n"
        "🤖 AI: <b>Gemini + Groq</b>\n"
        "👑 Support: @ethicalrobo",
        parse_mode="HTML"
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
        logger.info(f"✅ Registered: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting har 30 minutes:\n"
                "📋 Govt Jobs | 📅 Exams | 🎫 Admit Cards | ⚠️ Alerts\n\n"
                "🤖 AI se full details automatically fill hoti hain!\n\n"
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
        f"✅ <b>Chat Registered!</b>\n\n"
        f"📋 Name: <b>{chat.title or 'Private'}</b>\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"📂 Type: {chat.type}\n\n"
        "🎉 Ab auto-post shuru ho jayega!",
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
        "🤖 AI details extract kar raha hai...\n"
        "⏳ 1-2 min lag sakte hain...",
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
            f"🤖 AI: {ai_status}\n\n⬇️ <b>Preview:</b>",
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
            f"⏱ Interval: <b>{FETCH_INTERVAL_MINUTES} min</b>",
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
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posted: <code>{db.get_post_count()}</code>\n"
        f"⏱ Interval: <b>{FETCH_INTERVAL_MINUTES} min</b>\n"
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
        await update.message.reply_text(
            "⚠️ <b>No chats registered.</b>\n\n"
            "Bot ko group/channel mein Admin banao\n"
            "ya /addchat use karo.",
            parse_mode="HTML"
        )
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
    app.add_handler(CallbackQueryHandler(verify_start, pattern="^verify_start$"))
    app.add_handler(CallbackQueryHandler(show_help, pattern="^show_help$"))
    app.add_handler(CallbackQueryHandler(back_home, pattern="^back_home$"))
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

    # Background scheduler
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
