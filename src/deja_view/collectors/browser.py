"""
Browser activity collector for Deja View.

Reads local browser history databases to capture browsing activity.
Supports Chrome and Firefox history formats.
"""

import asyncio
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set

from deja_view.collectors.base import BaseCollector
from deja_view.config import get_config
from deja_view.models import Event, EventType


class BrowserCollector(BaseCollector):
    """
    Collector for browser history events.
    
    Reads Chrome and Firefox history databases to track
    web browsing activity. Copies databases to avoid locking issues.
    """
    
    # URL patterns to ignore
    IGNORE_URL_PATTERNS = [
        "chrome://",
        "chrome-extension://",
        "about:",
        "moz-extension://",
        "edge://",
        "brave://",
        "file://",
        "data:",
    ]
    
    def __init__(self, poll_interval: Optional[int] = None):
        """
        Initialize the browser collector.
        
        Args:
            poll_interval: Seconds between history database checks
        """
        super().__init__("browser")
        config = get_config()
        self.poll_interval = poll_interval or config.browser_poll_interval
        self.chrome_path = config.chrome_history_path
        self.firefox_path = config.firefox_history_path
        
        # Track last visit times to avoid duplicates
        self._last_chrome_visit: Optional[int] = None
        self._last_firefox_visit: Optional[int] = None
        self._seen_visits: Set[str] = set()
    
    def _should_ignore_url(self, url: str) -> bool:
        """Check if a URL should be ignored based on configured patterns.

        Args:
            url: The URL to check.

        Returns:
            True if the URL matches any ignore pattern, False otherwise.
        """
        for pattern in self.IGNORE_URL_PATTERNS:
            if url.startswith(pattern):
                return True
        return False
    
    def _copy_database(self, source: Path) -> Optional[Path]:
        """Copy a database file to temp location to avoid locking.

        Browser databases are often locked by the browser process.
        This method copies the database to a temporary location for safe reading.

        Args:
            source: Source database path.

        Returns:
            Path to copied database or None if copy failed.
        """
        try:
            temp_dir = tempfile.gettempdir()
            dest = Path(temp_dir) / f"DEJA_{source.name}"
            shutil.copy2(source, dest)
            return dest
        except (IOError, OSError) as e:
            self.logger.debug(f"Failed to copy database {source}: {e}")
            return None
    
    def _read_chrome_history(self, since_visit_time: Optional[int] = None) -> List[Dict]:
        """Read Chrome history database.

        Chrome stores timestamps as microseconds since 1601-01-01 (Windows FILETIME).
        This method copies the database to avoid locking issues with the browser.

        Args:
            since_visit_time: Only get visits after this Chrome timestamp
                (microseconds since 1601-01-01). Defaults to 1 hour ago.

        Returns:
            List of visit dictionaries containing url, title, timestamp,
            browser name, and visit_time.
        """
        if not self.chrome_path or not self.chrome_path.exists():
            return []
        
        visits = []
        db_copy = self._copy_database(self.chrome_path)
        if not db_copy:
            return []
        
        try:
            conn = sqlite3.connect(str(db_copy), timeout=5)
            cursor = conn.cursor()
            
            # Chrome timestamp epoch: 1601-01-01
            # Convert to Unix timestamp: subtract 11644473600 seconds
            query = """
                SELECT 
                    urls.url,
                    urls.title,
                    visits.visit_time
                FROM visits
                JOIN urls ON visits.url = urls.id
                WHERE visits.visit_time > ?
                ORDER BY visits.visit_time DESC
                LIMIT 100
            """
            
            # Default: last hour
            if since_visit_time is None:
                # Chrome timestamp for 1 hour ago
                since_visit_time = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000000) + 11644473600000000
            
            cursor.execute(query, (since_visit_time,))
            
            for row in cursor.fetchall():
                url, title, visit_time = row
                
                if self._should_ignore_url(url):
                    continue
                
                # Convert Chrome timestamp to datetime
                unix_timestamp = (visit_time / 1000000) - 11644473600
                try:
                    timestamp = datetime.fromtimestamp(unix_timestamp)
                except (ValueError, OSError):
                    timestamp = datetime.now()
                
                visits.append({
                    "url": url,
                    "title": title or "",
                    "timestamp": timestamp,
                    "browser": "chrome",
                    "visit_time": visit_time,
                })
            
            conn.close()
            
        except sqlite3.Error as e:
            self.logger.debug(f"Chrome history read error: {e}")
        finally:
            try:
                db_copy.unlink()
            except OSError:
                pass
        
        return visits
    
    def _read_firefox_history(self, since_visit_time: Optional[int] = None) -> List[Dict]:
        """Read Firefox history database.

        Firefox stores timestamps as microseconds since Unix epoch.
        This method copies the database to avoid locking issues with the browser.

        Args:
            since_visit_time: Only get visits after this timestamp
                (microseconds since Unix epoch). Defaults to 1 hour ago.

        Returns:
            List of visit dictionaries containing url, title, timestamp,
            browser name, and visit_time.
        """
        if not self.firefox_path or not self.firefox_path.exists():
            return []
        
        visits = []
        db_copy = self._copy_database(self.firefox_path)
        if not db_copy:
            return []
        
        try:
            conn = sqlite3.connect(str(db_copy), timeout=5)
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    moz_places.url,
                    moz_places.title,
                    moz_historyvisits.visit_date
                FROM moz_historyvisits
                JOIN moz_places ON moz_historyvisits.place_id = moz_places.id
                WHERE moz_historyvisits.visit_date > ?
                ORDER BY moz_historyvisits.visit_date DESC
                LIMIT 100
            """
            
            # Default: last hour in microseconds
            if since_visit_time is None:
                since_visit_time = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000000)
            
            cursor.execute(query, (since_visit_time,))
            
            for row in cursor.fetchall():
                url, title, visit_date = row
                
                if self._should_ignore_url(url):
                    continue
                
                # Convert Firefox timestamp to datetime
                try:
                    timestamp = datetime.fromtimestamp(visit_date / 1000000)
                except (ValueError, OSError):
                    timestamp = datetime.now()
                
                visits.append({
                    "url": url,
                    "title": title or "",
                    "timestamp": timestamp,
                    "browser": "firefox",
                    "visit_time": visit_date,
                })
            
            conn.close()
            
        except sqlite3.Error as e:
            self.logger.debug(f"Firefox history read error: {e}")
        finally:
            try:
                db_copy.unlink()
            except OSError:
                pass
        
        return visits
    
    def _create_visit_event(self, visit: Dict) -> Event:
        """Create an Event object for a browser visit.

        Args:
            visit: Dictionary containing visit data with keys: url, title,
                timestamp, browser, and visit_time.

        Returns:
            An Event object representing the browser visit.
        """
        # Extract domain from URL
        url = visit["url"]
        domain = ""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
        except Exception:
            pass
        
        return Event(
            event_type=EventType.BROWSER_VISIT,
            source=self.name,
            subject=url[:500],
            timestamp=visit["timestamp"],
            description=f"Visited: {visit['title'][:50] or domain}",
            url=url,
            title=visit["title"],
            browser=visit["browser"],
            metadata={
                "domain": domain,
            }
        )
    
    async def start(self) -> None:
        """Initialize browser collector state.

        Sets initial visit times to the current time to only capture new visits.
        Logs which browsers are available for monitoring.
        """
        # Set initial visit times to now to only capture new visits
        now_micro = int(datetime.now().timestamp() * 1000000)
        chrome_now = now_micro + 11644473600000000  # Chrome epoch offset
        
        self._last_chrome_visit = chrome_now
        self._last_firefox_visit = now_micro
        
        browsers = []
        if self.chrome_path and self.chrome_path.exists():
            browsers.append("Chrome")
        if self.firefox_path and self.firefox_path.exists():
            browsers.append("Firefox")
        
        if browsers:
            self.logger.info(f"Monitoring browsers: {', '.join(browsers)}")
        else:
            self.logger.warning("No browser history databases found")
    
    async def stop(self) -> None:
        """Clean up browser collector resources.

        Clears the seen visits cache to free memory.
        """
        self._seen_visits.clear()
    
    async def collect(self) -> AsyncIterator[Event]:
        """Yield browser visit events.

        Periodically reads Chrome and Firefox browser history databases
        and yields events for new page visits. Maintains a cache of seen
        visits to avoid duplicates.

        Yields:
            Event objects for each new browser page visit.
        """
        while self._running:
            try:
                # Collect Chrome history
                chrome_visits = self._read_chrome_history(self._last_chrome_visit)
                for visit in chrome_visits:
                    visit_key = f"chrome:{visit['visit_time']}"
                    if visit_key not in self._seen_visits:
                        self._seen_visits.add(visit_key)
                        self._last_chrome_visit = max(
                            self._last_chrome_visit or 0,
                            visit["visit_time"]
                        )
                        yield self._create_visit_event(visit)
                
                # Collect Firefox history
                firefox_visits = self._read_firefox_history(self._last_firefox_visit)
                for visit in firefox_visits:
                    visit_key = f"firefox:{visit['visit_time']}"
                    if visit_key not in self._seen_visits:
                        self._seen_visits.add(visit_key)
                        self._last_firefox_visit = max(
                            self._last_firefox_visit or 0,
                            visit["visit_time"]
                        )
                        yield self._create_visit_event(visit)
                
                # Limit seen visits cache
                if len(self._seen_visits) > 10000:
                    to_remove = list(self._seen_visits)[:5000]
                    for key in to_remove:
                        self._seen_visits.discard(key)
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in browser collection: {e}")
                await asyncio.sleep(self.poll_interval)
