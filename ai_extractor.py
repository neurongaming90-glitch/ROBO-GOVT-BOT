"""
AI Extractor — Gemini 1.5 Flash primary, Groq llama fallback.
"""
import logging
import re
import json
import urllib.request
import urllib.error
from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

AI_PROMPT = """You are an expert on Indian Government Exams and Recruitment.

Job notification details:
TITLE: {title}
SOURCE: {source}  
SUMMARY: {summary}

Using this info AND your knowledge about Indian govt exams, fill all fields.
Return ONLY a valid JSON object. No markdown. No code blocks. No explanation. Just JSON.

{{"exam_name": "Full official exam name", "exam_date": "Exam date or Not Announced Yet", "form_start_date": "Start date or Not Available", "form_last_date": "Last date to apply", "authority": "UPSC/SSC/NTA/Railway/State PSC etc", "institute": "Full organization name", "eligibility": "Education qualification and experience needed", "pattern": "Exam stages, subjects, marks, duration", "syllabus": "Key subjects and important topics", "strategy": "3 specific preparation tips for this exam", "insights": "Previous year cutoffs or useful exam trends", "selection": "Step by step selection process", "seats": "Total vacancies", "salary": "Pay scale or salary range", "why_exam": "2 reasons why candidates should apply", "admit_card_status": "Not Released Yet", "result_status": "Not Declared Yet", "min_age": "Minimum age", "max_age": "Maximum age with age relaxation", "fee": "Application fee General/OBC/SC/ST/Women", "qualification": "Minimum educational qualification required"}}"""


def call_gemini(title: str, source: str, summary: str) -> dict:
    """Call Google Gemini 1.5 Flash API."""
    try:
        prompt = AI_PROMPT.format(
            title=title,
            source=source,
            summary=summary[:600]
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
                "topP": 0.8,
                "topK": 10
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }).encode('utf-8')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')

        result = json.loads(raw)

        # Check for errors in response
        if 'error' in result:
            logger.error(f"Gemini API error: {result['error']}")
            return {}

        if not result.get('candidates'):
            logger.error(f"Gemini no candidates: {raw[:200]}")
            return {}

        text = result['candidates'][0]['content']['parts'][0]['text'].strip()

        # Clean markdown if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        # Find JSON object in response
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        data = json.loads(text)
        logger.info(f"✅ Gemini success: {title[:50]}")
        return data

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"Gemini HTTP {e.code}: {body[:400]}")
        return {}
    except urllib.error.URLError as e:
        logger.error(f"Gemini URL error: {e.reason}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Gemini exception: {type(e).__name__}: {e}")
        return {}


def call_groq(title: str, source: str, summary: str) -> dict:
    """Call Groq API with llama3-70b."""
    try:
        prompt = AI_PROMPT.format(
            title=title,
            source=source,
            summary=summary[:600]
        )

        payload = json.dumps({
            "model": "llama3-70b-8192",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an Indian government exam expert. Respond with valid JSON only. No other text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": False
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'User-Agent': 'python-urllib/3.11'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')

        result = json.loads(raw)
        text = result['choices'][0]['message']['content'].strip()

        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        data = json.loads(text)
        logger.info(f"✅ Groq success: {title[:50]}")
        return data

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"Groq HTTP {e.code}: {body[:400]}")
        return {}
    except urllib.error.URLError as e:
        logger.error(f"Groq URL error: {e.reason}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Groq JSON error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Groq exception: {type(e).__name__}: {e}")
        return {}


def ai_extract(item: dict) -> dict:
    """Main AI enrichment — Gemini first, Groq fallback."""
    title = item.get('title', '')
    source = item.get('source', '')
    summary = item.get('summary', '')

    if not title:
        item['ai_enriched'] = False
        return item

    logger.info(f"🤖 AI extracting: {title[:60]}")

    # Try Gemini
    data = call_gemini(title, source, summary)

    # Groq fallback
    if not data:
        logger.info("Gemini failed → Groq fallback...")
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
        logger.info(f"✅ AI done: {title[:50]}")
    else:
        item['ai_enriched'] = False
        logger.error(f"❌ Both AI failed: {title[:50]}")

    return item
