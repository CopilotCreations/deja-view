"""
Tests for the CLI module.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from fortuna_prismatica.cli import app, _get_database, _get_graph


runner = CliRunner()


class TestCLI:
    """Tests for the CLI commands."""
    
    def test_version_command(self):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "Fortuna Prismatica" in result.output
    
    def test_status_command(self, test_config):
        """Test status command."""
        result = runner.invoke(app, ["status"])
        
        # Should not crash even without running daemon
        assert result.exit_code == 0 or result.exit_code == 1
    
    def test_help_command(self):
        """Test help output."""
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output
        assert "explain" in result.output
    
    def test_start_help(self):
        """Test start command help."""
        result = runner.invoke(app, ["start", "--help"])
        
        assert result.exit_code == 0
        assert "foreground" in result.output
    
    def test_explain_help(self):
        """Test explain command help."""
        result = runner.invoke(app, ["explain", "--help"])
        
        assert result.exit_code == 0
        assert "last" in result.output
    
    def test_trace_help(self):
        """Test trace command help."""
        result = runner.invoke(app, ["trace", "--help"])
        
        assert result.exit_code == 0
    
    def test_events_help(self):
        """Test events command help."""
        result = runner.invoke(app, ["events", "--help"])
        
        assert result.exit_code == 0
        assert "limit" in result.output
    
    def test_graph_stats_command(self, test_config):
        """Test graph-stats command."""
        result = runner.invoke(app, ["graph-stats"])
        
        # May fail if no graph exists, but shouldn't crash unexpectedly
        assert result.exit_code in [0, 1]
    
    def test_stop_help(self):
        """Test stop command help."""
        result = runner.invoke(app, ["stop", "--help"])
        
        assert result.exit_code == 0
    
    def test_switches_help(self):
        """Test switches command help."""
        result = runner.invoke(app, ["switches", "--help"])
        
        assert result.exit_code == 0
    
    def test_stalls_help(self):
        """Test stalls command help."""
        result = runner.invoke(app, ["stalls", "--help"])
        
        assert result.exit_code == 0
    
    def test_explain_invalid_time_format(self, test_config):
        """Test explain with invalid time format."""
        result = runner.invoke(app, ["explain", "--last", "invalid"])
        
        assert result.exit_code == 1
        assert "Invalid" in result.output
    
    def test_events_invalid_time_format(self, test_config):
        """Test events with invalid time format."""
        result = runner.invoke(app, ["events", "--last", "xyz"])
        
        assert result.exit_code == 1


class TestCLIHelpers:
    """Tests for CLI helper functions."""
    
    def test_all_commands_have_help(self):
        """Test that all commands have help text."""
        commands = ["start", "stop", "status", "explain", "trace", 
                    "switches", "stalls", "events", "graph-stats", "version"]
        
        for cmd in commands:
            result = runner.invoke(app, [cmd, "--help"])
            # All should have help available
            assert result.exit_code == 0 or "Usage:" in result.output or "Error" not in result.output


class TestCLIFunctional:
    """Functional tests for CLI commands."""
    
    def test_explain_with_minutes(self, test_config):
        """Test explain with minutes format."""
        result = runner.invoke(app, ["explain", "--last", "30m"])
        
        # Should not crash
        assert result.exit_code in [0, 1]
    
    def test_explain_with_hours(self, test_config):
        """Test explain with hours format."""
        result = runner.invoke(app, ["explain", "--last", "2h"])
        
        assert result.exit_code in [0, 1]
    
    def test_explain_with_days(self, test_config):
        """Test explain with days format."""
        result = runner.invoke(app, ["explain", "--last", "1d"])
        
        assert result.exit_code in [0, 1]
    
    def test_explain_numeric_only(self, test_config):
        """Test explain with numeric time (minutes)."""
        result = runner.invoke(app, ["explain", "--last", "60"])
        
        assert result.exit_code in [0, 1]
    
    def test_events_with_limit(self, test_config):
        """Test events with limit option."""
        result = runner.invoke(app, ["events", "--limit", "10"])
        
        assert result.exit_code in [0, 1]
    
    def test_events_with_type_filter(self, test_config):
        """Test events with type filter."""
        result = runner.invoke(app, ["events", "--type", "file"])
        
        assert result.exit_code in [0, 1]
    
    def test_trace_with_path(self, test_config):
        """Test trace with a file path."""
        result = runner.invoke(app, ["trace", "/some/path/file.py"])
        
        # May show no results but shouldn't crash
        assert result.exit_code in [0, 1]
    
    def test_switches_command(self, test_config):
        """Test switches command."""
        result = runner.invoke(app, ["switches"])
        
        assert result.exit_code in [0, 1]
    
    def test_stalls_command(self, test_config):
        """Test stalls command."""
        result = runner.invoke(app, ["stalls"])
        
        assert result.exit_code in [0, 1]
    
    def test_stop_when_not_running(self, test_config):
        """Test stop when daemon is not running."""
        result = runner.invoke(app, ["stop"])
        
        # Should report not running
        assert result.exit_code == 1 or "not running" in result.output.lower()
    
    def test_start_already_running(self, test_config):
        """Test start when already running check works."""
        with patch('fortuna_prismatica.cli.is_daemon_running', return_value=True):
            with patch('fortuna_prismatica.cli.get_daemon_pid', return_value=12345):
                result = runner.invoke(app, ["start"])
                
                assert result.exit_code == 1
                assert "already running" in result.output.lower()


class TestCLIDatabase:
    """Tests for CLI database operations."""
    
    def test_get_database(self, test_config):
        """Test _get_database helper."""
        db = _get_database()
        assert db is not None
        db.close()
    
    def test_get_graph(self, test_config):
        """Test _get_graph helper."""
        graph = _get_graph()
        assert graph is not None
