"""
Narrative generation for Fortuna Prismatica.

Generates Markdown explanations of user activity based on
analyzed events and activity windows. Uses rule-based
generation for reproducible, deterministic output.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

from fortuna_prismatica.analysis.graph import ActivityGraph
from fortuna_prismatica.analysis.inference import InferenceEngine
from fortuna_prismatica.models import ActivityWindow, Event, EventType
from fortuna_prismatica.storage.database import EventDatabase


class NarrativeGenerator:
    """
    Rule-based narrative generator.
    
    Produces Markdown explanations of user activity using
    deterministic rules. LLM hooks are clearly isolated
    and optional.
    """
    
    # Task descriptions for human-readable output
    TASK_DESCRIPTIONS = {
        "coding": "writing and editing code",
        "research": "researching and browsing the web",
        "git_workflow": "managing version control",
        "terminal_work": "working in the terminal",
        "file_organization": "organizing files",
        "general_activity": "various activities",
    }
    
    # Time format for readable output
    TIME_FORMAT = "%Y-%m-%d %H:%M"
    
    def __init__(
        self,
        database: EventDatabase,
        graph: ActivityGraph,
        inference_engine: Optional[InferenceEngine] = None,
        llm_hook: Optional[Callable[[str], str]] = None
    ):
        """
        Initialize the narrative generator.
        
        Args:
            database: Event database for querying events
            graph: Activity graph for relationship analysis
            inference_engine: Optional custom inference engine
            llm_hook: Optional LLM function for enhanced narratives.
                     Takes a prompt string, returns enhanced text.
                     This is isolated and optional.
        """
        self.database = database
        self.graph = graph
        self.inference = inference_engine or InferenceEngine()
        self.llm_hook = llm_hook
        self.logger = logging.getLogger("fortuna.reporting.narrative")
    
    def _format_duration(self, seconds: float) -> str:
        """Format a duration in human-readable form."""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            return f"{int(seconds / 60)} minutes"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours} hours, {minutes} minutes"
    
    def _format_time_range(self, start: datetime, end: datetime) -> str:
        """Format a time range for display."""
        if start.date() == end.date():
            return f"{start.strftime(self.TIME_FORMAT)} - {end.strftime('%H:%M')}"
        return f"{start.strftime(self.TIME_FORMAT)} - {end.strftime(self.TIME_FORMAT)}"
    
    def _get_file_summary(self, paths: List[str]) -> str:
        """Summarize a list of file paths."""
        if not paths:
            return "no files"
        
        # Group by directory
        dirs: Dict[str, int] = {}
        for path in paths:
            p = Path(path)
            parent = str(p.parent)
            dirs[parent] = dirs.get(parent, 0) + 1
        
        if len(dirs) == 1:
            dir_name = list(dirs.keys())[0]
            return f"{len(paths)} files in {Path(dir_name).name}/"
        
        return f"{len(paths)} files across {len(dirs)} directories"
    
    def _generate_window_summary(self, window: ActivityWindow) -> str:
        """Generate a summary for a single activity window."""
        task_desc = self.TASK_DESCRIPTIONS.get(
            window.task_label,
            "various activities"
        )
        
        time_range = self._format_time_range(window.start_time, window.end_time)
        duration = self._format_duration(window.duration_seconds)
        
        # Count event types
        type_counts: Dict[str, int] = {}
        for event in window.events:
            type_name = event.event_type.value.split('.')[0]
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        summary = f"**{time_range}** ({duration})\n"
        summary += f"- Primary activity: {task_desc}\n"
        summary += f"- Confidence: {window.task_confidence:.0%}\n"
        summary += f"- Events: {len(window.events)} "
        summary += f"({', '.join(f'{v} {k}' for k, v in type_counts.items())})\n"
        
        if window.key_subjects:
            summary += f"- Key subjects: {', '.join(Path(s).name for s in window.key_subjects[:3])}\n"
        
        return summary
    
    def explain_time_window(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> str:
        """
        Generate a narrative explaining activity in a time window.
        
        Args:
            start_time: Start of the time window
            end_time: End of the time window
            
        Returns:
            Markdown narrative explaining the activity
        """
        # Query events
        events = self.database.get_events_in_range(start_time, end_time)
        
        if not events:
            return f"# Activity Report\n\nNo activity recorded between {start_time.strftime(self.TIME_FORMAT)} and {end_time.strftime(self.TIME_FORMAT)}.\n"
        
        # Create and analyze windows
        windows = self.inference.create_windows(events)
        windows = self.inference.analyze_windows(windows)
        
        # Get summary statistics
        summary = self.inference.get_activity_summary(windows)
        
        # Build narrative
        narrative = "# Activity Report\n\n"
        narrative += f"**Period:** {self._format_time_range(start_time, end_time)}\n\n"
        
        narrative += "## Summary\n\n"
        narrative += f"- **Total events:** {summary['total_events']}\n"
        narrative += f"- **Activity windows:** {summary['total_windows']}\n"
        if summary.get('dominant_task'):
            narrative += f"- **Primary focus:** {self.TASK_DESCRIPTIONS.get(summary['dominant_task'], summary['dominant_task'])}\n"
        narrative += f"- **Context switches:** {summary.get('context_switches', 0)}\n\n"
        
        # Task distribution
        if summary.get('task_distribution'):
            narrative += "## Task Distribution\n\n"
            for task, count in sorted(
                summary['task_distribution'].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                desc = self.TASK_DESCRIPTIONS.get(task, task)
                narrative += f"- {desc}: {count} windows\n"
            narrative += "\n"
        
        # Activity timeline
        narrative += "## Activity Timeline\n\n"
        for window in windows:
            narrative += self._generate_window_summary(window)
            narrative += "\n"
        
        # Context switches
        switches = self.inference.detect_context_switches(windows)
        if switches:
            narrative += "## Context Switches\n\n"
            for prev, curr, desc in switches:
                narrative += f"- {desc}\n"
            narrative += "\n"
        
        # Optionally enhance with LLM
        if self.llm_hook:
            try:
                prompt = f"Summarize this activity report concisely:\n\n{narrative}"
                enhanced = self.llm_hook(prompt)
                narrative += "## AI Summary\n\n"
                narrative += enhanced + "\n"
            except Exception as e:
                self.logger.warning(f"LLM enhancement failed: {e}")
        
        return narrative
    
    def explain_last(self, minutes: int = 60) -> str:
        """
        Explain what happened in the last N minutes.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            Markdown narrative
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)
        return self.explain_time_window(start_time, end_time)
    
    def trace_subject(self, subject: str) -> str:
        """
        Generate a trace report for a specific subject.
        
        Args:
            subject: File path, URL, repository, etc.
            
        Returns:
            Markdown narrative tracing the subject's history
        """
        # Find events related to this subject
        events = self.database.get_events_for_subject(subject, limit=200)
        
        if not events:
            return f"# Trace Report\n\nNo activity found for: {subject}\n"
        
        narrative = f"# Trace Report: {Path(subject).name}\n\n"
        narrative += f"**Full path:** `{subject}`\n\n"
        
        # Summarize activity
        first_seen = min(e.timestamp for e in events)
        last_seen = max(e.timestamp for e in events)
        
        narrative += "## Overview\n\n"
        narrative += f"- **First seen:** {first_seen.strftime(self.TIME_FORMAT)}\n"
        narrative += f"- **Last seen:** {last_seen.strftime(self.TIME_FORMAT)}\n"
        narrative += f"- **Total events:** {len(events)}\n\n"
        
        # Count by type
        type_counts: Dict[str, int] = {}
        for event in events:
            type_counts[event.event_type.value] = type_counts.get(event.event_type.value, 0) + 1
        
        narrative += "## Event Types\n\n"
        for event_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            narrative += f"- {event_type}: {count}\n"
        narrative += "\n"
        
        # Related nodes from graph
        node_matches = self.graph.find_node(subject)
        if node_matches:
            narrative += "## Related Items\n\n"
            for node_id in node_matches[:1]:
                related = self.graph.get_related_nodes(node_id, max_depth=2)
                for related_id, weight in related[:10]:
                    # Clean up node ID for display
                    display = related_id.split(":", 1)[1] if ":" in related_id else related_id
                    if len(display) > 60:
                        display = display[:60] + "..."
                    narrative += f"- `{display}` (weight: {weight})\n"
            narrative += "\n"
        
        # Recent events
        narrative += "## Recent Activity\n\n"
        for event in events[:20]:
            narrative += f"- **{event.timestamp.strftime(self.TIME_FORMAT)}** - "
            narrative += f"{event.event_type.value}: {event.description or event.subject[:50]}\n"
        
        return narrative
    
    def explain_stalls(self) -> str:
        """
        Generate a report on stalled tasks.
        
        Returns:
            Markdown narrative about detected stalls
        """
        # Get recent events (last 24 hours)
        events = self.database.get_recent_events(minutes=1440)
        
        if not events:
            return "# Stall Report\n\nNo activity in the last 24 hours.\n"
        
        windows = self.inference.create_windows(events)
        windows = self.inference.analyze_windows(windows)
        stalls = self.inference.find_stalled_tasks(windows)
        
        narrative = "# Stall Report\n\n"
        
        if not stalls:
            narrative += "No stalled tasks detected in recent activity.\n"
            return narrative
        
        narrative += f"Found {len(stalls)} potential stalls:\n\n"
        
        for window, reason in stalls:
            narrative += f"## Stall Detected\n\n"
            narrative += f"- **Time:** {window.end_time.strftime(self.TIME_FORMAT)}\n"
            narrative += f"- **Task:** {self.TASK_DESCRIPTIONS.get(window.task_label, window.task_label)}\n"
            narrative += f"- **Reason:** {reason}\n"
            if window.key_subjects:
                narrative += f"- **Subjects:** {', '.join(Path(s).name for s in window.key_subjects[:3])}\n"
            narrative += "\n"
        
        return narrative
    
    def explain_context_switches(self) -> str:
        """
        Generate a report on context switching patterns.
        
        Returns:
            Markdown narrative about context switches
        """
        # Get recent events
        events = self.database.get_recent_events(minutes=480)  # Last 8 hours
        
        if not events:
            return "# Context Switch Report\n\nNo activity in the last 8 hours.\n"
        
        windows = self.inference.create_windows(events)
        windows = self.inference.analyze_windows(windows)
        switches = self.inference.detect_context_switches(windows)
        
        narrative = "# Context Switch Report\n\n"
        
        if not switches:
            narrative += "No significant context switches detected.\n"
            narrative += "Your focus appears to have been consistent.\n"
            return narrative
        
        narrative += f"Detected {len(switches)} context switches:\n\n"
        
        for prev, curr, desc in switches:
            gap = (curr.start_time - prev.end_time).total_seconds() / 60
            
            narrative += f"### Switch at {curr.start_time.strftime(self.TIME_FORMAT)}\n\n"
            narrative += f"- {desc}\n"
            narrative += f"- Gap duration: {int(gap)} minutes\n"
            narrative += f"- From subjects: {', '.join(Path(s).name for s in prev.key_subjects[:2])}\n"
            narrative += f"- To subjects: {', '.join(Path(s).name for s in curr.key_subjects[:2])}\n"
            narrative += "\n"
        
        # Summary
        narrative += "## Analysis\n\n"
        if len(switches) > 5:
            narrative += "⚠️ High context switching detected. Consider:\n"
            narrative += "- Grouping similar tasks together\n"
            narrative += "- Using time blocking techniques\n"
            narrative += "- Reducing interruptions\n"
        else:
            narrative += "✓ Context switching is within normal range.\n"
        
        return narrative
