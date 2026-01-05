"""
Filesystem activity collector for Deja View.

Monitors file create, modify, and delete events using watchdog.
Provides real-time filesystem activity tracking.
"""

import asyncio
import platform
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import AsyncIterator, List, Optional

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from deja_view.collectors.base import BaseCollector
from deja_view.config import get_config
from deja_view.models import Event, EventType


class FilesystemEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler that queues filesystem events.
    
    Filters out common noise patterns and normalizes events
    for processing by the collector.
    """
    
    # Patterns to ignore (temporary files, IDE files, etc.)
    IGNORE_PATTERNS = [
        ".git/",
        "__pycache__/",
        ".pyc",
        ".pyo",
        ".swp",
        ".swo",
        "~",
        ".DS_Store",
        "Thumbs.db",
        ".idea/",
        ".vscode/",
        "node_modules/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".duckdb.wal",
    ]
    
    def __init__(self, event_queue: Queue):
        """
        Initialize the handler.
        
        Args:
            event_queue: Queue to push events into
        """
        super().__init__()
        self.event_queue = event_queue
    
    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored based on ignore patterns.
        
        Args:
            path: The file path to check.
            
        Returns:
            True if the path matches any ignore pattern, False otherwise.
        """
        for pattern in self.IGNORE_PATTERNS:
            if pattern in path:
                return True
        return False
    
    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events.
        
        Args:
            event: The filesystem event containing the created file path.
        """
        if not event.is_directory and not self._should_ignore(event.src_path):
            self.event_queue.put(("create", event.src_path, None))
    
    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.
        
        Args:
            event: The filesystem event containing the modified file path.
        """
        if not event.is_directory and not self._should_ignore(event.src_path):
            self.event_queue.put(("modify", event.src_path, None))
    
    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events.
        
        Args:
            event: The filesystem event containing the deleted file path.
        """
        if not event.is_directory and not self._should_ignore(event.src_path):
            self.event_queue.put(("delete", event.src_path, None))
    
    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events.
        
        Args:
            event: The filesystem event containing source and destination paths.
        """
        if not event.is_directory:
            if not self._should_ignore(event.src_path) and not self._should_ignore(event.dest_path):
                self.event_queue.put(("move", event.src_path, event.dest_path))


class FilesystemCollector(BaseCollector):
    """
    Collector for filesystem activity events.
    
    Uses watchdog to monitor specified directories for file changes.
    Normalizes events into the unified Event model.
    """
    
    def __init__(self, watch_paths: Optional[List[Path]] = None):
        """
        Initialize the filesystem collector.
        
        Args:
            watch_paths: List of paths to monitor. Uses config defaults if not provided.
        """
        super().__init__("filesystem")
        config = get_config()
        self.watch_paths = watch_paths or config.watch_paths
        self._event_queue: Queue = Queue()
        self._observer: Optional[Observer] = None
        self._handler: Optional[FilesystemEventHandler] = None
    
    def _find_repository(self, path: Path) -> Optional[str]:
        """
        Find the git repository containing a file.
        
        Args:
            path: Path to check
            
        Returns:
            Repository root path if found, None otherwise
        """
        current = path if path.is_dir() else path.parent
        while current != current.parent:
            if (current / ".git").exists():
                return str(current)
            current = current.parent
        return None
    
    def _create_event(
        self,
        event_type: EventType,
        path: str,
        dest_path: Optional[str] = None
    ) -> Event:
        """
        Create a normalized Event from filesystem data.
        
        Args:
            event_type: Type of filesystem event
            path: Source path
            dest_path: Destination path (for move events)
            
        Returns:
            Normalized Event object
        """
        file_path = Path(path)
        repo = self._find_repository(file_path)
        
        description = f"File {event_type.value.split('.')[1]}: {file_path.name}"
        if dest_path:
            description = f"File moved: {file_path.name} -> {Path(dest_path).name}"
        
        return Event(
            event_type=event_type,
            source=self.name,
            subject=str(path),
            subject_secondary=dest_path,
            description=description,
            repository=repo,
            metadata={
                "extension": file_path.suffix,
                "parent_dir": str(file_path.parent),
            }
        )
    
    async def start(self) -> None:
        """Start the filesystem observer.
        
        Initializes the watchdog observer and schedules monitoring
        for all configured watch paths.
        """
        self._handler = FilesystemEventHandler(self._event_queue)
        self._observer = Observer()
        
        for path in self.watch_paths:
            if path.exists():
                try:
                    self._observer.schedule(
                        self._handler,
                        str(path),
                        recursive=True
                    )
                    self.logger.info(f"Watching: {path}")
                except Exception as e:
                    self.logger.warning(f"Failed to watch {path}: {e}")
            else:
                self.logger.warning(f"Watch path does not exist: {path}")
        
        self._observer.start()
    
    async def stop(self) -> None:
        """Stop the filesystem observer.
        
        Stops the watchdog observer and waits for it to terminate.
        """
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
    
    async def collect(self) -> AsyncIterator[Event]:
        """
        Yield filesystem events as they occur.
        
        Polls the event queue and yields normalized events.
        """
        event_type_map = {
            "create": EventType.FILE_CREATE,
            "modify": EventType.FILE_MODIFY,
            "delete": EventType.FILE_DELETE,
            "move": EventType.FILE_MOVE,
        }
        
        while self._running:
            try:
                # Non-blocking check with timeout
                await asyncio.sleep(0.1)
                
                while not self._event_queue.empty():
                    action, src_path, dest_path = self._event_queue.get_nowait()
                    event_type = event_type_map.get(action)
                    
                    if event_type:
                        yield self._create_event(event_type, src_path, dest_path)
                        
            except Exception as e:
                self.logger.error(f"Error processing filesystem event: {e}")
                await asyncio.sleep(1.0)
