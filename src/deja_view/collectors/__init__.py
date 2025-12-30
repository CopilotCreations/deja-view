"""
Collectors package for Deja View.

This package contains all event collectors that gather activity data
from various sources on the local system.
"""

from deja_view.collectors.base import BaseCollector
from deja_view.collectors.filesystem import FilesystemCollector
from deja_view.collectors.git import GitCollector
from deja_view.collectors.process import ProcessCollector
from deja_view.collectors.terminal import TerminalCollector
from deja_view.collectors.browser import BrowserCollector

__all__ = [
    "BaseCollector",
    "FilesystemCollector",
    "GitCollector",
    "ProcessCollector",
    "TerminalCollector",
    "BrowserCollector",
]
