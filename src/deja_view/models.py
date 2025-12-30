"""
Unified Event Model for Deja View.

Defines the normalized event schema used across all collectors.
All signals are converted to this unified format for storage and analysis.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events that can be collected."""
    
    # Filesystem events
    FILE_CREATE = "file.create"
    FILE_MODIFY = "file.modify"
    FILE_DELETE = "file.delete"
    FILE_MOVE = "file.move"
    
    # Git events
    GIT_COMMIT = "git.commit"
    GIT_BRANCH_SWITCH = "git.branch_switch"
    GIT_BRANCH_CREATE = "git.branch_create"
    GIT_MERGE = "git.merge"
    GIT_PULL = "git.pull"
    GIT_PUSH = "git.push"
    
    # Process events
    PROCESS_START = "process.start"
    PROCESS_ACTIVE = "process.active"
    PROCESS_END = "process.end"
    
    # Terminal events
    SHELL_COMMAND = "shell.command"
    
    # Browser events
    BROWSER_VISIT = "browser.visit"


class Event(BaseModel):
    """
    Unified event model representing a single activity observation.
    
    All collectors normalize their data into this format for consistent
    storage and analysis. Events are immutable once created.
    """
    
    # Unique identifier
    id: UUID = Field(default_factory=uuid4)
    
    # Event classification
    event_type: EventType
    
    # Timestamp of when the event occurred
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Source collector that generated this event
    source: str
    
    # Primary subject of the event (file path, URL, command, etc.)
    subject: str
    
    # Optional secondary subject (e.g., destination for move events)
    subject_secondary: Optional[str] = None
    
    # Human-readable description
    description: Optional[str] = None
    
    # Associated repository path (if applicable)
    repository: Optional[str] = None
    
    # Associated git branch (if applicable)
    branch: Optional[str] = None
    
    # Process name (if applicable)
    process_name: Optional[str] = None
    
    # Process ID (if applicable)
    process_id: Optional[int] = None
    
    # URL (for browser events)
    url: Optional[str] = None
    
    # Page title (for browser events)
    title: Optional[str] = None
    
    # Browser name (for browser events)
    browser: Optional[str] = None
    
    # Additional metadata as key-value pairs
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Confidence score (0.0 to 1.0) for inferred events
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for storage."""
        data = self.model_dump()
        data["id"] = str(self.id)
        data["event_type"] = self.event_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        if isinstance(data.get("id"), str):
            data["id"] = UUID(data["id"])
        if isinstance(data.get("event_type"), str):
            data["event_type"] = EventType(data["event_type"])
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
    
    def __hash__(self) -> int:
        """Allow events to be used in sets."""
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        """Check equality based on ID."""
        if isinstance(other, Event):
            return self.id == other.id
        return False


class ActivityWindow(BaseModel):
    """
    A time window containing grouped events.
    
    Used for activity inference to cluster related events
    and identify task boundaries.
    """
    
    # Window boundaries
    start_time: datetime
    end_time: datetime
    
    # Events in this window
    events: list[Event] = Field(default_factory=list)
    
    # Inferred task label
    task_label: Optional[str] = None
    
    # Confidence score for the task inference
    task_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Key subjects involved in this window
    key_subjects: list[str] = Field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        """Get the duration of this window in seconds."""
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def event_count(self) -> int:
        """Get the number of events in this window."""
        return len(self.events)
    
    def add_event(self, event: Event) -> None:
        """Add an event to this window."""
        self.events.append(event)
        # Expand window if needed
        if event.timestamp < self.start_time:
            self.start_time = event.timestamp
        if event.timestamp > self.end_time:
            self.end_time = event.timestamp
    
    def overlaps(self, other: "ActivityWindow") -> bool:
        """Check if this window overlaps with another."""
        return self.start_time <= other.end_time and self.end_time >= other.start_time
    
    def merge(self, other: "ActivityWindow") -> "ActivityWindow":
        """Merge two overlapping windows."""
        return ActivityWindow(
            start_time=min(self.start_time, other.start_time),
            end_time=max(self.end_time, other.end_time),
            events=self.events + other.events,
        )
