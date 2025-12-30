# Deja View

[![CI](https://github.com/user/deja-view/actions/workflows/ci.yml/badge.svg)](https://github.com/user/deja-view/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Personal Background Agent OS** — A privacy-first local daemon that continuously records, correlates, and explains your background digital activity.

## Overview

Deja View is a local-first, privacy-focused system that passively observes your digital activity and provides intelligent insights about your work patterns. It runs as a background daemon, collecting events from various sources and using rule-based inference to help you understand:

- What you were doing in a specific time period
- Why certain tasks stalled
- Where you frequently context switch
- How different files, projects, and activities relate

**Key Principles:**
- 🔒 **Privacy First**: All data stays local. No cloud, no telemetry.
- 📝 **Append-Only**: Events are immutable once recorded.
- 🔍 **Deterministic Analysis**: Reproducible, rule-based inference.
- 💻 **Low Overhead**: Designed for minimal CPU and memory usage.

## Features

### Event Collectors
- **Filesystem Activity**: Monitors file create/modify/delete events
- **Git Activity**: Tracks commits, branch changes, repository activity
- **Process Activity**: Samples running processes and foreground apps
- **Terminal Activity**: Parses shell history (bash/zsh)
- **Browser Activity**: Reads local browser history (Chrome/Firefox)

### Analysis
- **Activity Windows**: Groups events into coherent time windows
- **Task Inference**: Classifies activity (coding, research, git workflow, etc.)
- **Activity Graph**: NetworkX graph showing relationships between entities
- **Context Switch Detection**: Identifies when you switch between tasks
- **Stall Detection**: Finds tasks that may have been interrupted

### Reporting
- **Markdown Narratives**: Human-readable explanations of activity
- **Subject Tracing**: Track the history of any file, repo, or URL
- **Pattern Analysis**: Understand your work patterns over time

## Installation

### Requirements
- Python 3.10 or higher
- Linux or macOS (Windows support is experimental)

### From Source

```bash
# Clone the repository
git clone https://github.com/user/deja-view.git
cd deja-view

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the CLI
python run.py --help
```

## Quick Start

### Start the Agent

```bash
# Start as background daemon
python run.py start

# Or run in foreground for debugging
python run.py start --foreground --verbose
```

### Check Status

```bash
python run.py status
```

### Get Activity Explanations

```bash
# What were you doing in the last hour?
python run.py explain --last 60m

# What about the last 2 hours?
python run.py explain --last 2h

# Save to a file
python run.py explain --last 1d --output report.md
```

### Trace a Subject

```bash
# Trace a specific file
python run.py trace /path/to/project/main.py

# Trace a repository
python run.py trace /path/to/project

# Trace a URL
python run.py trace "https://docs.python.org"
```

### View Recent Events

```bash
# Show last 50 events
python run.py events --limit 50

# Filter by type
python run.py events --type file

# Show events from last 2 hours
python run.py events --last 2h
```

### Stop the Agent

```bash
python run.py stop
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `start` | Start the agent (daemon or foreground) |
| `stop` | Stop the running agent |
| `status` | Show agent status and statistics |
| `explain` | Generate activity explanation |
| `trace` | Trace activity for a subject |
| `events` | List recent events |
| `switches` | Show context switching patterns |
| `stalls` | Show stalled tasks |
| `graph-stats` | Show activity graph statistics |
| `version` | Show version information |

## Configuration

Configuration is done via environment variables or a `.env` file:

```bash
# Copy example configuration
cp .env.example .env

# Edit as needed
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEJA_DATA_DIR` | Data storage directory | `~/.deja` |
| `DEJA_LOG_LEVEL` | Logging level | `INFO` |
| `DEJA_PROCESS_POLL_INTERVAL` | Process sampling interval (seconds) | `30` |
| `DEJA_SHELL_HISTORY_POLL_INTERVAL` | Shell history poll interval | `60` |
| `DEJA_BROWSER_POLL_INTERVAL` | Browser history poll interval | `300` |
| `DEJA_ACTIVITY_WINDOW_MINUTES` | Activity window size | `15` |
| `DEJA_WATCH_PATHS` | Directories to watch (comma-separated) | Home directory |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Interface                        │
│                   (Typer + Rich Console)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                           Daemon                             │
│              (Asyncio Event Loop + Lifecycle)                │
└─────────────────────────────────────────────────────────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Collectors    │  │    Storage      │  │    Analysis     │
│                 │  │                 │  │                 │
│ • Filesystem    │  │ • DuckDB        │  │ • Inference     │
│ • Git           │  │ • Event Table   │  │ • Activity      │
│ • Process       │  │                 │  │   Graph         │
│ • Terminal      │  │                 │  │                 │
│ • Browser       │  │                 │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Reporting                             │
│              (Narrative Generation + Markdown)               │
└─────────────────────────────────────────────────────────────┘
```

## Development

### Setup Development Environment

```bash
# Install all dependencies including dev tools
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src/deja_view --cov-report=html

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/deja_view
```

### Project Structure

```
deja-view/
├── run.py                # Application entry point
├── requirements.txt      # Python dependencies
├── .env.example         # Example environment file
├── .gitignore           # Git ignore patterns
│
├── .github/workflows/   # GitHub Actions CI/CD
│   └── ci.yml
│
├── src/deja_view/
│   ├── __init__.py
│   ├── cli.py           # CLI interface (Typer)
│   ├── config.py        # Configuration management
│   ├── daemon.py        # Main daemon
│   ├── models.py        # Data models (Event, ActivityWindow)
│   │
│   ├── collectors/      # Event collectors
│   │   ├── base.py
│   │   ├── filesystem.py
│   │   ├── git.py
│   │   ├── process.py
│   │   ├── terminal.py
│   │   └── browser.py
│   │
│   ├── storage/         # Data storage
│   │   └── database.py
│   │
│   ├── analysis/        # Analysis engine
│   │   ├── inference.py
│   │   └── graph.py
│   │
│   └── reporting/       # Report generation
│       └── narrative.py
│
├── tests/               # Test suite
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_storage.py
│   ├── test_analysis.py
│   ├── test_collectors.py
│   ├── test_reporting.py
│   ├── test_daemon.py
│   └── test_cli.py
│
└── docs/                # Documentation
    ├── ARCHITECTURE.md
    ├── USAGE.md
    └── SUGGESTIONS.md
```

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | ✅ Full | All features supported |
| macOS | ✅ Full | All features supported |
| Windows | ⚠️ Experimental | Some collectors may not work |

## Privacy & Security

- **All data is local**: Nothing is ever sent to external servers
- **No cloud dependencies**: Works completely offline
- **User-controlled**: You decide what to monitor
- **Transparent**: All source code is available for review

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read the contribution guidelines before submitting a pull request.

## Acknowledgments

- Built with [Typer](https://typer.tiangolo.com/) for CLI
- Uses [DuckDB](https://duckdb.org/) for storage
- Uses [NetworkX](https://networkx.org/) for graph analysis
- Uses [Watchdog](https://pythonhosted.org/watchdog/) for filesystem monitoring
