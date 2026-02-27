import feedparser
import hashlib
import logging
import re
import urllib.request
from datetime import datetime
from database import Database
from ai_extractor import ai_extract

logger = logging.getLogger(__name__)

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)

RSS_FEEDS = [
    ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),
    ("https://aglasem.com/feed/", "AglaSem"),
    ("https://testbook.com/blog/feed/", "Testbook"),
    ("https://currentaffairs.adda247.com/feed/", "Adda247"),
    ("https://www.bankersadda.com/feeds/posts/default?alt=rss", "BankersAdda"),
    ("https://www.sscadda.com/feeds/posts/default?alt=rss", "SSCAdda"),
    ("https://www.careerpower.in/blog/feed/", "CareerPower"),
    ("https://www.ibps.in/feed/", "IBPS"),
    ("https://www.jagranjosh.com/feed", "Jagran Josh"),
    ("https://www.employmentnews.gov.in/RSS/CurrentIssue.aspx", "Employment News"),
    ("https://www.fresherslive.com/rss/government-jobs", "FreshersLive"),
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
        clean = re.sub(r'<[^>]+>', '', text or '')
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:400]

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

                for entry in feed.entries[:3]:  # Max 3 per feed to save AI quota
                    item_id = self._generate_id(entry)

                    if self.db.is_posted(item_id):
                        continue

                    published = None
                    for date_field in ['published_parsed', 'updated_parsed']:
                        val = getattr(entry, date_field, None)
                        if val:
                            try:
                                published = datetime(*val[:6])
                                break
                            except Exception:
                                pass

                    summary_raw = (
                        entry.get('summary', '') or
                        entry.get('description', '') or ''
                    )
                    summary = self._clean_html(summary_raw)
                    title = entry.get('title', '').strip()
                    if not title:
                        continue

                    item = {
                        'id': item_id,
                        'title': title,
                        'link': entry.get('link', feed_url),
                        'summary': summary,
                        'published': published,
                        'source': source_name,
                    }

                    # 🤖 AI enrichment — scrape page + extract details
                    item = ai_extract(item)

                    new_items.append(item)
                    count += 1

                if count > 0:
                    logger.info(f"✅ {source_name}: {count} new items")

            except Exception as e:
                logger.error(f"💥 {source_name}: {e}")
                fail_count += 1

        logger.info(f"Fetch done — ✅ {success_count} OK | ❌ {fail_count} failed | 📦 {len(new_items)} new")
        return new_items
