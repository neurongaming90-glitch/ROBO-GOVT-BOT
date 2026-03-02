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
rss = RSSFetcher()
INTERVAL_SECONDS = FETCH_INTERVAL_MINUTES * 60
_bot_ref = None

# ─────────────────────────────────────────
# CORE: FETCH & POST
# ─────────────────────────────────────────
async def do_fetch_and_post(bot):
    logger.info("⏰ Fetch cycle started!")
    try:
        new_items = rss.fetch_new_items()
        logger.info(f"📦 {len(new_items)} new items found")

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

        logger.info(f"🎯 Done — {posted_total} messages to {len(chats)} chats")
        return posted_total
    except Exception as e:
        logger.error(f"fetch_and_post error: {e}")
        return 0

# ─────────────────────────────────────────
# BACKGROUND SCHEDULER
# ─────────────────────────────────────────
def scheduler_loop(loop):
    global _bot_ref
    logger.info("🕐 Scheduler thread started!")
    time.sleep(20)
    cycle = 0
    while True:
        cycle += 1
        logger.info(f"🔄 Scheduler cycle #{cycle}")
        if _bot_ref:
            try:
                future = asyncio.run_coroutine_threadsafe(do_fetch_and_post(_bot_ref), loop)
                result = future.result(timeout=300)
                logger.info(f"✅ Cycle #{cycle} done: {result} posts")
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
        else:
            logger.warning("Bot ref not ready!")
        logger.info(f"😴 Sleeping {FETCH_INTERVAL_MINUTES} min...")
        time.sleep(INTERVAL_SECONDS)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def is_admin(uid): return str(uid) == str(ADMIN_ID)

async def check_member(bot, uid) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL_USERNAME, uid)
        return m.status in ["member", "administrator", "creator"]
    except Exception:
        return False

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
        "🔥 <b>Features:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 15+ RSS Sources monitor\n"
        "🔍 Job page scrape — full details\n"
        "🚫 Duplicate posts kabhi nahi\n"
        "⚡ Real-time alerts with buttons\n\n"
        "👇 <b>Help dabao — saari commands dekho!</b>"
    )
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ─────────────────────────────────────────
# /start
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text("👋 Type /help for commands.", parse_mode="HTML")
        return

    is_member = await check_member(context.bot, update.effective_user.id)
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
            "Bot use karne ke liye pehle\n"
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
    if await check_member(context.bot, query.from_user.id):
        await send_welcome(query, context, edit=True)
    else:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel 🔔", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 Verify Again", callback_data="verify_start")],
        ]
        await query.edit_message_text(
            "❌ <b>Abhi Tak Join Nahi Kiya!</b>\n\nPehle join karo phir verify karo.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
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
        "3️⃣ Job page scrape karke full details nikalta hai\n"
        "4️⃣ Channel/Group mein auto-post karta hai\n"
        "5️⃣ Duplicates kabhi nahi aate\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Admin Commands:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 /forcefetch — Abhi turant fetch karo\n"
        "🗑 /cleardb — Database clear karo\n"
        "📊 /stats — Active chats aur posts\n"
        "📋 /listchats — Registered channels/groups\n"
        "➕ /addchat — Is chat ko register karo\n"
        "❌ /removechat &lt;id&gt; — Chat hatao\n"
        "📢 /broadcast &lt;msg&gt; — Sabko message\n"
        "🧪 /test — Live job preview dekho\n"
        "📝 /logs — Recent logs dekho\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>Features:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ 15+ RSS Sources\n"
        "✅ Page Scraping — Full Details\n"
        "✅ 5 Premium Templates\n"
        "✅ Smart Job Classification\n"
        "✅ Duplicate Prevention\n"
        "✅ Auto Dead Chat Cleanup\n"
        "✅ 30 Min Auto Schedule\n"
        "✅ Channel Verification\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Bot Add Karna:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Channel Settings → Administrators\n"
        "→ Add Admin → Bot search karo\n"
        "→ Post Messages ✅ → Save\n\n"
        "👑 Support: @ethicalrobo"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_welcome(query, context, edit=True)

# ─────────────────────────────────────────
# BOT ADDED TO CHAT
# ─────────────────────────────────────────
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    chat = result.chat
    status = result.new_chat_member.status
    if status in ["member", "administrator"]:
        db.add_chat(chat.id, chat.title or "", chat.type)
        logger.info(f"✅ Registered: {chat.title} ({chat.id})")
        try:
            await context.bot.send_message(
                chat.id,
                "👋 <b>GovtJobsBot Activated!</b> 🎉\n\n"
                "✅ Auto-posting har 30 minutes:\n"
                "📋 Govt Jobs | 📅 Exams | 🎫 Admit Cards | ⚠️ Alerts\n\n"
                "🔍 Page scraping se full details!\n"
                "Type /help for commands.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome msg failed: {e}")
    elif status in ["left", "kicked"]:
        db.remove_chat(chat.id)
        logger.info(f"❌ Removed: {chat.title} ({chat.id})")

# ─────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────
async def cmd_addchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chat = update.effective_chat
    db.add_chat(chat.id, chat.title or "Private", chat.type)
    await update.message.reply_text(
        f"✅ <b>Registered!</b>\nName: <b>{chat.title or 'Private'}</b>\nID: <code>{chat.id}</code>",
        parse_mode="HTML"
    )

async def cmd_cleardb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    db.clear_posted()
    await update.message.reply_text(
        "🗑 <b>Database cleared!</b>\n\nAb /forcefetch karo — fresh posts aayenge!",
        parse_mode="HTML"
    )

async def cmd_forcefetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text(
            "❌ <b>Koi chat registered nahi!</b>\n\nBot ko channel mein Admin banao phir /addchat bhejo.",
            parse_mode="HTML"
        )
        return
    msg = await update.message.reply_text(
        f"🔄 <b>Fetching...</b>\n👥 Chats: {len(chats)}\n🔍 Page scraping ho raha hai...\n⏳ Wait karo...",
        parse_mode="HTML"
    )
    count = await do_fetch_and_post(context.bot)
    await msg.edit_text(
        f"✅ <b>Done!</b>\n\n📨 Posted: <b>{count}</b>\n👥 Chats: <b>{len(chats)}</b>\n"
        f"{'⚠️ 0 posts — try /cleardb then /forcefetch again' if count == 0 else '🎉 Check your channel!'}",
        parse_mode="HTML"
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chats = db.get_all_chats()
    await update.message.reply_text(
        f"📊 <b>Bot Stats</b>\n\n"
        f"👥 Active Chats: <code>{len(chats)}</code>\n"
        f"📝 Total Posted: <code>{db.get_post_count()}</code>\n"
        f"⏱ Interval: <b>{FETCH_INTERVAL_MINUTES} min</b>\n"
        f"🔄 Scheduler: <b>✅ Running</b>",
        parse_mode="HTML"
    )

async def cmd_listchats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chats = db.get_all_chats()
    if not chats:
        await update.message.reply_text("⚠️ No chats. Bot ko channel mein Admin banao ya /addchat use karo.")
        return
    text = "📋 <b>Active Chats:</b>\n\n"
    for c in chats[:20]:
        text += f"• <code>{c['chat_id']}</code> — {c['title']} ({c['chat_type']})\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_removechat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Usage: /removechat &lt;chat_id&gt;", parse_mode="HTML")
        return
    db.remove_chat(int(context.args[0]))
    await update.message.reply_text("✅ Removed.")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
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

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return

    await update.message.reply_text("🔍 <b>Live job fetch + page scrape ho rahi hai...</b>", parse_mode="HTML")
    try:
        import feedparser, re as re2

        item = None
        for feed_url, sname in [
            ("https://www.freejobalert.com/feed/", "FreeJobAlert"),
            ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
            ("https://aglasem.com/feed/", "AglaSem"),
        ]:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    e = feed.entries[0]
                    summary = re2.sub(r'<[^>]+>', ' ', e.get('summary', '') or '')[:400]
                    item = {
                        'title': e.get('title', '').strip(),
                        'link': e.get('link', feed_url),
                        'summary': summary,
                        'source': sname,
                    }
                    break
            except Exception:
                continue

        if not item:
            await update.message.reply_text("❌ RSS fetch failed. Check /logs.")
            return

        await update.message.reply_text(f"📌 Fetched: <b>{item['title'][:60]}</b>\n🔍 Page scraping...", parse_mode="HTML")

        # Use rss_fetcher's scraper and extractor
        page_text = rss.scrape_page(item['link']) if hasattr(rss, '_scrape_page') else rss._scrape_page(item['link'])
        details = rss._extract_details(page_text, item['title'], item['summary'])

        import hashlib
        item_id = hashlib.md5((item['link'] + item['title']).encode()).hexdigest()
        full_item = {
            'id': 'test_' + item_id,
            'title': details.get('exam_name', item['title']),
            'link': item['link'],
            'summary': item['summary'],
            'published': None,
            'source': item['source'],
            'exam_date': details.get('exam_date', 'Not Announced Yet'),
            'form_dates': f"Start: {details.get('form_start_date','N/A')} | Last: {details.get('form_last_date','N/A')}",
            'authority': details.get('authority', item['source']),
            'institute': details.get('institute', item['source']),
            'eligibility': details.get('eligibility', 'Not Available'),
            'pattern': details.get('pattern', 'Not Available'),
            'syllabus': details.get('syllabus', 'Not Available'),
            'strategy': details.get('strategy', 'Not Available'),
            'insights': details.get('insights', 'Not Available'),
            'selection': details.get('selection', 'Not Available'),
            'seats': details.get('seats', 'Not Available'),
            'salary': details.get('salary', 'Not Available'),
            'why_exam': details.get('why_exam', 'Not Available'),
            'admit_card_status': details.get('admit_card_status', 'Not Released Yet'),
            'result_status': details.get('result_status', 'Not Declared Yet'),
            'min_age': details.get('min_age', 'Not Available'),
            'max_age': details.get('max_age', 'Not Available'),
            'fee': details.get('fee', 'Not Available'),
            'qualification': details.get('qualification', 'Not Available'),
        }

        cat = classify_update(full_item['title'] + ' ' + full_item.get('summary', ''))
        text, buttons = format_message(full_item, cat)

        await update.message.reply_text(
            f"✅ <b>Scraped!</b> Source: {item['source']} | Cat: <code>{cat}</code>\n"
            f"🔗 <a href='{item['link']}'>View Original</a>\n\n⬇️ Preview:",
            parse_mode="HTML", disable_web_page_preview=True
        )
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True
        )
        await update.message.reply_text(
            f"📊 Chats: <b>{len(db.get_all_chats())}</b> | Posted: <b>{db.get_post_count()}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Test error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        with open("bot.log", "r") as f:
            lines = f.readlines()[-40:]
        await update.message.reply_text(f"<pre>{''.join(lines)[-3500:]}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Commands:</b>\n\n"
        "🔄 /forcefetch\n🗑 /cleardb\n📊 /stats\n"
        "📋 /listchats\n➕ /addchat\n❌ /removechat &lt;id&gt;\n"
        "📢 /broadcast &lt;msg&gt;\n🧪 /test\n📝 /logs\n\n"
        "⏱ Auto: Har <b>30 min</b> | 👑 @ethicalrobo",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    global _bot_ref
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    _bot_ref = app.bot

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(verify_start, pattern="^verify_start$"))
    app.add_handler(CallbackQueryHandler(show_help, pattern="^show_help$"))
    app.add_handler(CallbackQueryHandler(back_home, pattern="^back_home$"))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("addchat", cmd_addchat))
    app.add_handler(CommandHandler("cleardb", cmd_cleardb))
    app.add_handler(CommandHandler("forcefetch", cmd_forcefetch))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("listchats", cmd_listchats))
    app.add_handler(CommandHandler("removechat", cmd_removechat))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("logs", cmd_logs))

    loop = asyncio.get_event_loop()
    t = threading.Thread(target=scheduler_loop, args=(loop,), daemon=True, name="Scheduler")
    t.start()
    logger.info("✅ Bot + Scheduler started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
