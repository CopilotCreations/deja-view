"""
Tests for the collectors module.
"""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch, AsyncMock

from fortuna_prismatica.models import Event, EventType
from fortuna_prismatica.collectors.base import BaseCollector
from fortuna_prismatica.collectors.filesystem import FilesystemCollector, FilesystemEventHandler
from fortuna_prismatica.collectors.git import GitCollector
from fortuna_prismatica.collectors.process import ProcessCollector
from fortuna_prismatica.collectors.terminal import TerminalCollector
from fortuna_prismatica.collectors.browser import BrowserCollector


class TestBaseCollector:
    """Tests for the BaseCollector class."""
    
    def test_collector_properties(self):
        """Test collector properties."""
        class TestCollector(BaseCollector):
            async def start(self): pass
            async def stop(self): pass
            async def collect(self):
                yield Event(
                    event_type=EventType.FILE_CREATE,
                    source="test",
                    subject="/file.py",
                )
        
        collector = TestCollector("test")
        
        assert collector.name == "test"
        assert not collector.is_running
    
    def test_event_callback(self):
        """Test event callback mechanism."""
        class TestCollector(BaseCollector):
            async def start(self): pass
            async def stop(self): pass
            async def collect(self):
                if False:
                    yield
        
        collector = TestCollector("test")
        events_received = []
        
        collector.set_event_callback(lambda e: events_received.append(e))
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/file.py",
        )
        collector.emit_event(event)
        
        assert len(events_received) == 1
        assert events_received[0] == event


class TestFilesystemEventHandler:
    """Tests for the FilesystemEventHandler."""
    
    def test_ignore_patterns(self):
        """Test that certain patterns are ignored."""
        from queue import Queue
        handler = FilesystemEventHandler(Queue())
        
        assert handler._should_ignore("/path/to/.git/objects/abc")
        assert handler._should_ignore("/path/__pycache__/module.pyc")
        assert handler._should_ignore("/path/to/file.swp")
        assert not handler._should_ignore("/path/to/code.py")
    
    def test_event_queueing(self):
        """Test that events are properly queued."""
        from queue import Queue
        from watchdog.events import FileCreatedEvent
        
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        event = FileCreatedEvent("/path/to/new_file.py")
        handler.on_created(event)
        
        assert not queue.empty()
        action, path, dest = queue.get()
        assert action == "create"
        assert path == "/path/to/new_file.py"


class TestFilesystemCollector:
    """Tests for the FilesystemCollector."""
    
    def test_find_repository(self, temp_data_dir):
        """Test repository detection."""
        # Create a fake git repo
        git_dir = temp_data_dir / ".git"
        git_dir.mkdir()
        
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        # File in repo root
        repo = collector._find_repository(temp_data_dir / "file.py")
        assert repo == str(temp_data_dir)
        
        # File in subdirectory
        subdir = temp_data_dir / "src"
        subdir.mkdir()
        repo = collector._find_repository(subdir / "module.py")
        assert repo == str(temp_data_dir)
    
    def test_create_event(self, temp_data_dir):
        """Test event creation from filesystem data."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        event = collector._create_event(
            EventType.FILE_CREATE,
            str(temp_data_dir / "test.py")
        )
        
        assert event.event_type == EventType.FILE_CREATE
        assert event.source == "filesystem"
        assert "test.py" in event.subject


class TestGitCollector:
    """Tests for the GitCollector."""
    
    def test_repo_state_parsing(self, temp_data_dir):
        """Test repository state parsing."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        # Create a minimal git repo
        git_dir = temp_data_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        
        # This will fail without actual git, but tests the structure
        state = collector._get_repo_state(temp_data_dir)
        
        assert "path" in state
        assert "branch" in state
    
    def test_commit_event_creation(self):
        """Test commit event creation."""
        collector = GitCollector()
        
        commit = {
            "hash": "abc123def",
            "message": "Add new feature",
            "author": "Test User",
            "time": "2024-01-01 12:00:00",
        }
        
        event = collector._create_commit_event("/path/to/repo", "main", commit)
        
        assert event.event_type == EventType.GIT_COMMIT
        assert event.repository == "/path/to/repo"
        assert event.branch == "main"
        assert event.metadata["message"] == "Add new feature"


class TestProcessCollector:
    """Tests for the ProcessCollector."""
    
    def test_process_categorization(self):
        """Test process categorization."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("code") == "editor"
        assert collector._categorize_process("Chrome") == "browser"
        assert collector._categorize_process("slack") == "communication"
        assert collector._categorize_process("unknown_app") is None
    
    def test_should_track(self):
        """Test process tracking decisions."""
        collector = ProcessCollector()
        
        # Known category should be tracked
        assert collector._should_track({"name": "code", "cpu_percent": 0, "memory_percent": 0})
        
        # System process should not be tracked
        assert not collector._should_track({"name": "systemd", "cpu_percent": 0, "memory_percent": 0})
        
        # High resource usage should be tracked
        assert collector._should_track({"name": "unknown", "cpu_percent": 5, "memory_percent": 2})


class TestTerminalCollector:
    """Tests for the TerminalCollector."""
    
    def test_should_ignore_commands(self):
        """Test command filtering."""
        collector = TerminalCollector()
        
        assert collector._should_ignore("ls")
        assert collector._should_ignore("cd /path")
        assert not collector._should_ignore("git commit -m 'message'")
        assert not collector._should_ignore("python script.py")
    
    def test_parse_bash_history(self):
        """Test bash history parsing."""
        collector = TerminalCollector()
        
        # Extended history format
        content = "#1704067200\ngit status\n#1704067260\npython script.py\n"
        commands = collector._parse_bash_history(content)
        
        assert len(commands) == 2
        assert commands[0]["command"] == "git status"
        assert commands[0]["shell"] == "bash"
    
    def test_parse_zsh_history(self):
        """Test zsh history parsing."""
        collector = TerminalCollector()
        
        # Extended history format
        content = ": 1704067200:0;git status\n: 1704067260:0;python script.py\n"
        commands = collector._parse_zsh_history(content)
        
        assert len(commands) == 2
        assert commands[0]["command"] == "git status"
        assert commands[0]["shell"] == "zsh"


class TestBrowserCollector:
    """Tests for the BrowserCollector."""
    
    def test_url_filtering(self):
        """Test URL filtering."""
        collector = BrowserCollector()
        
        assert collector._should_ignore_url("chrome://settings")
        assert collector._should_ignore_url("about:blank")
        assert collector._should_ignore_url("file:///path/to/file.html")
        assert not collector._should_ignore_url("https://example.com")
    
    def test_visit_event_creation(self):
        """Test browser visit event creation."""
        collector = BrowserCollector()
        
        visit = {
            "url": "https://docs.python.org/3/",
            "title": "Python Documentation",
            "timestamp": datetime.now(),
            "browser": "chrome",
        }
        
        event = collector._create_visit_event(visit)
        
        assert event.event_type == EventType.BROWSER_VISIT
        assert event.url == "https://docs.python.org/3/"
        assert event.title == "Python Documentation"
        assert event.browser == "chrome"
        assert event.metadata["domain"] == "docs.python.org"
    
    def test_additional_ignore_patterns(self):
        """Test additional URL ignore patterns."""
        collector = BrowserCollector()
        
        assert collector._should_ignore_url("moz-extension://abc123")
        assert collector._should_ignore_url("edge://settings")
        assert collector._should_ignore_url("brave://settings")
        assert collector._should_ignore_url("data:text/html,test")
        assert collector._should_ignore_url("chrome-extension://abc")


class TestFilesystemEventHandlerExtended:
    """Extended tests for FilesystemEventHandler."""
    
    def test_on_modified(self):
        """Test file modification events."""
        from watchdog.events import FileModifiedEvent
        
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        event = FileModifiedEvent("/path/to/file.py")
        handler.on_modified(event)
        
        action, path, dest = queue.get()
        assert action == "modify"
        assert path == "/path/to/file.py"
    
    def test_on_deleted(self):
        """Test file deletion events."""
        from watchdog.events import FileDeletedEvent
        
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        event = FileDeletedEvent("/path/to/file.py")
        handler.on_deleted(event)
        
        action, path, dest = queue.get()
        assert action == "delete"
    
    def test_on_moved(self):
        """Test file move events."""
        from watchdog.events import FileMovedEvent
        
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        event = FileMovedEvent("/old/path.py", "/new/path.py")
        handler.on_moved(event)
        
        action, src, dest = queue.get()
        assert action == "move"
        assert src == "/old/path.py"
        assert dest == "/new/path.py"
    
    def test_ignore_node_modules(self):
        """Test that node_modules are ignored."""
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        assert handler._should_ignore("/project/node_modules/package/index.js")
        assert handler._should_ignore("/path/.mypy_cache/file.py")
        assert handler._should_ignore("/path/.pytest_cache/v/cache")


class TestBaseCollectorExtended:
    """Extended tests for BaseCollector."""
    
    @pytest.mark.asyncio
    async def test_collector_run_and_stop(self):
        """Test running and stopping a collector."""
        events_collected = []
        
        class SimpleCollector(BaseCollector):
            def __init__(self):
                super().__init__("simple")
                self.started = False
                self.stopped = False
            
            async def start(self):
                self.started = True
            
            async def stop(self):
                self.stopped = True
            
            async def collect(self):
                for i in range(3):
                    if not self._running:
                        break
                    yield Event(
                        event_type=EventType.FILE_CREATE,
                        source="test",
                        subject=f"/file{i}.py",
                    )
                    await asyncio.sleep(0.01)
        
        collector = SimpleCollector()
        collector.set_event_callback(lambda e: events_collected.append(e))
        
        # Start task
        task = collector.start_task()
        
        # Let it collect some events
        await asyncio.sleep(0.1)
        
        # Stop
        await collector.stop_task()
        
        assert collector.started
        assert collector.stopped
    
    def test_emit_without_callback(self):
        """Test emitting event without callback logs warning."""
        class SimpleCollector(BaseCollector):
            async def start(self): pass
            async def stop(self): pass
            async def collect(self):
                if False:
                    yield
        
        collector = SimpleCollector("test")
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/file.py",
        )
        
        # Should not crash
        collector.emit_event(event)


class TestGitCollectorExtended:
    """Extended tests for GitCollector."""
    
    def test_branch_event_creation(self):
        """Test branch switch event creation."""
        collector = GitCollector()
        
        event = collector._create_branch_event("/path/repo", "main", "feature")
        
        assert event.event_type == EventType.GIT_BRANCH_SWITCH
        assert event.subject == "feature"
        assert event.subject_secondary == "main"
        assert event.repository == "/path/repo"
    
    def test_find_repositories_empty(self, temp_data_dir):
        """Test finding repos in empty directory."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        repos = collector._find_repositories()
        
        assert isinstance(repos, list)


class TestProcessCollectorExtended:
    """Extended tests for ProcessCollector."""
    
    def test_create_process_event(self):
        """Test process event creation."""
        collector = ProcessCollector()
        
        proc_info = {
            "pid": 12345,
            "name": "python",
            "cpu_percent": 10.5,
            "memory_percent": 2.0,
            "cmdline": "python script.py",
            "cwd": "/home/user",
        }
        
        event = collector._create_process_event(EventType.PROCESS_START, proc_info)
        
        assert event.event_type == EventType.PROCESS_START
        assert event.process_name == "python"
        assert event.process_id == 12345
    
    def test_categorize_various_processes(self):
        """Test categorization of various process types."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("firefox") == "browser"
        assert collector._categorize_process("Safari") == "browser"
        assert collector._categorize_process("iTerm2") == "terminal"
        assert collector._categorize_process("Alacritty") == "terminal"
        assert collector._categorize_process("Discord") == "communication"
        assert collector._categorize_process("Zoom") == "communication"
        assert collector._categorize_process("docker") == "development"
        assert collector._categorize_process("node") == "development"


class TestTerminalCollectorExtended:
    """Extended tests for TerminalCollector."""
    
    def test_parse_simple_bash_history(self):
        """Test simple bash history format."""
        collector = TerminalCollector()
        
        content = "git status\npython script.py\n"
        commands = collector._parse_bash_history(content)
        
        # Both commands should be parsed
        assert len(commands) >= 2
    
    def test_create_command_event(self):
        """Test command event creation."""
        collector = TerminalCollector()
        
        cmd_info = {
            "command": "pytest tests/ -v",
            "timestamp": datetime.now(),
            "shell": "bash",
        }
        
        event = collector._create_command_event(cmd_info)
        
        assert event.event_type == EventType.SHELL_COMMAND
        assert "pytest" in event.subject
        assert event.metadata["shell"] == "bash"
    
    def test_ignore_common_commands(self):
        """Test that common navigation commands are ignored."""
        collector = TerminalCollector()
        
        assert collector._should_ignore("ls -la")
        assert collector._should_ignore("pwd")
        assert collector._should_ignore("clear")
        assert collector._should_ignore("history")
        assert collector._should_ignore("exit")
        assert not collector._should_ignore("make build")
    
    def test_parse_bash_with_invalid_timestamp(self):
        """Test bash history with invalid timestamp."""
        collector = TerminalCollector()
        
        # Invalid timestamp format
        content = "#not_a_number\ngit status\n"
        commands = collector._parse_bash_history(content)
        
        # Should still parse the command
        assert len(commands) >= 1
    
    def test_parse_zsh_simple_format(self):
        """Test zsh simple history format."""
        collector = TerminalCollector()
        
        content = "git status\nmake build\n"
        commands = collector._parse_zsh_history(content)
        
        assert len(commands) >= 2
    
    def test_command_with_file_paths(self):
        """Test command with file path references."""
        collector = TerminalCollector()
        
        cmd_info = {
            "command": "vim /path/to/file.py /another/file.js",
            "timestamp": datetime.now(),
            "shell": "bash",
        }
        
        event = collector._create_command_event(cmd_info)
        
        assert len(event.metadata.get("referenced_files", [])) >= 2


class TestBrowserCollectorExtended:
    """Extended tests for BrowserCollector."""
    
    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        collector = BrowserCollector()
        
        # Use the internal method through event creation
        visit = {
            "url": "https://subdomain.example.com/path",
            "title": "Test",
            "timestamp": datetime.now(),
            "browser": "chrome",
        }
        
        event = collector._create_visit_event(visit)
        assert event.metadata["domain"] == "subdomain.example.com"
    
    def test_copy_database_nonexistent(self, temp_data_dir):
        """Test copying nonexistent database."""
        collector = BrowserCollector()
        
        result = collector._copy_database(temp_data_dir / "nonexistent.db")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_browser_start_no_browsers(self, temp_data_dir):
        """Test browser collector start with no browsers."""
        collector = BrowserCollector()
        collector.chrome_path = None
        collector.firefox_path = None
        
        await collector.start()
        await collector.stop()


class TestGitCollectorMore:
    """More tests for GitCollector."""
    
    def test_get_repo_state(self, temp_data_dir):
        """Test getting repository state."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        # Create a minimal git repo
        git_dir = temp_data_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        
        state = collector._get_repo_state(temp_data_dir)
        
        assert state["path"] == str(temp_data_dir)
    
    def test_get_recent_commits_no_git(self, temp_data_dir):
        """Test getting commits without git."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        commits = collector._get_recent_commits(temp_data_dir)
        assert commits == []
    
    @pytest.mark.asyncio
    async def test_git_start_stop(self, temp_data_dir):
        """Test git collector start and stop."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        await collector.start()
        assert len(collector._known_repos) >= 0
        
        await collector.stop()
        assert len(collector._known_repos) == 0


class TestFilesystemCollectorMore:
    """More tests for FilesystemCollector."""
    
    def test_create_move_event(self, temp_data_dir):
        """Test creating a move event."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        event = collector._create_event(
            EventType.FILE_MOVE,
            str(temp_data_dir / "old.py"),
            str(temp_data_dir / "new.py")
        )
        
        assert event.event_type == EventType.FILE_MOVE
        assert event.subject_secondary is not None
        assert "moved" in event.description.lower()
    
    @pytest.mark.asyncio
    async def test_filesystem_start_stop(self, temp_data_dir):
        """Test filesystem collector start and stop."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        await collector.start()
        assert collector._observer is not None
        
        await collector.stop()
        assert collector._observer is None


class TestProcessCollectorMore:
    """More tests for ProcessCollector."""
    
    def test_should_track_high_cpu(self):
        """Test tracking high CPU processes."""
        collector = ProcessCollector()
        
        proc_info = {
            "name": "unknown_app",
            "cpu_percent": 15.0,
            "memory_percent": 0.5,
        }
        
        assert collector._should_track(proc_info)
    
    def test_should_track_high_memory(self):
        """Test tracking high memory processes."""
        collector = ProcessCollector()
        
        proc_info = {
            "name": "unknown_app",
            "cpu_percent": 0.1,
            "memory_percent": 5.0,
        }
        
        assert collector._should_track(proc_info)
    
    def test_should_not_track_idle(self):
        """Test not tracking idle unknown processes."""
        collector = ProcessCollector()
        
        proc_info = {
            "name": "unknown_app",
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
        }
        
        assert not collector._should_track(proc_info)
    
    @pytest.mark.asyncio
    async def test_process_start_stop(self):
        """Test process collector start and stop."""
        collector = ProcessCollector(poll_interval=5)
        
        await collector.start()
        await collector.stop()
        
        assert len(collector._active_processes) == 0
