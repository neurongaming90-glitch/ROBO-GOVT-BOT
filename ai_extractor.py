"""
AI Extractor — Uses Gemini to research and fill job details.
Strategy: Give Gemini the job title + summary, it researches and fills ALL fields.
No web scraping needed — Gemini knows about Indian govt exams.
"""
import logging
import re
import json
import urllib.request
from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

PROMPT = """You are an expert on Indian Government Exams and Recruitment.

A new job/exam notification has been found:
TITLE: {title}
SOURCE: {source}
SUMMARY: {summary}
LINK: {link}

Based on this information AND your knowledge about Indian government exams, fill in ALL details.
If exact data is in the summary, use it. Otherwise use your knowledge about this type of exam/job.

Return ONLY a valid JSON object with these keys (no extra text, no markdown):
{{
  "exam_name": "Full official name of exam/recruitment",
  "exam_date": "Exam date if known, else write Not Announced Yet",
  "form_start_date": "Application start date if known",
  "form_last_date": "Last date to apply if mentioned in summary, else Not Announced Yet",
  "authority": "Conducting authority e.g. UPSC, SSC, NTA, State PSC, NIT etc",
  "institute": "Full organization name",
  "eligibility": "Education qualification, experience needed - be specific",
  "pattern": "Exam stages, subjects, total marks, duration if known",
  "syllabus": "Key subjects and important topics to study",
  "strategy": "3 practical preparation tips for this specific exam",
  "insights": "Previous year cutoff trends or useful insights about this exam",
  "selection": "Step by step selection process",
  "seats": "Total vacancies - use exact number from summary if available",
  "salary": "Pay scale, stipend or salary range for this post",
  "why_exam": "2-3 reasons why candidates should consider this opportunity",
  "admit_card_status": "Not Released Yet",
  "result_status": "Not Declared Yet",
  "min_age": "Minimum age limit with relaxation info",
  "max_age": "Maximum age limit with relaxation info",
  "fee": "Application fee for General/OBC/SC/ST/Women",
  "qualification": "Minimum educational qualification required"
}}

Be specific and helpful. Use your knowledge to fill gaps. Keep responses concise.
"""

def call_gemini(title: str, source: str, summary: str, link: str) -> dict:
    """Call Gemini API to research and fill job details."""
    try:
        prompt = PROMPT.format(
            title=title,
            source=source,
            summary=summary[:500],
            link=link
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2000,
                "responseMimeType": "application/json"
            }
        }).encode('utf-8')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url, data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        text = result['candidates'][0]['content']['parts'][0]['text']
        text = re.sub(r'```json|```', '', text).strip()
        data = json.loads(text)
        logger.info(f"✅ Gemini success: {title[:50]}")
        return data

    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        return {}


def call_groq(title: str, source: str, summary: str, link: str) -> dict:
    """Call Groq API as fallback."""
    try:
        prompt = PROMPT.format(
            title=title,
            source=source,
            summary=summary[:500],
            link=link
        )

        payload = json.dumps({
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GROQ_API_KEY}'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        text = result['choices'][0]['message']['content']
        text = re.sub(r'```json|```', '', text).strip()
        data = json.loads(text)
        logger.info(f"✅ Groq success: {title[:50]}")
        return data

    except Exception as e:
        logger.error(f"Groq failed: {e}")
        return {}


def ai_extract(item: dict) -> dict:
    """Main AI enrichment — try Gemini first, then Groq."""
    title = item.get('title', '')
    source = item.get('source', '')
    summary = item.get('summary', '')
    link = item.get('link', '')

    if not title:
        return item

    logger.info(f"🤖 AI enriching: {title[:60]}")

    # Try Gemini first
    data = call_gemini(title, source, summary, link)

    # Fallback to Groq
    if not data:
        logger.info("Gemini failed → trying Groq...")
        data = call_groq(title, source, summary, link)

    if data:
        # Merge AI data into item
        item.update({
            'title': data.get('exam_name', title),
            'exam_date': data.get('exam_date', 'Not Announced Yet'),
            'form_dates': f"📅 Start: {data.get('form_start_date', 'N/A')}\n📅 Last: {data.get('form_last_date', 'N/A')}",
            'authority': data.get('authority', source),
            'institute': data.get('institute', source),
            'eligibility': data.get('eligibility', 'Not Available'),
            'pattern': data.get('pattern', 'Not Available'),
            'syllabus': data.get('syllabus', 'Not Available'),
            'strategy': data.get('strategy', 'Not Available'),
            'insights': data.get('insights', 'Not Available'),
            'selection': data.get('selection', 'Not Available'),
            'seats': data.get('seats', 'Not Available'),
            'salary': data.get('salary', 'Not Available'),
            'why_exam': data.get('why_exam', 'Not Available'),
            'admit_card_status': data.get('admit_card_status', 'Not Released Yet'),
            'result_status': data.get('result_status', 'Not Declared Yet'),
            'min_age': data.get('min_age', 'Not Available'),
            'max_age': data.get('max_age', 'Not Available'),
            'fee': data.get('fee', 'Not Available'),
            'qualification': data.get('qualification', 'Not Available'),
            'ai_enriched': True,
        })
        logger.info(f"✅ AI enriched: {title[:50]}")
    else:
        item['ai_enriched'] = False
        logger.warning(f"⚠️ AI failed for: {title[:50]}")

    return item
