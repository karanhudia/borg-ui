from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from agent.borg_ui_agent import __version__
from agent.borg_ui_agent.borg import detect_borg_binaries, detect_platform
from agent.borg_ui_agent.client import AgentClient, AgentClientError
from agent.borg_ui_agent.config import (
    AgentConfig,
    delete_config,
    load_config,
    save_config,
)
from agent.borg_ui_agent.runtime import AgentRuntime, get_capabilities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="borg-ui-agent")
    parser.add_argument("--config", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("--server", required=True)
    register.add_argument("--token", required=True)
    register.add_argument("--name", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("once")
    subparsers.add_parser("unregister")

    run = subparsers.add_parser("run")
    run.add_argument("--poll-interval", type=int, default=15)
    run.add_argument("--max-iterations", type=int, default=None)

    return parser


def _register(args: argparse.Namespace) -> int:
    machine = detect_platform()
    borg_versions = [binary.to_api_payload() for binary in detect_borg_binaries()]
    client = AgentClient(args.server)
    response = client.register(
        enrollment_token=args.token,
        name=args.name,
        hostname=machine["hostname"],
        os_name=machine["os"],
        arch=machine["arch"],
        agent_version=__version__,
        borg_versions=borg_versions,
        capabilities=get_capabilities(),
    )
    config_path = save_config(
        AgentConfig(
            server_url=args.server,
            agent_id=response["agent_id"],
            agent_token=response["agent_token"],
            name=args.name,
        ),
        args.config,
    )
    print(f"Registered {response['agent_id']}")
    print(f"Config: {config_path}")
    return 0


def _status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"Server: {config.server_url}")
    print(f"Agent ID: {config.agent_id}")
    if config.name:
        print(f"Name: {config.name}")

    borg_versions = detect_borg_binaries()
    if not borg_versions:
        print("Borg: not found")
    else:
        for binary in borg_versions:
            print(f"Borg {binary.major}: {binary.version} ({binary.path})")
    return 0


def _once(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = AgentRuntime(config).run_once()
    if result.job_id is None:
        print(result.message)
    else:
        print(f"Job {result.job_id}: {result.status}")
    return 0


def _unregister(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    AgentClient.from_config(config).unregister()
    config_path = delete_config(args.config)
    print(f"Unregistered {config.agent_id}")
    print(f"Removed config: {config_path}")
    return 0


def _run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    AgentRuntime(config).run_forever(
        poll_interval_seconds=args.poll_interval,
        max_iterations=args.max_iterations,
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "register":
            return _register(args)
        if args.command == "status":
            return _status(args)
        if args.command == "once":
            return _once(args)
        if args.command == "unregister":
            return _unregister(args)
        if args.command == "run":
            return _run(args)
    except (AgentClientError, OSError, KeyError) as exc:
        parser.exit(1, f"borg-ui-agent: {exc}\n")
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
