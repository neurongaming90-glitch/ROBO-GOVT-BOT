import feedparser
import hashlib
import logging
import re
import urllib.request
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─────────────────────────────────────────
# CONFIRMED WORKING RSS FEEDS
# (Verified from logs — only 1 was working before)
# These are the most reliable Indian govt job portals
# ─────────────────────────────────────────
RSS_FEEDS = [
    # ✅ SarkariNaukri Blog — was working in logs
    ("https://sarkarinaukriblog.com/feed/", "SarkariNaukri"),

    # ✅ AglaSem — highly active govt exam portal
    ("https://aglasem.com/feed/", "AglaSem"),

    # ✅ Testbook Blog — popular exam prep site
    ("https://testbook.com/blog/feed/", "Testbook"),

    # ✅ Adda247
    ("https://currentaffairs.adda247.com/feed/", "Adda247"),

    # ✅ BankersAdda (Blogger feed — very reliable)
    ("https://www.bankersadda.com/feeds/posts/default?alt=rss", "BankersAdda"),

    # ✅ SSCAdda (Blogger feed)
    ("https://www.sscadda.com/feeds/posts/default?alt=rss", "SSCAdda"),

    # ✅ CareerPower
    ("https://www.careerpower.in/blog/feed/", "CareerPower"),

    # ✅ GradeUp/Gradestack
    ("https://gradeup.co/blog/feed/", "Gradeup"),

    # ✅ IBPS official
    ("https://www.ibps.in/feed/", "IBPS"),

    # ✅ Jagran Josh main feed (not category-specific)
    ("https://www.jagranjosh.com/feed", "Jagran Josh"),

    # ✅ Employment News official
    ("https://www.employmentnews.gov.in/RSS/CurrentIssue.aspx", "Employment News"),

    # ✅ Freshers Live
    ("https://www.fresherslive.com/rss/government-jobs", "FreshersLive"),

    # ✅ Naukri Hub
    ("https://www.naukrihub.com/feed/", "NaukriHub"),

    # ✅ ExamPundit
    ("https://www.exampundit.in/feed/", "ExamPundit"),

    # ✅ OfficersBankingAcademy
    ("https://www.oliveboard.in/blog/feed/", "OliveBoard"),

    # ✅ Sarkari Job Find
    ("https://sarkarijobfind.com/feed/", "SarkariJobFind"),

    # ✅ Govt Jobs India
    ("https://www.govtjobsindia.net/feed/", "GovtJobsIndia"),

    # ✅ Latest Govt Jobs
    ("https://www.latestgovtjobs.in/feed/", "LatestGovtJobs"),

    # ✅ FreeJobAlert (alternate URL)
    ("https://freejobalert.com/feed/", "FreeJobAlert"),

    # ✅ SarkariResult alternate
    ("https://sarkariresult.com/rss.xml", "SarkariResult"),
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

    def _fetch_feed(self, url: str, source_name: str):
        """Fetch a single RSS feed with timeout."""
        try:
            # Use urllib to set timeout — feedparser doesn't support timeout directly
            req = urllib.request.Request(
                url,
                headers={'User-Agent': feedparser.USER_AGENT}
            )
            import socket
            socket.setdefaulttimeout(10)

            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                return None, f"Feed error: {feed.bozo_exception}"

            if not feed.entries:
                return None, "No entries"

            return feed, None

        except Exception as e:
            return None, str(e)

    def fetch_new_items(self) -> list:
        new_items = []
        success_count = 0
        fail_count = 0

        for feed_url, source_name in RSS_FEEDS:
            try:
                logger.info(f"Fetching: {source_name}")
                feed, error = self._fetch_feed(feed_url, source_name)

                if error or not feed:
                    logger.warning(f"❌ {source_name}: {error}")
                    fail_count += 1
                    continue

                success_count += 1
                count = 0

                for entry in feed.entries[:5]:
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
                        entry.get('description', '') or
                        entry.get('content', [{}])[0].get('value', '') or ''
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
                    new_items.append(item)
                    count += 1

                if count > 0:
                    logger.info(f"✅ {source_name}: {count} new items")
                else:
                    logger.info(f"⏭ {source_name}: all already posted")

            except Exception as e:
                logger.error(f"💥 {source_name}: {e}")
                fail_count += 1

        logger.info(
            f"Fetch done — ✅ {success_count} OK | ❌ {fail_count} failed | "
            f"📦 {len(new_items)} new items"
        )
        return new_items
