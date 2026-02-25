"""
Classify RSS feed entries into update categories based on keywords.
"""

KEYWORDS = {
    "result": [
        "result", "results", "declared", "merit list", "cut off", "cutoff",
        "selected", "qualified", "final answer key", "scorecard"
    ],
    "admit_card": [
        "admit card", "hall ticket", "call letter", "e-admit", "admit",
        "download card", "entry permit"
    ],
    "last_date": [
        "last date", "last day", "deadline", "closing date", "apply before",
        "extended", "application closes", "final date", "hurry", "urgent",
        "only", "days left", "date extended"
    ],
    "exam_update": [
        "notification", "recruitment", "vacancy", "vacancies", "advertisement",
        "apply online", "application form", "exam date", "schedule", "syllabus",
        "pattern", "eligibility", "post", "posts"
    ],
}

CATEGORY_ORDER = ["result", "admit_card", "last_date", "exam_update"]

def classify_update(text: str) -> str:
    """Return a category string: result | admit_card | last_date | exam_update | general"""
    text_lower = text.lower()
    for cat in CATEGORY_ORDER:
        for kw in KEYWORDS[cat]:
            if kw in text_lower:
                return cat
    return "general"
