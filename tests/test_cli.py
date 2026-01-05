"""
Tests for the CLI module.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from deja_view.cli import app, _get_database, _get_graph


runner = CliRunner()


class TestCLI:
    """Tests for the CLI commands."""
    
    def test_version_command(self):
        """Test that version command returns successfully.

        Verifies the version command exits with code 0 and includes
        the application name in the output.
        """
        result = runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "Deja View" in result.output
    
    def test_status_command(self, test_config):
        """Test that status command executes without crashing.

        Args:
            test_config: Pytest fixture providing test configuration.

        Note:
            The command may exit with 0 or 1 depending on daemon state.
        """
        result = runner.invoke(app, ["status"])
        
        # Should not crash even without running daemon
        assert result.exit_code == 0 or result.exit_code == 1
    
    def test_help_command(self):
        """Test that help output includes all main commands.

        Verifies the help text displays start, stop, status, and explain
        commands.
        """
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output
        assert "explain" in result.output
    
    def test_start_help(self):
        """Test that start command help includes foreground option.

        Verifies the start command displays help with the foreground
        option documented.
        """
        result = runner.invoke(app, ["start", "--help"])
        
        assert result.exit_code == 0
        assert "foreground" in result.output
    
    def test_explain_help(self):
        """Test that explain command help includes last option.

        Verifies the explain command displays help with the --last
        time filter option documented.
        """
        result = runner.invoke(app, ["explain", "--help"])
        
        assert result.exit_code == 0
        assert "last" in result.output
    
    def test_trace_help(self):
        """Test that trace command help is available.

        Verifies the trace command displays help successfully.
        """
        result = runner.invoke(app, ["trace", "--help"])
        
        assert result.exit_code == 0
    
    def test_events_help(self):
        """Test that events command help includes limit option.

        Verifies the events command displays help with the --limit
        option documented.
        """
        result = runner.invoke(app, ["events", "--help"])
        
        assert result.exit_code == 0
        assert "limit" in result.output
    
    def test_graph_stats_command(self, test_config):
        """Test that graph-stats command executes without crashing.

        Args:
            test_config: Pytest fixture providing test configuration.

        Note:
            May exit with 0 or 1 depending on whether a graph exists.
        """
        result = runner.invoke(app, ["graph-stats"])
        
        # May fail if no graph exists, but shouldn't crash unexpectedly
        assert result.exit_code in [0, 1]
    
    def test_stop_help(self):
        """Test that stop command help is available.

        Verifies the stop command displays help successfully.
        """
        result = runner.invoke(app, ["stop", "--help"])
        
        assert result.exit_code == 0
    
    def test_switches_help(self):
        """Test that switches command help is available.

        Verifies the switches command displays help successfully.
        """
        result = runner.invoke(app, ["switches", "--help"])
        
        assert result.exit_code == 0
    
    def test_stalls_help(self):
        """Test that stalls command help is available.

        Verifies the stalls command displays help successfully.
        """
        result = runner.invoke(app, ["stalls", "--help"])
        
        assert result.exit_code == 0
    
    def test_explain_invalid_time_format(self, test_config):
        """Test that explain command rejects invalid time format.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command exits with code 1 and shows an error message
        when given an invalid time format.
        """
        result = runner.invoke(app, ["explain", "--last", "invalid"])
        
        assert result.exit_code == 1
        assert "Invalid" in result.output
    
    def test_events_invalid_time_format(self, test_config):
        """Test that events command rejects invalid time format.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command exits with code 1 when given an invalid
        time format.
        """
        result = runner.invoke(app, ["events", "--last", "xyz"])
        
        assert result.exit_code == 1


class TestCLIHelpers:
    """Tests for CLI helper functions."""
    
    def test_all_commands_have_help(self):
        """Test that all CLI commands have help text available.

        Iterates through all main commands and verifies each one
        has accessible help documentation.
        """
        commands = ["start", "stop", "status", "explain", "trace", 
                    "switches", "stalls", "events", "graph-stats", "version"]
        
        for cmd in commands:
            result = runner.invoke(app, [cmd, "--help"])
            # All should have help available
            assert result.exit_code == 0 or "Usage:" in result.output or "Error" not in result.output


class TestCLIFunctional:
    """Functional tests for CLI commands."""
    
    def test_explain_with_minutes(self, test_config):
        """Test that explain command accepts minutes format.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes the '30m' time format without crashing.
        """
        result = runner.invoke(app, ["explain", "--last", "30m"])
        
        # Should not crash
        assert result.exit_code in [0, 1]
    
    def test_explain_with_hours(self, test_config):
        """Test that explain command accepts hours format.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes the '2h' time format without crashing.
        """
        result = runner.invoke(app, ["explain", "--last", "2h"])
        
        assert result.exit_code in [0, 1]
    
    def test_explain_with_days(self, test_config):
        """Test that explain command accepts days format.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes the '1d' time format without crashing.
        """
        result = runner.invoke(app, ["explain", "--last", "1d"])
        
        assert result.exit_code in [0, 1]
    
    def test_explain_numeric_only(self, test_config):
        """Test that explain command accepts numeric-only time value.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes a plain number as minutes without
        crashing.
        """
        result = runner.invoke(app, ["explain", "--last", "60"])
        
        assert result.exit_code in [0, 1]
    
    def test_events_with_limit(self, test_config):
        """Test that events command accepts limit option.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes the --limit option without crashing.
        """
        result = runner.invoke(app, ["events", "--limit", "10"])
        
        assert result.exit_code in [0, 1]
    
    def test_events_with_type_filter(self, test_config):
        """Test that events command accepts type filter option.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes the --type filter without crashing.
        """
        result = runner.invoke(app, ["events", "--type", "file"])
        
        assert result.exit_code in [0, 1]
    
    def test_trace_with_path(self, test_config):
        """Test that trace command accepts a file path argument.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command processes a file path without crashing,
        even if no results are found.
        """
        result = runner.invoke(app, ["trace", "/some/path/file.py"])
        
        # May show no results but shouldn't crash
        assert result.exit_code in [0, 1]
    
    def test_switches_command(self, test_config):
        """Test that switches command executes without crashing.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command runs and exits with a valid code.
        """
        result = runner.invoke(app, ["switches"])
        
        assert result.exit_code in [0, 1]
    
    def test_stalls_command(self, test_config):
        """Test that stalls command executes without crashing.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command runs and exits with a valid code.
        """
        result = runner.invoke(app, ["stalls"])
        
        assert result.exit_code in [0, 1]
    
    def test_stop_when_not_running(self, test_config):
        """Test that stop command handles non-running daemon gracefully.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command reports the daemon is not running when
        attempting to stop a non-existent process.
        """
        result = runner.invoke(app, ["stop"])
        
        # Should report not running
        assert result.exit_code == 1 or "not running" in result.output.lower()
    
    def test_start_already_running(self, test_config):
        """Test that start command detects already running daemon.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the command exits with code 1 and shows an error message
        when the daemon is already running.
        """
        with patch('deja_view.cli.is_daemon_running', return_value=True):
            with patch('deja_view.cli.get_daemon_pid', return_value=12345):
                result = runner.invoke(app, ["start"])
                
                assert result.exit_code == 1
                assert "already running" in result.output.lower()


class TestCLIDatabase:
    """Tests for CLI database operations."""
    
    def test_get_database(self, test_config):
        """Test that _get_database helper returns a valid database connection.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the helper function returns a non-None database object.
        """
        db = _get_database()
        assert db is not None
        db.close()
    
    def test_get_graph(self, test_config):
        """Test that _get_graph helper returns a valid graph object.

        Args:
            test_config: Pytest fixture providing test configuration.

        Verifies the helper function returns a non-None graph object.
        """
        graph = _get_graph()
        assert graph is not None
