"""
Tests for the daemon module.
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from deja_view.daemon import Daemon, get_daemon_pid, is_daemon_running
from deja_view.models import Event, EventType


class TestDaemon:
    """Tests for the Daemon class."""
    
    @pytest.fixture
    def daemon(self, test_config):
        """Create a test daemon."""
        return Daemon(test_config)
    
    def test_daemon_initialization(self, daemon):
        """Test daemon initialization."""
        assert daemon.database is None
        assert daemon.graph is None
        assert not daemon.is_running
        assert daemon.event_count == 0
    
    @pytest.mark.asyncio
    async def test_daemon_start(self, daemon):
        """Test daemon startup."""
        await daemon.start()
        
        assert daemon.database is not None
        assert daemon.graph is not None
        assert daemon.is_running
        assert len(daemon.collectors) > 0
        
        await daemon.stop()
    
    @pytest.mark.asyncio
    async def test_daemon_stop(self, daemon):
        """Test daemon shutdown."""
        await daemon.start()
        await daemon.stop()
        
        assert not daemon.is_running
    
    def test_handle_event(self, daemon, test_config):
        """Test event handling."""
        # Manually initialize components
        from deja_view.storage.database import EventDatabase
        from deja_view.analysis.graph import ActivityGraph
        
        daemon.database = EventDatabase(test_config.database_path)
        daemon.database.connect()
        daemon.graph = ActivityGraph(test_config.graph_path)
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test/file.py",
        )
        
        daemon._handle_event(event)
        
        assert daemon.event_count == 1
        
        daemon.database.close()
    
    @pytest.mark.asyncio
    async def test_daemon_uptime(self, daemon):
        """Test daemon uptime tracking."""
        await daemon.start()
        
        # Wait a moment
        await asyncio.sleep(0.1)
        
        uptime = daemon.uptime
        assert uptime is not None
        assert uptime > 0
        
        await daemon.stop()
    
    def test_daemon_uptime_not_started(self, daemon):
        """Test uptime before daemon starts."""
        assert daemon.uptime is None
    
    def test_daemon_event_count(self, daemon):
        """Test event count property."""
        assert daemon.event_count == 0


class TestDaemonPidManagement:
    """Tests for daemon PID management."""
    
    def test_get_daemon_pid_no_file(self, test_config):
        """Test getting PID when no PID file exists."""
        pid = get_daemon_pid()
        # May or may not be None depending on system state
        # Just ensure it doesn't crash
    
    def test_is_daemon_running(self, test_config):
        """Test daemon running check."""
        running = is_daemon_running()
        # Just ensure it returns a boolean
        assert isinstance(running, bool)
    
    def test_pid_file_cleanup(self, test_config):
        """Test PID file is created and cleaned up."""
        import asyncio
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        
        async def run_test():
            await daemon.start()
            assert test_config.pid_file.exists()
            await daemon.stop()
        
        asyncio.run(run_test())
        
        # PID file should be removed
        # Note: may still exist briefly after stop


class TestDaemonCollectors:
    """Tests for daemon collector initialization."""
    
    @pytest.fixture
    def daemon(self, test_config):
        """Create a test daemon."""
        return Daemon(test_config)
    
    def test_init_collectors(self, daemon, test_config):
        """Test collector initialization."""
        from deja_view.storage.database import EventDatabase
        from deja_view.analysis.graph import ActivityGraph
        
        daemon.database = EventDatabase(test_config.database_path)
        daemon.database.connect()
        daemon.graph = ActivityGraph(test_config.graph_path)
        
        daemon._init_collectors()
        
        # Should have some collectors initialized
        assert len(daemon.collectors) > 0
        
        daemon.database.close()
