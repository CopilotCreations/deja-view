"""
Storage package for Deja View.

This package provides the storage layer for events and activity data
using DuckDB for append-only, time-indexed storage.
"""

from deja_view.storage.database import EventDatabase

__all__ = ["EventDatabase"]
