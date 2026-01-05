"""
Tests for the event models.
"""

import pytest
from datetime import datetime, timedelta
from uuid import UUID

from deja_view.models import Event, EventType, ActivityWindow


class TestEvent:
    """Tests for the Event model."""
    
    def test_event_creation(self):
        """Test basic event creation.

        Verifies that an Event can be created with minimal required fields
        and that default values are properly set for optional fields.
        """
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        assert event.event_type == EventType.FILE_CREATE
        assert event.source == "test"
        assert event.subject == "/path/to/file.py"
        assert isinstance(event.id, UUID)
        assert isinstance(event.timestamp, datetime)
        assert event.confidence == 1.0
    
    def test_event_with_all_fields(self):
        """Test event creation with all fields.

        Verifies that an Event can be created with all optional fields
        including repository, branch, and metadata.
        """
        event = Event(
            event_type=EventType.GIT_COMMIT,
            source="git",
            subject="abc123",
            description="Commit message",
            repository="/path/to/repo",
            branch="main",
            metadata={"author": "test"},
        )
        
        assert event.repository == "/path/to/repo"
        assert event.branch == "main"
        assert event.metadata == {"author": "test"}
    
    def test_event_to_dict(self):
        """Test event serialization to dictionary.

        Verifies that an Event can be serialized to a dictionary format
        with properly formatted string representations for id and timestamp.
        """
        event = Event(
            event_type=EventType.FILE_MODIFY,
            source="filesystem",
            subject="/path/to/file.py",
        )
        
        data = event.to_dict()
        
        assert isinstance(data["id"], str)
        assert data["event_type"] == "file.modify"
        assert isinstance(data["timestamp"], str)
        assert data["source"] == "filesystem"
        assert data["subject"] == "/path/to/file.py"
    
    def test_event_from_dict(self):
        """Test event deserialization from dictionary.

        Verifies that an Event can be reconstructed from a dictionary
        representation with all fields properly parsed.
        """
        data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "event_type": "file.create",
            "timestamp": "2024-01-01T12:00:00",
            "source": "test",
            "subject": "/path/to/file.py",
            "confidence": 0.9,
        }
        
        event = Event.from_dict(data)
        
        assert str(event.id) == "12345678-1234-5678-1234-567812345678"
        assert event.event_type == EventType.FILE_CREATE
        assert event.source == "test"
        assert event.confidence == 0.9
    
    def test_event_equality(self):
        """Test event equality based on ID.

        Verifies that Event equality is determined by the unique ID,
        not by the event's content or other attributes.
        """
        event1 = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        event2 = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        # Different events have different IDs
        assert event1 != event2
        
        # Same event is equal to itself
        assert event1 == event1
    
    def test_event_hash(self):
        """Test event hashing for use in sets.

        Verifies that Events are hashable and can be used as elements
        in sets and as dictionary keys.
        """
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        event_set = {event}
        assert event in event_set
        assert len(event_set) == 1


class TestEventType:
    """Tests for EventType enum."""
    
    def test_all_event_types(self):
        """Test that all expected event types exist.

        Verifies that the EventType enum contains all expected event type
        values for file, git, process, shell, and browser events.
        """
        expected_types = [
            "file.create", "file.modify", "file.delete", "file.move",
            "git.commit", "git.branch_switch", "git.branch_create",
            "git.merge", "git.pull", "git.push",
            "process.start", "process.active", "process.end",
            "shell.command", "browser.visit",
        ]
        
        for type_value in expected_types:
            assert EventType(type_value) is not None


class TestActivityWindow:
    """Tests for the ActivityWindow model."""
    
    def test_window_creation(self):
        """Test basic window creation.

        Verifies that an ActivityWindow can be created with start and end times
        and that default values are properly set for event count and duration.
        """
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=10),
            end_time=now,
        )
        
        assert window.event_count == 0
        assert window.duration_seconds == 600.0
    
    def test_add_event(self):
        """Test adding events to a window.

        Verifies that events can be added to an ActivityWindow and that
        the window's time boundaries expand to include the event timestamp.
        """
        now = datetime.now()
        window = ActivityWindow(
            start_time=now,
            end_time=now,
        )
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
            timestamp=now - timedelta(minutes=5),
        )
        
        window.add_event(event)
        
        assert window.event_count == 1
        assert event in window.events
        # Window should expand to include event
        assert window.start_time == event.timestamp
    
    def test_window_overlap(self):
        """Test window overlap detection.

        Verifies that the overlaps method correctly identifies when two
        ActivityWindows have overlapping time ranges.
        """
        now = datetime.now()
        
        window1 = ActivityWindow(
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(minutes=10),
        )
        
        window2 = ActivityWindow(
            start_time=now - timedelta(minutes=20),
            end_time=now,
        )
        
        window3 = ActivityWindow(
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(minutes=5),
        )
        
        assert window1.overlaps(window2)  # Overlap
        assert not window1.overlaps(window3)  # No overlap
    
    def test_window_merge(self):
        """Test merging overlapping windows.

        Verifies that two overlapping ActivityWindows can be merged into
        a single window that spans both time ranges and contains all events.
        """
        now = datetime.now()
        
        event1 = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/file1.py",
        )
        event2 = Event(
            event_type=EventType.FILE_MODIFY,
            source="test",
            subject="/file2.py",
        )
        
        window1 = ActivityWindow(
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(minutes=10),
            events=[event1],
        )
        
        window2 = ActivityWindow(
            start_time=now - timedelta(minutes=20),
            end_time=now,
            events=[event2],
        )
        
        merged = window1.merge(window2)
        
        assert merged.start_time == window1.start_time
        assert merged.end_time == window2.end_time
        assert len(merged.events) == 2
