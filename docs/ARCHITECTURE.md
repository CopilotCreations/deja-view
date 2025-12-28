# Architecture

This document describes the architecture of Fortuna Prismatica, a privacy-first local daemon for tracking and analyzing digital activity.

## System Overview

Fortuna Prismatica is designed as a modular, asyncio-based system with clear separation of concerns between collection, storage, analysis, and reporting.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interface                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        CLI (Typer + Rich)                            │   │
│  │                                                                      │   │
│  │  Commands: start | stop | status | explain | trace | events | ...   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               Core Daemon                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Asyncio Event Loop                                │   │
│  │                                                                      │   │
│  │  • Collector Task Management                                         │   │
│  │  • Event Routing                                                     │   │
│  │  • Periodic Graph Saves                                              │   │
│  │  • Graceful Shutdown Handling                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                              │
          ▼                                              ▼
┌───────────────────────────────┐    ┌───────────────────────────────────────┐
│       Event Collectors        │    │            Data Layer                  │
│                               │    │                                        │
│  ┌─────────────────────────┐ │    │  ┌──────────────────────────────────┐ │
│  │ Filesystem Collector    │ │    │  │         EventDatabase            │ │
│  │ (Watchdog Observer)     │ │    │  │         (DuckDB)                 │ │
│  └─────────────────────────┘ │    │  │                                  │ │
│  ┌─────────────────────────┐ │    │  │  • Append-only event storage     │ │
│  │ Git Collector           │ │    │  │  • Time-indexed queries          │ │
│  │ (Repo Polling)          │ │    │  │  • Subject/type filtering        │ │
│  └─────────────────────────┘ │    │  └──────────────────────────────────┘ │
│  ┌─────────────────────────┐ │    │                                        │
│  │ Process Collector       │ │    │  ┌──────────────────────────────────┐ │
│  │ (psutil Sampling)       │ │    │  │         ActivityGraph            │ │
│  └─────────────────────────┘ │    │  │         (NetworkX)               │ │
│  ┌─────────────────────────┐ │    │  │                                  │ │
│  │ Terminal Collector      │ │    │  │  • Node: files, repos, URLs      │ │
│  │ (History Parsing)       │ │    │  │  • Edge: co-occurrence           │ │
│  └─────────────────────────┘ │    │  │  • Pickle persistence            │ │
│  ┌─────────────────────────┐ │    │  └──────────────────────────────────┘ │
│  │ Browser Collector       │ │    │                                        │
│  │ (SQLite History)        │ │    │                                        │
│  └─────────────────────────┘ │    │                                        │
└───────────────────────────────┘    └───────────────────────────────────────┘
                                                        │
                                                        ▼
                               ┌───────────────────────────────────────────────┐
                               │              Analysis Layer                    │
                               │                                                │
                               │  ┌──────────────────────────────────────────┐ │
                               │  │           InferenceEngine                 │ │
                               │  │                                           │ │
                               │  │  • Time window creation                   │ │
                               │  │  • Task classification                    │ │
                               │  │  • Context switch detection               │ │
                               │  │  • Stall detection                        │ │
                               │  └──────────────────────────────────────────┘ │
                               └───────────────────────────────────────────────┘
                                                        │
                                                        ▼
                               ┌───────────────────────────────────────────────┐
                               │             Reporting Layer                    │
                               │                                                │
                               │  ┌──────────────────────────────────────────┐ │
                               │  │         NarrativeGenerator                │ │
                               │  │                                           │ │
                               │  │  • Markdown report generation             │ │
                               │  │  • Time window explanations               │ │
                               │  │  • Subject tracing                        │ │
                               │  │  • Optional LLM hooks (isolated)          │ │
                               │  └──────────────────────────────────────────┘ │
                               └───────────────────────────────────────────────┘
```

## Core Components

### 1. Event Model (`models.py`)

The unified event model normalizes all activity signals into a consistent schema:

```python
class Event:
    id: UUID              # Unique identifier
    event_type: EventType # Categorized event type
    timestamp: datetime   # When it occurred
    source: str          # Which collector generated it
    subject: str         # Primary subject (file, URL, command)
    # ... additional fields for metadata
```

**Event Types:**
- `file.*`: Filesystem events (create, modify, delete, move)
- `git.*`: Git events (commit, branch_switch, etc.)
- `process.*`: Process events (start, active, end)
- `shell.command`: Terminal commands
- `browser.visit`: Browser page visits

### 2. Collectors (`collectors/`)

Each collector inherits from `BaseCollector` and implements:
- `start()`: Initialize resources
- `stop()`: Clean up resources  
- `collect()`: Async generator yielding events

**Collector implementations:**

| Collector | Mechanism | Interval |
|-----------|-----------|----------|
| Filesystem | Watchdog Observer | Real-time |
| Git | Repository polling | 60 seconds |
| Process | psutil sampling | 30 seconds |
| Terminal | History file polling | 60 seconds |
| Browser | SQLite DB polling | 300 seconds |

### 3. Storage (`storage/database.py`)

DuckDB-based storage with:
- Append-only event insertion
- Time-indexed queries
- Subject and type filtering
- Efficient iteration over large datasets

**Schema:**
```sql
CREATE TABLE events (
    id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    source VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    -- ... additional columns
    metadata JSON
);
```

### 4. Analysis (`analysis/`)

#### InferenceEngine
Groups events into ActivityWindows based on time gaps, then classifies each window into task types:
- `coding`: File modifications with git activity
- `research`: Multiple browser visits
- `terminal_work`: Command-heavy activity
- `git_workflow`: Commit-focused work
- `file_organization`: Move/delete operations

#### ActivityGraph
NetworkX graph where:
- **Nodes**: Files, repos, URLs, commands, processes
- **Edges**: Co-occurrence within activity windows
- **Weights**: Number of co-occurrences

### 5. Reporting (`reporting/narrative.py`)

Rule-based Markdown generation that produces:
- Activity summaries
- Timeline views
- Context switch analysis
- Stall reports
- Subject traces

**LLM Integration:**
Optional LLM hooks are clearly isolated:
```python
def __init__(self, ..., llm_hook: Optional[Callable[[str], str]] = None):
    self.llm_hook = llm_hook  # Completely optional
```

## Data Flow

### Event Collection Flow
```
1. Collector detects activity
2. Collector creates Event object
3. Event passed to daemon via callback
4. Daemon stores event in DuckDB
5. Daemon updates ActivityGraph
```

### Query Flow
```
1. CLI receives user command
2. Query EventDatabase for events
3. Pass to InferenceEngine for analysis
4. Generate narrative via NarrativeGenerator
5. Output to console or file
```

## Design Decisions

### Why DuckDB?
- Embedded database (no server)
- SQL interface for complex queries
- Excellent performance for analytics
- Append-friendly operations

### Why NetworkX?
- Well-documented graph library
- Pickle serialization for persistence
- Rich algorithm support
- No external dependencies

### Why Asyncio?
- Efficient I/O multiplexing
- Natural fit for event-driven architecture
- Easy cancellation and cleanup
- Low memory overhead

### Why Rule-Based Inference?
- Reproducible results
- No training data required
- Transparent decision making
- Easy to extend and customize

## Resource Usage

The daemon is designed for minimal impact:

| Resource | Target | Strategy |
|----------|--------|----------|
| CPU | < 2% idle | Polling with long intervals |
| Memory | < 50MB | Streaming processing, bounded caches |
| Disk | Proportional to activity | Append-only, optional compaction |
| I/O | Minimal | Batched writes, lazy loading |

## Security Considerations

1. **Local-only**: No network communication
2. **No external dependencies**: Works offline
3. **File permissions**: Respects system permissions
4. **Browser database**: Copies before reading to avoid locks

## Extension Points

### Adding a New Collector
1. Inherit from `BaseCollector`
2. Implement `start()`, `stop()`, `collect()`
3. Register in `daemon._init_collectors()`

### Adding a New Event Type
1. Add to `EventType` enum in `models.py`
2. Update relevant collectors
3. Update inference patterns if needed

### Custom Task Patterns
Modify `TASK_PATTERNS` in `InferenceEngine` to recognize new activity types.

## File Organization

```
src/fortuna_prismatica/
├── __init__.py          # Package metadata
├── cli.py               # CLI interface
├── config.py            # Configuration management
├── daemon.py            # Main daemon logic
├── models.py            # Data models
├── collectors/          # Event collectors
│   ├── base.py         # Base collector class
│   ├── filesystem.py   # Filesystem monitoring
│   ├── git.py          # Git repository tracking
│   ├── process.py      # Process sampling
│   ├── terminal.py     # Shell history parsing
│   └── browser.py      # Browser history reading
├── storage/             # Data storage
│   └── database.py     # DuckDB interface
├── analysis/            # Analysis engine
│   ├── inference.py    # Task inference
│   └── graph.py        # Activity graph
└── reporting/           # Report generation
    └── narrative.py    # Markdown narratives
```
