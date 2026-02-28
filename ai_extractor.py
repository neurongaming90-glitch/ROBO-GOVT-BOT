"""
AI Extractor — Gemini first, Groq fallback.
Gives job title+summary to AI, AI fills all details using its knowledge.
"""
import logging
import re
import json
import urllib.request
import urllib.error
from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

PROMPT = """You are an expert on Indian Government Exams and Recruitment.

A new job/exam notification:
TITLE: {title}
SOURCE: {source}
SUMMARY: {summary}

Using this info AND your knowledge about Indian govt exams, fill ALL fields.
Use exact data from summary where available. Use your knowledge for the rest.

Return ONLY a raw JSON object. No markdown, no code blocks, no explanation.

{{
  "exam_name": "Full official exam/recruitment name",
  "exam_date": "Exam date if known, else Not Announced Yet",
  "form_start_date": "Application start date if known, else Not Available",
  "form_last_date": "Last date from summary if available, else Not Announced Yet",
  "authority": "Conducting authority e.g. UPSC SSC NTA State PSC",
  "institute": "Full organization name",
  "eligibility": "Education and experience requirements - be specific",
  "pattern": "Exam stages subjects total marks duration",
  "syllabus": "Key subjects and important topics",
  "strategy": "3 short practical preparation tips for this exam",
  "insights": "Previous year cutoff or exam trends",
  "selection": "Step by step selection process",
  "seats": "Total vacancies - use number from summary if available",
  "salary": "Pay scale stipend or salary range",
  "why_exam": "2 reasons why this is a good opportunity",
  "admit_card_status": "Not Released Yet",
  "result_status": "Not Declared Yet",
  "min_age": "Minimum age limit",
  "max_age": "Maximum age limit with relaxation",
  "fee": "Fee for General OBC SC ST",
  "qualification": "Minimum educational qualification"
}}"""


def call_gemini(title: str, source: str, summary: str) -> dict:
    try:
        prompt = PROMPT.format(
            title=title,
            source=source,
            summary=summary[:600]
        )

        payload = json.dumps({
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048
            }
        }).encode('utf-8')

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        )

        req = urllib.request.Request(
            url, data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode('utf-8')
            result = json.loads(raw)

        # Extract text from response
        text = result['candidates'][0]['content']['parts'][0]['text']

        # Clean any markdown wrapping
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        data = json.loads(text)
        logger.info(f"✅ Gemini OK: {title[:50]}")
        return data

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"Gemini HTTP {e.code}: {body[:300]}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON parse error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Gemini error: {type(e).__name__}: {e}")
        return {}


def call_groq(title: str, source: str, summary: str) -> dict:
    try:
        prompt = PROMPT.format(
            title=title,
            source=source,
            summary=summary[:600]
        )

        payload = json.dumps({
            "model": "llama3-70b-8192",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an Indian government exam expert. Always respond with valid JSON only, no other text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_tokens": 2048
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

        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode('utf-8')
            result = json.loads(raw)

        text = result['choices'][0]['message']['content'].strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        data = json.loads(text)
        logger.info(f"✅ Groq OK: {title[:50]}")
        return data

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"Groq HTTP {e.code}: {body[:300]}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Groq JSON parse error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Groq error: {type(e).__name__}: {e}")
        return {}


def ai_extract(item: dict) -> dict:
    """Main function — try Gemini, fallback Groq."""
    title = item.get('title', '')
    source = item.get('source', '')
    summary = item.get('summary', '')

    if not title:
        item['ai_enriched'] = False
        return item

    logger.info(f"🤖 AI starting: {title[:60]}")

    # Try Gemini first
    data = call_gemini(title, source, summary)

    # Groq fallback
    if not data:
        logger.info("⚠️ Gemini failed → trying Groq...")
        data = call_groq(title, source, summary)

    if data:
        item.update({
            'title':             data.get('exam_name', title),
            'exam_date':         data.get('exam_date', 'Not Announced Yet'),
            'form_dates':        f"Start: {data.get('form_start_date', 'N/A')} | Last: {data.get('form_last_date', 'N/A')}",
            'authority':         data.get('authority', source),
            'institute':         data.get('institute', source),
            'eligibility':       data.get('eligibility', 'Not Available'),
            'pattern':           data.get('pattern', 'Not Available'),
            'syllabus':          data.get('syllabus', 'Not Available'),
            'strategy':          data.get('strategy', 'Not Available'),
            'insights':          data.get('insights', 'Not Available'),
            'selection':         data.get('selection', 'Not Available'),
            'seats':             data.get('seats', 'Not Available'),
            'salary':            data.get('salary', 'Not Available'),
            'why_exam':          data.get('why_exam', 'Not Available'),
            'admit_card_status': data.get('admit_card_status', 'Not Released Yet'),
            'result_status':     data.get('result_status', 'Not Declared Yet'),
            'min_age':           data.get('min_age', 'Not Available'),
            'max_age':           data.get('max_age', 'Not Available'),
            'fee':               data.get('fee', 'Not Available'),
            'qualification':     data.get('qualification', 'Not Available'),
            'ai_enriched':       True,
        })
        logger.info(f"✅ AI enriched: {title[:50]}")
    else:
        item['ai_enriched'] = False
        logger.warning(f"❌ Both AI failed for: {title[:50]}")

    return item
