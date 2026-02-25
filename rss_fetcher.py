import feedparser
import hashlib
import logging
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# ONLY VERIFIED WORKING RSS FEEDS
# ─────────────────────────────────────────
RSS_FEEDS = [
    # ✅ Employment News — Govt of India official
    ("https://www.employmentnews.gov.in/RSS/CurrentIssue.aspx", "Employment News"),

    # ✅ SarkariResult — very active
    ("https://www.sarkariresult.com/rss.xml", "SarkariResult"),

    # ✅ FreeJobAlert — reliable
    ("https://www.freejobalert.com/feed/", "FreeJobAlert"),

    # ✅ SarkariNaukri Blog
    ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),

    # ✅ Freshersworld Govt Jobs
    ("https://www.freshersworld.com/rss/government-jobs", "FreshersWorld"),

    # ✅ Naukri.com Govt Jobs RSS
    ("https://www.naukri.com/rss/jobs-in-government-sector.rss", "Naukri.com"),

    # ✅ TimesJobs Govt sector
    ("https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=submit&txtKeywords=government&txtLocation=", "TimesJobs"),

    # ✅ Jagran Josh — top exam portal
    ("https://www.jagranjosh.com/rss/jobs.xml", "Jagran Josh"),

    # ✅ AglaSem Jobs
    ("https://aglasem.com/feed/", "AglaSem"),

    # ✅ Careers360
    ("https://news.careers360.com/rss/jobs", "Careers360"),

    # ✅ Rojgar Samachar
    ("https://rojgarsamachar.gov.in/rss.xml", "Rojgar Samachar"),

    # ✅ IBPS official
    ("https://www.ibps.in/feed/", "IBPS"),

    # ✅ SSC via Jagran
    ("https://www.jagranjosh.com/rss/ssc.xml", "SSC Updates"),

    # ✅ UPSC via Jagran
    ("https://www.jagranjosh.com/rss/upsc.xml", "UPSC Updates"),

    # ✅ Railway Jobs via Jagran
    ("https://www.jagranjosh.com/rss/railway-jobs.xml", "Railway Jobs"),

    # ✅ Bank Jobs via Jagran
    ("https://www.jagranjosh.com/rss/bank-jobs.xml", "Bank Jobs"),

    # ✅ State Govt Jobs via Jagran
    ("https://www.jagranjosh.com/rss/state-govt-jobs.xml", "State Govt Jobs"),

    # ✅ Defence Jobs via Jagran
    ("https://www.jagranjosh.com/rss/defence-jobs.xml", "Defence Jobs"),

    # ✅ Teaching Jobs via Jagran
    ("https://www.jagranjosh.com/rss/teaching-jobs.xml", "Teaching Jobs"),

    # ✅ Results via Jagran
    ("https://www.jagranjosh.com/rss/results.xml", "Exam Results"),

    # ✅ Admit Card via Jagran
    ("https://www.jagranjosh.com/rss/admit-card.xml", "Admit Cards"),
]


class RSSFetcher:
    def __init__(self):
        self.db = Database()
        # Set a browser-like user agent to avoid blocks
        feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def _generate_id(self, entry) -> str:
        raw = (entry.get('link', '') + entry.get('title', '')).encode('utf-8')
        return hashlib.md5(raw).hexdigest()

    def _clean_summary(self, text: str) -> str:
        """Strip HTML tags from summary."""
        import re
        clean = re.sub(r'<[^>]+>', '', text or '')
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:400]

    def fetch_new_items(self) -> list:
        new_items = []
        success_count = 0
        fail_count = 0

        for feed_url, source_name in RSS_FEEDS:
            try:
                logger.info(f"Fetching: {source_name} — {feed_url}")
                feed = feedparser.parse(feed_url)

                # Skip if no entries
                if not feed.entries:
                    logger.warning(f"No entries from {source_name}")
                    fail_count += 1
                    continue

                success_count += 1
                count = 0

                for entry in feed.entries[:5]:  # Max 5 per feed
                    item_id = self._generate_id(entry)

                    if self.db.is_posted(item_id):
                        continue

                    published = None
                    for date_field in ['published_parsed', 'updated_parsed']:
                        if hasattr(entry, date_field) and getattr(entry, date_field):
                            try:
                                published = datetime(*getattr(entry, date_field)[:6])
                                break
                            except Exception:
                                pass

                    summary_raw = entry.get('summary', '') or entry.get('description', '') or ''
                    summary = self._clean_summary(summary_raw)

                    item = {
                        'id': item_id,
                        'title': entry.get('title', 'No Title').strip(),
                        'link': entry.get('link', feed_url),
                        'summary': summary,
                        'published': published,
                        'source': source_name,
                    }
                    new_items.append(item)
                    count += 1

                logger.info(f"✅ {source_name}: {count} new items")

            except Exception as e:
                logger.error(f"❌ Failed {source_name}: {e}")
                fail_count += 1

        logger.info(f"Fetch complete — ✅ {success_count} feeds OK, ❌ {fail_count} failed, 📦 {len(new_items)} new items total")
        return new_items
