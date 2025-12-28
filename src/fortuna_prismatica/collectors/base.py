"""
Base collector interface for Fortuna Prismatica.

Defines the abstract base class that all collectors must implement.
Provides common functionality for event collection and lifecycle management.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable, Optional

from fortuna_prismatica.models import Event


class BaseCollector(ABC):
    """
    Abstract base class for all event collectors.
    
    Collectors are responsible for observing a specific source of activity
    (filesystem, git, processes, etc.) and generating normalized Event objects.
    """
    
    def __init__(self, name: str):
        """
        Initialize the collector.
        
        Args:
            name: Unique identifier for this collector
        """
        self.name = name
        self.logger = logging.getLogger(f"fortuna.collectors.{name}")
        self._running = False
        self._event_callback: Optional[Callable[[Event], None]] = None
        self._task: Optional[asyncio.Task] = None
    
    @property
    def is_running(self) -> bool:
        """Check if the collector is currently running."""
        return self._running
    
    def set_event_callback(self, callback: Callable[[Event], None]) -> None:
        """
        Set the callback function for emitting events.
        
        Args:
            callback: Function to call with each collected event
        """
        self._event_callback = callback
    
    def emit_event(self, event: Event) -> None:
        """
        Emit an event through the registered callback.
        
        Args:
            event: The event to emit
        """
        if self._event_callback:
            self._event_callback(event)
        else:
            self.logger.warning("Event emitted but no callback registered")
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the collector.
        
        This method should initialize any resources needed for collection
        and begin the collection process.
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the collector.
        
        This method should clean up resources and stop the collection process.
        """
        pass
    
    @abstractmethod
    async def collect(self) -> AsyncIterator[Event]:
        """
        Generator that yields collected events.
        
        This is the main collection loop that should continuously
        yield events as they are observed.
        
        Yields:
            Event objects as they are collected
        """
        pass
    
    async def run(self) -> None:
        """
        Run the collector in a continuous loop.
        
        This method starts the collector and processes events
        through the registered callback.
        """
        self._running = True
        self.logger.info(f"Starting collector: {self.name}")
        
        try:
            await self.start()
            async for event in self.collect():
                if not self._running:
                    break
                self.emit_event(event)
        except asyncio.CancelledError:
            self.logger.info(f"Collector cancelled: {self.name}")
        except Exception as e:
            self.logger.error(f"Collector error: {e}", exc_info=True)
        finally:
            await self.stop()
            self._running = False
            self.logger.info(f"Stopped collector: {self.name}")
    
    def start_task(self) -> asyncio.Task:
        """
        Start the collector as an asyncio task.
        
        Returns:
            The created task
        """
        self._task = asyncio.create_task(self.run())
        return self._task
    
    async def stop_task(self) -> None:
        """Stop the collector task if running."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
