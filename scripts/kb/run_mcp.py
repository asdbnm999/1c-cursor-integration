#!/usr/bin/env python3
"""Запуск MCP-сервера для конкретного профиля."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", "-p", required=True)
    parser.add_argument("--transport", choices=["stdio", "http"], default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "mcp_server.server", "--profile", args.profile]
    if args.transport:
        cmd.extend(["--transport", args.transport])
    if args.port:
        cmd.extend(["--port", str(args.port)])

    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
