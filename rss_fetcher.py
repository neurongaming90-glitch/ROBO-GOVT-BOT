import feedparser
import hashlib
import logging
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    # NTA
    "https://nta.ac.in/rss",
    # UPSC
    "https://upsc.gov.in/rss.xml",
    # SSC
    "https://ssc.nic.in/SSCFileServer/Portal/rss/rss.xml",
    # Railway (RRB/RRC)
    "https://indianrailways.gov.in/railwayboard/view_section.jsp?lang=0&id=0,1,304,366,554",
    # IBPS
    "https://www.ibps.in/feed/",
    # Employment News (Rozgar Samachar)
    "https://www.employmentnews.gov.in/RSS/CurrentIssue.aspx",
    # Freshersworld — broad job portal
    "https://www.freshersworld.com/rss/government-jobs",
    # SarkariResult
    "https://www.sarkariresult.com/rss.xml",
    # FreeJobAlert
    "https://www.freejobalert.com/feed/",
    # SarkariNaukri
    "https://sarkarinaukriblog.com/feed/",
    # GovtJobGuru
    "https://www.govtjobguru.in/feed/",
    # India Post
    "https://www.indiapost.gov.in/rss/rss_main.aspx",
    # Defence/Army
    "https://joinindianarmy.nic.in/rss/rss.xml",
    # State PSC — sample: BPSC, MPSC
    "https://www.bpsc.bih.nic.in/rss.xml",
]

class RSSFetcher:
    def __init__(self):
        self.db = Database()

    def _generate_id(self, entry) -> str:
        """Generate a unique ID for a feed entry."""
        raw = (entry.get('link', '') + entry.get('title', '')).encode('utf-8')
        return hashlib.md5(raw).hexdigest()

    def fetch_new_items(self) -> list:
        new_items = []

        for feed_url in RSS_FEEDS:
            try:
                logger.info(f"Fetching: {feed_url}")
                feed = feedparser.parse(feed_url)

                if feed.bozo and not feed.entries:
                    logger.warning(f"Feed error for {feed_url}: {feed.bozo_exception}")
                    continue

                for entry in feed.entries[:10]:  # Limit to 10 newest per feed
                    item_id = self._generate_id(entry)

                    if self.db.is_posted(item_id):
                        continue

                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6])
                        except Exception:
                            pass

                    item = {
                        'id': item_id,
                        'title': entry.get('title', 'No Title').strip(),
                        'link': entry.get('link', ''),
                        'summary': entry.get('summary', ''),
                        'published': published,
                        'source': feed.feed.get('title', feed_url),
                    }
                    new_items.append(item)

            except Exception as e:
                logger.error(f"Failed to fetch {feed_url}: {e}")

        logger.info(f"Total new items: {len(new_items)}")
        return new_items
