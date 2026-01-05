"""
Daemon module for Deja View.

Provides the core daemon functionality for running collectors
and managing the agent lifecycle.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from deja_view.analysis.graph import ActivityGraph
from deja_view.analysis.inference import InferenceEngine
from deja_view.collectors import (
    BaseCollector,
    BrowserCollector,
    FilesystemCollector,
    GitCollector,
    ProcessCollector,
    TerminalCollector,
)
from deja_view.config import Config, get_config
from deja_view.models import Event
from deja_view.storage.database import EventDatabase


class Daemon:
    """
    Main daemon class for the Deja View agent.
    
    Manages collector lifecycle, event storage, and periodic
    analysis tasks. Runs as a long-lived asyncio process.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the daemon.
        
        Args:
            config: Optional configuration object.
                   Uses global config if not provided.
        """
        self.config = config or get_config()
        self.logger = logging.getLogger("deja.daemon")
        
        # Core components
        self.database: Optional[EventDatabase] = None
        self.graph: Optional[ActivityGraph] = None
        self.inference: Optional[InferenceEngine] = None
        
        # Collectors
        self.collectors: List[BaseCollector] = []
        
        # State
        self._running = False
        self._event_count = 0
        self._start_time: Optional[datetime] = None
    
    def _setup_logging(self) -> None:
        """Configure logging for the daemon.
        
        Sets up both console and file handlers with a standard format.
        The log level is determined by the configuration.
        """
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # File handler
        file_handler = logging.FileHandler(self.config.log_path)
        file_handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger("deja.)
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
    
    def _write_pid_file(self) -> None:
        """Write the current process ID to the PID file.
        
        The PID file location is determined by the configuration.
        """
        self.config.pid_file.write_text(str(os.getpid()))
        self.logger.info(f"PID file written: {self.config.pid_file}")
    
    def _remove_pid_file(self) -> None:
        """Remove the PID file if it exists.
        
        Called during daemon shutdown to clean up.
        """
        if self.config.pid_file.exists():
            self.config.pid_file.unlink()
            self.logger.info("PID file removed")
    
    def _handle_event(self, event: Event) -> None:
        """
        Handle an event from a collector.
        
        Args:
            event: Event to process
        """
        try:
            # Store in database
            self.database.insert_event(event)
            self._event_count += 1
            
            # Add to graph
            self.graph.add_event(event)
            
            self.logger.debug(f"Event processed: {event.event_type.value} - {event.subject[:50]}")
            
        except Exception as e:
            self.logger.error(f"Error handling event: {e}")
    
    def _init_collectors(self) -> None:
        """Initialize all event collectors.
        
        Attempts to initialize each collector type (filesystem, git, process,
        terminal, browser). Failures are logged but do not prevent other
        collectors from being initialized.
        """
        # Filesystem collector
        try:
            fs_collector = FilesystemCollector()
            fs_collector.set_event_callback(self._handle_event)
            self.collectors.append(fs_collector)
        except Exception as e:
            self.logger.warning(f"Failed to init filesystem collector: {e}")
        
        # Git collector
        try:
            git_collector = GitCollector()
            git_collector.set_event_callback(self._handle_event)
            self.collectors.append(git_collector)
        except Exception as e:
            self.logger.warning(f"Failed to init git collector: {e}")
        
        # Process collector
        try:
            process_collector = ProcessCollector()
            process_collector.set_event_callback(self._handle_event)
            self.collectors.append(process_collector)
        except Exception as e:
            self.logger.warning(f"Failed to init process collector: {e}")
        
        # Terminal collector
        try:
            terminal_collector = TerminalCollector()
            terminal_collector.set_event_callback(self._handle_event)
            self.collectors.append(terminal_collector)
        except Exception as e:
            self.logger.warning(f"Failed to init terminal collector: {e}")
        
        # Browser collector
        try:
            browser_collector = BrowserCollector()
            browser_collector.set_event_callback(self._handle_event)
            self.collectors.append(browser_collector)
        except Exception as e:
            self.logger.warning(f"Failed to init browser collector: {e}")
        
        self.logger.info(f"Initialized {len(self.collectors)} collectors")
    
    async def _periodic_save(self, interval_seconds: int = 300) -> None:
        """
        Periodically save the activity graph.
        
        Args:
            interval_seconds: Save interval in seconds
        """
        while self._running:
            await asyncio.sleep(interval_seconds)
            try:
                self.graph.save()
                self.logger.debug("Activity graph saved")
            except Exception as e:
                self.logger.error(f"Failed to save graph: {e}")
    
    async def _status_reporter(self, interval_seconds: int = 60) -> None:
        """
        Periodically log status information.
        
        Args:
            interval_seconds: Report interval in seconds
        """
        while self._running:
            await asyncio.sleep(interval_seconds)
            uptime = datetime.now() - self._start_time if self._start_time else timedelta()
            self.logger.info(
                f"Status: {self._event_count} events collected, "
                f"uptime {str(uptime).split('.')[0]}"
            )
    
    async def start(self) -> None:
        """Start the daemon and all collectors.
        
        Initializes the database, activity graph, inference engine, and
        all collectors. Writes the PID file and sets the running state.
        """
        # Ensure data directory exists
        self.config.ensure_data_dir()
        
        # Setup logging
        self._setup_logging()
        
        self.logger.info("Starting Deja View daemon...")
        
        # Initialize core components
        self.database = EventDatabase()
        self.database.connect()
        
        self.graph = ActivityGraph()
        self.graph.load()  # Load existing graph if available
        
        self.inference = InferenceEngine()
        
        # Initialize collectors
        self._init_collectors()
        
        # Write PID file
        self._write_pid_file()
        
        # Set running state
        self._running = True
        self._start_time = datetime.now()
        
        self.logger.info("Daemon started successfully")
    
    async def run(self) -> None:
        """Run the daemon main loop.
        
        Starts all collectors and periodic tasks, then waits for them
        to complete or be cancelled. Ensures proper cleanup on exit.
        """
        await self.start()
        
        try:
            # Start all collector tasks
            tasks = [collector.start_task() for collector in self.collectors]
            
            # Start periodic tasks
            tasks.append(asyncio.create_task(self._periodic_save()))
            tasks.append(asyncio.create_task(self._status_reporter()))
            
            # Wait for all tasks (they run indefinitely)
            await asyncio.gather(*tasks)
            
        except asyncio.CancelledError:
            self.logger.info("Daemon received cancel signal")
        except Exception as e:
            self.logger.error(f"Daemon error: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the daemon and all collectors.
        
        Gracefully stops all collectors, saves the activity graph,
        closes the database, and removes the PID file.
        """
        self.logger.info("Stopping daemon...")
        self._running = False
        
        # Stop all collectors
        for collector in self.collectors:
            try:
                await collector.stop_task()
            except Exception as e:
                self.logger.warning(f"Error stopping collector {collector.name}: {e}")
        
        # Save graph
        if self.graph:
            try:
                self.graph.save()
            except Exception as e:
                self.logger.error(f"Failed to save graph: {e}")
        
        # Close database
        if self.database:
            try:
                self.database.close()
            except Exception as e:
                self.logger.error(f"Failed to close database: {e}")
        
        # Remove PID file
        self._remove_pid_file()
        
        self.logger.info(f"Daemon stopped. Total events collected: {self._event_count}")
    
    @property
    def is_running(self) -> bool:
        """Check if the daemon is running.
        
        Returns:
            True if the daemon is currently running, False otherwise.
        """
        return self._running
    
    @property
    def uptime(self) -> Optional[float]:
        """Get daemon uptime in seconds.
        
        Returns:
            The uptime in seconds if the daemon has started, None otherwise.
        """
        if self._start_time:
            return (datetime.now() - self._start_time).total_seconds()
        return None
    
    @property
    def event_count(self) -> int:
        """Get the number of events collected.
        
        Returns:
            The total count of events processed by this daemon instance.
        """
        return self._event_count


def run_daemon() -> None:
    """Run the daemon in the foreground.
    
    Creates a daemon instance, sets up signal handlers for graceful
    shutdown, and runs the event loop until completion or interruption.
    """
    daemon = Daemon()
    
    # Handle signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler():
        loop.create_task(daemon.stop())
    
    # Setup signal handlers
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    
    try:
        loop.run_until_complete(daemon.run())
    except KeyboardInterrupt:
        loop.run_until_complete(daemon.stop())
    finally:
        loop.close()


def get_daemon_pid() -> Optional[int]:
    """Get the PID of a running daemon if any.
    
    Reads the PID file and verifies the process is actually running.
    Cleans up stale PID files if the process is no longer running.
    
    Returns:
        The PID of the running daemon, or None if no daemon is running.
    """
    config = get_config()
    if config.pid_file.exists():
        try:
            pid = int(config.pid_file.read_text().strip())
            # Check if process is actually running
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                # Process not running, clean up stale PID file
                config.pid_file.unlink()
                return None
        except (ValueError, IOError):
            return None
    return None


def is_daemon_running() -> bool:
    """Check if the daemon is currently running.
    
    Returns:
        True if a daemon process is running, False otherwise.
    """
    return get_daemon_pid() is not None
