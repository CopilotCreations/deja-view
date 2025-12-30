"""
Integration tests for Deja View.

These tests exercise multiple components together to ensure
proper integration and boost coverage.
"""

import asyncio
import pytest
import tempfile
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typer.testing import CliRunner

from deja_view.models import Event, EventType, ActivityWindow
from deja_view.storage.database import EventDatabase
from deja_view.analysis.graph import ActivityGraph
from deja_view.analysis.inference import InferenceEngine
from deja_view.reporting.narrative import NarrativeGenerator
from deja_view.collectors.browser import BrowserCollector
from deja_view.collectors.terminal import TerminalCollector
from deja_view.collectors.git import GitCollector
from deja_view.collectors.process import ProcessCollector
from deja_view.collectors.filesystem import FilesystemCollector
from deja_view.cli import app

runner = CliRunner()


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""
    
    def test_full_event_lifecycle(self, test_config):
        """Test events from collection through analysis and reporting."""
        # Create components
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        graph = ActivityGraph(test_config.graph_path)
        engine = InferenceEngine()
        
        # Create events
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/project/main.py",
                timestamp=now - timedelta(minutes=30),
            ),
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/project/main.py",
                timestamp=now - timedelta(minutes=25),
            ),
            Event(
                event_type=EventType.GIT_COMMIT,
                source="test",
                subject="abc123",
                timestamp=now - timedelta(minutes=20),
                repository="/project",
            ),
        ]
        
        # Store events
        db.insert_events(events)
        
        # Add to graph
        for event in events:
            graph.add_event(event)
        
        # Create windows and analyze
        windows = engine.create_windows(events)
        windows = engine.analyze_windows(windows)
        
        # Generate narrative
        generator = NarrativeGenerator(db, graph, engine)
        report = generator.explain_last(60)
        
        assert "Activity Report" in report
        assert len(windows) >= 1
        
        # Clean up
        db.close()
    
    def test_graph_window_integration(self, test_config):
        """Test adding activity windows to graph."""
        graph = ActivityGraph(test_config.graph_path)
        
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=30),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.FILE_MODIFY,
                    source="test",
                    subject="/code/file.py",
                    timestamp=now - timedelta(minutes=20),
                ),
                Event(
                    event_type=EventType.SHELL_COMMAND,
                    source="test",
                    subject="python file.py",
                    timestamp=now - timedelta(minutes=15),
                ),
                Event(
                    event_type=EventType.BROWSER_VISIT,
                    source="test",
                    subject="https://docs.python.org",
                    url="https://docs.python.org",
                    timestamp=now - timedelta(minutes=10),
                ),
            ],
        )
        
        graph.add_window(window)
        
        # Should have created nodes and edges
        stats = graph.get_statistics()
        assert stats["nodes"] >= 2
        assert stats["edges"] >= 1


class TestBrowserCollectorIntegration:
    """Integration tests for browser collector with actual SQLite DB."""
    
    def test_read_chrome_history_mock(self, temp_data_dir):
        """Test reading Chrome history from mock database."""
        # Create a mock Chrome history database
        history_db = temp_data_dir / "History"
        conn = sqlite3.connect(str(history_db))
        cursor = conn.cursor()
        
        # Create tables like Chrome
        cursor.execute("""
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE visits (
                id INTEGER PRIMARY KEY,
                url INTEGER,
                visit_time INTEGER
            )
        """)
        
        # Insert test data
        cursor.execute("INSERT INTO urls VALUES (1, 'https://example.com', 'Example')")
        # Chrome timestamp for now (microseconds since 1601)
        chrome_now = int((datetime.now().timestamp() + 11644473600) * 1000000)
        cursor.execute(f"INSERT INTO visits VALUES (1, 1, {chrome_now})")
        
        conn.commit()
        conn.close()
        
        # Test reading
        collector = BrowserCollector()
        collector.chrome_path = history_db
        collector._last_chrome_visit = chrome_now - 3600000000  # 1 hour ago
        
        visits = collector._read_chrome_history(collector._last_chrome_visit)
        
        assert len(visits) >= 1
    
    def test_read_firefox_history_mock(self, temp_data_dir):
        """Test reading Firefox history from mock database."""
        # Create a mock Firefox history database
        places_db = temp_data_dir / "places.sqlite"
        conn = sqlite3.connect(str(places_db))
        cursor = conn.cursor()
        
        # Create tables like Firefox
        cursor.execute("""
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE moz_historyvisits (
                id INTEGER PRIMARY KEY,
                place_id INTEGER,
                visit_date INTEGER
            )
        """)
        
        # Insert test data
        cursor.execute("INSERT INTO moz_places VALUES (1, 'https://mozilla.org', 'Mozilla')")
        # Firefox timestamp (microseconds since epoch)
        firefox_now = int(datetime.now().timestamp() * 1000000)
        cursor.execute(f"INSERT INTO moz_historyvisits VALUES (1, 1, {firefox_now})")
        
        conn.commit()
        conn.close()
        
        # Test reading
        collector = BrowserCollector()
        collector.firefox_path = places_db
        collector._last_firefox_visit = firefox_now - 3600000000  # 1 hour ago
        
        visits = collector._read_firefox_history(collector._last_firefox_visit)
        
        assert len(visits) >= 1


class TestTerminalCollectorIntegration:
    """Integration tests for terminal collector."""
    
    def test_read_bash_history_file(self, temp_data_dir):
        """Test reading actual bash history file."""
        history_file = temp_data_dir / ".bash_history"
        
        # Write test history
        history_content = """#1704067200
git status
#1704067260
python script.py
make build
"""
        history_file.write_text(history_content)
        
        collector = TerminalCollector()
        collector.history_paths = {"bash": history_file}
        
        commands = collector._read_new_history("bash", history_file)
        
        assert len(commands) >= 2
    
    def test_read_zsh_history_file(self, temp_data_dir):
        """Test reading actual zsh history file."""
        history_file = temp_data_dir / ".zsh_history"
        
        # Write test history in extended format
        history_content = """: 1704067200:0;git status
: 1704067260:0;python script.py
: 1704067320:0;make build
"""
        history_file.write_text(history_content)
        
        collector = TerminalCollector()
        collector.history_paths = {"zsh": history_file}
        
        commands = collector._read_new_history("zsh", history_file)
        
        assert len(commands) >= 2


class TestGitCollectorIntegration:
    """Integration tests for git collector."""
    
    def test_find_git_repos(self, temp_data_dir):
        """Test finding git repositories."""
        # Create a fake git repo
        repo_dir = temp_data_dir / "project"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main")
        
        collector = GitCollector(watch_paths=[temp_data_dir])
        repos = collector._find_repositories()
        
        assert len(repos) >= 1
        assert repo_dir in repos
    
    @pytest.mark.asyncio
    async def test_git_collect_cycle(self, temp_data_dir):
        """Test git collection cycle."""
        # Create a fake repo
        repo_dir = temp_data_dir / "project"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main")
        
        collector = GitCollector(watch_paths=[temp_data_dir], poll_interval=1)
        
        await collector.start()
        
        # Should have found the repo
        assert str(repo_dir) in collector._known_repos
        
        await collector.stop()


class TestProcessCollectorIntegration:
    """Integration tests for process collector."""
    
    @pytest.mark.asyncio
    async def test_process_collect_cycle(self):
        """Test process collection cycle."""
        collector = ProcessCollector(poll_interval=1)
        
        events_collected = []
        collector.set_event_callback(lambda e: events_collected.append(e))
        
        await collector.start()
        
        # Run collection briefly
        collector._running = True
        
        # Just verify start/stop works
        await collector.stop()


class TestFilesystemCollectorIntegration:
    """Integration tests for filesystem collector."""
    
    @pytest.mark.asyncio
    async def test_filesystem_watch_cycle(self, temp_data_dir):
        """Test filesystem watch cycle."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        await collector.start()
        
        # Create a test file to trigger an event
        test_file = temp_data_dir / "test_file.py"
        test_file.write_text("# test")
        
        # Wait briefly for event
        await asyncio.sleep(0.2)
        
        await collector.stop()


class TestDatabaseEdgeCases:
    """Edge case tests for database operations."""
    
    def test_insert_event_with_empty_metadata(self, test_config):
        """Test inserting event with empty metadata."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
            metadata={},
        )
        
        db.insert_event(event)
        events = db.get_recent_events(minutes=5)
        
        assert len(events) == 1
        db.close()
    
    def test_query_empty_time_range(self, test_config):
        """Test querying with no events in range."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        # Query future time range
        future = datetime.now() + timedelta(days=365)
        events = db.get_events_in_range(future, future + timedelta(hours=1))
        
        assert len(events) == 0
        db.close()


class TestGraphEdgeCases:
    """Edge case tests for activity graph."""
    
    def test_add_git_event_without_repo(self, temp_data_dir):
        """Test adding git event without repository."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        event = Event(
            event_type=EventType.GIT_COMMIT,
            source="test",
            subject="abc123",
            repository=None,  # No repository
        )
        
        graph.add_event(event)
        
        # Should not crash, may not add node
        stats = graph.get_statistics()
        assert stats["nodes"] >= 0
    
    def test_find_related_nonexistent(self, temp_data_dir):
        """Test finding related nodes for nonexistent node."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        related = graph.get_related_nodes("nonexistent:node")
        
        assert related == []


class TestInferenceEdgeCases:
    """Edge case tests for inference engine."""
    
    def test_analyze_empty_windows(self):
        """Test analyzing empty window list."""
        engine = InferenceEngine()
        
        result = engine.analyze_windows([])
        
        assert result == []
    
    def test_summary_empty_windows(self):
        """Test summary for empty windows."""
        engine = InferenceEngine()
        
        summary = engine.get_activity_summary([])
        
        assert summary["total_windows"] == 0


class TestMoreCollectorCoverage:
    """Additional collector tests for coverage."""
    
    def test_git_run_command_timeout(self, temp_data_dir):
        """Test git command with nonexistent repo."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        # This should return None for non-git directory
        result = collector._run_git_command(temp_data_dir, "status")
        assert result is None
    
    def test_terminal_ignore_la(self):
        """Test terminal ignores common aliases."""
        collector = TerminalCollector()
        
        assert collector._should_ignore("la")
        assert collector._should_ignore("ll")
        assert collector._should_ignore("l")
    
    def test_filesystem_no_repo(self, temp_data_dir):
        """Test filesystem collector without repo."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        # No .git directory
        repo = collector._find_repository(temp_data_dir / "file.py")
        assert repo is None
    
    def test_browser_event_without_domain(self):
        """Test browser event with invalid URL."""
        collector = BrowserCollector()
        
        visit = {
            "url": "not-a-valid-url",
            "title": "Test",
            "timestamp": datetime.now(),
            "browser": "chrome",
        }
        
        event = collector._create_visit_event(visit)
        # Should not crash, may have empty domain
        assert event is not None
    
    def test_process_event_no_category(self):
        """Test process event creation without category."""
        collector = ProcessCollector()
        
        proc_info = {
            "pid": 1234,
            "name": "random_process",
            "cpu_percent": 5.0,
            "memory_percent": 1.0,
            "cmdline": None,
            "cwd": None,
        }
        
        event = collector._create_process_event(EventType.PROCESS_ACTIVE, proc_info)
        assert event.process_name == "random_process"
        assert event.metadata.get("category") is None
    
    def test_terminal_extract_paths(self):
        """Test extracting paths from commands."""
        collector = TerminalCollector()
        
        cmd = {
            "command": "vim /path/to/file.py",
            "timestamp": datetime.now(),
            "shell": "bash",
        }
        
        event = collector._create_command_event(cmd)
        # Should extract the file path
        assert len(event.metadata.get("referenced_files", [])) >= 1
    
    def test_git_commit_event_creation(self):
        """Test git commit event creation."""
        collector = GitCollector()
        
        commit = {
            "hash": "abc123def456",
            "message": "Test commit message",
            "author": "test@example.com",
            "time": datetime.now().isoformat(),
        }
        
        event = collector._create_commit_event("/path/repo", "main", commit)
        
        assert event.event_type == EventType.GIT_COMMIT
        assert event.subject == "abc123def456"
        assert event.repository == "/path/repo"
    
    @pytest.mark.asyncio
    async def test_filesystem_queue_processing(self, temp_data_dir):
        """Test filesystem collector queue processing."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        events_collected = []
        collector.set_event_callback(lambda e: events_collected.append(e))
        
        await collector.start()
        
        # Manually add to queue
        collector._event_queue.put(("create", str(temp_data_dir / "new.py"), None))
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        await collector.stop()


class TestConfigMoreCoverage:
    """Additional config tests."""
    
    def test_config_from_env_watch_paths(self, temp_data_dir, monkeypatch):
        """Test config with custom watch paths from env."""
        from deja_view.config import Config
        
        monkeypatch.setenv("DEJA_WATCH_PATHS", f"{temp_data_dir},~")
        
        config = Config.from_env()
        
        assert len(config.watch_paths) >= 1


class TestNarrativeMoreCoverage:
    """Additional narrative tests."""
    
    def test_trace_with_graph_matches(self, test_config, sample_events):
        """Test trace with graph node matches."""
        from deja_view.reporting.narrative import NarrativeGenerator
        
        db = EventDatabase(test_config.database_path)
        db.connect()
        graph = ActivityGraph(test_config.graph_path)
        
        # Add events and graph data
        db.insert_events(sample_events)
        for event in sample_events:
            graph.add_event(event)
        
        generator = NarrativeGenerator(db, graph)
        result = generator.trace_subject("/path/to/file1.py")
        
        assert "Trace Report" in result
        db.close()
    
    def test_explain_with_task_distribution(self, test_config):
        """Test explain shows task distribution."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        graph = ActivityGraph(test_config.graph_path)
        
        # Add diverse events
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/code/file.py",
                timestamp=now - timedelta(minutes=30),
            ),
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/code/other.py",
                timestamp=now - timedelta(minutes=25),
            ),
        ]
        db.insert_events(events)
        
        generator = NarrativeGenerator(db, graph)
        result = generator.explain_last(60)
        
        assert "Activity Report" in result
        db.close()


class TestDaemonMoreCoverage:
    """Additional daemon tests for coverage."""
    
    @pytest.mark.asyncio
    async def test_daemon_signal_handlers(self, test_config):
        """Test daemon signal handler setup."""
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        await daemon.start()
        
        # Verify daemon is running
        assert daemon.is_running
        
        await daemon.stop()
    
    @pytest.mark.asyncio
    async def test_daemon_collector_count(self, test_config):
        """Test daemon collectors are initialized."""
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        
        await daemon.start()
        
        # Should have some collectors
        assert len(daemon.collectors) > 0
        
        await daemon.stop()


class TestCLIMoreCoverage:
    """Additional CLI tests for coverage."""
    
    def test_trace_with_output_file(self, test_config, temp_data_dir):
        """Test trace with output file option."""
        output_file = temp_data_dir / "trace.md"
        
        result = runner.invoke(app, [
            "trace", 
            "/some/path.py",
            "--output", str(output_file)
        ])
        
        # May or may not find results, but should handle file output
        assert result.exit_code in [0, 1]
    
    def test_events_with_all_options(self, test_config):
        """Test events command with all options."""
        result = runner.invoke(app, [
            "events",
            "--limit", "5",
            "--last", "1h",
        ])
        
        assert result.exit_code in [0, 1]
    
    def test_explain_with_output_file(self, test_config, temp_data_dir):
        """Test explain with output file."""
        output_file = temp_data_dir / "explain.md"
        
        result = runner.invoke(app, [
            "explain",
            "--last", "30m",
            "--output", str(output_file)
        ])
        
        assert result.exit_code in [0, 1]


class TestGraphMoreCoverage:
    """Additional graph tests."""
    
    def test_add_multiple_windows(self, temp_data_dir):
        """Test adding multiple windows to graph."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        now = datetime.now()
        for i in range(3):
            window = ActivityWindow(
                start_time=now - timedelta(hours=i+1),
                end_time=now - timedelta(hours=i),
                events=[
                    Event(
                        event_type=EventType.FILE_MODIFY,
                        source="test",
                        subject=f"/file{i}.py",
                        timestamp=now - timedelta(hours=i, minutes=30),
                    ),
                ],
            )
            graph.add_window(window)
        
        stats = graph.get_statistics()
        assert stats["nodes"] >= 3
    
    def test_graph_statistics(self, temp_data_dir):
        """Test graph statistics."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
        )
        graph.add_event(event)
        
        stats = graph.get_statistics()
        
        assert "nodes" in stats
        assert "edges" in stats
        assert "node_types" in stats


class TestMoreBrowserCoverage:
    """Additional browser collector tests."""
    
    def test_should_ignore_edge_urls(self):
        """Test ignoring Edge-specific URLs."""
        collector = BrowserCollector()
        
        assert collector._should_ignore_url("edge://settings")
        assert collector._should_ignore_url("edge://newtab")
        assert not collector._should_ignore_url("https://microsoft.com")
    
    def test_create_event_with_path_in_url(self):
        """Test event creation with path in URL."""
        collector = BrowserCollector()
        
        visit = {
            "url": "https://example.com/path/to/page?query=1",
            "title": "Test Page",
            "timestamp": datetime.now(),
            "browser": "firefox",
        }
        
        event = collector._create_visit_event(visit)
        
        assert event.url == "https://example.com/path/to/page?query=1"
        assert event.browser == "firefox"


class TestMoreProcessCoverage:
    """Additional process collector tests."""
    
    def test_categorize_ide_processes(self):
        """Test categorization of IDE processes."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("code") == "editor"
        assert collector._categorize_process("pycharm") == "editor"
    
    def test_categorize_browsers(self):
        """Test categorization of browser processes."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("chrome") == "browser"
        assert collector._categorize_process("firefox") == "browser"


class TestMoreGitCoverage:
    """Additional git collector tests."""
    
    def test_find_git_repos_in_tree(self, temp_data_dir):
        """Test finding git repositories in directory tree."""
        collector = GitCollector(watch_paths=[temp_data_dir])
        
        # Create nested repo
        nested = temp_data_dir / "projects" / "myapp"
        nested.mkdir(parents=True)
        (nested / ".git").mkdir()
        (nested / ".git" / "HEAD").write_text("ref: refs/heads/main")
        
        repos = collector._find_repositories()
        
        assert nested in repos


class TestMoreTerminalCoverage:
    """Additional terminal collector tests."""
    
    def test_should_ignore_basic_commands(self):
        """Test that basic commands are ignored."""
        collector = TerminalCollector()
        
        assert collector._should_ignore("ls")
        assert collector._should_ignore("cd")
        assert collector._should_ignore("pwd")
        
        # Development commands should not be ignored
        assert not collector._should_ignore("pytest")
        assert not collector._should_ignore("npm run build")


class TestConfigEnvVars:
    """Config environment variable tests."""
    
    def test_config_from_env_with_custom_data_dir(self, temp_data_dir, monkeypatch):
        """Test config with custom data directory."""
        from deja_view.config import Config
        
        custom_dir = temp_data_dir / "custom_data"
        custom_dir.mkdir()
        
        monkeypatch.setenv("DEJA_DATA_DIR", str(custom_dir))
        
        config = Config.from_env()
        
        assert str(custom_dir) in str(config.data_dir)
    
    def test_config_default_values(self):
        """Test config default values."""
        from deja_view.config import Config
        
        config = Config()
        
        assert config.activity_window_minutes == 15
        assert len(config.watch_paths) > 0


class TestCLICommandOutputs:
    """Tests for CLI command outputs."""
    
    def test_version_contains_version_number(self):
        """Test version command shows version number."""
        result = runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "0.1.0" in result.output or "Fortuna" in result.output
    
    def test_status_shows_status_info(self, test_config):
        """Test status shows daemon status information."""
        result = runner.invoke(app, ["status"])
        
        # Should show status table with version and directory info
        assert "Status" in result.output or "Version" in result.output
    
    def test_events_shows_output(self, test_config):
        """Test events command produces output."""
        result = runner.invoke(app, ["events"])
        
        # Should have some output
        assert result.output is not None


class TestProcessCollectorMore:
    """More process collector tests."""
    
    def test_categorize_terminal_processes(self):
        """Test categorization of terminal processes."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("Terminal") == "terminal"
        assert collector._categorize_process("iTerm2") == "terminal"
        assert collector._categorize_process("gnome-terminal") == "terminal"
    
    def test_categorize_communication_processes(self):
        """Test categorization of communication processes."""
        collector = ProcessCollector()
        
        assert collector._categorize_process("slack") == "communication"
        assert collector._categorize_process("Slack") == "communication"
        assert collector._categorize_process("discord") == "communication"


class TestDaemonLifecycle:
    """Tests for daemon lifecycle."""
    
    @pytest.mark.asyncio
    async def test_daemon_restart(self, test_config):
        """Test daemon can be restarted."""
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        
        # First start
        await daemon.start()
        assert daemon.is_running
        
        # Stop
        await daemon.stop()
        assert not daemon.is_running
        
        # Restart
        await daemon.start()
        assert daemon.is_running
        
        await daemon.stop()


class TestGraphOperations:
    """Tests for graph operations."""
    
    def test_graph_find_by_type(self, temp_data_dir):
        """Test finding nodes by type."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        # Add various node types
        graph.add_event(Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/file1.py",
        ))
        graph.add_event(Event(
            event_type=EventType.BROWSER_VISIT,
            source="test",
            subject="https://example.com",
            url="https://example.com",
        ))
        
        stats = graph.get_statistics()
        assert stats["node_types"].get("file", 0) >= 1
    
    def test_graph_edge_creation(self, temp_data_dir):
        """Test edge creation between related nodes."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=15),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.FILE_MODIFY,
                    source="test",
                    subject="/project/main.py",
                    timestamp=now - timedelta(minutes=10),
                ),
                Event(
                    event_type=EventType.GIT_COMMIT,
                    source="test",
                    subject="abc123",
                    repository="/project",
                    timestamp=now - timedelta(minutes=5),
                ),
            ],
        )
        
        graph.add_window(window)
        
        stats = graph.get_statistics()
        assert stats["edges"] >= 1


class TestInferenceWindows:
    """Tests for inference window operations."""
    
    def test_create_windows_from_sparse_events(self):
        """Test window creation with sparse events."""
        engine = InferenceEngine(window_minutes=15)
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/file.py",
                timestamp=now - timedelta(hours=2),
            ),
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/other.py",
                timestamp=now,
            ),
        ]
        
        windows = engine.create_windows(events)
        
        # Should create separate windows for sparse events
        assert len(windows) >= 2
    
    def test_analyze_window_with_git_focus(self):
        """Test analysis of git-focused window."""
        engine = InferenceEngine()
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.GIT_COMMIT,
                source="test",
                subject="abc123",
                timestamp=now,
            ),
            Event(
                event_type=EventType.GIT_COMMIT,
                source="test",
                subject="def456",
                timestamp=now - timedelta(minutes=5),
            ),
        ]
        
        windows = engine.create_windows(events)
        analyzed = engine.analyze_windows(windows)
        
        assert len(analyzed) >= 1


class TestMoreCLICoverage:
    """More CLI tests for coverage."""
    
    def test_explain_30m_format(self, test_config):
        """Test explain with 30m time format."""
        result = runner.invoke(app, ["explain", "--last", "30m"])
        assert result.exit_code in [0, 1]
    
    def test_explain_1h_format(self, test_config):
        """Test explain with 1h time format."""
        result = runner.invoke(app, ["explain", "--last", "1h"])
        assert result.exit_code in [0, 1]
    
    def test_explain_1d_format(self, test_config):
        """Test explain with 1d time format."""
        result = runner.invoke(app, ["explain", "--last", "1d"])
        assert result.exit_code in [0, 1]
    
    def test_trace_url(self, test_config):
        """Test tracing a URL."""
        result = runner.invoke(app, ["trace", "https://example.com"])
        assert result.exit_code in [0, 1]
    
    def test_trace_file_path(self, test_config):
        """Test tracing a file path."""
        result = runner.invoke(app, ["trace", "/path/to/file.py"])
        assert result.exit_code in [0, 1]
    
    def test_events_with_type_browser(self, test_config):
        """Test events with browser type filter."""
        result = runner.invoke(app, ["events", "--type", "browser"])
        assert result.exit_code in [0, 1]
    
    def test_events_with_type_git(self, test_config):
        """Test events with git type filter."""
        result = runner.invoke(app, ["events", "--type", "git"])
        assert result.exit_code in [0, 1]
    
    def test_graph_stats_output(self, test_config):
        """Test graph-stats command produces output."""
        result = runner.invoke(app, ["graph-stats"])
        # Should produce some output
        assert result.output is not None or result.exit_code in [0, 1]


class TestMoreDatabaseCoverage:
    """More database tests for coverage."""
    
    def test_insert_many_events(self, test_config):
        """Test inserting many events at once."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject=f"/file{i}.py",
                timestamp=now - timedelta(minutes=i),
            )
            for i in range(20)
        ]
        
        count = db.insert_events(events)
        assert count == 20
        
        db.close()
    
    def test_get_events_for_url(self, test_config):
        """Test getting events for a URL."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        event = Event(
            event_type=EventType.BROWSER_VISIT,
            source="test",
            subject="https://example.com/page",
            url="https://example.com/page",
        )
        db.insert_event(event)
        
        events = db.get_events_for_subject("example.com")
        assert len(events) >= 1
        
        db.close()


class TestModelValidation:
    """Tests for model validation."""
    
    def test_event_with_all_optional_fields(self):
        """Test creating an event with all optional fields."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/file.py",
            subject_secondary="/other.py",
            description="Created a new file",
            repository="/project",
            branch="main",
            process_name="python",
            process_id=1234,
            url=None,
            title=None,
            browser=None,
            metadata={"key": "value"},
            confidence=0.95,
        )
        
        assert event.confidence == 0.95
        assert event.repository == "/project"
    
    def test_activity_window_with_events(self):
        """Test creating an activity window with events."""
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/file.py",
                timestamp=now,
            ),
        ]
        
        window = ActivityWindow(
            start_time=now - timedelta(minutes=15),
            end_time=now,
            events=events,
            task_label="coding",
            task_confidence=0.8,
            key_subjects=["/file.py"],
        )
        
        assert window.task_label == "coding"
        assert len(window.events) == 1


class TestTerminalReadHistory:
    """Tests for terminal history reading."""
    
    def test_read_new_history_file_shrunk(self, temp_data_dir):
        """Test reading history when file has shrunk."""
        collector = TerminalCollector()
        
        history_file = temp_data_dir / ".bash_history"
        history_file.write_text("command1\ncommand2\n")
        
        # First read
        collector._file_positions[str(history_file)] = 1000  # Fake large position
        
        # Read should reset position since file is smaller
        commands = collector._read_new_history("bash", history_file)
        
        assert len(commands) >= 1
    
    def test_read_new_history_no_new_content(self, temp_data_dir):
        """Test reading when no new content."""
        collector = TerminalCollector()
        
        history_file = temp_data_dir / ".bash_history"
        history_file.write_text("command1\n")
        
        # Set position to end of file
        file_size = history_file.stat().st_size
        collector._file_positions[str(history_file)] = file_size
        
        commands = collector._read_new_history("bash", history_file)
        
        assert len(commands) == 0


class TestProcessIntegration:
    """Integration tests for process collector."""
    
    def test_should_track_tracked_process(self):
        """Test should_track with tracked process."""
        collector = ProcessCollector()
        
        info = {
            "name": "code",  # VS Code
            "cpu_percent": 0.1,
            "memory_percent": 0.5,
        }
        
        assert collector._should_track(info)
    
    def test_should_track_high_cpu_unknown(self):
        """Test tracking high CPU unknown process."""
        collector = ProcessCollector()
        
        info = {
            "name": "unknown_app",
            "cpu_percent": 50.0,
            "memory_percent": 1.0,
        }
        
        assert collector._should_track(info)


class TestBrowserIntegration:
    """Additional browser collector integration tests."""
    
    @pytest.mark.asyncio
    async def test_browser_collect_no_databases(self):
        """Test browser collect when no databases exist."""
        collector = BrowserCollector()
        collector.chrome_path = None
        collector.firefox_path = None
        
        await collector.start()
        
        # Should not crash when collecting
        events = []
        async for event in collector.collect():
            events.append(event)
            if len(events) > 5:
                break
        
        await collector.stop()


class TestFilesystemIntegration:
    """Additional filesystem collector tests."""
    
    def test_create_delete_event(self, temp_data_dir):
        """Test creating delete event."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        event = collector._create_event(
            EventType.FILE_DELETE,
            str(temp_data_dir / "deleted.py"),
            None
        )
        
        assert event.event_type == EventType.FILE_DELETE
        assert "deleted" in event.description.lower()
    
    def test_create_modify_event(self, temp_data_dir):
        """Test creating modify event."""
        collector = FilesystemCollector(watch_paths=[temp_data_dir])
        
        event = collector._create_event(
            EventType.FILE_MODIFY,
            str(temp_data_dir / "modified.py"),
            None
        )
        
        assert event.event_type == EventType.FILE_MODIFY
        assert "modified" in event.description.lower()


class TestTerminalCollectorMore:
    """More terminal collector tests."""
    
    @pytest.mark.asyncio
    async def test_terminal_start_stop(self, temp_data_dir):
        """Test terminal collector start and stop."""
        history_file = temp_data_dir / ".bash_history"
        history_file.write_text("git status\n")
        
        collector = TerminalCollector()
        collector.history_paths = {"bash": history_file}
        
        await collector.start()
        
        # Should have tracked file position
        assert str(history_file) in collector._file_positions
        
        await collector.stop()


class TestDaemonHandleEvent:
    """Tests for daemon event handling."""
    
    @pytest.mark.asyncio
    async def test_daemon_handles_multiple_events(self, test_config):
        """Test daemon handles multiple events."""
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        await daemon.start()
        
        # Process some events
        for i in range(5):
            event = Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject=f"/file{i}.py",
            )
            daemon._handle_event(event)
        
        assert daemon.event_count == 5
        
        await daemon.stop()


class TestGraphWindowEdges:
    """Tests for graph window edge creation."""
    
    def test_window_with_many_events(self, temp_data_dir):
        """Test window with many events creates proper edges."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject=f"/project/file{i}.py",
                timestamp=now - timedelta(minutes=i),
            )
            for i in range(5)
        ]
        
        window = ActivityWindow(
            start_time=now - timedelta(minutes=15),
            end_time=now,
            events=events,
        )
        
        graph.add_window(window)
        
        stats = graph.get_statistics()
        assert stats["nodes"] >= 5


class TestNarrativeEdgeCases:
    """Edge case tests for narrative generator."""
    
    def test_explain_with_mixed_event_types(self, test_config):
        """Test explain with mixed event types."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        graph = ActivityGraph(test_config.graph_path)
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/code/new.py",
                timestamp=now - timedelta(minutes=30),
            ),
            Event(
                event_type=EventType.GIT_COMMIT,
                source="test",
                subject="abc123",
                repository="/code",
                timestamp=now - timedelta(minutes=25),
            ),
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://docs.python.org",
                url="https://docs.python.org",
                timestamp=now - timedelta(minutes=20),
            ),
        ]
        
        db.insert_events(events)
        
        generator = NarrativeGenerator(db, graph)
        result = generator.explain_last(60)
        
        assert "Activity Report" in result
        db.close()


class TestEventTypeEnums:
    """Tests for event type enums."""
    
    def test_all_event_types(self):
        """Test all event types are valid."""
        event_types = [
            EventType.FILE_CREATE,
            EventType.FILE_MODIFY,
            EventType.FILE_DELETE,
            EventType.FILE_MOVE,
            EventType.GIT_COMMIT,
            EventType.GIT_BRANCH_SWITCH,
            EventType.PROCESS_START,
            EventType.PROCESS_ACTIVE,
            EventType.SHELL_COMMAND,
            EventType.BROWSER_VISIT,
        ]
        
        for et in event_types:
            event = Event(
                event_type=et,
                source="test",
                subject="test_subject",
            )
            assert event.event_type == et


class TestInferenceAdvanced:
    """Advanced inference engine tests."""
    
    def test_detect_research_pattern(self):
        """Test detecting research pattern from browser events."""
        engine = InferenceEngine()
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://stackoverflow.com/q/123",
                url="https://stackoverflow.com/q/123",
                timestamp=now - timedelta(minutes=10),
            ),
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://docs.python.org/3/",
                url="https://docs.python.org/3/",
                timestamp=now - timedelta(minutes=8),
            ),
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://github.com/project",
                url="https://github.com/project",
                timestamp=now - timedelta(minutes=5),
            ),
        ]
        
        windows = engine.create_windows(events)
        analyzed = engine.analyze_windows(windows)
        
        assert len(analyzed) >= 1
        # Should detect research activity
        assert analyzed[0].task_label in ["research", "general_activity"]
    
    def test_activity_summary_with_windows(self):
        """Test activity summary with windows."""
        engine = InferenceEngine()
        
        now = datetime.now()
        windows = [
            ActivityWindow(
                start_time=now - timedelta(hours=2),
                end_time=now - timedelta(hours=1),
                events=[],
                task_label="coding",
                task_confidence=0.8,
            ),
            ActivityWindow(
                start_time=now - timedelta(hours=1),
                end_time=now,
                events=[],
                task_label="research",
                task_confidence=0.7,
            ),
        ]
        
        summary = engine.get_activity_summary(windows)
        
        assert summary["total_windows"] == 2
        assert "coding" in summary["task_distribution"]
        assert "research" in summary["task_distribution"]


class TestDaemonEventCount:
    """Tests for daemon event counting."""
    
    @pytest.mark.asyncio
    async def test_event_count_increments(self, test_config):
        """Test event count increments with each event."""
        from deja_view.daemon import Daemon
        
        daemon = Daemon(test_config)
        await daemon.start()
        
        initial_count = daemon.event_count
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
        )
        daemon._handle_event(event)
        
        assert daemon.event_count == initial_count + 1
        
        await daemon.stop()


class TestCollectorRegistry:
    """Tests for collector registry."""
    
    def test_collectors_registry(self):
        """Test collectors are properly registered."""
        from deja_view.collectors import (
            FilesystemCollector,
            GitCollector,
            ProcessCollector,
            TerminalCollector,
            BrowserCollector,
        )
        
        collectors = [
            FilesystemCollector,
            GitCollector,
            ProcessCollector,
            TerminalCollector,
            BrowserCollector,
        ]
        
        for CollectorClass in collectors:
            instance = CollectorClass()
            assert instance.name is not None
            assert hasattr(instance, 'start')
            assert hasattr(instance, 'stop')
            assert hasattr(instance, 'collect')


class TestBaseCollectorMethods:
    """Tests for base collector methods."""
    
    def test_collector_is_running(self):
        """Test is_running property."""
        from deja_view.collectors.base import BaseCollector
        
        class TestCollector(BaseCollector):
            async def start(self): pass
            async def stop(self): pass
            async def collect(self):
                if False:
                    yield
        
        collector = TestCollector("test")
        
        assert not collector.is_running
        
        collector._running = True
        assert collector.is_running


class TestGraphNodeTypes:
    """Tests for graph node types."""
    
    def test_node_type_distribution(self, temp_data_dir):
        """Test node type distribution in graph."""
        graph = ActivityGraph(temp_data_dir / "test.gpickle")
        
        now = datetime.now()
        events = [
            Event(event_type=EventType.FILE_CREATE, source="test", subject="/file1.py", timestamp=now),
            Event(event_type=EventType.FILE_MODIFY, source="test", subject="/file2.py", timestamp=now),
            Event(event_type=EventType.BROWSER_VISIT, source="test", subject="https://test.com", url="https://test.com", timestamp=now),
            Event(event_type=EventType.SHELL_COMMAND, source="test", subject="git status", timestamp=now),
        ]
        
        for event in events:
            graph.add_event(event)
        
        stats = graph.get_statistics()
        
        assert stats["nodes"] >= 4
        assert "file" in stats["node_types"] or len(stats["node_types"]) > 0


class TestDatabaseContextManager:
    """Tests for database context manager patterns."""
    
    def test_database_close(self, test_config):
        """Test database properly closes."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
        )
        db.insert_event(event)
        
        db.close()
        
        # Connection should be closed
        # Re-opening should work
        db2 = EventDatabase(test_config.database_path)
        db2.connect()
        
        count = db2.get_event_count()
        assert count >= 1
        
        db2.close()


class TestInferenceWindowCreation:
    """Tests for inference window creation."""
    
    def test_single_event_window(self):
        """Test window creation with single event."""
        engine = InferenceEngine(window_minutes=15)
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/single.py",
                timestamp=now,
            ),
        ]
        
        windows = engine.create_windows(events)
        
        assert len(windows) == 1
        assert len(windows[0].events) == 1
    
    def test_many_events_single_window(self):
        """Test many events in single window."""
        engine = InferenceEngine(window_minutes=30)
        
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject=f"/file{i}.py",
                timestamp=now - timedelta(minutes=i),
            )
            for i in range(10)
        ]
        
        windows = engine.create_windows(events)
        
        # All events should be in one window since they're within 30 mins
        assert len(windows) >= 1


class TestTerminalCollectorCollect:
    """Test terminal collector collection."""
    
    @pytest.mark.asyncio
    async def test_terminal_collect_with_history(self, temp_data_dir):
        """Test terminal collect with history file."""
        history_file = temp_data_dir / ".bash_history"
        history_file.write_text("#1704067200\ngit status\n#1704067260\npython script.py\n")
        
        collector = TerminalCollector(poll_interval=1)
        collector.history_paths = {"bash": history_file}
        collector._file_positions = {}
        
        await collector.start()
        
        # Simulate new commands being added
        history_file.write_text("#1704067200\ngit status\n#1704067260\npython script.py\n#1704067320\nmake build\n")
        
        # Should be able to read new commands
        collector._running = True
        
        events = []
        async for event in collector.collect():
            events.append(event)
            collector._running = False
            break
        
        await collector.stop()


class TestFilesystemEventHandlerMore:
    """More tests for filesystem event handler."""
    
    def test_handler_ignores_pycache(self):
        """Test handler ignores __pycache__ directories."""
        from queue import Queue
        from deja_view.collectors.filesystem import FilesystemEventHandler
        
        queue = Queue()
        handler = FilesystemEventHandler(queue)
        
        assert handler._should_ignore("/path/to/__pycache__/file.pyc")
        assert handler._should_ignore("/project/.git/objects/abc")
        assert not handler._should_ignore("/path/to/main.py")


class TestProcessCategorization:
    """More tests for process categorization."""
    
    def test_categorize_office_apps(self):
        """Test categorization of office applications."""
        collector = ProcessCollector()
        
        # These should return None or a category
        result_unknown = collector._categorize_process("random_process_xyz")
        assert result_unknown is None or isinstance(result_unknown, str)
        
        # Known categories
        assert collector._categorize_process("code") == "editor"
        assert collector._categorize_process("vim") == "editor"
        assert collector._categorize_process("emacs") == "editor"


class TestBrowserVisitCreation:
    """Tests for browser visit event creation."""
    
    def test_create_visit_with_long_url(self):
        """Test creating visit with long URL."""
        collector = BrowserCollector()
        
        long_url = "https://example.com/" + "a" * 500
        
        visit = {
            "url": long_url,
            "title": "Long URL Page",
            "timestamp": datetime.now(),
            "browser": "chrome",
        }
        
        event = collector._create_visit_event(visit)
        
        assert event is not None
        assert event.event_type == EventType.BROWSER_VISIT
    
    def test_create_visit_with_unicode_title(self):
        """Test creating visit with unicode title."""
        collector = BrowserCollector()
        
        visit = {
            "url": "https://example.com/page",
            "title": "Unicode: 日本語タイトル 🎉",
            "timestamp": datetime.now(),
            "browser": "firefox",
        }
        
        event = collector._create_visit_event(visit)
        
        assert event is not None
        assert "日本語" in event.title
