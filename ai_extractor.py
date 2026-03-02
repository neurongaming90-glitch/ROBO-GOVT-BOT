"""
Smart Extractor — Scrapes job page directly and extracts details using regex patterns.
No external AI API needed — works 100% on Railway.
Also tries Gemini if available as bonus enrichment.
"""
import logging
import re
import json
import urllib.request
import urllib.error
from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-IN,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


def scrape_page(url: str) -> str:
    """Scrape webpage and return clean text."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            # Handle gzip
            try:
                import gzip
                raw = gzip.decompress(raw)
            except Exception:
                pass
            html = raw.decode('utf-8', errors='ignore')

        # Remove unwanted sections
        for tag in ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']:
            html = re.sub(f'<{tag}[^>]*>.*?</{tag}>', ' ', html, flags=re.DOTALL | re.IGNORECASE)

        # Strip all HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Clean whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        text = text.strip()

        logger.info(f"✅ Scraped {len(text)} chars from {url[:60]}")
        return text[:8000]

    except Exception as e:
        logger.error(f"Scrape failed {url}: {e}")
        return ""


def extract_field(text: str, patterns: list, default: str = "Not Available") -> str:
    """Try multiple regex patterns to extract a field."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            result = match.group(1).strip()
            result = re.sub(r'\s+', ' ', result)
            if result and len(result) > 2:
                return result[:300]
    return default


def smart_extract(page_text: str, title: str, summary: str) -> dict:
    """Extract all job details from page text using smart patterns."""

    combined = f"{title}\n{summary}\n{page_text}"

    data = {}

    # Exam/Post Name
    data['exam_name'] = title

    # Total Posts/Vacancies
    data['seats'] = extract_field(combined, [
        r'(?:total\s+)?(?:vacancies?|posts?|seats?)[:\s]+(\d[\d,\s]+)',
        r'(\d[\d,]+)\s+(?:vacancies?|posts?|seats?)',
        r'for\s+(\d[\d,]+)\s+(?:posts?|vacancies?)',
        r'recruitment\s+(?:of\s+)?(\d[\d,]+)',
    ])

    # Last Date
    data['form_last_date'] = extract_field(combined, [
        r'last\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'apply\s+(?:before|by)[:\s]+([^\n\r,\.]{5,50})',
        r'closing\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'(?:walk.?in|walkin)\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'date[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})',
    ])

    # Form Start Date
    data['form_start_date'] = extract_field(combined, [
        r'(?:start|starting|begin|beginning|opening)\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'application\s+(?:start|from)[:\s]+([^\n\r,\.]{5,50})',
        r'(?:notification|advt)\s+date[:\s]+([^\n\r,\.]{5,50})',
    ])

    # Exam Date
    data['exam_date'] = extract_field(combined, [
        r'exam\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'(?:written\s+)?test\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'examination\s+date[:\s]+([^\n\r,\.]{5,50})',
        r'interview\s+date[:\s]+([^\n\r,\.]{5,50})',
    ], "Not Announced Yet")

    # Salary
    data['salary'] = extract_field(combined, [
        r'(?:pay\s+scale|salary|stipend|remuneration|emoluments?|ctc)[:\s]+([^\n\r]{10,150})',
        r'(?:rs\.?|₹|inr)\s*[\d,]+(?:\s*[-–to]+\s*[\d,]+)?(?:\s*(?:per\s+month|p\.?m\.?|per\s+annum|p\.?a\.?))?',
        r'level\s*[-:]?\s*(\d+[^\n\r]{5,80})',
        r'pay\s+(?:band|matrix)[:\s]+([^\n\r]{5,100})',
    ])

    # Eligibility / Qualification
    data['qualification'] = extract_field(combined, [
        r'(?:qualification|education(?:al)?\s+qualification)[:\s]+([^\n\r]{10,300})',
        r'(?:essential\s+)?(?:educational\s+)?qualification[:\s]+([^\n\r]{10,300})',
        r'(?:minimum\s+)?(?:required\s+)?qualification[:\s]+([^\n\r]{10,300})',
    ])

    data['eligibility'] = extract_field(combined, [
        r'eligibility[:\s]+([^\n\r]{10,300})',
        r'who\s+can\s+apply[:\s]+([^\n\r]{10,200})',
        r'candidates?\s+with\s+([^\n\r]{10,200})',
    ], data.get('qualification', 'Not Available'))

    # Age Limit
    data['min_age'] = extract_field(combined, [
        r'(?:minimum|min\.?)\s+age[:\s]+(\d+\s*years?)',
        r'age\s+(?:limit\s+)?(?:minimum|min\.?)[:\s]+(\d+)',
        r'(\d+)\s*[-–]\s*\d+\s*years?\s*(?:age|old)',
    ])

    data['max_age'] = extract_field(combined, [
        r'(?:maximum|max\.?)\s+age[:\s]+([^\n\r]{5,80})',
        r'age\s+(?:limit\s+)?(?:maximum|max\.?)[:\s]+([^\n\r]{5,60})',
        r'age\s+(?:limit|up\s+to)[:\s]+([^\n\r]{5,60})',
        r'not\s+(?:more\s+than|exceeding)\s+(\d+\s*years?)',
        r'\d+\s*[-–]\s*(\d+\s*years?)\s*(?:age|old)',
    ])

    # Application Fee
    data['fee'] = extract_field(combined, [
        r'(?:application\s+)?fee[:\s]+([^\n\r]{5,200})',
        r'(?:registration\s+)?fee[:\s]+([^\n\r]{5,200})',
        r'(?:exam|examination)\s+fee[:\s]+([^\n\r]{5,200})',
        r'no\s+(?:application\s+)?fee',
        r'(?:fee\s+)?(?:is\s+)?(?:nil|waived|exempt)',
    ])

    # Selection Process
    data['selection'] = extract_field(combined, [
        r'selection\s+(?:process|procedure|criteria)[:\s]+([^\n\r]{10,300})',
        r'selection\s+(?:will\s+be\s+(?:made\s+)?(?:on\s+)?(?:the\s+)?basis\s+of)[:\s]+([^\n\r]{10,200})',
        r'(?:shortlisting|interview|written\s+test|walk.?in)[^\n\r]{10,200}',
    ])

    # Authority
    data['authority'] = extract_field(combined, [
        r'(?:conducted|organized)\s+by[:\s]+([^\n\r]{5,100})',
        r'(?:issuing|recruiting)\s+(?:authority|body|organization)[:\s]+([^\n\r]{5,100})',
    ], _guess_authority(title))

    data['institute'] = extract_field(combined, [
        r'(?:organization|organisation|department|ministry|board|commission|university|college|hospital|institute)[:\s]+([^\n\r]{5,150})',
    ], _guess_institute(title, summary))

    # Exam Pattern
    data['pattern'] = extract_field(combined, [
        r'(?:exam\s+)?pattern[:\s]+([^\n\r]{10,300})',
        r'(?:selection\s+)?(?:test|examination)\s+(?:pattern|scheme)[:\s]+([^\n\r]{10,200})',
        r'(?:written|objective|descriptive)\s+(?:test|exam)[^\n\r]{10,200}',
    ])

    # Syllabus
    data['syllabus'] = extract_field(combined, [
        r'syllabus[:\s]+([^\n\r]{10,300})',
        r'subjects?[:\s]+([^\n\r]{10,200})',
        r'topics?\s+(?:covered|included)[:\s]+([^\n\r]{10,200})',
    ])

    # Admit Card / Result status
    data['admit_card_status'] = extract_field(combined, [
        r'admit\s+card[:\s]+([^\n\r]{5,100})',
    ], "Not Released Yet")

    data['result_status'] = extract_field(combined, [
        r'result[:\s]+([^\n\r]{5,100})',
    ], "Not Declared Yet")

    # Why consider — build from summary
    if 'walk' in combined.lower() or 'walkin' in combined.lower():
        data['why_exam'] = "Direct Walk-in opportunity — no written exam required. Immediate joining for eligible candidates."
    elif data['salary'] != 'Not Available':
        data['why_exam'] = f"Good salary package: {data['salary'][:100]}. Permanent government job with job security."
    else:
        data['why_exam'] = "Permanent government job with job security, allowances and career growth opportunities."

    # Strategy based on job type
    data['strategy'] = _get_strategy(title, combined)

    # Insights
    data['insights'] = extract_field(combined, [
        r'(?:previous|last)\s+year[:\s]+([^\n\r]{10,200})',
        r'cutoff[:\s]+([^\n\r]{10,150})',
    ], "Keep checking official website for updates and notifications.")

    return data


def _guess_authority(title: str) -> str:
    title_lower = title.lower()
    if 'upsc' in title_lower: return 'UPSC'
    if 'ssc' in title_lower: return 'SSC'
    if 'nta' in title_lower: return 'NTA'
    if 'railway' in title_lower or 'rrb' in title_lower: return 'Railway Recruitment Board'
    if 'ibps' in title_lower: return 'IBPS'
    if 'sbi' in title_lower: return 'SBI'
    if 'bank' in title_lower: return 'Banking Authority'
    if 'police' in title_lower: return 'Police Department'
    if 'army' in title_lower or 'defence' in title_lower: return 'Ministry of Defence'
    if 'psc' in title_lower: return 'Public Service Commission'
    if 'aiims' in title_lower or 'hospital' in title_lower or 'medical' in title_lower: return 'Ministry of Health'
    return 'Government of India'


def _guess_institute(title: str, summary: str) -> str:
    combined = (title + ' ' + summary)
    match = re.search(
        r'([A-Z][A-Za-z\s&]+(?:University|College|Hospital|Institute|Board|Commission|Corporation|Department|Ministry|Authority|Council))',
        combined
    )
    if match:
        return match.group(1).strip()[:100]
    return _guess_authority(title)


def _get_strategy(title: str, text: str) -> str:
    title_lower = title.lower()
    if 'doctor' in title_lower or 'medical' in title_lower or 'mbbs' in text.lower():
        return "1. Prepare for clinical interview. 2. Keep all original documents ready. 3. Arrive early for walk-in."
    if 'engineer' in title_lower:
        return "1. Revise core engineering subjects. 2. Practice technical MCQs. 3. Keep degree & experience certificates ready."
    if 'teacher' in title_lower or 'lecturer' in title_lower:
        return "1. Revise subject knowledge. 2. Prepare demo lesson. 3. Keep all academic certificates ready."
    if 'bank' in title_lower:
        return "1. Practice Quantitative Aptitude daily. 2. Focus on English & Reasoning. 3. Stay updated on banking news."
    if 'police' in title_lower:
        return "1. Focus on physical fitness. 2. Study GK & current affairs. 3. Practice reasoning & math."
    return "1. Study from official syllabus. 2. Practice previous year papers. 3. Stay updated on official notifications."


def ai_extract(item: dict) -> dict:
    """Main extraction — scrape page + smart regex extraction."""
    title = item.get('title', '')
    summary = item.get('summary', '')
    link = item.get('link', '')
    source = item.get('source', '')

    if not title:
        item['ai_enriched'] = False
        return item

    logger.info(f"🔍 Extracting: {title[:60]}")

    # Step 1: Scrape the actual job page
    page_text = ""
    if link:
        page_text = scrape_page(link)

    # Step 2: Smart regex extraction from page + summary
    combined_text = f"{summary}\n{page_text}"
    data = smart_extract(combined_text, title, summary)

    # Step 3: Try Gemini as bonus (if page text available)
    if page_text and GEMINI_API_KEY:
        gemini_data = call_gemini_bonus(title, source, summary, page_text[:3000])
        if gemini_data:
            # Merge — prefer Gemini data but keep regex data as fallback
            for key, val in gemini_data.items():
                if val and val not in ['Not Available', 'Not Announced Yet', 'Not Released Yet', 'Not Declared Yet']:
                    data[key] = val
            logger.info(f"✅ Gemini bonus applied")

    # Build form_dates
    start = data.get('form_start_date', 'Not Available')
    last = data.get('form_last_date', 'Not Available')
    data['form_dates'] = f"Start: {start} | Last: {last}"

    item.update({
        'title':             data.get('exam_name', title),
        'exam_date':         data.get('exam_date', 'Not Announced Yet'),
        'form_dates':        data['form_dates'],
        'authority':         data.get('authority', source),
        'institute':         data.get('institute', source),
        'eligibility':       data.get('eligibility', 'Not Available'),
        'pattern':           data.get('pattern', 'Walk-in Interview'),
        'syllabus':          data.get('syllabus', 'Not Available'),
        'strategy':          data.get('strategy', 'Not Available'),
        'insights':          data.get('insights', 'Not Available'),
        'selection':         data.get('selection', 'Walk-in Interview / Direct Selection'),
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

    logger.info(f"✅ Extraction done: {title[:50]}")
    return item


def call_gemini_bonus(title: str, source: str, summary: str, page_text: str) -> dict:
    """Optional Gemini call for better extraction."""
    try:
        import requests

        prompt = f"""Extract job details from this Indian govt job page content.
Return ONLY valid JSON with these keys: exam_name, exam_date, form_start_date, form_last_date, authority, institute, eligibility, pattern, syllabus, strategy, insights, selection, seats, salary, why_exam, admit_card_status, result_status, min_age, max_age, fee, qualification.

TITLE: {title}
CONTENT: {page_text[:2000]}

Return raw JSON only."""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1500}
        }

        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            return {}

        result = resp.json()
        text = result['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'```json\s*|```\s*', '', text).strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}
    except Exception as e:
        logger.debug(f"Gemini bonus failed: {e}")
        return {}
