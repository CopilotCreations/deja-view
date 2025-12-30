"""
Activity inference engine for Deja View.

Groups events into time windows and clusters them into
inferred "tasks" with confidence scores.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from deja_view.config import get_config
from deja_view.models import ActivityWindow, Event, EventType


class InferenceEngine:
    """
    Inference engine for activity analysis.
    
    Groups events into time windows and uses heuristics to
    cluster related events into coherent tasks.
    """
    
    # Event type weights for task scoring
    EVENT_WEIGHTS = {
        EventType.FILE_CREATE: 0.8,
        EventType.FILE_MODIFY: 0.7,
        EventType.FILE_DELETE: 0.5,
        EventType.FILE_MOVE: 0.6,
        EventType.GIT_COMMIT: 1.0,
        EventType.GIT_BRANCH_SWITCH: 0.9,
        EventType.GIT_BRANCH_CREATE: 0.8,
        EventType.PROCESS_START: 0.6,
        EventType.PROCESS_ACTIVE: 0.4,
        EventType.SHELL_COMMAND: 0.7,
        EventType.BROWSER_VISIT: 0.5,
    }
    
    # Task label patterns based on activity signatures
    TASK_PATTERNS = {
        "coding": {
            "required_types": {EventType.FILE_MODIFY},
            "optional_types": {EventType.GIT_COMMIT, EventType.SHELL_COMMAND},
            "process_hints": {"code", "vim", "nvim", "pycharm", "idea"},
        },
        "research": {
            "required_types": {EventType.BROWSER_VISIT},
            "optional_types": set(),
            "process_hints": {"chrome", "firefox", "safari"},
            "min_browser_visits": 3,
        },
        "git_workflow": {
            "required_types": {EventType.GIT_COMMIT},
            "optional_types": {EventType.GIT_BRANCH_SWITCH},
            "process_hints": set(),
        },
        "terminal_work": {
            "required_types": {EventType.SHELL_COMMAND},
            "optional_types": set(),
            "process_hints": {"terminal", "iterm", "alacritty"},
            "min_commands": 3,
        },
        "file_organization": {
            "required_types": {EventType.FILE_MOVE, EventType.FILE_DELETE},
            "optional_types": set(),
            "process_hints": {"finder", "explorer"},
        },
    }
    
    def __init__(self, window_minutes: Optional[int] = None):
        """
        Initialize the inference engine.
        
        Args:
            window_minutes: Size of activity windows in minutes
        """
        config = get_config()
        self.window_minutes = window_minutes or config.activity_window_minutes
        self.logger = logging.getLogger("deja.analysis.inference")
    
    def create_windows(
        self,
        events: List[Event],
        gap_threshold_minutes: int = 5
    ) -> List[ActivityWindow]:
        """
        Group events into activity windows.
        
        Windows are created based on time gaps between events.
        Events within gap_threshold of each other are grouped together.
        
        Args:
            events: List of events to group
            gap_threshold_minutes: Maximum gap between events in same window
            
        Returns:
            List of activity windows
        """
        if not events:
            return []
        
        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        
        windows: List[ActivityWindow] = []
        current_window: Optional[ActivityWindow] = None
        
        gap_threshold = timedelta(minutes=gap_threshold_minutes)
        
        for event in sorted_events:
            if current_window is None:
                # Start new window
                current_window = ActivityWindow(
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    events=[event],
                )
            elif event.timestamp - current_window.end_time <= gap_threshold:
                # Add to current window
                current_window.add_event(event)
            else:
                # Close current window and start new one
                windows.append(current_window)
                current_window = ActivityWindow(
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    events=[event],
                )
        
        # Don't forget the last window
        if current_window:
            windows.append(current_window)
        
        return windows
    
    def _get_event_types(self, window: ActivityWindow) -> Set[EventType]:
        """Get the set of event types in a window."""
        return {event.event_type for event in window.events}
    
    def _get_process_names(self, window: ActivityWindow) -> Set[str]:
        """Get the set of process names in a window."""
        names = set()
        for event in window.events:
            if event.process_name:
                names.add(event.process_name.lower())
        return names
    
    def _count_event_type(self, window: ActivityWindow, event_type: EventType) -> int:
        """Count events of a specific type in a window."""
        return sum(1 for e in window.events if e.event_type == event_type)
    
    def _extract_key_subjects(self, window: ActivityWindow) -> List[str]:
        """
        Extract the most significant subjects from a window.
        
        Args:
            window: Activity window to analyze
            
        Returns:
            List of key subject strings
        """
        subject_scores: Dict[str, float] = defaultdict(float)
        
        for event in window.events:
            weight = self.EVENT_WEIGHTS.get(event.event_type, 0.5)
            subject_scores[event.subject] += weight
            
            if event.repository:
                subject_scores[event.repository] += weight * 1.5
        
        # Sort by score and return top subjects
        sorted_subjects = sorted(
            subject_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [s[0] for s in sorted_subjects[:5]]
    
    def infer_task(self, window: ActivityWindow) -> Tuple[str, float]:
        """
        Infer the task label for an activity window.
        
        Args:
            window: Activity window to analyze
            
        Returns:
            Tuple of (task_label, confidence_score)
        """
        event_types = self._get_event_types(window)
        process_names = self._get_process_names(window)
        
        best_match = ("general_activity", 0.3)
        
        for task_name, pattern in self.TASK_PATTERNS.items():
            required = pattern["required_types"]
            optional = pattern["optional_types"]
            hints = pattern["process_hints"]
            
            # Check if required types are present
            if not required.issubset(event_types):
                continue
            
            # Base score from required match
            score = 0.5
            
            # Bonus for optional types
            optional_matches = optional.intersection(event_types)
            score += len(optional_matches) * 0.1
            
            # Bonus for process hints
            hint_matches = hints.intersection(process_names)
            score += len(hint_matches) * 0.15
            
            # Check minimum counts if specified
            if "min_browser_visits" in pattern:
                if self._count_event_type(window, EventType.BROWSER_VISIT) < pattern["min_browser_visits"]:
                    score *= 0.5
            
            if "min_commands" in pattern:
                if self._count_event_type(window, EventType.SHELL_COMMAND) < pattern["min_commands"]:
                    score *= 0.5
            
            # Normalize score
            score = min(score, 1.0)
            
            if score > best_match[1]:
                best_match = (task_name, score)
        
        return best_match
    
    def analyze_windows(
        self,
        windows: List[ActivityWindow]
    ) -> List[ActivityWindow]:
        """
        Analyze windows and add task inferences.
        
        Args:
            windows: List of activity windows
            
        Returns:
            Windows with task labels and confidence scores
        """
        for window in windows:
            task_label, confidence = self.infer_task(window)
            window.task_label = task_label
            window.task_confidence = confidence
            window.key_subjects = self._extract_key_subjects(window)
        
        return windows
    
    def detect_context_switches(
        self,
        windows: List[ActivityWindow],
        threshold: float = 0.3
    ) -> List[Tuple[ActivityWindow, ActivityWindow, str]]:
        """
        Detect context switches between windows.
        
        Args:
            windows: List of analyzed activity windows
            threshold: Minimum dissimilarity for a context switch
            
        Returns:
            List of (from_window, to_window, description) tuples
        """
        switches = []
        
        for i in range(1, len(windows)):
            prev = windows[i - 1]
            curr = windows[i]
            
            # Check for task type change
            if prev.task_label != curr.task_label:
                # Check for significant gap
                gap = (curr.start_time - prev.end_time).total_seconds() / 60
                
                # Calculate subject overlap
                prev_subjects = set(prev.key_subjects)
                curr_subjects = set(curr.key_subjects)
                overlap = len(prev_subjects.intersection(curr_subjects))
                
                if overlap == 0 or gap > 30:
                    description = f"Switched from {prev.task_label} to {curr.task_label}"
                    if gap > 30:
                        description += f" (after {int(gap)} min break)"
                    switches.append((prev, curr, description))
        
        return switches
    
    def find_stalled_tasks(
        self,
        windows: List[ActivityWindow],
        stall_threshold_minutes: int = 60
    ) -> List[Tuple[ActivityWindow, str]]:
        """
        Find tasks that appear to have stalled.
        
        Args:
            windows: List of analyzed activity windows
            stall_threshold_minutes: Minimum gap to consider a stall
            
        Returns:
            List of (window, reason) tuples for stalled tasks
        """
        stalls = []
        threshold = timedelta(minutes=stall_threshold_minutes)
        
        # Group windows by repository/project
        project_windows: Dict[str, List[ActivityWindow]] = defaultdict(list)
        
        for window in windows:
            for subject in window.key_subjects:
                if "/" in subject or "\\" in subject:
                    project_windows[subject].append(window)
        
        for project, proj_windows in project_windows.items():
            if len(proj_windows) < 2:
                continue
            
            sorted_windows = sorted(proj_windows, key=lambda w: w.end_time)
            
            for i in range(len(sorted_windows) - 1):
                current = sorted_windows[i]
                next_window = sorted_windows[i + 1]
                gap = next_window.start_time - current.end_time
                
                if gap > threshold:
                    reason = f"Work on {project} paused for {int(gap.total_seconds() / 60)} minutes"
                    stalls.append((current, reason))
        
        return stalls
    
    def get_activity_summary(
        self,
        windows: List[ActivityWindow]
    ) -> Dict:
        """
        Generate a summary of activity across windows.
        
        Args:
            windows: List of analyzed activity windows
            
        Returns:
            Dictionary with activity summary
        """
        if not windows:
            return {"total_windows": 0}
        
        task_counts: Dict[str, int] = defaultdict(int)
        total_events = 0
        
        for window in windows:
            task_counts[window.task_label] += 1
            total_events += len(window.events)
        
        time_span = windows[-1].end_time - windows[0].start_time
        
        return {
            "total_windows": len(windows),
            "total_events": total_events,
            "time_span_minutes": time_span.total_seconds() / 60,
            "task_distribution": dict(task_counts),
            "dominant_task": max(task_counts.items(), key=lambda x: x[1])[0] if task_counts else None,
            "context_switches": len(self.detect_context_switches(windows)),
        }
