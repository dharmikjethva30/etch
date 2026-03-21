"""Daemon module - can be run as: python -m etch.daemon.runner"""

import sys
from pathlib import Path

from etch.daemon.runner import DaemonRunner


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m etch.daemon.runner <etch_dir>")
        sys.exit(1)

    etch_dir = Path(sys.argv[1])
    if not etch_dir.exists():
        print(f"Error: {etch_dir} does not exist")
        sys.exit(1)

    runner = DaemonRunner(etch_dir)
    runner.run()
