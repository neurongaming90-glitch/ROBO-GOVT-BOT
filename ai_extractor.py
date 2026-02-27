import json
import logging
import urllib.request
import ssl

logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

PROMPT = """You are an expert at extracting Indian government job/exam details.

From the title and description below, extract all available info and return ONLY a valid JSON object.
If a field is not mentioned anywhere, use "Not Available".
Be smart — infer eligibility, age limits, salary from context if possible.

JSON structure to return:
{{
  "exam_date": "date of exam or Not Available",
  "form_dates": "application start and last date",
  "authority": "conducting authority like UPSC/SSC/State Govt",
  "institute": "organizing body like NTA/IBPS/Railway Board",
  "eligibility": "educational qualification and criteria",
  "pattern": "exam pattern if mentioned",
  "syllabus": "subjects/topics if mentioned",
  "strategy": "preparation tips based on exam type",
  "insights": "previous year cutoff or paper insights if known",
  "selection": "selection process like written/interview/medical",
  "seats": "total vacancies number",
  "salary": "pay scale or salary range",
  "why_exam": "why candidates should apply - benefits",
  "admit_card_status": "admit card release status",
  "result_status": "result status",
  "min_age": "minimum age limit",
  "max_age": "maximum age limit",
  "fee": "application fee for general/SC/ST",
  "qualification": "minimum qualification required"
}}

Title: {title}
Description: {summary}

Return ONLY the JSON object, nothing else."""


def _parse_response(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    return json.loads(text)


def extract_with_gemini(title, summary):
    from config import GEMINI_API_KEY
    prompt = PROMPT.format(title=title, summary=summary)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=ssl_context, timeout=25) as r:
        data = json.loads(r.read().decode())
    text = data['candidates'][0]['content']['parts'][0]['text']
    return _parse_response(text)


def extract_with_groq(title, summary):
    from config import GROQ_API_KEY
    prompt = PROMPT.format(title=title, summary=summary)
    payload = json.dumps({
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1024
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=ssl_context, timeout=25) as r:
        data = json.loads(r.read().decode())
    text = data['choices'][0]['message']['content']
    return _parse_response(text)


def ai_extract(item: dict) -> dict:
    """Enrich item with AI-extracted fields. Gemini first, Groq fallback."""
    title = item.get('title', '')
    summary = item.get('summary', '')

    try:
        logger.info(f"🤖 Gemini: {title[:50]}")
        extracted = extract_with_gemini(title, summary)
        logger.info("✅ Gemini OK")
        return {**item, **extracted}
    except Exception as e:
        logger.warning(f"Gemini failed ({e}), trying Groq...")

    try:
        extracted = extract_with_groq(title, summary)
        logger.info("✅ Groq OK")
        return {**item, **extracted}
    except Exception as e:
        logger.error(f"Both AI failed: {e}")
        return item
