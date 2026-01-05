"""
Test configuration for Deja View.
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path

from deja_view.config import Config, set_config


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests.

    Yields:
        Path: The path to the temporary directory.

    Note:
        Cleanup is best-effort as Windows may have file locks.
    """
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    # Best-effort cleanup (Windows may have file locks)
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def test_config(temp_data_dir):
    """Create a test configuration.

    Args:
        temp_data_dir: Fixture providing a temporary data directory.

    Returns:
        Config: A configured Config instance for testing.
    """
    config = Config(
        data_dir=temp_data_dir,
        log_level="DEBUG",
        process_poll_interval=5,
        shell_history_poll_interval=10,
        browser_poll_interval=60,
        activity_window_minutes=5,
        watch_paths=[temp_data_dir],
    )
    set_config(config)
    return config


@pytest.fixture
def sample_events():
    """Create sample events for testing.

    Returns:
        list[Event]: A list of sample Event objects covering various event types
            including file operations, git commits, browser visits, shell commands,
            and process starts.
    """
    from datetime import datetime, timedelta
    from deja_view.models import Event, EventType
    
    base_time = datetime.now()
    
    return [
        Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file1.py",
            timestamp=base_time - timedelta(minutes=30),
            description="Created file1.py",
        ),
        Event(
            event_type=EventType.FILE_MODIFY,
            source="test",
            subject="/path/to/file1.py",
            timestamp=base_time - timedelta(minutes=25),
            description="Modified file1.py",
            repository="/path/to/repo",
        ),
        Event(
            event_type=EventType.GIT_COMMIT,
            source="test",
            subject="abc123",
            timestamp=base_time - timedelta(minutes=20),
            description="Commit: Add feature",
            repository="/path/to/repo",
            branch="main",
        ),
        Event(
            event_type=EventType.BROWSER_VISIT,
            source="test",
            subject="https://example.com/docs",
            timestamp=base_time - timedelta(minutes=15),
            description="Visited docs",
            url="https://example.com/docs",
            title="Documentation",
            browser="chrome",
        ),
        Event(
            event_type=EventType.SHELL_COMMAND,
            source="test",
            subject="git status",
            timestamp=base_time - timedelta(minutes=10),
            description="Ran git status",
        ),
        Event(
            event_type=EventType.PROCESS_START,
            source="test",
            subject="code",
            timestamp=base_time - timedelta(minutes=5),
            description="Started VS Code",
            process_name="code",
            process_id=12345,
        ),
    ]
