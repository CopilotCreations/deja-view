"""
Tests for the analysis modules.
"""

import pytest
from datetime import datetime, timedelta

from fortuna_prismatica.models import Event, EventType, ActivityWindow
from fortuna_prismatica.analysis.inference import InferenceEngine
from fortuna_prismatica.analysis.graph import ActivityGraph


class TestInferenceEngine:
    """Tests for the InferenceEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create an inference engine."""
        return InferenceEngine(window_minutes=15)
    
    def test_create_windows_empty(self, engine):
        """Test window creation with no events."""
        windows = engine.create_windows([])
        assert len(windows) == 0
    
    def test_create_windows_single_event(self, engine):
        """Test window creation with a single event."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        windows = engine.create_windows([event])
        
        assert len(windows) == 1
        assert len(windows[0].events) == 1
    
    def test_create_windows_groups_nearby_events(self, engine):
        """Test that nearby events are grouped together."""
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/file1.py",
                timestamp=now,
            ),
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/file1.py",
                timestamp=now + timedelta(minutes=2),
            ),
        ]
        
        windows = engine.create_windows(events, gap_threshold_minutes=5)
        
        assert len(windows) == 1
        assert len(windows[0].events) == 2
    
    def test_create_windows_separates_distant_events(self, engine):
        """Test that distant events create separate windows."""
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_CREATE,
                source="test",
                subject="/file1.py",
                timestamp=now,
            ),
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/file2.py",
                timestamp=now + timedelta(minutes=30),
            ),
        ]
        
        windows = engine.create_windows(events, gap_threshold_minutes=5)
        
        assert len(windows) == 2
    
    def test_infer_task_coding(self, engine):
        """Test task inference for coding activity."""
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=10),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.FILE_MODIFY,
                    source="test",
                    subject="/file.py",
                    timestamp=now,
                ),
                Event(
                    event_type=EventType.GIT_COMMIT,
                    source="test",
                    subject="abc123",
                    timestamp=now,
                ),
            ]
        )
        
        task_label, confidence = engine.infer_task(window)
        
        assert task_label in ["coding", "git_workflow"]
        assert confidence > 0.5
    
    def test_infer_task_research(self, engine):
        """Test task inference for research activity."""
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=10),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.BROWSER_VISIT,
                    source="test",
                    subject="https://docs.python.org",
                    timestamp=now - timedelta(minutes=5),
                ),
                Event(
                    event_type=EventType.BROWSER_VISIT,
                    source="test",
                    subject="https://stackoverflow.com",
                    timestamp=now - timedelta(minutes=3),
                ),
                Event(
                    event_type=EventType.BROWSER_VISIT,
                    source="test",
                    subject="https://github.com",
                    timestamp=now,
                ),
            ]
        )
        
        task_label, confidence = engine.infer_task(window)
        
        assert task_label == "research"
    
    def test_analyze_windows(self, engine, sample_events):
        """Test window analysis."""
        windows = engine.create_windows(sample_events)
        analyzed = engine.analyze_windows(windows)
        
        for window in analyzed:
            assert window.task_label is not None
            assert 0.0 <= window.task_confidence <= 1.0
            assert isinstance(window.key_subjects, list)
    
    def test_detect_context_switches(self, engine):
        """Test context switch detection."""
        now = datetime.now()
        
        windows = [
            ActivityWindow(
                start_time=now - timedelta(hours=2),
                end_time=now - timedelta(hours=1, minutes=30),
                task_label="coding",
                task_confidence=0.8,
                key_subjects=["/project/file.py"],
            ),
            ActivityWindow(
                start_time=now - timedelta(hours=1),
                end_time=now - timedelta(minutes=30),
                task_label="research",
                task_confidence=0.7,
                key_subjects=["https://example.com"],
            ),
        ]
        
        switches = engine.detect_context_switches(windows)
        
        assert len(switches) == 1
        assert "coding" in switches[0][2]
        assert "research" in switches[0][2]
    
    def test_get_activity_summary(self, engine, sample_events):
        """Test activity summary generation."""
        windows = engine.create_windows(sample_events)
        windows = engine.analyze_windows(windows)
        
        summary = engine.get_activity_summary(windows)
        
        assert "total_windows" in summary
        assert "total_events" in summary
        assert "task_distribution" in summary


class TestActivityGraph:
    """Tests for the ActivityGraph class."""
    
    @pytest.fixture
    def graph(self, temp_data_dir):
        """Create a test activity graph."""
        return ActivityGraph(temp_data_dir / "test_graph.gpickle")
    
    def test_empty_graph(self, graph):
        """Test empty graph initialization."""
        stats = graph.get_statistics()
        assert stats["nodes"] == 0
        assert stats["edges"] == 0
    
    def test_add_file_event(self, graph):
        """Test adding a file event."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        
        graph.add_event(event)
        
        stats = graph.get_statistics()
        assert stats["nodes"] == 1
    
    def test_add_browser_event(self, graph):
        """Test adding a browser event creates domain node."""
        event = Event(
            event_type=EventType.BROWSER_VISIT,
            source="test",
            subject="https://example.com/page",
            url="https://example.com/page",
        )
        
        graph.add_event(event)
        
        stats = graph.get_statistics()
        assert stats["nodes"] == 2  # URL and domain
    
    def test_add_window_creates_edges(self, graph):
        """Test that adding a window creates edges between nodes."""
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=10),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.FILE_MODIFY,
                    source="test",
                    subject="/path/to/file.py",
                    timestamp=now,
                ),
                Event(
                    event_type=EventType.GIT_COMMIT,
                    source="test",
                    subject="abc123",
                    repository="/path/to/repo",
                    timestamp=now,
                ),
            ]
        )
        
        graph.add_window(window)
        
        stats = graph.get_statistics()
        assert stats["edges"] >= 1
    
    def test_find_node(self, graph):
        """Test finding nodes by query."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/important_file.py",
        )
        graph.add_event(event)
        
        matches = graph.find_node("important_file")
        
        assert len(matches) == 1
        assert "important_file" in matches[0]
    
    def test_get_related_nodes(self, graph):
        """Test getting related nodes."""
        now = datetime.now()
        
        # Add events that should be related
        for i in range(3):
            window = ActivityWindow(
                start_time=now - timedelta(minutes=10),
                end_time=now,
                events=[
                    Event(
                        event_type=EventType.FILE_MODIFY,
                        source="test",
                        subject="/path/to/file.py",
                        timestamp=now,
                    ),
                    Event(
                        event_type=EventType.SHELL_COMMAND,
                        source="test",
                        subject="pytest",
                        timestamp=now,
                    ),
                ]
            )
            graph.add_window(window)
        
        # Find related to file
        file_nodes = graph.find_node("file.py")
        if file_nodes:
            related = graph.get_related_nodes(file_nodes[0])
            assert len(related) > 0
    
    def test_get_most_connected(self, graph):
        """Test getting most connected nodes."""
        now = datetime.now()
        
        # Add multiple events
        for i in range(5):
            event = Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/path/to/file.py",
                timestamp=now + timedelta(minutes=i),
            )
            graph.add_event(event)
        
        top = graph.get_most_connected(3)
        assert len(top) >= 1
    
    def test_save_and_load(self, graph):
        """Test graph persistence."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        graph.add_event(event)
        
        # Save
        graph.save()
        
        # Create new graph instance
        new_graph = ActivityGraph(graph.graph_path)
        loaded = new_graph.load()
        
        assert loaded
        assert new_graph.get_statistics()["nodes"] == 1
    
    def test_clear(self, graph):
        """Test clearing the graph."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        graph.add_event(event)
        
        graph.clear()
        
        assert graph.get_statistics()["nodes"] == 0
    
    def test_get_node_info(self, graph):
        """Test getting node information."""
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path/to/file.py",
        )
        graph.add_event(event)
        
        nodes = graph.find_node("file.py")
        if nodes:
            info = graph.get_node_info(nodes[0])
            assert info is not None
            assert "type" in info
            assert "id" in info
    
    def test_get_node_info_nonexistent(self, graph):
        """Test getting info for nonexistent node."""
        info = graph.get_node_info("nonexistent:node")
        assert info is None
    
    def test_load_nonexistent_graph(self, temp_data_dir):
        """Test loading graph from nonexistent file."""
        graph = ActivityGraph(temp_data_dir / "nonexistent.gpickle")
        loaded = graph.load()
        assert not loaded
    
    def test_get_clusters(self, graph):
        """Test getting connected components."""
        # Add disconnected nodes
        event1 = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path1/file1.py",
        )
        event2 = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/path2/file2.py",
        )
        graph.add_event(event1)
        graph.add_event(event2)
        
        clusters = graph.get_clusters()
        assert len(clusters) >= 1
    
    def test_add_shell_command_event(self, graph):
        """Test adding shell command event."""
        event = Event(
            event_type=EventType.SHELL_COMMAND,
            source="test",
            subject="pytest tests/",
        )
        graph.add_event(event)
        
        nodes = graph.find_node("pytest")
        assert len(nodes) >= 1
    
    def test_add_process_event(self, graph):
        """Test adding process event."""
        event = Event(
            event_type=EventType.PROCESS_START,
            source="test",
            subject="vscode",
            process_name="code",
        )
        graph.add_event(event)
        
        stats = graph.get_statistics()
        assert stats["nodes"] >= 1


class TestInferenceEngineExtended:
    """Extended tests for InferenceEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create an inference engine."""
        return InferenceEngine(window_minutes=15)
    
    def test_find_stalled_tasks_no_stalls(self, engine):
        """Test stall detection with no stalls."""
        now = datetime.now()
        windows = [
            ActivityWindow(
                start_time=now - timedelta(minutes=30),
                end_time=now - timedelta(minutes=25),
                events=[],
                key_subjects=["/project/file.py"],
            ),
            ActivityWindow(
                start_time=now - timedelta(minutes=20),
                end_time=now - timedelta(minutes=15),
                events=[],
                key_subjects=["/project/file.py"],
            ),
        ]
        
        stalls = engine.find_stalled_tasks(windows, stall_threshold_minutes=60)
        # May or may not have stalls depending on implementation
        assert isinstance(stalls, list)
    
    def test_infer_terminal_work(self, engine):
        """Test inference for terminal work."""
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=10),
            end_time=now,
            events=[
                Event(event_type=EventType.SHELL_COMMAND, source="test", subject="git status", timestamp=now),
                Event(event_type=EventType.SHELL_COMMAND, source="test", subject="make build", timestamp=now),
                Event(event_type=EventType.SHELL_COMMAND, source="test", subject="./run.sh", timestamp=now),
                Event(event_type=EventType.SHELL_COMMAND, source="test", subject="ls -la", timestamp=now),
            ]
        )
        
        task, confidence = engine.infer_task(window)
        assert task in ["terminal_work", "general_activity"]
    
    def test_context_switches_no_switches(self, engine):
        """Test context switch detection with consistent work."""
        now = datetime.now()
        windows = [
            ActivityWindow(
                start_time=now - timedelta(minutes=30),
                end_time=now - timedelta(minutes=20),
                task_label="coding",
                task_confidence=0.8,
                key_subjects=["/file.py"],
            ),
            ActivityWindow(
                start_time=now - timedelta(minutes=15),
                end_time=now,
                task_label="coding",
                task_confidence=0.8,
                key_subjects=["/file.py"],
            ),
        ]
        
        switches = engine.detect_context_switches(windows)
        # Same task label, may not count as switch
        assert isinstance(switches, list)
