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

# Global bot reference for scheduler
_bot_ref = None

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
            logger.warning("⚠️ No chats registered!")
            return 0

        if not new_items:
            logger.info("No new items to post")
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

        logger.info(f"🎯 Cycle done — {posted_total} messages to {len(chats)} chats")
        return posted_total

    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")
        return 0

# ─────────────────────────────────────────
# BACKGROUND SCHEDULER — runs forever
# ─────────────────────────────────────────
def scheduler_loop(loop):
    """Infinite loop in background thread."""
    global _bot_ref
    logger.info("🕐 Scheduler thread alive!")

    # Wait for bot to initialize
    time.sleep(20)

    cycle = 0
    while True:
        cycle += 1
        logger.info(f"🔄 Scheduler cycle #{cycle} starting...")

        if _bot_ref:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    do_fetch_and_post(_bot_ref), loop
                )
                result = future.result(timeout=300)
                logger.info(f"🔄 Cycle #{cycle} done: {result} posts")
            except Exception as e:
                logger.error(f"Scheduler cycle #{cycle} error: {e}")
        else:
            logger.warning("Bot ref not ready yet...")

        logger.info(f"😴 Sleeping {FETCH_INTERVAL_MINUTES} min until next cycle...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

async def check_member(bot, user_id) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# ─────────────────────────────────────────
# WELCOME MESSAGE
# ─────────────────────────────────────────
async def send_welcome(target, context, edit=False):
    keyboard = [
        [InlineKeyboardButton("📖 Help & All Commands", callback_data="show_help")],
        [
            InlineKeyboardButton("➕ Add to Your Channel", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startadmin"),
            InlineKeyboardButton("👑 @ethicalrobo", url="https://t.me/ethicalrobo"),
        ],
    ]
    text = (
        "🇮🇳 <b>GovtJobs Alert Bot — Activated!</b> 🇮🇳\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Bot kya karta hai?</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Har 30 minute mein automatically:\n\n"
        "📋 Government Job Notifications\n"
        "📅 Exam Dates &amp; Schedules\n"
        "🏆 Results &amp; Merit Lists\n"
        "🎫 Admit Cards &amp; Hall Tickets\n"
        "⚠️ Last Date Alerts &amp; Reminders\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>Special Features:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 AI-Powered (Gemini + Groq)\n"
        "   → Full details auto-fill hoti hain\n"
        "🌐 15+ RSS Sources monitor\n"
        "🚫 Duplicate posts kabhi nahi\n"
        "⚡ Real-time alerts with buttons\n\n"
        "👇 <b>Help dabao — saari commands dekho!</b>"
    )
    markup = InlineKeyboardMarkup(keyboard)
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

# ─────────────────────────────────────────
# /start
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        await update.message.reply_text(
            f"👋 <b>Hello!</b> Type /help for commands.",
            parse_mode="HTML"
        )
        return

    is_member = await check_member(context.bot, user.id)

    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("✅ Joined? Verify Karo", callback_data="verify_start")],
        ]
        await update.message.reply_text(
            "🇮🇳 <b>Welcome to GovtJobs Alert Bot!</b> 🇮🇳\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Pehle Channel Join Karo!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot use karne ke liye humara\n"
            "official channel join karna zaroori hai.\n\n"
            "👇 Join karo phir verify karo:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await send_welcome(update, context, edit=False)

# ─────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────
async def verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking...")
    is_member = await check_member(context.bot, query.from_user.id)
    if is_member:
        await send_welcome(query, context, edit=True)
    else:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Verify Again", callback_data="verify_start")],
        ]
        await query.edit_message_text(
            "❌ <b>Abhi Tak Join Nahi Kiya!</b>\n\nPehle join karo phir verify karo.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]
    text = (
        "📖 <b>GovtJobs Bot — Complete Guide</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Kaise Kaam Karta Hai?</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ 15+ govt job sites monitor karta hai\n"
        "2️⃣ Har 30 min mein naye jobs fetch karta hai\n"
        "3️⃣ AI (Gemini+Groq) se full details fill karta hai\n"
        "4️⃣ Channel/Group mein auto-post karta hai\n"
        "5️⃣ Duplicates kabhi nahi aate\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Admin Commands:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 /forcefetch\n"
        "   Abhi turant jobs fetch karke post karo\n\n"
        "🗑 /cleardb\n"
        "   Database clear karo (fresh start)\n\n"
        "📊 /stats\n"
        "   Active chats, posts, scheduler status\n\n"
        "📋 /listchats\n"
        "   Saare registered groups/channels\n\n"
        "➕ /addchat\n"
        "   Is chat ko manually register karo\n\n"
        "❌ /removechat &lt;id&gt;\n"
        "   Kisi chat ko hatao\n\n"
        "📢 /broadcast &lt;msg&gt;\n"
        "   Sabko ek saath message bhejo\n\n"
        "🧪 /test\n"
        "   Live job fetch + AI preview dekho\n\n"
        "📝 /logs\n"
        "   Recent bot logs dekho\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>Features A to Z:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ AI Full Details — Gemini + Groq\n"
        "✅ 15+ RSS Sources\n"
        "✅ 5 Premium Templates\n"
        "✅ Smart Classification\n"
        "✅ Duplicate Prevention\n"
        "✅ Channel Verification\n"
        "✅ 30 Min Auto Schedule\n"
        "✅ Broadcast System\n"
        "✅ Auto Dead Chat Cleanup\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Bot Add Karne Ka Tarika:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Channel Settings → Administrators\n"
        "→ Add Admin → Bot search karo\n"
        "→ Post Messages ON karo → Save\n\n"
        "👑 Support: @ethicalrobo"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_welcome(query, context, edit=True)

# ─────────────────────────────────────────
# /help command
# ─────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Commands:</b>\n\n"
        "🔄 /forcefetch — Turant fetch &amp; post\n"
        "🗑 /cleardb — Database clear karo\n"
        "📊 /stats — Bot stats\n"
        "📋 /listchats — Registered chats\n"
        "➕ /addchat — Is chat register karo\n"
        "📢 /broadcast &lt;msg&gt; — Sabko message\n"
        "🧪 /test — Bot test karo\n"
        "📝 /logs — Logs dekho\n\n"
        "⏱ Auto: Har <b>30 min</b>\n"
        "👑 @ethicalrobo",
        parse_mode="HTML"
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
                "✅ Auto-posting har 30 minutes:\n"
                "📋 Govt Jobs | 📅 Exams | 🎫 Admit Cards\n\n"
                "🤖 AI se full details auto-fill!\n"
                "Type /help for commands.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome msg failed: {e}")
    elif new_status in ["left", "kicked"]:
        db.remove_chat(chat.id)

# ─────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────
async def add_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chat = update.effective_chat
    db.add_chat(chat.id, chat.title or "Private", chat.type)
    await update.message.reply_text(
        f"✅ <b>Registered!</b>\n"
        f"Name: <b>{chat.title or 'Private'}</b>\n"
        f"ID: <code>{chat.id}</code>",
        parse_mode="HTML"
    )

async def admin_clear_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    db.clear_posted()
    await update.message.reply_text(
        "🗑 <b>Database cleared!</b>\n\n"
        "Saari posted items delete ho gayi.\n"
        "Ab /forcefetch karo — fresh posts aayenge!",
        parse_mode="HTML"
    )

async def admin_force_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text(
            "❌ <b>Koi chat registered nahi!</b>\n\n"
            "Bot ko channel mein Admin banao\n"
            "phir /addchat bhejo us channel mein.",
            parse_mode="HTML"
        )
        return
    await update.message.reply_text(
        f"🔄 <b>Fetching now...</b>\n"
        f"👥 Chats: {len(chats)}\n"
        "🤖 AI details extract kar raha hai...\n"
        "⏳ Please wait 1-2 min...",
        parse_mode="HTML"
    )
    count = await do_fetch_and_post(context.bot)
    await update.message.reply_text(
        f"✅ <b>Done!</b>\n\n"
        f"📨 Posted: <b>{count}</b> messages\n"
        f"👥 Chats: <b>{len(chats)}</b>\n\n"
        f"{'⚠️ 0 posts — try /cleardb then /forcefetch' if count == 0 else '🎉 Check your channel!'}",
        parse_mode="HTML"
    )

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
        await update.message.reply_text(
            "⚠️ <b>No chats registered.</b>\n\n"
            "Channel mein bot ko Admin banao\n"
            "phir channel mein jaake /addchat bhejo.",
            parse_mode="HTML"
        )
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

async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 <b>AI se live job fetch...</b>", parse_mode="HTML")
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
                    summary = re.sub(r'<[^>]+>', '', e.get('summary','') or '')[:400]
                    item = {
                        'id': 'test_' + hashlib.md5(raw).hexdigest(),
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
                'summary': 'SSC CGL 2025 notification released for 17727 posts.',
                'published': None,
                'source': 'SSC',
            }

        await update.message.reply_text("🤖 Gemini AI research kar raha hai...")
        item = ai_extract(item)

        cat = classify_update(item['title'] + ' ' + item.get('summary', ''))
        text, buttons = format_message(item, cat)
        ai_status = "✅ AI Enriched" if item.get('ai_enriched') else "⚠️ AI Failed (Raw Data)"

        await update.message.reply_text(
            f"📌 Source: <b>{item['source']}</b> | Cat: <code>{cat}</code> | {ai_status}\n⬇️",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

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
    global _bot_ref
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    _bot_ref = app.bot

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(verify_start, pattern="^verify_start$"))
    app.add_handler(CallbackQueryHandler(show_help, pattern="^show_help$"))
    app.add_handler(CallbackQueryHandler(back_home, pattern="^back_home$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin
    app.add_handler(CommandHandler("addchat", add_chat))
    app.add_handler(CommandHandler("cleardb", admin_clear_db))
    app.add_handler(CommandHandler("test", admin_test))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("forcefetch", admin_force_fetch))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("listchats", admin_list_chats))
    app.add_handler(CommandHandler("removechat", admin_remove_chat))
    app.add_handler(CommandHandler("logs", admin_logs))

    # Start background scheduler
    loop = asyncio.get_event_loop()
    t = threading.Thread(target=scheduler_loop, args=(loop,), daemon=True, name="Scheduler")
    t.start()
    logger.info("✅ Scheduler started!")

    logger.info("🤖 Bot running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
