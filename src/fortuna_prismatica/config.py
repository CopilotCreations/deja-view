"""
Configuration management for Fortuna Prismatica.

Provides centralized configuration with sensible defaults,
environment variable overrides, and platform-specific paths.
"""

import os
import platform
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def get_default_data_dir() -> Path:
    """Get the default data directory based on platform."""
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "fortuna"
    elif platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", home)) / "fortuna"
    else:
        return home / ".fortuna"


def get_default_watch_paths() -> List[Path]:
    """Get default paths to watch for filesystem events."""
    home = Path.home()
    paths = [home]
    
    for subdir in ["Documents", "Projects", "Code", "Development", "src"]:
        path = home / subdir
        if path.exists():
            paths.append(path)
    
    return paths


def get_chrome_history_path() -> Optional[Path]:
    """Get Chrome history database path based on platform."""
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
    """Get Firefox history database path based on platform."""
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
    """Get shell history file paths."""
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
        """Initialize derived fields after model creation."""
        if self.pid_file is None:
            self.pid_file = self.data_dir / "fortuna.pid"
    
    @property
    def database_path(self) -> Path:
        """Path to the DuckDB database file."""
        return self.data_dir / "events.duckdb"
    
    @property
    def graph_path(self) -> Path:
        """Path to the activity graph file."""
        return self.data_dir / "activity_graph.gpickle"
    
    @property
    def log_path(self) -> Path:
        """Path to the log file."""
        return self.data_dir / "fortuna.log"
    
    def ensure_data_dir(self) -> None:
        """Create the data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        kwargs = {}
        
        if data_dir := os.environ.get("FORTUNA_DATA_DIR"):
            kwargs["data_dir"] = Path(data_dir).expanduser()
        
        if log_level := os.environ.get("FORTUNA_LOG_LEVEL"):
            kwargs["log_level"] = log_level
        
        if interval := os.environ.get("FORTUNA_PROCESS_POLL_INTERVAL"):
            kwargs["process_poll_interval"] = int(interval)
        
        if interval := os.environ.get("FORTUNA_SHELL_HISTORY_POLL_INTERVAL"):
            kwargs["shell_history_poll_interval"] = int(interval)
        
        if interval := os.environ.get("FORTUNA_BROWSER_POLL_INTERVAL"):
            kwargs["browser_poll_interval"] = int(interval)
        
        if window := os.environ.get("FORTUNA_ACTIVITY_WINDOW_MINUTES"):
            kwargs["activity_window_minutes"] = int(window)
        
        if paths := os.environ.get("FORTUNA_WATCH_PATHS"):
            kwargs["watch_paths"] = [Path(p.strip()).expanduser() for p in paths.split(",")]
        
        if path := os.environ.get("FORTUNA_CHROME_HISTORY_PATH"):
            kwargs["chrome_history_path"] = Path(path).expanduser()
        
        if path := os.environ.get("FORTUNA_FIREFOX_HISTORY_PATH"):
            kwargs["firefox_history_path"] = Path(path).expanduser()
        
        return cls(**kwargs)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config
