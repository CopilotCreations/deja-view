#!/usr/bin/env python3
"""
Fortuna Prismatica - Personal Background Agent OS

Application entry point that bootstraps the CLI interface.
This script provides a convenient way to run the agent from the project root.
"""

import sys
from pathlib import Path

# Add src directory to path for development
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from fortuna_prismatica.cli import app

if __name__ == "__main__":
    app()
