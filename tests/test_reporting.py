"""
Tests for the reporting module.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from deja_view.models import Event, EventType, ActivityWindow
from deja_view.analysis.graph import ActivityGraph
from deja_view.analysis.inference import InferenceEngine
from deja_view.reporting.narrative import NarrativeGenerator
from deja_view.storage.database import EventDatabase


class TestNarrativeGenerator:
    """Tests for the NarrativeGenerator class."""
    
    @pytest.fixture
    def database(self, test_config):
        """Create a test database with events."""
        db = EventDatabase(test_config.database_path)
        db.connect()
        return db
    
    @pytest.fixture
    def graph(self, test_config):
        """Create a test graph."""
        return ActivityGraph(test_config.graph_path)
    
    @pytest.fixture
    def generator(self, database, graph):
        """Create a narrative generator."""
        return NarrativeGenerator(database, graph)
    
    def test_format_duration(self, generator):
        """Test duration formatting."""
        assert generator._format_duration(30) == "30 seconds"
        assert generator._format_duration(120) == "2 minutes"
        assert generator._format_duration(3700) == "1 hours, 1 minutes"
    
    def test_format_time_range_same_day(self, generator):
        """Test time range formatting for same day."""
        start = datetime(2024, 1, 15, 10, 0)
        end = datetime(2024, 1, 15, 12, 30)
        
        result = generator._format_time_range(start, end)
        
        assert "10:00" in result
        assert "12:30" in result
    
    def test_format_time_range_different_days(self, generator):
        """Test time range formatting for different days."""
        start = datetime(2024, 1, 15, 10, 0)
        end = datetime(2024, 1, 16, 12, 30)
        
        result = generator._format_time_range(start, end)
        
        # Should include full date for both
        assert "01-15" in result or "2024" in result
    
    def test_explain_empty_period(self, generator, database):
        """Test explanation for period with no events."""
        database.close()
        database.connect()  # Fresh database
        
        result = generator.explain_last(30)
        
        assert "No activity recorded" in result
        database.close()
    
    def test_explain_with_events(self, generator, database, sample_events):
        """Test explanation with events."""
        database.insert_events(sample_events)
        
        result = generator.explain_last(60)
        
        assert "Activity Report" in result
        assert "Summary" in result
        database.close()
    
    def test_trace_subject_not_found(self, generator, database):
        """Test trace for nonexistent subject."""
        database.close()
        database.connect()
        
        result = generator.trace_subject("/nonexistent/path")
        
        assert "No activity found" in result
        database.close()
    
    def test_trace_subject_with_events(self, generator, database, sample_events):
        """Test trace for subject with events."""
        database.insert_events(sample_events)
        
        result = generator.trace_subject("file1.py")
        
        assert "Trace Report" in result
        assert "First seen" in result
        database.close()
    
    def test_generate_window_summary(self, generator):
        """Test window summary generation."""
        now = datetime.now()
        window = ActivityWindow(
            start_time=now - timedelta(minutes=15),
            end_time=now,
            events=[
                Event(
                    event_type=EventType.FILE_MODIFY,
                    source="test",
                    subject="/file.py",
                    timestamp=now,
                ),
            ],
            task_label="coding",
            task_confidence=0.8,
            key_subjects=["/file.py"],
        )
        
        summary = generator._generate_window_summary(window)
        
        assert "coding" in summary.lower() or "writing" in summary.lower()
        assert "15 minutes" in summary or "file" in summary.lower()
    
    def test_llm_hook_isolation(self, database, graph):
        """Test that LLM hook is properly isolated."""
        llm_called = False
        
        def mock_llm(prompt):
            nonlocal llm_called
            llm_called = True
            return "AI-enhanced summary"
        
        generator = NarrativeGenerator(database, graph, llm_hook=mock_llm)
        
        # Add an event so there's something to explain
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
        )
        database.insert_event(event)
        
        result = generator.explain_last(60)
        
        assert llm_called
        assert "AI Summary" in result
        database.close()
    
    def test_stalls_report(self, generator, database):
        """Test stalls report generation."""
        # Add events with a long gap
        now = datetime.now()
        events = [
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/project/file.py",
                timestamp=now - timedelta(hours=3),
                repository="/project",
            ),
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/project/file.py",
                timestamp=now,
                repository="/project",
            ),
        ]
        database.insert_events(events)
        
        result = generator.explain_stalls()
        
        assert "Stall" in result
        database.close()
    
    def test_context_switches_report(self, generator, database):
        """Test context switches report generation."""
        result = generator.explain_context_switches()
        
        assert "Context Switch" in result
        database.close()
    
    def test_explain_time_window(self, generator, database, sample_events):
        """Test explaining a specific time window."""
        database.insert_events(sample_events)
        
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        
        result = generator.explain_time_window(start, end)
        
        assert "Activity Report" in result
        database.close()
    
    def test_get_file_summary(self, generator):
        """Test file summary generation."""
        paths = [
            "/project/src/main.py",
            "/project/src/utils.py",
            "/project/src/config.py",
        ]
        
        summary = generator._get_file_summary(paths)
        
        assert "3 files" in summary
    
    def test_get_file_summary_empty(self, generator):
        """Test file summary with no files."""
        summary = generator._get_file_summary([])
        assert "no files" in summary
    
    def test_get_file_summary_multiple_dirs(self, generator):
        """Test file summary with multiple directories."""
        paths = [
            "/project/src/main.py",
            "/project/tests/test_main.py",
        ]
        
        summary = generator._get_file_summary(paths)
        
        assert "2 files" in summary
        assert "directories" in summary
    
    def test_llm_hook_error_handling(self, database, graph):
        """Test that LLM hook errors are handled gracefully."""
        def failing_llm(prompt):
            raise Exception("LLM error")
        
        generator = NarrativeGenerator(database, graph, llm_hook=failing_llm)
        
        event = Event(
            event_type=EventType.FILE_CREATE,
            source="test",
            subject="/test.py",
        )
        database.insert_event(event)
        
        # Should not raise, should handle error
        result = generator.explain_last(60)
        
        assert "Activity Report" in result
        database.close()
    
    def test_task_descriptions(self, generator):
        """Test that all task types have descriptions."""
        task_types = ["coding", "research", "git_workflow", "terminal_work", 
                      "file_organization", "general_activity"]
        
        for task in task_types:
            desc = generator.TASK_DESCRIPTIONS.get(task)
            assert desc is not None, f"Missing description for {task}"
    
    def test_stalls_no_events(self, database, graph):
        """Test stalls report with no events."""
        generator = NarrativeGenerator(database, graph)
        
        result = generator.explain_stalls()
        
        assert "No activity" in result or "Stall" in result
        database.close()
    
    def test_context_switches_with_events(self, generator, database):
        """Test context switches with actual events."""
        now = datetime.now()
        events = [
            # Coding session
            Event(
                event_type=EventType.FILE_MODIFY,
                source="test",
                subject="/code/file.py",
                timestamp=now - timedelta(hours=2),
            ),
            # Research session
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://docs.python.org",
                url="https://docs.python.org",
                timestamp=now - timedelta(hours=1),
            ),
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://stackoverflow.com",
                url="https://stackoverflow.com",
                timestamp=now - timedelta(minutes=55),
            ),
            Event(
                event_type=EventType.BROWSER_VISIT,
                source="test",
                subject="https://github.com",
                url="https://github.com",
                timestamp=now - timedelta(minutes=50),
            ),
        ]
        database.insert_events(events)
        
        result = generator.explain_context_switches()
        
        assert "Context Switch" in result
        database.close()
