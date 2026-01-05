"""
Tests for the configuration module.
"""

import os
import pytest
from pathlib import Path

from deja_view.config import (
    Config,
    get_config,
    set_config,
    get_default_data_dir,
    get_default_watch_paths,
)


class TestConfig:
    """Tests for the Config class."""
    
    def test_default_config(self):
        """Test default configuration values.

        Verifies that a Config instance created without arguments has
        the expected default values for log_level, poll intervals,
        and activity window.
        """
        config = Config()
        
        assert config.log_level == "INFO"
        assert config.process_poll_interval == 30
        assert config.shell_history_poll_interval == 60
        assert config.browser_poll_interval == 300
        assert config.activity_window_minutes == 15
    
    def test_config_with_custom_values(self, temp_data_dir):
        """Test configuration with custom values.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that custom configuration values are correctly applied
        when explicitly provided to the Config constructor.
        """
        config = Config(
            data_dir=temp_data_dir,
            log_level="DEBUG",
            process_poll_interval=10,
        )
        
        assert config.data_dir == temp_data_dir
        assert config.log_level == "DEBUG"
        assert config.process_poll_interval == 10
    
    def test_database_path_property(self, temp_data_dir):
        """Test database path is derived from data_dir.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that the database_path property correctly constructs
        the path to the DuckDB file within the data directory.
        """
        config = Config(data_dir=temp_data_dir)
        
        assert config.database_path == temp_data_dir / "events.duckdb"
    
    def test_graph_path_property(self, temp_data_dir):
        """Test graph path is derived from data_dir.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that the graph_path property correctly constructs
        the path to the activity graph file within the data directory.
        """
        config = Config(data_dir=temp_data_dir)
        
        assert config.graph_path == temp_data_dir / "activity_graph.gpickle"
    
    def test_log_path_property(self, temp_data_dir):
        """Test log path is derived from data_dir.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that the log_path property correctly constructs
        the path to the log file within the data directory.
        """
        config = Config(data_dir=temp_data_dir)
        
        assert config.log_path == temp_data_dir / "fortuna.log"
    
    def test_ensure_data_dir(self, temp_data_dir):
        """Test data directory creation.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that ensure_data_dir() creates the data directory
        and any necessary parent directories if they don't exist.
        """
        subdir = temp_data_dir / "nested" / "subdir"
        config = Config(data_dir=subdir)
        
        assert not subdir.exists()
        config.ensure_data_dir()
        assert subdir.exists()
    
    def test_config_from_env(self, temp_data_dir, monkeypatch):
        """Test configuration from environment variables.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.
            monkeypatch: Pytest fixture for modifying environment variables.

        Verifies that Config.from_env() correctly reads and applies
        configuration values from DEJA_* environment variables.
        """
        monkeypatch.setenv("DEJA_DATA_DIR", str(temp_data_dir))
        monkeypatch.setenv("DEJA_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("DEJA_PROCESS_POLL_INTERVAL", "45")
        
        config = Config.from_env()
        
        assert config.data_dir == temp_data_dir
        assert config.log_level == "WARNING"
        assert config.process_poll_interval == 45
    
    def test_interval_validation(self):
        """Test that intervals have minimum values.

        Verifies that Config raises ValueError when poll interval
        values are below their required minimums (5 for process,
        10 for shell history).
        """
        with pytest.raises(ValueError):
            Config(process_poll_interval=1)  # Minimum is 5
        
        with pytest.raises(ValueError):
            Config(shell_history_poll_interval=5)  # Minimum is 10
    
    def test_pid_file_default(self, temp_data_dir):
        """Test PID file path is set after model creation.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that the pid_file property correctly constructs
        the path to the PID file within the data directory.
        """
        config = Config(data_dir=temp_data_dir)
        
        assert config.pid_file == temp_data_dir / "fortuna.pid"


class TestGlobalConfig:
    """Tests for global configuration management."""
    
    def test_get_set_config(self, temp_data_dir):
        """Test getting and setting global config.

        Args:
            temp_data_dir: Pytest fixture providing a temporary directory path.

        Verifies that set_config() stores a Config instance and
        get_config() retrieves it with the same values.
        """
        config = Config(data_dir=temp_data_dir)
        set_config(config)
        
        retrieved = get_config()
        assert retrieved.data_dir == temp_data_dir
    
    def test_default_data_dir(self):
        """Test default data directory is reasonable.

        Verifies that get_default_data_dir() returns a Path object
        located somewhere under the user's home directory.
        """
        data_dir = get_default_data_dir()
        
        assert isinstance(data_dir, Path)
        # Should be under user's home directory
        assert str(Path.home()) in str(data_dir)
    
    def test_default_watch_paths(self):
        """Test default watch paths include home directory.

        Verifies that get_default_watch_paths() returns a list
        containing at least the user's home directory.
        """
        paths = get_default_watch_paths()
        
        assert len(paths) >= 1
        assert Path.home() in paths
