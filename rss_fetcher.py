import feedparser
import hashlib
import logging
import re
import urllib.request
import gzip
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-IN,en;q=0.5',
    'Connection': 'keep-alive',
}

RSS_FEEDS = [
    ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
    ("https://aglasem.com/feed/", "AglaSem"),
    ("https://testbook.com/blog/feed/", "Testbook"),
    ("https://currentaffairs.adda247.com/feed/", "Adda247"),
    ("https://www.bankersadda.com/feeds/posts/default?alt=rss", "BankersAdda"),
    ("https://www.sscadda.com/feeds/posts/default?alt=rss", "SSCAdda"),
    ("https://www.ibps.in/feed/", "IBPS"),
    ("https://www.jagranjosh.com/feed", "Jagran Josh"),
    ("https://www.employmentnews.gov.in/RSS/CurrentIssue.aspx", "Employment News"),
    ("https://www.exampundit.in/feed/", "ExamPundit"),
    ("https://www.oliveboard.in/blog/feed/", "OliveBoard"),
    ("https://sarkarijobfind.com/feed/", "SarkariJobFind"),
    ("https://www.freejobalert.com/feed/", "FreeJobAlert"),
    ("https://www.sarkariresult.com/rss.xml", "SarkariResult"),
]


class RSSFetcher:
    def __init__(self):
        self.db = Database()

    def _generate_id(self, entry) -> str:
        raw = (entry.get('link', '') + entry.get('title', '')).encode('utf-8')
        return hashlib.md5(raw).hexdigest()

    def _clean_html(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', text or '')
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]

    def _scrape_page(self, url: str) -> str:
        """Scrape job page and return clean text."""
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
                html = raw.decode('utf-8', errors='ignore')

            # Remove unwanted tags
            for tag in ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript', 'aside']:
                html = re.sub(f'<{tag}[^>]*>.*?</{tag}>', ' ', html, flags=re.DOTALL | re.IGNORECASE)

            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n+', '\n', text)
            return text.strip()[:8000]
        except Exception as e:
            logger.warning(f"Scrape failed {url[:60]}: {e}")
            return ""

    def _extract(self, text: str, patterns: list, default: str = "Not Available") -> str:
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                val = m.group(1).strip() if m.lastindex else m.group(0).strip()
                val = re.sub(r'\s+', ' ', val)[:250]
                if val and len(val) > 2:
                    return val
        return default

    def _extract_details(self, page: str, title: str, summary: str) -> dict:
        """Extract all job details from page text."""
        text = f"{title}\n{summary}\n{page}"
        d = {}

        # Vacancies
        d['seats'] = self._extract(text, [
            r'(?:total\s+)?(?:vacancies?|posts?|seats?)[:\s–-]+(\d[\d,\s]+)',
            r'(\d[\d,]+)\s+(?:vacancies?|posts?|seats?)',
            r'for\s+(\d[\d,]+)\s+(?:posts?|vacancies?)',
            r'recruitment\s+(?:of\s+)?(\d[\d,]+)\s+',
            r'(\d+)\s+(?:junior|senior|assistant|officer)',
        ])

        # Last Date
        d['form_last_date'] = self._extract(text, [
            r'last\s+date(?:\s+(?:to|for|of)\s+(?:apply|submission|application))?[:\s–-]+([^\n\r,]{5,60})',
            r'apply\s+(?:before|by|till|upto|up\s+to)[:\s–-]+([^\n\r,]{5,50})',
            r'closing\s+date[:\s–-]+([^\n\r,]{5,50})',
            r'(?:walk.?in|walkin)\s+(?:date|interview)[:\s–-]+([^\n\r,]{5,50})',
            r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
            r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4})',
        ])

        # Start Date
        d['form_start_date'] = self._extract(text, [
            r'(?:start|starting|begin|opening)\s+date[:\s–-]+([^\n\r,]{5,50})',
            r'application\s+(?:start|from|begin)[:\s–-]+([^\n\r,]{5,50})',
            r'(?:from|w\.?e\.?f)[:\s–-]+([^\n\r,]{5,50})',
        ])

        # Exam Date
        d['exam_date'] = self._extract(text, [
            r'exam(?:ination)?\s+date[:\s–-]+([^\n\r,]{5,50})',
            r'(?:written\s+)?test\s+date[:\s–-]+([^\n\r,]{5,50})',
            r'interview\s+date[:\s–-]+([^\n\r,]{5,50})',
            r'(?:cbt|tier|phase)\s+\d+\s+date[:\s–-]+([^\n\r,]{5,50})',
        ], "Not Announced Yet")

        # Salary
        d['salary'] = self._extract(text, [
            r'(?:pay\s+(?:scale|band|matrix|level)|salary|stipend|remuneration|emoluments?|ctc)[:\s–-]+([^\n\r]{10,150})',
            r'(?:rs\.?|₹)\s*[\d,]+(?:\s*[-–/]\s*[\d,]+)?(?:[^\n\r]{0,50}(?:month|annum|p\.?m\.?|p\.?a\.?))?',
            r'level\s*[-:]?\s*(\d+[^\n\r]{5,80})',
        ])

        # Qualification
        d['qualification'] = self._extract(text, [
            r'(?:essential\s+)?(?:educational\s+)?qualification(?:s)?[:\s–-]+([^\n]{15,300})',
            r'(?:minimum\s+)?(?:required\s+)?qualification[:\s–-]+([^\n]{15,300})',
            r'education(?:al)?\s+qualification[:\s–-]+([^\n]{15,300})',
        ])

        # Eligibility
        d['eligibility'] = self._extract(text, [
            r'eligibility[:\s–-]+([^\n]{15,300})',
            r'who\s+can\s+apply[:\s–-]+([^\n]{15,200})',
            r'candidates?\s+(?:must\s+have|with|having)[:\s–-]?\s+([^\n]{15,200})',
        ], d.get('qualification', 'Not Available'))

        # Age
        d['min_age'] = self._extract(text, [
            r'(?:minimum|min\.?)\s+age[:\s–-]+(\d+\s*years?)',
            r'age[:\s–-]+(\d+)\s*[-–to]+\s*\d+',
            r'not\s+less\s+than\s+(\d+\s*years?)',
        ])

        d['max_age'] = self._extract(text, [
            r'(?:maximum|max\.?|upper)\s+age(?:\s+limit)?[:\s–-]+([^\n]{5,80})',
            r'age(?:\s+limit)?[:\s–-]+\d+\s*[-–to]+\s*(\d+\s*years?[^\n]{0,50})',
            r'not\s+(?:more\s+than|exceeding|above)\s+(\d+\s*years?[^\n]{0,50})',
            r'age\s+(?:limit\s+)?(?:up\s+to|upto)[:\s–-]+(\d+\s*years?[^\n]{0,50})',
        ])

        # Fee
        d['fee'] = self._extract(text, [
            r'(?:application|exam(?:ination)?|registration)\s+fee[:\s–-]+([^\n]{5,200})',
            r'fee[:\s–-]+([^\n]{5,150})',
            r'(no\s+(?:application\s+)?fee[^\n]{0,50})',
            r'fee\s+(?:is\s+)?(?:nil|waived|exempted?|free)',
        ])

        # Selection
        d['selection'] = self._extract(text, [
            r'selection\s+(?:process|procedure|criteria|mode)[:\s–-]+([^\n]{10,300})',
            r'selection\s+(?:will\s+be\s+(?:done|made|based)\s+(?:on|through))[:\s–-]?\s+([^\n]{10,200})',
        ])

        # Pattern
        d['pattern'] = self._extract(text, [
            r'(?:exam(?:ination)?\s+)?pattern[:\s–-]+([^\n]{10,300})',
            r'(?:test|paper)\s+pattern[:\s–-]+([^\n]{10,200})',
        ])

        # Syllabus
        d['syllabus'] = self._extract(text, [
            r'syllabus[:\s–-]+([^\n]{10,300})',
            r'subjects?[:\s–-]+([^\n]{10,200})',
        ])

        # Authority / Institute
        d['authority'] = self._guess_authority(title)
        d['institute'] = self._guess_institute(title, text)

        # Why exam
        d['why_exam'] = self._get_why(title, text, d)

        # Strategy
        d['strategy'] = self._get_strategy(title, text)

        # Insights
        d['insights'] = self._extract(text, [
            r'(?:previous|last)\s+year[^\n]{0,10}(?:cutoff|cut.?off)[:\s–-]+([^\n]{10,150})',
            r'cutoff[:\s–-]+([^\n]{10,150})',
        ], "Prepare well and keep checking official website for updates.")

        d['admit_card_status'] = self._extract(text, [
            r'admit\s+card[:\s–-]+([^\n]{5,100})',
        ], "Not Released Yet")

        d['result_status'] = self._extract(text, [
            r'result[:\s–-]+([^\n]{5,100})',
        ], "Not Declared Yet")

        return d

    def _guess_authority(self, title: str) -> str:
        t = title.lower()
        if 'upsc' in t: return 'UPSC (Union Public Service Commission)'
        if 'ssc' in t: return 'SSC (Staff Selection Commission)'
        if 'nta' in t: return 'NTA (National Testing Agency)'
        if 'rrb' in t or 'railway' in t or 'rrc' in t: return 'Railway Recruitment Board (RRB)'
        if 'ibps' in t: return 'IBPS (Institute of Banking Personnel Selection)'
        if 'sbi' in t: return 'SBI (State Bank of India)'
        if 'rbi' in t: return 'RBI (Reserve Bank of India)'
        if 'aiims' in t: return 'AIIMS'
        if 'esic' in t: return 'ESIC'
        if 'drdo' in t: return 'DRDO'
        if 'isro' in t: return 'ISRO'
        if 'psc' in t: return 'Public Service Commission'
        if 'police' in t: return 'Police Recruitment Board'
        if 'army' in t or 'defence' in t or 'military' in t: return 'Ministry of Defence'
        if 'nit' in t or 'iit' in t: return 'Ministry of Education'
        if 'hospital' in t or 'medical' in t or 'health' in t: return 'Ministry of Health'
        return 'Government of India'

    def _guess_institute(self, title: str, text: str) -> str:
        m = re.search(
            r'([A-Z][A-Za-z\s&\(\)]+(?:University|College|Hospital|Institute|Board|Commission|Corporation|Department|Ministry|Authority|Council|Bank|Railway|Police|Academy))',
            title + ' ' + text[:500]
        )
        if m:
            return m.group(1).strip()[:120]
        return self._guess_authority(title)

    def _get_why(self, title: str, text: str, d: dict) -> str:
        t = title.lower()
        if 'walk' in t or 'walkin' in t:
            return "Direct Walk-in — no written exam! Immediate opportunity for eligible candidates with government benefits."
        if d.get('salary', 'Not Available') != 'Not Available':
            sal = d['salary'][:80]
            return f"Attractive pay: {sal}. Permanent govt job with pension, allowances and job security."
        if 'upsc' in t:
            return "Most prestigious govt exam in India. Leads to IAS/IPS/IFS — top administrative positions with high salary and authority."
        if 'ssc' in t:
            return "Central govt job with Grade Pay benefits, job security and career growth across India."
        if 'bank' in t or 'ibps' in t or 'sbi' in t:
            return "Banking job with excellent salary, perks, housing loan benefits and career advancement opportunities."
        if 'railway' in t or 'rrb' in t:
            return "Railway job with free travel pass, housing, medical benefits and lifetime job security."
        return "Permanent government job with job security, pension benefits and career growth opportunities."

    def _get_strategy(self, title: str, text: str) -> str:
        t = (title + text[:200]).lower()
        if 'doctor' in t or 'mbbs' in t or 'medical' in t or 'hospital' in t:
            return "1. Prepare for clinical/technical interview. 2. Keep all original certificates & documents ready. 3. Arrive 30 min early for walk-in."
        if 'engineer' in t:
            return "1. Revise core engineering concepts. 2. Practice technical MCQs from previous papers. 3. Keep degree & experience certificates ready."
        if 'teacher' in t or 'lecturer' in t or 'professor' in t:
            return "1. Master your subject thoroughly. 2. Prepare a demo lesson. 3. Keep all academic certificates organized."
        if 'bank' in t or 'ibps' in t or 'sbi' in t:
            return "1. Practice Quantitative Aptitude & Reasoning daily. 2. Focus on English & Computer Knowledge. 3. Stay updated on banking/finance news."
        if 'upsc' in t:
            return "1. Study NCERT books thoroughly. 2. Read The Hindu daily for current affairs. 3. Practice answer writing regularly."
        if 'ssc' in t:
            return "1. Focus on Maths, English & GK. 2. Practice Tier-1 speed & accuracy. 3. Solve last 5 years papers."
        if 'railway' in t or 'rrb' in t:
            return "1. Focus on Maths, GK & Reasoning. 2. Practice RRB previous year papers. 3. Be physically fit for medical test."
        if 'police' in t:
            return "1. Build physical fitness daily. 2. Study GK & Current Affairs. 3. Practice Reasoning and Maths."
        return "1. Read official notification carefully. 2. Practice previous year question papers. 3. Stay updated on official website."

    def fetch_new_items(self) -> list:
        new_items = []
        success_count = 0
        fail_count = 0

        for feed_url, source_name in RSS_FEEDS:
            try:
                logger.info(f"Fetching: {source_name}")
                feed = feedparser.parse(feed_url)

                if not feed.entries:
                    logger.warning(f"❌ No entries: {source_name}")
                    fail_count += 1
                    continue

                success_count += 1
                count = 0

                for entry in feed.entries[:3]:
                    item_id = self._generate_id(entry)

                    if self.db.is_posted(item_id):
                        continue

                    published = None
                    for f in ['published_parsed', 'updated_parsed']:
                        val = getattr(entry, f, None)
                        if val:
                            try:
                                published = datetime(*val[:6])
                                break
                            except Exception:
                                pass

                    summary = self._clean_html(
                        entry.get('summary', '') or entry.get('description', '') or ''
                    )
                    title = entry.get('title', '').strip()
                    link = entry.get('link', feed_url)

                    if not title:
                        continue

                    # Scrape the actual job page
                    logger.info(f"🔍 Scraping: {title[:50]}")
                    page_text = self._scrape_page(link)

                    # Extract details
                    details = self._extract_details(page_text, title, summary)

                    item = {
                        'id': item_id,
                        'title': details.get('exam_name', title),
                        'link': link,
                        'summary': summary,
                        'published': published,
                        'source': source_name,
                        'exam_date': details.get('exam_date', 'Not Announced Yet'),
                        'form_dates': f"Start: {details.get('form_start_date','N/A')} | Last: {details.get('form_last_date','N/A')}",
                        'authority': details.get('authority', source_name),
                        'institute': details.get('institute', source_name),
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

                    new_items.append(item)
                    count += 1
                    logger.info(f"✅ Extracted: {title[:50]}")

                if count > 0:
                    logger.info(f"✅ {source_name}: {count} new items")

            except Exception as e:
                logger.error(f"💥 {source_name}: {e}")
                fail_count += 1

        logger.info(f"Done — ✅ {success_count} feeds | 📦 {len(new_items)} new items")
        return new_items
