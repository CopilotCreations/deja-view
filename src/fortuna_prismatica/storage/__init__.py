"""
Storage package for Fortuna Prismatica.

This package provides the storage layer for events and activity data
using DuckDB for append-only, time-indexed storage.
"""

from fortuna_prismatica.storage.database import EventDatabase

__all__ = ["EventDatabase"]
