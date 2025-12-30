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
        """Test default configuration values."""
        config = Config()
        
        assert config.log_level == "INFO"
        assert config.process_poll_interval == 30
        assert config.shell_history_poll_interval == 60
        assert config.browser_poll_interval == 300
        assert config.activity_window_minutes == 15
    
    def test_config_with_custom_values(self, temp_data_dir):
        """Test configuration with custom values."""
        config = Config(
            data_dir=temp_data_dir,
            log_level="DEBUG",
            process_poll_interval=10,
        )
        
        assert config.data_dir == temp_data_dir
        assert config.log_level == "DEBUG"
        assert config.process_poll_interval == 10
    
    def test_database_path_property(self, temp_data_dir):
        """Test database path is derived from data_dir."""
        config = Config(data_dir=temp_data_dir)
        
        assert config.database_path == temp_data_dir / "events.duckdb"
    
    def test_graph_path_property(self, temp_data_dir):
        """Test graph path is derived from data_dir."""
        config = Config(data_dir=temp_data_dir)
        
        assert config.graph_path == temp_data_dir / "activity_graph.gpickle"
    
    def test_log_path_property(self, temp_data_dir):
        """Test log path is derived from data_dir."""
        config = Config(data_dir=temp_data_dir)
        
        assert config.log_path == temp_data_dir / "fortuna.log"
    
    def test_ensure_data_dir(self, temp_data_dir):
        """Test data directory creation."""
        subdir = temp_data_dir / "nested" / "subdir"
        config = Config(data_dir=subdir)
        
        assert not subdir.exists()
        config.ensure_data_dir()
        assert subdir.exists()
    
    def test_config_from_env(self, temp_data_dir, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("DEJA_DATA_DIR", str(temp_data_dir))
        monkeypatch.setenv("DEJA_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("DEJA_PROCESS_POLL_INTERVAL", "45")
        
        config = Config.from_env()
        
        assert config.data_dir == temp_data_dir
        assert config.log_level == "WARNING"
        assert config.process_poll_interval == 45
    
    def test_interval_validation(self):
        """Test that intervals have minimum values."""
        with pytest.raises(ValueError):
            Config(process_poll_interval=1)  # Minimum is 5
        
        with pytest.raises(ValueError):
            Config(shell_history_poll_interval=5)  # Minimum is 10
    
    def test_pid_file_default(self, temp_data_dir):
        """Test PID file path is set after model creation."""
        config = Config(data_dir=temp_data_dir)
        
        assert config.pid_file == temp_data_dir / "fortuna.pid"


class TestGlobalConfig:
    """Tests for global configuration management."""
    
    def test_get_set_config(self, temp_data_dir):
        """Test getting and setting global config."""
        config = Config(data_dir=temp_data_dir)
        set_config(config)
        
        retrieved = get_config()
        assert retrieved.data_dir == temp_data_dir
    
    def test_default_data_dir(self):
        """Test default data directory is reasonable."""
        data_dir = get_default_data_dir()
        
        assert isinstance(data_dir, Path)
        # Should be under user's home directory
        assert str(Path.home()) in str(data_dir)
    
    def test_default_watch_paths(self):
        """Test default watch paths include home directory."""
        paths = get_default_watch_paths()
        
        assert len(paths) >= 1
        assert Path.home() in paths
