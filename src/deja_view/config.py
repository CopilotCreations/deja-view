"""
Configuration management for Deja View.

Provides centralized configuration with sensible defaults,
environment variable overrides, and platform-specific paths.
"""

import os
import platform
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def get_default_data_dir() -> Path:
    """Get the default data directory based on platform.

    Returns platform-specific application data directories:
    - macOS: ~/Library/Application Support/deja.
    - Windows: %APPDATA%/deja.
    - Linux: ~/.deja.

    Returns:
        Path: The default data directory path for the current platform.
    """
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "deja.
    elif platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", home)) / "deja.
    else:
        return home / ".deja.


def get_default_watch_paths() -> List[Path]:
    """Get default paths to watch for filesystem events.

    Includes the home directory and common development directories
    (Documents, Projects, Code, Development, src) if they exist.

    Returns:
        List[Path]: List of existing paths to monitor for file changes.
    """
    home = Path.home()
    paths = [home]
    
    for subdir in ["Documents", "Projects", "Code", "Development", "src"]:
        path = home / subdir
        if path.exists():
            paths.append(path)
    
    return paths


def get_chrome_history_path() -> Optional[Path]:
    """Get Chrome history database path based on platform.

    Returns platform-specific Chrome history database locations:
    - macOS: ~/Library/Application Support/Google/Chrome/Default/History
    - Windows: %LOCALAPPDATA%/Google/Chrome/User Data/Default/History
    - Linux: ~/.config/google-chrome/Default/History

    Returns:
        Optional[Path]: Path to the Chrome history database if it exists,
            None otherwise.
    """
    home = Path.home()
    system = platform.system()
    
    if system == "Darwin":
        path = home / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "History"
    elif system == "Windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        path = local_app_data / "Google" / "Chrome" / "User Data" / "Default" / "History"
    else:
        path = home / ".config" / "google-chrome" / "Default" / "History"
    
    return path if path.exists() else None


def get_firefox_history_path() -> Optional[Path]:
    """Get Firefox history database path based on platform.

    Searches for the places.sqlite database within Firefox profile
    directories at platform-specific locations:
    - macOS: ~/Library/Application Support/Firefox/Profiles
    - Windows: %APPDATA%/Mozilla/Firefox/Profiles
    - Linux: ~/.mozilla/firefox

    Returns:
        Optional[Path]: Path to the Firefox places.sqlite database if found,
            None otherwise.
    """
    home = Path.home()
    system = platform.system()
    
    if system == "Darwin":
        profiles_dir = home / "Library" / "Application Support" / "Firefox" / "Profiles"
    elif system == "Windows":
        app_data = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        profiles_dir = app_data / "Mozilla" / "Firefox" / "Profiles"
    else:
        profiles_dir = home / ".mozilla" / "firefox"
    
    if not profiles_dir.exists():
        return None
    
    # Find the default profile
    for profile in profiles_dir.iterdir():
        if profile.is_dir():
            places = profile / "places.sqlite"
            if places.exists():
                return places
    
    return None


def get_shell_history_paths() -> dict:
    """Get shell history file paths.

    Checks for the existence of common shell history files
    (~/.bash_history and ~/.zsh_history).

    Returns:
        dict: Dictionary mapping shell names ('bash', 'zsh') to their
            history file paths. Only includes shells with existing
            history files.
    """
    home = Path.home()
    paths = {}
    
    bash_history = home / ".bash_history"
    if bash_history.exists():
        paths["bash"] = bash_history
    
    zsh_history = home / ".zsh_history"
    if zsh_history.exists():
        paths["zsh"] = zsh_history
    
    return paths


class Config(BaseModel):
    """Application configuration with sensible defaults."""
    
    # Data storage
    data_dir: Path = Field(default_factory=get_default_data_dir)
    
    # Logging
    log_level: str = Field(default="INFO")
    
    # Collection intervals (seconds)
    process_poll_interval: int = Field(default=30, ge=5)
    shell_history_poll_interval: int = Field(default=60, ge=10)
    browser_poll_interval: int = Field(default=300, ge=60)
    
    # Activity analysis
    activity_window_minutes: int = Field(default=15, ge=1)
    
    # Paths to monitor
    watch_paths: List[Path] = Field(default_factory=get_default_watch_paths)
    
    # Browser history paths
    chrome_history_path: Optional[Path] = Field(default_factory=get_chrome_history_path)
    firefox_history_path: Optional[Path] = Field(default_factory=get_firefox_history_path)
    
    # Shell history paths
    shell_history_paths: dict = Field(default_factory=get_shell_history_paths)
    
    # Daemon settings
    pid_file: Path = Field(default=None)
    
    def model_post_init(self, __context) -> None:
        """Initialize derived fields after model creation.

        Sets the pid_file path to data_dir/deja.pid if not explicitly provided.

        Args:
            __context: Pydantic validation context (unused).
        """
        if self.pid_file is None:
            self.pid_file = self.data_dir / "deja.pid"
    
    @property
    def database_path(self) -> Path:
        """Path to the DuckDB database file.

        Returns:
            Path: The path to events.duckdb within the data directory.
        """
        return self.data_dir / "events.duckdb"
    
    @property
    def graph_path(self) -> Path:
        """Path to the activity graph file.

        Returns:
            Path: The path to activity_graph.gpickle within the data directory.
        """
        return self.data_dir / "activity_graph.gpickle"
    
    @property
    def log_path(self) -> Path:
        """Path to the log file.

        Returns:
            Path: The path to deja.log within the data directory.
        """
        return self.data_dir / "deja.log"
    
    def ensure_data_dir(self) -> None:
        """Create the data directory if it doesn't exist.

        Creates the data directory and any necessary parent directories.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables.

        Reads configuration from environment variables with the DEJA_ prefix:
        - DEJA_DATA_DIR: Data directory path
        - DEJA_LOG_LEVEL: Logging level
        - DEJA_PROCESS_POLL_INTERVAL: Process polling interval in seconds
        - DEJA_SHELL_HISTORY_POLL_INTERVAL: Shell history polling interval
        - DEJA_BROWSER_POLL_INTERVAL: Browser history polling interval
        - DEJA_ACTIVITY_WINDOW_MINUTES: Activity analysis window size
        - DEJA_WATCH_PATHS: Comma-separated list of paths to monitor
        - DEJA_CHROME_HISTORY_PATH: Custom Chrome history path
        - DEJA_FIREFOX_HISTORY_PATH: Custom Firefox history path

        Returns:
            Config: Configuration instance with environment overrides applied.
        """
        kwargs = {}
        
        if data_dir := os.environ.get("DEJA_DATA_DIR"):
            kwargs["data_dir"] = Path(data_dir).expanduser()
        
        if log_level := os.environ.get("DEJA_LOG_LEVEL"):
            kwargs["log_level"] = log_level
        
        if interval := os.environ.get("DEJA_PROCESS_POLL_INTERVAL"):
            kwargs["process_poll_interval"] = int(interval)
        
        if interval := os.environ.get("DEJA_SHELL_HISTORY_POLL_INTERVAL"):
            kwargs["shell_history_poll_interval"] = int(interval)
        
        if interval := os.environ.get("DEJA_BROWSER_POLL_INTERVAL"):
            kwargs["browser_poll_interval"] = int(interval)
        
        if window := os.environ.get("DEJA_ACTIVITY_WINDOW_MINUTES"):
            kwargs["activity_window_minutes"] = int(window)
        
        if paths := os.environ.get("DEJA_WATCH_PATHS"):
            kwargs["watch_paths"] = [Path(p.strip()).expanduser() for p in paths.split(",")]
        
        if path := os.environ.get("DEJA_CHROME_HISTORY_PATH"):
            kwargs["chrome_history_path"] = Path(path).expanduser()
        
        if path := os.environ.get("DEJA_FIREFOX_HISTORY_PATH"):
            kwargs["firefox_history_path"] = Path(path).expanduser()
        
        return cls(**kwargs)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance.

    Creates a new configuration from environment variables if one
    hasn't been set yet.

    Returns:
        Config: The global configuration instance.
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance.

    Args:
        config: The configuration instance to use globally.
    """
    global _config
    _config = config
