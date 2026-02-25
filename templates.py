"""
Premium message templates for all 4 update categories.
Returns (text, buttons) tuple.
"""
from datetime import datetime
from telegram import InlineKeyboardButton


def _escape(text: str) -> str:
    """Basic HTML safety."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _source_line(item: dict) -> str:
    source = _escape(item.get('source', 'Govt Update'))
    return f"🏛️ <b>Source:</b> {source}"


def _date_line(item: dict) -> str:
    pub = item.get('published')
    if pub:
        return f"📅 <b>Posted:</b> {pub.strftime('%d %b %Y, %I:%M %p')}"
    return f"📅 <b>Posted:</b> {datetime.now().strftime('%d %b %Y')}"


# ─────────────────────────────────────────
# TEMPLATE 1 — FULL EXAM UPDATE
# ─────────────────────────────────────────
def template_exam_update(item: dict) -> tuple:
    title = _escape(item.get('title', 'New Exam Notification'))
    summary = _escape(item.get('summary', ''))[:300]
    link = item.get('link', '#')

    text = (
        "┌─────────────────────────────┐\n"
        f"📋 <b>{title}</b>\n"
        "└─────────────────────────────┘\n\n"
        f"📢 <b>UPDATE TYPE:</b> Exam Notification\n"
        f"{_source_line(item)}\n"
        f"{_date_line(item)}\n\n"
        f"📝 <b>Details:</b>\n{summary}\n\n"
        "─────────────────────────────\n"
        "📌 <b>Key Information:</b>\n"
        "• Exam Date:         <i>(Check official site)</i>\n"
        "• Form Last Date:    <i>(Check official site)</i>\n"
        "• Conducting Body:   <i>(Check official site)</i>\n"
        "• Vacancies:         <i>(Check official site)</i>\n"
        "• Application Fee:   <i>(Check official site)</i>\n\n"
        "─────────────────────────────\n"
        "⚡ <b>Act Fast — Limited Seats!</b>\n\n"
        "🔔 <i>Share with friends preparing for govt exams!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🔎 More Details", url=link),
            InlineKeyboardButton("🚀 Apply Now", url=link)
        ]
    ]
    return text, buttons


# ─────────────────────────────────────────
# TEMPLATE 2 — IMPORTANT ALERT
# ─────────────────────────────────────────
def template_alert(item: dict) -> tuple:
    title = _escape(item.get('title', 'Important Alert'))
    summary = _escape(item.get('summary', ''))[:250]
    link = item.get('link', '#')

    text = (
        "⚠️━━━━━━━━━━━━━━━━━━━━━━━━⚠️\n"
        "         🚨 <b>IMPORTANT ALERT</b> 🚨\n"
        "⚠️━━━━━━━━━━━━━━━━━━━━━━━━⚠️\n\n"
        f"🔴 <b>{title}</b>\n\n"
        f"{_source_line(item)}\n"
        f"{_date_line(item)}\n\n"
        f"⏳ <b>Alert Details:</b>\n{summary}\n\n"
        "⚠️ <b>LAST DATE APPROACHING!</b>\n"
        "Don't miss this opportunity. Apply immediately!\n\n"
        "💪 <i>Your dream govt job is one application away!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🚀 Apply Now", url=link),
            InlineKeyboardButton("🔎 Full Details", url=link)
        ]
    ]
    return text, buttons


# ─────────────────────────────────────────
# TEMPLATE 3 — RESULT OUT
# ─────────────────────────────────────────
def template_result(item: dict) -> tuple:
    title = _escape(item.get('title', 'Result Declared'))
    summary = _escape(item.get('summary', ''))[:250]
    link = item.get('link', '#')

    text = (
        "🎉━━━━━━━━━━━━━━━━━━━━━━━━🎉\n"
        "      ✅ <b>RESULT DECLARED!</b> ✅\n"
        "🎉━━━━━━━━━━━━━━━━━━━━━━━━🎉\n\n"
        f"🏆 <b>{title}</b>\n\n"
        f"{_source_line(item)}\n"
        f"{_date_line(item)}\n\n"
        f"📋 <b>Result Info:</b>\n{summary}\n\n"
        "─────────────────────────────\n"
        "👉 Check your result immediately!\n"
        "📥 Download your scorecard from the official website.\n\n"
        "🌟 <i>All the best to all candidates!</i>"
    )

    buttons = [
        [InlineKeyboardButton("✅ Check Your Result", url=link)]
    ]
    return text, buttons


# ─────────────────────────────────────────
# TEMPLATE 4 — GENERAL UPDATE
# ─────────────────────────────────────────
def template_general(item: dict) -> tuple:
    title = _escape(item.get('title', 'New Update'))
    summary = _escape(item.get('summary', ''))[:300]
    link = item.get('link', '#')

    text = (
        "📢━━━━━━━━━━━━━━━━━━━━━━━━📢\n"
        f"          📌 <b>UPDATE</b> 📌\n"
        "📢━━━━━━━━━━━━━━━━━━━━━━━━📢\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"{_source_line(item)}\n"
        f"{_date_line(item)}\n\n"
        f"📝 <b>Details:</b>\n{summary}\n\n"
        "─────────────────────────────\n"
        "🔔 <i>Stay updated with latest govt job news!</i>"
    )

    buttons = [
        [InlineKeyboardButton("🔎 More Details", url=link)]
    ]
    return text, buttons


# ─────────────────────────────────────────
# ADMIT CARD TEMPLATE (variant of general)
# ─────────────────────────────────────────
def template_admit_card(item: dict) -> tuple:
    title = _escape(item.get('title', 'Admit Card Available'))
    summary = _escape(item.get('summary', ''))[:250]
    link = item.get('link', '#')

    text = (
        "🪪━━━━━━━━━━━━━━━━━━━━━━━━🪪\n"
        "     🎫 <b>ADMIT CARD RELEASED!</b> 🎫\n"
        "🪪━━━━━━━━━━━━━━━━━━━━━━━━🪪\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"{_source_line(item)}\n"
        f"{_date_line(item)}\n\n"
        f"📝 <b>Details:</b>\n{summary}\n\n"
        "─────────────────────────────\n"
        "⚠️ Download your admit card <b>NOW</b>!\n"
        "📸 Carry a printed copy + valid ID to the exam.\n\n"
        "✨ <i>Best of luck for your exam!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🔎 More Details", url=link),
            InlineKeyboardButton("⬇️ Download Card", url=link)
        ]
    ]
    return text, buttons


# ─────────────────────────────────────────
# DISPATCHER
# ─────────────────────────────────────────
def format_message(item: dict, category: str) -> tuple:
    if category == "result":
        return template_result(item)
    elif category == "admit_card":
        return template_admit_card(item)
    elif category == "last_date":
        return template_alert(item)
    elif category == "exam_update":
        return template_exam_update(item)
    else:
        return template_general(item)
