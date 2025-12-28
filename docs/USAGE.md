# Usage Guide

This guide provides comprehensive instructions for using Fortuna Prismatica.

## Table of Contents

1. [Installation](#installation)
2. [Starting the Agent](#starting-the-agent)
3. [Understanding Events](#understanding-events)
4. [Querying Activity](#querying-activity)
5. [Activity Analysis](#activity-analysis)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- Git (for repository tracking)

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/user/fortuna-prismatica.git
cd fortuna-prismatica

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Verify Installation

```bash
python run.py version
# Output: Fortuna Prismatica v0.1.0
```

## Starting the Agent

### Daemon Mode (Recommended)

Start the agent as a background daemon:

```bash
python run.py start
```

The agent will:
1. Create the data directory (`~/.fortuna`)
2. Initialize the database
3. Start all collectors
4. Begin recording activity

### Foreground Mode

For debugging or development, run in foreground:

```bash
python run.py start --foreground --verbose
```

Press `Ctrl+C` to stop.

### Checking Status

```bash
python run.py status
```

Example output:
```
╭──────────────────────────────────────╮
│      Fortuna Prismatica Status       │
├─────────────────┬────────────────────┤
│ Property        │ Value              │
├─────────────────┼────────────────────┤
│ Version         │ 0.1.0              │
│ Data Directory  │ /home/user/.fortuna│
│ Status          │ Running            │
│ PID             │ 12345              │
│ Total Events    │ 1,234              │
│ Database Size   │ 512.5 KB           │
│ Top Event Types │ file.modify: 456,  │
│                 │ shell.command: 234 │
│ Graph Nodes     │ 89                 │
│ Graph Edges     │ 156                │
└─────────────────┴────────────────────┘
```

### Stopping the Agent

```bash
python run.py stop
```

## Understanding Events

### Event Types

Fortuna Prismatica captures the following event types:

| Type | Description | Source |
|------|-------------|--------|
| `file.create` | New file created | Filesystem |
| `file.modify` | File content changed | Filesystem |
| `file.delete` | File deleted | Filesystem |
| `file.move` | File moved/renamed | Filesystem |
| `git.commit` | New commit detected | Git |
| `git.branch_switch` | Branch changed | Git |
| `git.branch_create` | New branch created | Git |
| `process.start` | Application launched | Process Monitor |
| `process.active` | High CPU activity | Process Monitor |
| `process.end` | Application closed | Process Monitor |
| `shell.command` | Terminal command executed | Shell History |
| `browser.visit` | Web page visited | Browser History |

### Viewing Recent Events

```bash
# Show last 50 events
python run.py events --limit 50

# Show events from last 2 hours
python run.py events --last 2h

# Filter by type
python run.py events --type file
python run.py events --type git
python run.py events --type browser
```

Example output:
```
╭────────────────────────────────────────────────────────────────────╮
│                    Recent Events (last 60m)                         │
├──────────────────┬─────────────────┬───────────────────────────────┤
│ Time             │ Type            │ Subject                       │
├──────────────────┼─────────────────┼───────────────────────────────┤
│ 12-27 14:32:15   │ file.modify     │ /home/user/project/main.py    │
│ 12-27 14:31:45   │ git.commit      │ abc123def                     │
│ 12-27 14:30:22   │ shell.command   │ pytest tests/                 │
│ 12-27 14:28:10   │ browser.visit   │ https://docs.python.org/...   │
└──────────────────┴─────────────────┴───────────────────────────────┘
```

## Querying Activity

### Time-Based Explanations

Get an explanation of what you were doing:

```bash
# Last hour
python run.py explain --last 60m

# Last 2 hours
python run.py explain --last 2h

# Last day
python run.py explain --last 1d
```

Example output:
```markdown
# Activity Report

**Period:** 2024-12-27 13:00 - 14:00

## Summary

- **Total events:** 156
- **Activity windows:** 3
- **Primary focus:** writing and editing code
- **Context switches:** 2

## Task Distribution

- writing and editing code: 2 windows
- researching and browsing the web: 1 window

## Activity Timeline

**2024-12-27 13:00 - 13:25** (25 minutes)
- Primary activity: writing and editing code
- Confidence: 85%
- Events: 45 (23 file, 12 shell, 10 git)
- Key subjects: main.py, utils.py, tests/

...
```

### Subject Tracing

Trace the history of a specific file, repository, or URL:

```bash
# Trace a file
python run.py trace /path/to/project/main.py

# Trace a repository
python run.py trace /path/to/project

# Trace a URL
python run.py trace "https://docs.python.org"
```

Example output:
```markdown
# Trace Report: main.py

**Full path:** `/home/user/project/main.py`

## Overview

- **First seen:** 2024-12-20 09:15
- **Last seen:** 2024-12-27 14:32
- **Total events:** 89

## Event Types

- file.modify: 67
- file.create: 1
- git.commit: 21

## Related Items

- `tests/test_main.py` (weight: 45)
- `/home/user/project` (weight: 32)
- `pytest` (weight: 28)
```

### Saving Reports

Save any report to a file:

```bash
python run.py explain --last 1d --output daily_report.md
python run.py trace /path/to/file --output trace.md
```

## Activity Analysis

### Context Switches

View when you switched between different types of work:

```bash
python run.py switches
```

Example output:
```markdown
# Context Switch Report

Detected 5 context switches:

### Switch at 2024-12-27 11:45

- Switched from coding to research (after 15 min break)
- Gap duration: 15 minutes
- From subjects: main.py, utils.py
- To subjects: docs.python.org, stackoverflow.com

...

## Analysis

⚠️ High context switching detected. Consider:
- Grouping similar tasks together
- Using time blocking techniques
- Reducing interruptions
```

### Stalled Tasks

Find tasks that may have been interrupted:

```bash
python run.py stalls
```

Example output:
```markdown
# Stall Report

Found 2 potential stalls:

## Stall Detected

- **Time:** 2024-12-27 10:30
- **Task:** writing and editing code
- **Reason:** Work on /home/user/project paused for 120 minutes
- **Subjects:** feature.py, tests/
```

### Activity Graph

View statistics about the activity relationship graph:

```bash
python run.py graph-stats
```

Example output:
```
╭────────────────────────────────────╮
│     Activity Graph Statistics      │
├────────────────┬───────────────────┤
│ Metric         │ Value             │
├────────────────┼───────────────────┤
│ Total Nodes    │ 156               │
│ Total Edges    │ 423               │
│ Clusters       │ 8                 │
│ Density        │ 0.0234            │
│   file nodes   │ 89                │
│   repo nodes   │ 12                │
│   domain nodes │ 34                │
│   command nodes│ 21                │
└────────────────┴───────────────────┘

Most Connected Nodes:
  /home/user/project: 45 connections
  github.com: 32 connections
  pytest: 28 connections
```

## Configuration

### Configuration File

Create a `.env` file from the example:

```bash
cp .env.example .env
```

### Available Settings

```bash
# Data storage location
FORTUNA_DATA_DIR=~/.fortuna

# Logging level (DEBUG, INFO, WARNING, ERROR)
FORTUNA_LOG_LEVEL=INFO

# Collection intervals (seconds)
FORTUNA_PROCESS_POLL_INTERVAL=30
FORTUNA_SHELL_HISTORY_POLL_INTERVAL=60
FORTUNA_BROWSER_POLL_INTERVAL=300

# Activity window size for analysis (minutes)
FORTUNA_ACTIVITY_WINDOW_MINUTES=15

# Paths to monitor (comma-separated)
FORTUNA_WATCH_PATHS=~,~/Documents,~/Projects
```

### Directories Monitored

By default, Fortuna monitors:
- Your home directory
- Common project directories (Documents, Projects, Code, etc.)

Files matching these patterns are ignored:
- `.git/` directories
- `__pycache__/` directories
- `node_modules/` directories
- Temporary files (`.swp`, `.swo`, `~`)
- IDE files (`.idea/`, `.vscode/`)

## Troubleshooting

### Agent Won't Start

1. Check if already running:
   ```bash
   python run.py status
   ```

2. Check for stale PID file:
   ```bash
   rm ~/.fortuna/fortuna.pid
   ```

3. Check logs:
   ```bash
   cat ~/.fortuna/fortuna.log
   ```

### No Events Being Collected

1. Verify collector status:
   ```bash
   python run.py start --foreground --verbose
   ```

2. Check permissions on monitored directories

3. For browser history, ensure browser is not running (locks database)

### Database Issues

Reset the database:
```bash
rm ~/.fortuna/events.duckdb
python run.py start
```

### High Resource Usage

1. Increase polling intervals in `.env`
2. Reduce monitored paths
3. Check for very large directories being watched

### Browser History Not Working

1. Chrome/Firefox must be closed for history reading
2. Check browser profile path in configuration
3. Verify browser history database exists

### Common Error Messages

| Error | Solution |
|-------|----------|
| "Agent already running" | Stop existing agent or remove PID file |
| "Permission denied" | Check file permissions |
| "Database locked" | Wait for other processes to release |
| "No browser history found" | Check browser paths in config |

## Best Practices

1. **Start at login**: Add to startup scripts for continuous tracking
2. **Regular backups**: Back up `~/.fortuna` periodically
3. **Review weekly**: Check context switches and stalls weekly
4. **Tune intervals**: Adjust polling intervals based on needs
5. **Monitor disk usage**: Large databases may need cleanup
