"""
RSS feed fetcher for news events.
Fetches and filters news from configured RSS feeds.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import feedparser
from bs4 import BeautifulSoup
import aiohttp

from app.schemas import RSSFeedItem
from app.config import RSS_FEEDS, get_settings
from app.utils import (
    generate_cluster_id, get_utc_now, to_utc,
    extract_tickers_from_text, setup_logger
)

logger = setup_logger(__name__)

# User-Agent to avoid blocking
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class RSSFetcher:
    """
    Fetches news from RSS feeds and filters by ticker whitelist.
    """

    def __init__(self):
        self.settings = get_settings()
        self.feeds = RSS_FEEDS
        self.whitelist = self.settings.tickers

    async def fetch_recent_items(
        self,
        since: Optional[datetime] = None,
        delay_minutes: int = 3
    ) -> list[RSSFeedItem]:
        """
        Fetch recent RSS feed items.

        Args:
            since: Fetch items published after this time (defaults to delay_minutes ago)
            delay_minutes: How many minutes back to look if since not provided

        Returns:
            List of RSSFeedItem objects filtered by ticker whitelist
        """
        if since is None:
            since = get_utc_now() - timedelta(minutes=delay_minutes)

        logger.info(f"Fetching RSS items since {since.isoformat()}")

        # Fetch from all feeds concurrently
        tasks = [
            self._fetch_feed(feed["name"], feed["url"], since)
            for feed in self.feeds
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all items
        all_items = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Feed fetch failed: {result}")
                continue
            all_items.extend(result)

        # Deduplicate by cluster_id
        seen_clusters = set()
        unique_items = []
        for item in all_items:
            if item.cluster_id not in seen_clusters:
                seen_clusters.add(item.cluster_id)
                unique_items.append(item)

        logger.info(f"Fetched {len(unique_items)} unique items (from {len(all_items)} total)")
        return unique_items

    async def _fetch_feed(
        self,
        source: str,
        url: str,
        since: datetime
    ) -> list[RSSFeedItem]:
        """
        Fetch items from a single RSS feed.

        Args:
            source: Feed source name
            url: Feed URL
            since: Minimum publication time

        Returns:
            List of filtered RSS items
        """
        try:
            # Fetch RSS content with aiohttp (with timeout and User-Agent)
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {'User-Agent': USER_AGENT}

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Feed {source} returned status {response.status}")
                        return []

                    content = await response.text()

            # Parse RSS content with feedparser (no network I/O)
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, content)

            if feed.bozo:
                logger.warning(f"Feed parse warning for {source}: {feed.get('bozo_exception', 'Unknown')}")

            items = []
            for entry in feed.entries:
                # Parse publication time
                pub_time = self._parse_pub_time(entry)
                if pub_time is None or pub_time < since:
                    continue

                # Extract headline and snippet
                headline = entry.get('title', '')
                snippet = self._extract_snippet(entry)
                combined_text = f"{headline} {snippet}"

                # Check if any whitelisted ticker is mentioned
                tickers = extract_tickers_from_text(combined_text, self.whitelist)
                if not tickers:
                    continue

                # Create RSS item
                cluster_id = generate_cluster_id(source, headline)
                item = RSSFeedItem(
                    source=source,
                    headline=headline,
                    url=entry.get('link', ''),
                    published_at=pub_time,
                    snippet=snippet,
                    cluster_id=cluster_id
                )
                items.append(item)

            logger.debug(f"Fetched {len(items)} items from {source}")
            return items

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching feed {source} (10s limit)")
            return []
        except aiohttp.ClientError as e:
            logger.warning(f"Network error fetching feed {source}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching feed {source}: {e}")
            return []

    def _parse_pub_time(self, entry: dict) -> Optional[datetime]:
        """Parse publication time from feed entry."""
        # Try different time fields
        for field in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if field in entry and entry[field]:
                try:
                    dt = datetime(*entry[field][:6])
                    return to_utc(dt)
                except Exception:
                    continue

        # Fallback: try string parsing
        for field in ['published', 'updated', 'created']:
            if field in entry:
                try:
                    from dateutil import parser
                    dt = parser.parse(entry[field])
                    return to_utc(dt)
                except Exception:
                    continue

        return None

    def _extract_snippet(self, entry: dict) -> str:
        """Extract text snippet from entry summary/content."""
        # Try summary first
        text = entry.get('summary', '')

        # Try content if summary is empty
        if not text and 'content' in entry and entry['content']:
            text = entry['content'][0].get('value', '')

        # Clean HTML
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)

        # Truncate
        return text[:500] if text else ''


async def main():
    """Test RSS fetcher."""
    fetcher = RSSFetcher()
    items = await fetcher.fetch_recent_items(delay_minutes=60)

    print(f"\nFetched {len(items)} items:\n")
    for item in items[:5]:  # Show first 5
        print(f"Source: {item.source}")
        print(f"Headline: {item.headline}")
        print(f"Published: {item.published_at}")
        print(f"Cluster ID: {item.cluster_id}")
        print(f"URL: {item.url}")
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())
