"""
Collectors package for Fortuna Prismatica.

This package contains all event collectors that gather activity data
from various sources on the local system.
"""

from fortuna_prismatica.collectors.base import BaseCollector
from fortuna_prismatica.collectors.filesystem import FilesystemCollector
from fortuna_prismatica.collectors.git import GitCollector
from fortuna_prismatica.collectors.process import ProcessCollector
from fortuna_prismatica.collectors.terminal import TerminalCollector
from fortuna_prismatica.collectors.browser import BrowserCollector

__all__ = [
    "BaseCollector",
    "FilesystemCollector",
    "GitCollector",
    "ProcessCollector",
    "TerminalCollector",
    "BrowserCollector",
]
