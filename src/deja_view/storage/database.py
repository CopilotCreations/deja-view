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
        """Connect to the database and initialize schema.
        
        Establishes a connection to the DuckDB database and creates
        the events table and indexes if they don't exist.
        """
        self._conn = duckdb.connect(str(self.database_path))
        self._initialize_schema()
        self.logger.info(f"Connected to database: {self.database_path}")
    
    def close(self) -> None:
        """Close the database connection.
        
        Safely closes the DuckDB connection if one is open.
        """
        if self._conn:
            self._conn.close()
            self._conn = None
            self.logger.info("Database connection closed")
    
    def _initialize_schema(self) -> None:
        """Create the events table if it doesn't exist.
        
        Creates the events table with all required columns and sets up
        indexes for timestamp, event_type, source, and subject columns.
        """
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
        """Insert a single event into the database.
        
        Args:
            event: The Event object to insert into the events table.
        
        Raises:
            duckdb.Error: If the insert operation fails.
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
        """Insert multiple events into the database.
        
        Args:
            events: List of Event objects to insert.
            
        Returns:
            The number of events that were attempted to be inserted.
            Note that individual insert failures are logged but do not
            prevent other events from being inserted.
        """
        for event in events:
            try:
                self.insert_event(event)
            except Exception as e:
                self.logger.warning(f"Failed to insert event {event.id}: {e}")
        return len(events)
    
    def _row_to_event(self, row: tuple) -> Event:
        """Convert a database row to an Event object.
        
        Args:
            row: A tuple containing the database row values in column order.
        
        Returns:
            An Event object populated with values from the database row.
        """
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
        """Query events within a time range.
        
        Args:
            start_time: Start of the time range (inclusive).
            end_time: End of the time range (inclusive).
            event_types: Optional list of EventType values to filter by.
            sources: Optional list of source names to filter by.
            limit: Maximum number of events to return. Defaults to 1000.
            
        Returns:
            A list of Event objects matching the criteria, ordered by
            timestamp descending (most recent first).
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
        """Query events related to a specific subject.
        
        Performs a partial match search on both subject and subject_secondary
        fields using SQL LIKE with wildcards.
        
        Args:
            subject: Subject string to search for (partial match supported).
            limit: Maximum number of events to return. Defaults to 100.
            
        Returns:
            A list of Event objects matching the subject, ordered by
            timestamp descending (most recent first).
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
        """Query events related to a specific repository.
        
        Args:
            repository: The exact repository path to match.
            limit: Maximum number of events to return. Defaults to 100.
            
        Returns:
            A list of Event objects for the repository, ordered by
            timestamp descending (most recent first).
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
        """Get events from the last N minutes.
        
        Args:
            minutes: Number of minutes to look back from now. Defaults to 60.
            limit: Maximum number of events to return. Defaults to 500.
            
        Returns:
            A list of Event objects from the specified time window,
            ordered by timestamp descending (most recent first).
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
        """Get the count of events in a time range.
        
        Args:
            start_time: Optional start of time range (inclusive).
                If not provided, no lower bound is applied.
            end_time: Optional end of time range (inclusive).
                If not provided, no upper bound is applied.
            
        Returns:
            The total number of events matching the time criteria.
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
        """Get counts of events by type.
        
        Returns:
            A dictionary mapping event type strings to their counts,
            ordered by count descending.
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
        """Iterate over events in batches.
        
        Provides memory-efficient iteration over large result sets by
        fetching events in batches.
        
        Args:
            start_time: Optional start of time range (inclusive).
            end_time: Optional end of time range (inclusive).
            batch_size: Number of events to fetch per database query.
                Defaults to 1000.
            
        Yields:
            Event objects ordered by timestamp ascending.
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
        """Optimize the database by running VACUUM.
        
        Reclaims unused space and optimizes the database file.
        """
        self._conn.execute("VACUUM")
        self.logger.info("Database vacuumed")
