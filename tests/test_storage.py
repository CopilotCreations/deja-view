"""
Tests for the storage module.
"""

import pytest
from datetime import datetime, timedelta

from fortuna_prismatica.models import Event, EventType
from fortuna_prismatica.storage.database import EventDatabase


class TestEventDatabase:
    """Tests for the EventDatabase class."""
    
    @pytest.fixture
    def database(self, test_config):
        """Create a test database."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        yield db
        db.close()
    
    def test_database_connection(self, database):
        """Test database connection."""
        assert database._conn is not None
    
    def test_insert_event(self, database):
        """Test inserting a single event."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        database.insert_event(event)
        
        # Verify by querying
        events = database.get_recent_events(minutes=5)
        assert len(events) == 1
        assert events[0].subject == "/path/to/file.py"
    
    def test_insert_multiple_events(self, database, sample_events):
        """Test inserting multiple events."""
        count = database.insert_events(sample_events)
        
        assert count == len(sample_events)
        assert database.get_event_count() == len(sample_events)
    
    def test_get_events_in_range(self, database, sample_events):
        """Test querying events by time range."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        
        events = database.get_events_in_range(start, end)
        
        assert len(events) == len(sample_events)
    
    def test_get_events_by_type(self, database, sample_events):
        """Test filtering events by type."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        
        file_events = database.get_events_in_range(
            start, end,
            event_types=[EventType.FILE_CREATE, EventType.FILE_MODIFY]
        )
        
        assert len(file_events) == 2
    
    def test_get_events_for_subject(self, database, sample_events):
        """Test querying events by subject."""
        database.insert_events(sample_events)
        
        events = database.get_events_for_subject("file1.py")
        
        assert len(events) == 2  # CREATE and MODIFY
    
    def test_get_events_for_repository(self, database, sample_events):
        """Test querying events by repository."""
        database.insert_events(sample_events)
        
        events = database.get_events_for_repository("/path/to/repo")
        
        assert len(events) == 2  # FILE_MODIFY and GIT_COMMIT
    
    def test_get_event_type_counts(self, database, sample_events):
        """Test getting event type counts."""
        database.insert_events(sample_events)
        
        counts = database.get_event_type_counts()
        
        assert counts["file.create"] == 1
        assert counts["file.modify"] == 1
        assert counts["git.commit"] == 1
        assert counts["browser.visit"] == 1
    
    def test_iter_events(self, database, sample_events):
        """Test iterating over events."""
        database.insert_events(sample_events)
        
        count = 0
        for event in database.iter_events():
            count += 1
            assert isinstance(event, Event)
        
        assert count == len(sample_events)
    
    def test_event_metadata_persistence(self, database):
        """Test that metadata is preserved through storage."""
        event = Event(
            event_type=EventType.GIT_COMMIT,
            source="git",
            subject="abc123",
            metadata={"author": "test", "files_changed": 5},
        )
        
        database.insert_event(event)
        
        events = database.get_recent_events(minutes=5)
        assert events[0].metadata["author"] == "test"
        assert events[0].metadata["files_changed"] == 5
    
    def test_empty_database(self, database):
        """Test querying empty database."""
        events = database.get_recent_events()
        assert len(events) == 0
        
        count = database.get_event_count()
        assert count == 0
    
    def test_get_events_with_sources_filter(self, database, sample_events):
        """Test filtering events by source."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        
        events = database.get_events_in_range(start, end, sources=["test"])
        assert len(events) == len(sample_events)
    
    def test_get_event_count_with_time_range(self, database, sample_events):
        """Test getting event count with time filters."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        count = database.get_event_count(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1)
        )
        
        assert count == len(sample_events)
    
    def test_get_event_count_start_only(self, database, sample_events):
        """Test getting event count with start time only."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        count = database.get_event_count(start_time=now - timedelta(hours=2))
        
        assert count == len(sample_events)
    
    def test_get_event_count_end_only(self, database, sample_events):
        """Test getting event count with end time only."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        count = database.get_event_count(end_time=now + timedelta(hours=1))
        
        assert count == len(sample_events)
    
    def test_iter_events_with_time_range(self, database, sample_events):
        """Test iterating events with time range."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        count = 0
        for event in database.iter_events(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1)
        ):
            count += 1
        
        assert count == len(sample_events)
    
    def test_event_all_fields(self, database):
        """Test event with all fields populated."""
        event = Event(
            event_type=EventType.BROWSER_VISIT,
            source="browser",
            subject="https://example.com",
            subject_secondary="https://previous.com",
            description="Visited example.com",
            repository=None,
            branch=None,
            process_name="chrome",
            process_id=12345,
            url="https://example.com",
            title="Example Site",
            browser="chrome",
            metadata={"referer": "https://google.com"},
            confidence=0.95,
        )
        
        database.insert_event(event)
        
        events = database.get_recent_events(minutes=5)
        assert len(events) == 1
        assert events[0].url == "https://example.com"
        assert events[0].browser == "chrome"
        assert events[0].confidence == 0.95
