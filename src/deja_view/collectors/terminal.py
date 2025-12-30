"""
Terminal activity collector for Deja View.

Parses shell history files (bash/zsh) to capture command history.
Associates commands with timestamps where available.
"""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set

from deja_view.collectors.base import BaseCollector
from deja_view.config import get_config
from deja_view.models import Event, EventType


class TerminalCollector(BaseCollector):
    """
    Collector for terminal/shell command history.
    
    Reads shell history files and extracts commands with timestamps.
    Supports bash and zsh history formats.
    """
    
    # Commands to ignore (too noisy or not useful)
    IGNORE_COMMANDS = {
        "ls", "cd", "pwd", "clear", "exit", "history",
        "ll", "la", "l", ".", "..",
    }
    
    def __init__(self, poll_interval: Optional[int] = None):
        """
        Initialize the terminal collector.
        
        Args:
            poll_interval: Seconds between history file checks
        """
        super().__init__("terminal")
        config = get_config()
        self.poll_interval = poll_interval or config.shell_history_poll_interval
        self.history_paths = config.shell_history_paths
        
        # Track seen commands to avoid duplicates
        self._seen_commands: Set[str] = set()
        self._file_positions: Dict[str, int] = {}
    
    def _parse_bash_history(self, content: str, start_pos: int = 0) -> List[Dict]:
        """
        Parse bash history format.
        
        Bash format: 
        - Simple: one command per line
        - Extended (HISTTIMEFORMAT): #timestamp\\ncommand
        
        Args:
            content: History file content
            start_pos: Position to start reading from
            
        Returns:
            List of command dictionaries
        """
        commands = []
        lines = content[start_pos:].split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for timestamp line
            if line.startswith("#") and line[1:].isdigit():
                try:
                    timestamp = datetime.fromtimestamp(int(line[1:]))
                    if i + 1 < len(lines):
                        cmd = lines[i + 1].strip()
                        if cmd and not self._should_ignore(cmd):
                            commands.append({
                                "command": cmd,
                                "timestamp": timestamp,
                                "shell": "bash",
                            })
                        i += 2
                        continue
                except (ValueError, OSError):
                    pass
            
            # Regular command line
            if line and not line.startswith("#") and not self._should_ignore(line):
                commands.append({
                    "command": line,
                    "timestamp": datetime.now(),
                    "shell": "bash",
                })
            
            i += 1
        
        return commands
    
    def _parse_zsh_history(self, content: str, start_pos: int = 0) -> List[Dict]:
        """
        Parse zsh history format.
        
        Zsh extended format: : timestamp:duration;command
        
        Args:
            content: History file content
            start_pos: Position to start reading from
            
        Returns:
            List of command dictionaries
        """
        commands = []
        lines = content[start_pos:].split("\n")
        
        # Pattern for extended history format
        extended_pattern = re.compile(r"^: (\d+):\d+;(.+)$")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try extended format
            match = extended_pattern.match(line)
            if match:
                try:
                    timestamp = datetime.fromtimestamp(int(match.group(1)))
                    cmd = match.group(2)
                    if not self._should_ignore(cmd):
                        commands.append({
                            "command": cmd,
                            "timestamp": timestamp,
                            "shell": "zsh",
                        })
                except (ValueError, OSError):
                    pass
            elif not self._should_ignore(line):
                # Simple format
                commands.append({
                    "command": line,
                    "timestamp": datetime.now(),
                    "shell": "zsh",
                })
        
        return commands
    
    def _should_ignore(self, command: str) -> bool:
        """
        Check if a command should be ignored.
        
        Args:
            command: Command string
            
        Returns:
            True if the command should be ignored
        """
        # Get base command
        base_cmd = command.split()[0] if command.split() else ""
        base_cmd = os.path.basename(base_cmd)
        
        return base_cmd.lower() in self.IGNORE_COMMANDS
    
    def _create_command_event(self, cmd_info: Dict) -> Event:
        """Create an event for a shell command."""
        command = cmd_info["command"]
        
        # Extract potential file paths from command
        files = []
        for part in command.split():
            if "/" in part or "\\" in part:
                files.append(part)
        
        return Event(
            event_type=EventType.SHELL_COMMAND,
            source=self.name,
            subject=command[:200],
            timestamp=cmd_info["timestamp"],
            description=f"Shell command ({cmd_info['shell']}): {command[:50]}",
            metadata={
                "shell": cmd_info["shell"],
                "referenced_files": files[:5],
                "command_length": len(command),
            }
        )
    
    def _read_new_history(self, shell: str, path: Path) -> List[Dict]:
        """
        Read new entries from a history file.
        
        Args:
            shell: Shell type (bash or zsh)
            path: Path to history file
            
        Returns:
            List of new command dictionaries
        """
        try:
            path_str = str(path)
            
            # Get current file size
            current_size = path.stat().st_size
            last_pos = self._file_positions.get(path_str, 0)
            
            # If file shrunk, reset position
            if current_size < last_pos:
                last_pos = 0
            
            # No new content
            if current_size == last_pos:
                return []
            
            # Read new content
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(last_pos)
                new_content = f.read()
                self._file_positions[path_str] = f.tell()
            
            # Parse based on shell type
            if shell == "bash":
                return self._parse_bash_history(new_content)
            elif shell == "zsh":
                return self._parse_zsh_history(new_content)
            
            return []
            
        except (IOError, OSError) as e:
            self.logger.debug(f"Error reading {path}: {e}")
            return []
    
    async def start(self) -> None:
        """Initialize terminal collector state."""
        # Set initial file positions to current end
        for shell, path in self.history_paths.items():
            if path.exists():
                try:
                    self._file_positions[str(path)] = path.stat().st_size
                    self.logger.info(f"Monitoring {shell} history: {path}")
                except OSError:
                    pass
    
    async def stop(self) -> None:
        """Clean up terminal collector."""
        self._seen_commands.clear()
        self._file_positions.clear()
    
    async def collect(self) -> AsyncIterator[Event]:
        """
        Yield terminal command events.
        
        Periodically checks history files for new commands
        and yields events for each new command.
        """
        while self._running:
            try:
                for shell, path in self.history_paths.items():
                    if not path.exists():
                        continue
                    
                    new_commands = self._read_new_history(shell, path)
                    
                    for cmd_info in new_commands:
                        # Create unique key to avoid duplicates
                        cmd_key = f"{cmd_info['timestamp'].isoformat()}:{cmd_info['command'][:100]}"
                        
                        if cmd_key not in self._seen_commands:
                            self._seen_commands.add(cmd_key)
                            yield self._create_command_event(cmd_info)
                            
                            # Limit seen commands cache
                            if len(self._seen_commands) > 10000:
                                # Remove oldest entries
                                to_remove = list(self._seen_commands)[:5000]
                                for key in to_remove:
                                    self._seen_commands.discard(key)
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in terminal collection: {e}")
                await asyncio.sleep(self.poll_interval)
