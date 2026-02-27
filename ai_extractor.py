"""
AI Extractor — scrapes job page then uses Gemini to extract all details.
Falls back to Groq if Gemini fails.
"""
import logging
import re
import json
import urllib.request
import urllib.error
from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

EXTRACT_PROMPT = """You are an expert Indian government job analyst.

Below is the content of a government job/exam notification page.

Extract ALL available information and return a JSON object with these exact keys:
{{
  "exam_name": "Full official exam/job name",
  "exam_date": "Exam date if mentioned, else Not Available",
  "form_start_date": "Form start date if mentioned, else Not Available",
  "form_last_date": "Last date to apply if mentioned, else Not Available",
  "authority": "Conducting authority (UPSC/SSC/NTA/State PSC etc)",
  "institute": "Organization name",
  "eligibility": "Eligibility criteria - education, experience etc",
  "pattern": "Exam pattern - stages, subjects, marks",
  "syllabus": "Key subjects/topics in syllabus",
  "strategy": "Short preparation tips for this exam",
  "insights": "Previous year cutoff or exam trends if available",
  "selection": "Selection process steps",
  "seats": "Total vacancies/seats number",
  "salary": "Salary, pay scale or stipend",
  "why_exam": "Why this is a good opportunity - benefits, job security etc",
  "admit_card_status": "Admit card status if mentioned, else Not Available",
  "result_status": "Result status if mentioned, else Not Available",
  "min_age": "Minimum age limit",
  "max_age": "Maximum age limit",
  "fee": "Application fee for General/OBC/SC/ST",
  "qualification": "Educational qualification required"
}}

RULES:
- Write in clear simple English
- If info not found on page, write "Not Available"
- Keep each field concise but informative
- For strategy, give 2-3 short tips even if not on page (based on exam type)
- Return ONLY valid JSON, no extra text

PAGE CONTENT:
{content}
"""

def scrape_page(url: str) -> str:
    """Scrape webpage and return clean text."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # Remove scripts, styles, nav
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL)

        # Strip all HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Clean whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Limit to 4000 chars for AI
        return text[:4000]

    except Exception as e:
        logger.error(f"Scrape failed for {url}: {e}")
        return ""


def extract_with_gemini(content: str, title: str) -> dict:
    """Use Gemini API to extract job details."""
    try:
        import urllib.parse
        prompt = EXTRACT_PROMPT.format(content=f"TITLE: {title}\n\n{content}")

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1500
            }
        }).encode('utf-8')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        text = result['candidates'][0]['content']['parts'][0]['text']
        # Extract JSON from response
        text = re.sub(r'```json|```', '', text).strip()
        data = json.loads(text)
        logger.info(f"✅ Gemini extracted data for: {title[:50]}")
        return data

    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        return {}


def extract_with_groq(content: str, title: str) -> dict:
    """Use Groq API as fallback."""
    try:
        prompt = EXTRACT_PROMPT.format(content=f"TITLE: {title}\n\n{content}")

        payload = json.dumps({
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1500
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
        logger.info(f"✅ Groq extracted data for: {title[:50]}")
        return data

    except Exception as e:
        logger.error(f"Groq extraction failed: {e}")
        return {}


def ai_extract(item: dict) -> dict:
    """
    Main function — scrape page then extract with AI.
    Returns enriched item dict.
    """
    url = item.get('link', '')
    title = item.get('title', '')

    if not url:
        return item

    logger.info(f"🤖 AI extracting: {title[:60]}")

    # Step 1: Scrape the page
    page_content = scrape_page(url)

    if not page_content:
        logger.warning(f"Empty page content for {url}")
        return item

    # Combine with RSS summary
    combined = f"{item.get('summary', '')}\n\n{page_content}"

    # Step 2: Try Gemini first
    ai_data = extract_with_gemini(combined, title)

    # Step 3: Fallback to Groq
    if not ai_data:
        logger.info("Gemini failed, trying Groq...")
        ai_data = extract_with_groq(combined, title)

    # Step 4: Merge AI data into item
    if ai_data:
        item.update({
            'title': ai_data.get('exam_name', title),
            'exam_date': ai_data.get('exam_date', 'Not Available'),
            'form_dates': f"Start: {ai_data.get('form_start_date', 'N/A')} | Last: {ai_data.get('form_last_date', 'N/A')}",
            'authority': ai_data.get('authority', 'Not Available'),
            'institute': ai_data.get('institute', 'Not Available'),
            'eligibility': ai_data.get('eligibility', 'Not Available'),
            'pattern': ai_data.get('pattern', 'Not Available'),
            'syllabus': ai_data.get('syllabus', 'Not Available'),
            'strategy': ai_data.get('strategy', 'Not Available'),
            'insights': ai_data.get('insights', 'Not Available'),
            'selection': ai_data.get('selection', 'Not Available'),
            'seats': ai_data.get('seats', 'Not Available'),
            'salary': ai_data.get('salary', 'Not Available'),
            'why_exam': ai_data.get('why_exam', 'Not Available'),
            'admit_card_status': ai_data.get('admit_card_status', 'Not Available'),
            'result_status': ai_data.get('result_status', 'Not Available'),
            'min_age': ai_data.get('min_age', 'Not Available'),
            'max_age': ai_data.get('max_age', 'Not Available'),
            'fee': ai_data.get('fee', 'Not Available'),
            'qualification': ai_data.get('qualification', 'Not Available'),
            'ai_enriched': True,
        })
        logger.info(f"✅ AI enrichment done for: {title[:50]}")
    else:
        logger.warning(f"⚠️ AI extraction failed, using raw data for: {title[:50]}")
        item['ai_enriched'] = False

    return item
