# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""This is server module"""

import importlib
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from typing import List

from trpc_sdk.log import logger
from trpc_sdk.server import create_server

# import sdk and plugins
# pylint: disable=unused-import
# Optional plugins: runtime metrics are used when installed.
try:
    import trpc_metrics_runtime as _
except ImportError:
    pass
# pylint: enable=unused-import

# add the stub to the path
sys.path.append(str(Path(__file__) / "agents"))  # noqa
sys.path.append(str(Path(__file__) / "stub"))  # noqa
sys.path.append(str(Path(__file__)))  # Add this directory to the import path

# Each module calls register_service with the same service name, so only one is imported.
AGENT_MODULES = {
    "basic": "agents.basic_agent",
    "streaming": "agents.streaming_agent",
    "multiturn": "agents.multiturn_agent",
    "error": "agents.error_agent",
    "push_notify": "agents.push_notify_agent",
    "task_push_notify": "agents.task_push_notify_agent",
}

DEFAULT_CONF_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "trpc_python.yaml"))


def load_agent(name: str) -> None:
    """Import one agent so ``register_service`` runs before ``create_server``.

    Args:
        name: Key in ``AGENT_MODULES``.
    """
    importlib.import_module(AGENT_MODULES[name])


def parse_args(argv: List[str]) -> tuple[str, str]:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments.

    Returns:
        The config path and the agent name to import.
    """
    # argparse parser
    parser = argparse.ArgumentParser(description='TRPC Python Framework Server')
    parser.add_argument('--conf',
                        '-c',
                        default=DEFAULT_CONF_PATH,
                        help='start server with conf, for example: `python3 trpc_main.py  --conf=trpc_python.yaml`')
    parser.add_argument('--agent',
                        '-a',
                        default='basic',
                        choices=sorted(AGENT_MODULES),
                        help='agent to register before the server starts (default: basic)')
    try:
        args = parser.parse_args(argv[1:])  # Skip the script name
        if os.path.exists(args.conf):
            print(f"conf_path: {args.conf}")
            return args.conf, args.agent
        print(f"conf_path: {args.conf} not exists")
        if os.path.exists(DEFAULT_CONF_PATH):
            print(f"use default conf path: {DEFAULT_CONF_PATH}")
            return DEFAULT_CONF_PATH, args.agent
        print(f"default conf path: {DEFAULT_CONF_PATH} not exists, please check the path")
        sys.exit(1)
    except SystemExit:
        # argparse will call sys.exit() when --help is used or invalid args
        sys.exit(1)


def serve(conf_path: str):
    """Start the server.

    Args:
        conf_path: Path to the configuration file.
    """

    create_server(conf_path).serve()


def main():
    """Load config and start the server."""
    # Load environment variables from a .env file.
    load_dotenv()
    # Parse command-line arguments.
    conf_path, agent = parse_args(sys.argv)
    logger.info("load config %s", conf_path)
    logger.info("load agent %s", agent)
    load_agent(agent)

    # Start the server.
    serve(conf_path)


if __name__ == '__main__':
    sys.exit(main())
