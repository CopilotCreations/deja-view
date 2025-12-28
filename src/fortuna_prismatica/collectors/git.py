"""
Git activity collector for Fortuna Prismatica.

Monitors git repositories for commits, branch changes, and other activity.
Polls git repositories found in watched directories.
"""

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set

from fortuna_prismatica.collectors.base import BaseCollector
from fortuna_prismatica.config import get_config
from fortuna_prismatica.models import Event, EventType


class GitCollector(BaseCollector):
    """
    Collector for git repository activity.
    
    Periodically scans for git repositories and tracks commits,
    branch changes, and other git operations.
    """
    
    def __init__(self, watch_paths: Optional[List[Path]] = None, poll_interval: int = 60):
        """
        Initialize the git collector.
        
        Args:
            watch_paths: Paths to scan for git repositories
            poll_interval: Seconds between repository scans
        """
        super().__init__("git")
        config = get_config()
        self.watch_paths = watch_paths or config.watch_paths
        self.poll_interval = poll_interval
        
        # Track state for change detection
        self._repo_states: Dict[str, Dict] = {}
        self._known_repos: Set[str] = set()
    
    def _run_git_command(self, repo_path: Path, *args: str) -> Optional[str]:
        """
        Run a git command in a repository.
        
        Args:
            repo_path: Path to the repository
            args: Git command arguments
            
        Returns:
            Command output or None if failed
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "--no-pager"] + list(args),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            self.logger.debug(f"Git command failed in {repo_path}: {e}")
            return None
    
    def _find_repositories(self) -> List[Path]:
        """
        Find git repositories in watched directories.
        
        Returns:
            List of repository root paths
        """
        repos = []
        for watch_path in self.watch_paths:
            if not watch_path.exists():
                continue
                
            # Check if watch_path itself is a repo
            if (watch_path / ".git").exists():
                repos.append(watch_path)
            
            # Search for repos (limit depth to avoid deep traversal)
            try:
                for item in watch_path.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        if (item / ".git").exists():
                            repos.append(item)
                        else:
                            # One more level deep
                            for subitem in item.iterdir():
                                if subitem.is_dir() and (subitem / ".git").exists():
                                    repos.append(subitem)
            except PermissionError:
                continue
        
        return repos
    
    def _get_repo_state(self, repo_path: Path) -> Dict:
        """
        Get the current state of a repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Dictionary with current branch, HEAD commit, etc.
        """
        state = {
            "path": str(repo_path),
            "branch": None,
            "head_commit": None,
            "last_commit_time": None,
            "commit_count": 0,
        }
        
        # Get current branch
        branch = self._run_git_command(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        if branch:
            state["branch"] = branch
        
        # Get HEAD commit
        head = self._run_git_command(repo_path, "rev-parse", "HEAD")
        if head:
            state["head_commit"] = head[:12]
        
        # Get last commit time
        commit_time = self._run_git_command(
            repo_path, "log", "-1", "--format=%ci"
        )
        if commit_time:
            state["last_commit_time"] = commit_time
        
        # Get commit count (approximate)
        count = self._run_git_command(repo_path, "rev-list", "--count", "HEAD")
        if count:
            try:
                state["commit_count"] = int(count)
            except ValueError:
                pass
        
        return state
    
    def _get_recent_commits(self, repo_path: Path, since_commit: Optional[str] = None) -> List[Dict]:
        """
        Get recent commits from a repository.
        
        Args:
            repo_path: Path to the repository
            since_commit: Only get commits after this one
            
        Returns:
            List of commit dictionaries
        """
        commits = []
        
        # Get commit log
        format_str = "%H|%s|%an|%ci"
        args = ["log", f"--format={format_str}", "-n", "10"]
        if since_commit:
            args.append(f"{since_commit}..HEAD")
        
        output = self._run_git_command(repo_path, *args)
        if not output:
            return commits
        
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:12],
                    "message": parts[1],
                    "author": parts[2],
                    "time": parts[3],
                })
        
        return commits
    
    def _create_commit_event(self, repo_path: str, branch: str, commit: Dict) -> Event:
        """Create an event for a git commit."""
        return Event(
            event_type=EventType.GIT_COMMIT,
            source=self.name,
            subject=commit["hash"],
            description=f"Commit: {commit['message'][:50]}",
            repository=repo_path,
            branch=branch,
            metadata={
                "author": commit["author"],
                "message": commit["message"],
                "commit_time": commit["time"],
            }
        )
    
    def _create_branch_event(
        self,
        repo_path: str,
        old_branch: Optional[str],
        new_branch: str
    ) -> Event:
        """Create an event for a branch switch."""
        return Event(
            event_type=EventType.GIT_BRANCH_SWITCH,
            source=self.name,
            subject=new_branch,
            subject_secondary=old_branch,
            description=f"Branch switch: {old_branch or 'unknown'} -> {new_branch}",
            repository=repo_path,
            branch=new_branch,
            metadata={
                "old_branch": old_branch,
            }
        )
    
    async def start(self) -> None:
        """Initialize git collector state."""
        # Initial scan of repositories
        repos = self._find_repositories()
        for repo in repos:
            state = self._get_repo_state(repo)
            self._repo_states[str(repo)] = state
            self._known_repos.add(str(repo))
        
        self.logger.info(f"Found {len(repos)} git repositories")
    
    async def stop(self) -> None:
        """Clean up git collector."""
        self._repo_states.clear()
        self._known_repos.clear()
    
    async def collect(self) -> AsyncIterator[Event]:
        """
        Yield git events as repositories change.
        
        Periodically polls repositories for changes and yields
        events for new commits, branch switches, etc.
        """
        while self._running:
            try:
                repos = self._find_repositories()
                
                for repo in repos:
                    repo_str = str(repo)
                    current_state = self._get_repo_state(repo)
                    previous_state = self._repo_states.get(repo_str, {})
                    
                    # Check for new repository
                    if repo_str not in self._known_repos:
                        self._known_repos.add(repo_str)
                        self.logger.info(f"Discovered repository: {repo}")
                    
                    # Check for branch change
                    old_branch = previous_state.get("branch")
                    new_branch = current_state.get("branch")
                    if old_branch and new_branch and old_branch != new_branch:
                        yield self._create_branch_event(repo_str, old_branch, new_branch)
                    
                    # Check for new commits
                    old_head = previous_state.get("head_commit")
                    new_head = current_state.get("head_commit")
                    if old_head and new_head and old_head != new_head:
                        commits = self._get_recent_commits(repo, old_head)
                        for commit in commits:
                            yield self._create_commit_event(
                                repo_str,
                                new_branch or "unknown",
                                commit
                            )
                    
                    # Update state
                    self._repo_states[repo_str] = current_state
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in git collection: {e}")
                await asyncio.sleep(self.poll_interval)
