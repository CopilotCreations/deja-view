"""
CLI interface for Fortuna Prismatica.

Provides the command-line interface for managing the agent
and querying activity data.
"""

import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from fortuna_prismatica import __version__
from fortuna_prismatica.analysis.graph import ActivityGraph
from fortuna_prismatica.analysis.inference import InferenceEngine
from fortuna_prismatica.config import get_config, set_config, Config
from fortuna_prismatica.daemon import get_daemon_pid, is_daemon_running, run_daemon
from fortuna_prismatica.reporting.narrative import NarrativeGenerator
from fortuna_prismatica.storage.database import EventDatabase

# Create CLI app
app = typer.Typer(
    name="fortuna",
    help="Fortuna Prismatica - Personal Background Agent OS",
    add_completion=False,
)

console = Console()


def _get_database() -> EventDatabase:
    """Get a connected database instance."""
    config = get_config()
    config.ensure_data_dir()
    db = EventDatabase()
    db.connect()
    return db


def _get_graph() -> ActivityGraph:
    """Get an activity graph instance."""
    graph = ActivityGraph()
    graph.load()
    return graph


@app.command()
def start(
    foreground: bool = typer.Option(
        False, "--foreground", "-f",
        help="Run in foreground instead of as daemon"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging"
    ),
) -> None:
    """Start the Fortuna Prismatica agent."""
    
    # Check if already running
    if is_daemon_running():
        pid = get_daemon_pid()
        console.print(f"[yellow]Agent is already running (PID: {pid})[/yellow]")
        raise typer.Exit(1)
    
    config = get_config()
    config.ensure_data_dir()
    
    if verbose:
        config.log_level = "DEBUG"
        set_config(config)
    
    if foreground:
        console.print("[green]Starting agent in foreground...[/green]")
        console.print("Press Ctrl+C to stop")
        run_daemon()
    else:
        # Start as background process
        console.print("[green]Starting agent as daemon...[/green]")
        
        # Use the same Python interpreter
        python = sys.executable
        script = Path(__file__).parent.parent.parent.parent / "run.py"
        
        if not script.exists():
            # Fall back to module execution
            cmd = [python, "-m", "fortuna_prismatica.cli", "start", "--foreground"]
        else:
            cmd = [python, str(script), "start", "--foreground"]
        
        if verbose:
            cmd.append("--verbose")
        
        # Start detached process
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        
        console.print("[green]Agent started successfully[/green]")


@app.command()
def stop() -> None:
    """Stop the Fortuna Prismatica agent."""
    
    pid = get_daemon_pid()
    if not pid:
        console.print("[yellow]Agent is not running[/yellow]")
        raise typer.Exit(1)
    
    console.print(f"[yellow]Stopping agent (PID: {pid})...[/yellow]")
    
    try:
        if sys.platform == "win32":
            os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
        
        # Wait briefly for process to stop
        import time
        for _ in range(10):
            if not is_daemon_running():
                break
            time.sleep(0.5)
        
        if is_daemon_running():
            console.print("[red]Agent did not stop gracefully, force killing...[/red]")
            os.kill(pid, signal.SIGKILL)
        
        console.print("[green]Agent stopped[/green]")
        
    except ProcessLookupError:
        console.print("[yellow]Agent process not found (may have already stopped)[/yellow]")
        # Clean up PID file
        config = get_config()
        if config.pid_file.exists():
            config.pid_file.unlink()
    except PermissionError:
        console.print("[red]Permission denied. Try running with sudo.[/red]")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show the status of the Fortuna Prismatica agent."""
    
    config = get_config()
    pid = get_daemon_pid()
    
    # Create status table
    table = Table(title="Fortuna Prismatica Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Version", __version__)
    table.add_row("Data Directory", str(config.data_dir))
    
    if pid:
        table.add_row("Status", "[green]Running[/green]")
        table.add_row("PID", str(pid))
    else:
        table.add_row("Status", "[red]Stopped[/red]")
    
    # Database stats
    if config.database_path.exists():
        try:
            db = _get_database()
            event_count = db.get_event_count()
            type_counts = db.get_event_type_counts()
            db.close()
            
            table.add_row("Total Events", str(event_count))
            table.add_row("Database Size", f"{config.database_path.stat().st_size / 1024:.1f} KB")
            
            # Top event types
            if type_counts:
                top_types = list(type_counts.items())[:3]
                types_str = ", ".join(f"{t}: {c}" for t, c in top_types)
                table.add_row("Top Event Types", types_str)
        except Exception as e:
            table.add_row("Database", f"[red]Error: {e}[/red]")
    else:
        table.add_row("Database", "[yellow]Not initialized[/yellow]")
    
    # Graph stats
    if config.graph_path.exists():
        try:
            graph = _get_graph()
            stats = graph.get_statistics()
            table.add_row("Graph Nodes", str(stats.get("nodes", 0)))
            table.add_row("Graph Edges", str(stats.get("edges", 0)))
        except Exception:
            pass
    
    console.print(table)


@app.command()
def explain(
    last: str = typer.Option(
        "60m",
        "--last", "-l",
        help="Time period to explain (e.g., 30m, 2h, 1d)"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Write output to file instead of stdout"
    ),
) -> None:
    """Explain what you were doing in a time period."""
    
    # Parse time string
    time_str = last.lower()
    try:
        if time_str.endswith("m"):
            minutes = int(time_str[:-1])
        elif time_str.endswith("h"):
            minutes = int(time_str[:-1]) * 60
        elif time_str.endswith("d"):
            minutes = int(time_str[:-1]) * 60 * 24
        else:
            minutes = int(time_str)
    except ValueError:
        console.print(f"[red]Invalid time format: {last}[/red]")
        console.print("Use format like: 30m, 2h, 1d")
        raise typer.Exit(1)
    
    try:
        db = _get_database()
        graph = _get_graph()
        
        generator = NarrativeGenerator(db, graph)
        narrative = generator.explain_last(minutes)
        
        db.close()
        
        if output:
            output.write_text(narrative)
            console.print(f"[green]Report written to {output}[/green]")
        else:
            console.print(Panel(narrative, title="Activity Report"))
            
    except Exception as e:
        console.print(f"[red]Error generating explanation: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def trace(
    target: str = typer.Argument(
        ...,
        help="File path, repository, or URL to trace"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Write output to file instead of stdout"
    ),
) -> None:
    """Trace activity related to a file, repo, or URL."""
    
    try:
        db = _get_database()
        graph = _get_graph()
        
        generator = NarrativeGenerator(db, graph)
        narrative = generator.trace_subject(target)
        
        db.close()
        
        if output:
            output.write_text(narrative)
            console.print(f"[green]Report written to {output}[/green]")
        else:
            console.print(Panel(narrative, title=f"Trace: {target}"))
            
    except Exception as e:
        console.print(f"[red]Error generating trace: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def switches() -> None:
    """Show context switching patterns."""
    
    try:
        db = _get_database()
        graph = _get_graph()
        
        generator = NarrativeGenerator(db, graph)
        narrative = generator.explain_context_switches()
        
        db.close()
        
        console.print(Panel(narrative, title="Context Switches"))
        
    except Exception as e:
        console.print(f"[red]Error analyzing context switches: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stalls() -> None:
    """Show stalled tasks."""
    
    try:
        db = _get_database()
        graph = _get_graph()
        
        generator = NarrativeGenerator(db, graph)
        narrative = generator.explain_stalls()
        
        db.close()
        
        console.print(Panel(narrative, title="Stalled Tasks"))
        
    except Exception as e:
        console.print(f"[red]Error analyzing stalls: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def events(
    last: str = typer.Option(
        "60m",
        "--last", "-l",
        help="Time period to show (e.g., 30m, 2h, 1d)"
    ),
    limit: int = typer.Option(
        50,
        "--limit", "-n",
        help="Maximum number of events to show"
    ),
    event_type: Optional[str] = typer.Option(
        None,
        "--type", "-t",
        help="Filter by event type"
    ),
) -> None:
    """List recent events."""
    
    # Parse time string
    time_str = last.lower()
    try:
        if time_str.endswith("m"):
            minutes = int(time_str[:-1])
        elif time_str.endswith("h"):
            minutes = int(time_str[:-1]) * 60
        elif time_str.endswith("d"):
            minutes = int(time_str[:-1]) * 60 * 24
        else:
            minutes = int(time_str)
    except ValueError:
        console.print(f"[red]Invalid time format: {last}[/red]")
        raise typer.Exit(1)
    
    try:
        db = _get_database()
        events = db.get_recent_events(minutes=minutes, limit=limit)
        db.close()
        
        if not events:
            console.print("[yellow]No events found in the specified time period[/yellow]")
            return
        
        # Create events table
        table = Table(title=f"Recent Events (last {last})")
        table.add_column("Time", style="cyan", width=16)
        table.add_column("Type", style="green", width=15)
        table.add_column("Subject", style="white")
        
        for event in events:
            if event_type and event_type not in event.event_type.value:
                continue
            
            time_str = event.timestamp.strftime("%m-%d %H:%M:%S")
            subject = event.subject[:60] + "..." if len(event.subject) > 60 else event.subject
            table.add_row(time_str, event.event_type.value, subject)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing events: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def graph_stats() -> None:
    """Show activity graph statistics."""
    
    try:
        graph = _get_graph()
        stats = graph.get_statistics()
        
        table = Table(title="Activity Graph Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Total Nodes", str(stats.get("nodes", 0)))
        table.add_row("Total Edges", str(stats.get("edges", 0)))
        table.add_row("Clusters", str(stats.get("clusters", 0)))
        table.add_row("Density", f"{stats.get('density', 0):.4f}")
        
        # Node types
        node_types = stats.get("node_types", {})
        for node_type, count in sorted(node_types.items(), key=lambda x: x[1], reverse=True):
            table.add_row(f"  {node_type} nodes", str(count))
        
        console.print(table)
        
        # Most connected nodes
        top_nodes = graph.get_most_connected(10)
        if top_nodes:
            console.print("\n[bold]Most Connected Nodes:[/bold]")
            for node_id, degree in top_nodes:
                display = node_id.split(":", 1)[1] if ":" in node_id else node_id
                if len(display) > 60:
                    display = display[:60] + "..."
                console.print(f"  {display}: {degree} connections")
        
    except Exception as e:
        console.print(f"[red]Error getting graph stats: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"Fortuna Prismatica v{__version__}")


@app.callback()
def main(
    ctx: typer.Context,
) -> None:
    """
    Fortuna Prismatica - Personal Background Agent OS
    
    A privacy-first local daemon that continuously records, correlates,
    and explains your background digital activity.
    """
    pass


if __name__ == "__main__":
    app()
