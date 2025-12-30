"""
Process activity collector for Deja View.

Monitors running processes to track application usage patterns.
Samples active processes at regular intervals.
"""

import asyncio
import platform
from datetime import datetime
from typing import AsyncIterator, Dict, Optional, Set

import psutil

from deja_view.collectors.base import BaseCollector
from deja_view.config import get_config
from deja_view.models import Event, EventType


class ProcessCollector(BaseCollector):
    """
    Collector for process activity events.
    
    Periodically samples running processes and tracks which applications
    are actively being used. Focuses on user-interactive processes.
    """
    
    # Processes to ignore (system processes, etc.)
    IGNORE_PROCESSES = {
        "systemd", "init", "kthreadd", "migration", "watchdog",
        "launchd", "kernel_task", "WindowServer", "loginwindow",
        "System", "csrss", "smss", "wininit", "services", "lsass",
        "svchost", "dwm", "explorer", "RuntimeBroker", "ShellExperienceHost",
    }
    
    # Process categories for classification
    PROCESS_CATEGORIES = {
        "browser": {"chrome", "firefox", "safari", "edge", "brave", "opera", "chromium"},
        "editor": {"code", "vim", "nvim", "emacs", "sublime", "atom", "notepad++", "idea", "pycharm", "webstorm"},
        "terminal": {"terminal", "iterm", "alacritty", "kitty", "gnome-terminal", "konsole", "wt", "powershell", "cmd"},
        "communication": {"slack", "discord", "teams", "zoom", "skype", "telegram", "signal"},
        "productivity": {"word", "excel", "powerpoint", "libreoffice", "notion", "obsidian"},
        "development": {"docker", "node", "python", "java", "go", "rust", "cargo", "npm", "pip"},
    }
    
    def __init__(self, poll_interval: Optional[int] = None):
        """
        Initialize the process collector.
        
        Args:
            poll_interval: Seconds between process samples
        """
        super().__init__("process")
        config = get_config()
        self.poll_interval = poll_interval or config.process_poll_interval
        
        # Track process state
        self._active_processes: Dict[int, Dict] = {}
        self._seen_pids: Set[int] = set()
    
    def _categorize_process(self, name: str) -> Optional[str]:
        """
        Categorize a process by its name.
        
        Args:
            name: Process name (lowercase)
            
        Returns:
            Category string or None if uncategorized
        """
        name_lower = name.lower()
        for category, processes in self.PROCESS_CATEGORIES.items():
            for proc in processes:
                if proc in name_lower:
                    return category
        return None
    
    def _should_track(self, proc_info: Dict) -> bool:
        """
        Determine if a process should be tracked.
        
        Args:
            proc_info: Process information dictionary
            
        Returns:
            True if the process should be tracked
        """
        name = proc_info.get("name", "").lower()
        
        # Skip ignored processes
        for ignored in self.IGNORE_PROCESSES:
            if ignored.lower() in name:
                return False
        
        # Skip processes with very low CPU and memory
        cpu = proc_info.get("cpu_percent", 0) or 0
        memory = proc_info.get("memory_percent", 0) or 0
        
        # Track if categorizable or has notable resource usage
        if self._categorize_process(name):
            return True
        
        return cpu > 1.0 or memory > 1.0
    
    def _get_process_info(self, proc: psutil.Process) -> Optional[Dict]:
        """
        Get information about a process.
        
        Args:
            proc: psutil Process object
            
        Returns:
            Process info dictionary or None if unavailable
        """
        try:
            with proc.oneshot():
                info = {
                    "pid": proc.pid,
                    "name": proc.name(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_percent": proc.memory_percent(),
                    "status": proc.status(),
                    "create_time": proc.create_time(),
                }
                
                try:
                    info["cmdline"] = " ".join(proc.cmdline())[:200]
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    info["cmdline"] = None
                
                try:
                    info["cwd"] = proc.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    info["cwd"] = None
                
                return info
                
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
    
    def _create_process_event(
        self,
        event_type: EventType,
        proc_info: Dict
    ) -> Event:
        """Create an event for process activity."""
        category = self._categorize_process(proc_info["name"])
        
        return Event(
            event_type=event_type,
            source=self.name,
            subject=proc_info["name"],
            description=f"Process {event_type.value.split('.')[1]}: {proc_info['name']}",
            process_name=proc_info["name"],
            process_id=proc_info["pid"],
            metadata={
                "category": category,
                "cpu_percent": proc_info.get("cpu_percent"),
                "memory_percent": proc_info.get("memory_percent"),
                "cmdline": proc_info.get("cmdline"),
                "cwd": proc_info.get("cwd"),
            }
        )
    
    async def start(self) -> None:
        """Initialize process collector state."""
        # Initial CPU percent reading (first call always returns 0)
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        await asyncio.sleep(0.1)
        self.logger.info("Process collector initialized")
    
    async def stop(self) -> None:
        """Clean up process collector."""
        self._active_processes.clear()
        self._seen_pids.clear()
    
    async def collect(self) -> AsyncIterator[Event]:
        """
        Yield process events at regular intervals.
        
        Samples running processes and yields events for
        notable process activity.
        """
        while self._running:
            try:
                current_pids: Set[int] = set()
                
                for proc in psutil.process_iter():
                    proc_info = self._get_process_info(proc)
                    if not proc_info or not self._should_track(proc_info):
                        continue
                    
                    pid = proc_info["pid"]
                    current_pids.add(pid)
                    
                    # New process
                    if pid not in self._seen_pids:
                        self._seen_pids.add(pid)
                        self._active_processes[pid] = proc_info
                        yield self._create_process_event(EventType.PROCESS_START, proc_info)
                    
                    # Active process (significant CPU usage)
                    elif proc_info.get("cpu_percent", 0) > 5.0:
                        yield self._create_process_event(EventType.PROCESS_ACTIVE, proc_info)
                        self._active_processes[pid] = proc_info
                
                # Detect ended processes
                ended_pids = self._seen_pids - current_pids
                for pid in ended_pids:
                    if pid in self._active_processes:
                        proc_info = self._active_processes[pid]
                        yield self._create_process_event(EventType.PROCESS_END, proc_info)
                        del self._active_processes[pid]
                    self._seen_pids.discard(pid)
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in process collection: {e}")
                await asyncio.sleep(self.poll_interval)
