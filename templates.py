"""
Premium message templates for all 4 update categories.
Returns (text, buttons) tuple.
"""
from datetime import datetime
from telegram import InlineKeyboardButton


def _escape(text: str) -> str:
    """Basic HTML safety."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _get(item: dict, key: str, fallback: str = "Not Available") -> str:
    val = item.get(key, "")
    if val and str(val).strip():
        return _escape(str(val).strip())
    return fallback


def _source_line(item: dict) -> str:
    return _escape(item.get('source', 'Govt Update'))


def _date_line(item: dict) -> str:
    pub = item.get('published')
    if pub:
        return pub.strftime('%d %b %Y')
    return datetime.now().strftime('%d %b %Y')


# ─────────────────────────────────────────
# TEMPLATE 1 — FULL EXAM UPDATE
# ─────────────────────────────────────────
def template_exam_update(item: dict) -> tuple:
    title    = _get(item, 'title', 'New Exam Notification')
    link     = item.get('link', '#')
    summary  = _escape(item.get('summary', ''))[:200]

    # Try to extract fields — RSS usually won't have all, so fallback gracefully
    exam_date   = _get(item, 'exam_date')
    form_dates  = _get(item, 'form_dates', summary if summary else "Not Available")
    authority   = _get(item, 'authority', _source_line(item))
    institute   = _get(item, 'institute', _source_line(item))
    eligibility = _get(item, 'eligibility')
    pattern     = _get(item, 'pattern')
    syllabus    = _get(item, 'syllabus')
    strategy    = _get(item, 'strategy')
    insights    = _get(item, 'insights')
    selection   = _get(item, 'selection')
    seats       = _get(item, 'seats')
    salary      = _get(item, 'salary')
    why_exam    = _get(item, 'why_exam')
    admit_card  = _get(item, 'admit_card_status')
    result_st   = _get(item, 'result_status')
    min_age     = _get(item, 'min_age')
    max_age     = _get(item, 'max_age')
    fee         = _get(item, 'fee')
    qualification = _get(item, 'qualification')

    text = (
        "🚨 ⚠ <b>EXAM UPDATE</b> ⚠ 🚨\n\n"
        f"✨ 📚 <b>{title}</b>\n\n"
        f"📅 <b>Exam Date:</b> {exam_date}\n"
        f"📝 <b>Form Date:</b> {form_dates}\n"
        f"🏛 <b>Conducting Authority:</b> {authority}\n"
        f"🏢 <b>Organizing Institute:</b> {institute}\n\n"
        f"🎯 <b>Eligibility Criteria:</b>\n{eligibility}\n\n"
        f"🎯 <b>Exam Pattern:</b>\n{pattern}\n\n"
        f"📖 <b>Syllabus Overview:</b>\n{syllabus}\n\n"
        f"🧠 <b>Preparation Strategy:</b>\n{strategy}\n\n"
        f"📊 <b>Previous Year Insights:</b>\n{insights}\n\n"
        f"🏛 <b>Selection Process:</b>\n{selection}\n\n"
        f"🎟 <b>Total Seats:</b> {seats}\n\n"
        f"💰 <b>Salary / Benefits:</b>\n{salary}\n\n"
        f"🎯 <b>Why Consider This Exam?</b>\n{why_exam}\n\n"
        "🚨 <b>Important Alerts:</b>\n"
        f"⚠ Admit Card – {admit_card}\n"
        f"⚠ Result – {result_st}\n\n"
        "🎂 <b>Age Limit:</b>\n"
        f"Minimum Age: {min_age}\n"
        f"Maximum Age: {max_age}\n\n"
        f"💰 <b>Application Fee:</b>\n{fee}\n\n"
        f"🎓 <b>Qualification Required:</b>\n{qualification}\n\n"
        "👇 <b>Take Action Below</b>"
    )

    buttons = [
        [
            InlineKeyboardButton("🚀 Apply Now", url=link),
            InlineKeyboardButton("📖 Full Details 🔍", url=link)
        ]
    ]
    return text, buttons


# ─────────────────────────────────────────
# TEMPLATE 2 — IMPORTANT ALERT
# ─────────────────────────────────────────
def template_alert(item: dict) -> tuple:
    title   = _get(item, 'title', 'Important Alert')
    summary = _escape(item.get('summary', ''))[:250]
    link    = item.get('link', '#')

    text = (
        "⚠️━━━━━━━━━━━━━━━━━━━━━━━━⚠️\n"
        "         🚨 <b>IMPORTANT ALERT</b> 🚨\n"
        "⚠️━━━━━━━━━━━━━━━━━━━━━━━━⚠️\n\n"
        f"🔴 <b>{title}</b>\n\n"
        f"🏛️ <b>Source:</b> {_source_line(item)}\n"
        f"📅 <b>Date:</b> {_date_line(item)}\n\n"
        f"⏳ <b>Alert Details:</b>\n{summary}\n\n"
        "⚠️ <b>LAST DATE APPROACHING!</b>\n"
        "Don't miss this opportunity. Apply immediately!\n\n"
        "💪 <i>Your dream govt job is one application away!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🚀 Apply Now", url=link),
            InlineKeyboardButton("📖 Full Details 🔍", url=link)
        ]
    ]
    return text, buttons


# ─────────────────────────────────────────
# TEMPLATE 3 — RESULT OUT
# ─────────────────────────────────────────
def template_result(item: dict) -> tuple:
    title   = _get(item, 'title', 'Result Declared')
    summary = _escape(item.get('summary', ''))[:250]
    link    = item.get('link', '#')

    text = (
        "🎉━━━━━━━━━━━━━━━━━━━━━━━━🎉\n"
        "      ✅ <b>RESULT DECLARED!</b> ✅\n"
        "🎉━━━━━━━━━━━━━━━━━━━━━━━━🎉\n\n"
        f"🏆 <b>{title}</b>\n\n"
        f"🏛️ <b>Source:</b> {_source_line(item)}\n"
        f"📅 <b>Date:</b> {_date_line(item)}\n\n"
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
# TEMPLATE 4 — ADMIT CARD
# ─────────────────────────────────────────
def template_admit_card(item: dict) -> tuple:
    title   = _get(item, 'title', 'Admit Card Available')
    summary = _escape(item.get('summary', ''))[:250]
    link    = item.get('link', '#')

    text = (
        "🪪━━━━━━━━━━━━━━━━━━━━━━━━🪪\n"
        "     🎫 <b>ADMIT CARD RELEASED!</b> 🎫\n"
        "🪪━━━━━━━━━━━━━━━━━━━━━━━━🪪\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"🏛️ <b>Source:</b> {_source_line(item)}\n"
        f"📅 <b>Date:</b> {_date_line(item)}\n\n"
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
# TEMPLATE 5 — GENERAL UPDATE
# ─────────────────────────────────────────
def template_general(item: dict) -> tuple:
    title   = _get(item, 'title', 'New Update')
    summary = _escape(item.get('summary', ''))[:300]
    link    = item.get('link', '#')

    text = (
        "📢━━━━━━━━━━━━━━━━━━━━━━━━📢\n"
        "          📌 <b>UPDATE</b> 📌\n"
        "📢━━━━━━━━━━━━━━━━━━━━━━━━📢\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"🏛️ <b>Source:</b> {_source_line(item)}\n"
        f"📅 <b>Date:</b> {_date_line(item)}\n\n"
        f"📝 <b>Details:</b>\n{summary}\n\n"
        "─────────────────────────────\n"
        "🔔 <i>Stay updated with latest govt job news!</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🚀 Apply Now", url=link),
            InlineKeyboardButton("📖 Full Details 🔍", url=link)
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
