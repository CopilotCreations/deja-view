"""
DuckDB event storage for Deja View.

Provides append-only, time-indexed storage for events using DuckDB.
Supports efficient querying by time range, event type, and subject.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Any
from uuid import UUID

import duckdb

from deja_view.config import get_config
from deja_view.models import Event, EventType


class EventDatabase:
    """
    DuckDB-based event storage.
    
    Provides thread-safe, append-only storage for events with
    efficient time-based queries.
    """
    
    def __init__(self, database_path: Optional[Path] = None):
        """
        Initialize the event database.
        
        Args:
            database_path: Path to the DuckDB database file.
                          Uses config default if not provided.
        """
        config = get_config()
        self.database_path = database_path or config.database_path
        self.logger = logging.getLogger("deja.storage.database")
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        
        # Ensure data directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    def connect(self) -> None:
        """Connect to the database and initialize schema."""
        self._conn = duckdb.connect(str(self.database_path))
        self._initialize_schema()
        self.logger.info(f"Connected to database: {self.database_path}")
    
    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self.logger.info("Database connection closed")
    
    def _initialize_schema(self) -> None:
        """Create the events table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id VARCHAR PRIMARY KEY,
                event_type VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                source VARCHAR NOT NULL,
                subject VARCHAR NOT NULL,
                subject_secondary VARCHAR,
                description VARCHAR,
                repository VARCHAR,
                branch VARCHAR,
                process_name VARCHAR,
                process_id INTEGER,
                url VARCHAR,
                title VARCHAR,
                browser VARCHAR,
                metadata JSON,
                confidence DOUBLE DEFAULT 1.0
            )
        """)
        
        # Create indexes for common query patterns
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp 
            ON events (timestamp)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type 
            ON events (event_type)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_source 
            ON events (source)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_subject 
            ON events (subject)
        """)
    
    def insert_event(self, event: Event) -> None:
        """
        Insert a single event into the database.
        
        Args:
            event: Event to insert
        """
        self._conn.execute("""
            INSERT INTO events (
                id, event_type, timestamp, source, subject, subject_secondary,
                description, repository, branch, process_name, process_id,
                url, title, browser, metadata, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            str(event.id),
            event.event_type.value,
            event.timestamp,
            event.source,
            event.subject,
            event.subject_secondary,
            event.description,
            event.repository,
            event.branch,
            event.process_name,
            event.process_id,
            event.url,
            event.title,
            event.browser,
            json.dumps(event.metadata) if event.metadata else None,
            event.confidence,
        ])
    
    def insert_events(self, events: List[Event]) -> int:
        """
        Insert multiple events into the database.
        
        Args:
            events: List of events to insert
            
        Returns:
            Number of events inserted
        """
        for event in events:
            try:
                self.insert_event(event)
            except Exception as e:
                self.logger.warning(f"Failed to insert event {event.id}: {e}")
        return len(events)
    
    def _row_to_event(self, row: tuple) -> Event:
        """Convert a database row to an Event object."""
        # Parse metadata JSON
        metadata = {}
        if row[14]:
            try:
                metadata = json.loads(row[14])
            except json.JSONDecodeError:
                pass
        
        return Event(
            id=UUID(row[0]),
            event_type=EventType(row[1]),
            timestamp=row[2],
            source=row[3],
            subject=row[4],
            subject_secondary=row[5],
            description=row[6],
            repository=row[7],
            branch=row[8],
            process_name=row[9],
            process_id=row[10],
            url=row[11],
            title=row[12],
            browser=row[13],
            metadata=metadata,
            confidence=row[15] or 1.0,
        )
    
    def get_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[EventType]] = None,
        sources: Optional[List[str]] = None,
        limit: int = 1000
    ) -> List[Event]:
        """
        Query events within a time range.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            event_types: Optional filter by event types
            sources: Optional filter by sources
            limit: Maximum number of events to return
            
        Returns:
            List of matching events
        """
        query = "SELECT * FROM events WHERE timestamp >= ? AND timestamp <= ?"
        params: List[Any] = [start_time, end_time]
        
        if event_types:
            placeholders = ", ".join(["?" for _ in event_types])
            query += f" AND event_type IN ({placeholders})"
            params.extend([et.value for et in event_types])
        
        if sources:
            placeholders = ", ".join(["?" for _ in sources])
            query += f" AND source IN ({placeholders})"
            params.extend(sources)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        result = self._conn.execute(query, params)
        return [self._row_to_event(row) for row in result.fetchall()]
    
    def get_events_for_subject(
        self,
        subject: str,
        limit: int = 100
    ) -> List[Event]:
        """
        Query events related to a specific subject.
        
        Args:
            subject: Subject to search for (partial match)
            limit: Maximum number of events to return
            
        Returns:
            List of matching events
        """
        result = self._conn.execute("""
            SELECT * FROM events 
            WHERE subject LIKE ? OR subject_secondary LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, [f"%{subject}%", f"%{subject}%", limit])
        
        return [self._row_to_event(row) for row in result.fetchall()]
    
    def get_events_for_repository(
        self,
        repository: str,
        limit: int = 100
    ) -> List[Event]:
        """
        Query events related to a specific repository.
        
        Args:
            repository: Repository path
            limit: Maximum number of events to return
            
        Returns:
            List of matching events
        """
        result = self._conn.execute("""
            SELECT * FROM events 
            WHERE repository = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, [repository, limit])
        
        return [self._row_to_event(row) for row in result.fetchall()]
    
    def get_recent_events(
        self,
        minutes: int = 60,
        limit: int = 500
    ) -> List[Event]:
        """
        Get events from the last N minutes.
        
        Args:
            minutes: Number of minutes to look back
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        from datetime import timedelta
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)
        return self.get_events_in_range(start_time, end_time, limit=limit)
    
    def get_event_count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        Get the count of events in a time range.
        
        Args:
            start_time: Optional start time
            end_time: Optional end time
            
        Returns:
            Number of events
        """
        query = "SELECT COUNT(*) FROM events"
        params: List[Any] = []
        
        if start_time and end_time:
            query += " WHERE timestamp >= ? AND timestamp <= ?"
            params = [start_time, end_time]
        elif start_time:
            query += " WHERE timestamp >= ?"
            params = [start_time]
        elif end_time:
            query += " WHERE timestamp <= ?"
            params = [end_time]
        
        result = self._conn.execute(query, params)
        return result.fetchone()[0]
    
    def get_event_type_counts(self) -> Dict[str, int]:
        """
        Get counts of events by type.
        
        Returns:
            Dictionary mapping event types to counts
        """
        result = self._conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM events
            GROUP BY event_type
            ORDER BY count DESC
        """)
        
        return {row[0]: row[1] for row in result.fetchall()}
    
    def iter_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        batch_size: int = 1000
    ) -> Iterator[Event]:
        """
        Iterate over events in batches.
        
        Args:
            start_time: Optional start time
            end_time: Optional end time
            batch_size: Number of events per batch
            
        Yields:
            Event objects
        """
        query = "SELECT * FROM events"
        params: List[Any] = []
        
        if start_time and end_time:
            query += " WHERE timestamp >= ? AND timestamp <= ?"
            params = [start_time, end_time]
        elif start_time:
            query += " WHERE timestamp >= ?"
            params = [start_time]
        elif end_time:
            query += " WHERE timestamp <= ?"
            params = [end_time]
        
        query += " ORDER BY timestamp"
        
        offset = 0
        while True:
            batch_query = f"{query} LIMIT {batch_size} OFFSET {offset}"
            result = self._conn.execute(batch_query, params)
            rows = result.fetchall()
            
            if not rows:
                break
            
            for row in rows:
                yield self._row_to_event(row)
            
            offset += batch_size
    
    def vacuum(self) -> None:
        """Optimize the database by running VACUUM."""
        self._conn.execute("VACUUM")
        self.logger.info("Database vacuumed")
