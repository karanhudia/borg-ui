from __future__ import annotations

import os
import platform
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AgentConfig:
    server_url: str
    agent_id: str
    agent_token: str
    name: str = ""


def default_config_path() -> Path:
    system = platform.system().lower()
    if system == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "borg-ui-agent"
            / "config.toml"
        )
    if system == "windows":
        root = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(root) / "borg-ui-agent" / "config.toml"
    return Path.home() / ".config" / "borg-ui-agent" / "config.toml"


def load_config(path: Optional[Path] = None) -> AgentConfig:
    config_path = path or default_config_path()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return AgentConfig(
        server_url=str(data["server_url"]).rstrip("/"),
        agent_id=str(data["agent_id"]),
        agent_token=str(data["agent_token"]),
        name=str(data.get("name") or ""),
    )


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_config(config: AgentConfig, path: Optional[Path] = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    content = "\n".join(
        [
            f"server_url = {_toml_quote(config.server_url.rstrip('/'))}",
            f"agent_id = {_toml_quote(config.agent_id)}",
            f"agent_token = {_toml_quote(config.agent_token)}",
            f"name = {_toml_quote(config.name)}",
            "",
        ]
    )
    config_path.write_text(content, encoding="utf-8")

    if os.name == "posix":
        os.chmod(config_path.parent, 0o700)
        os.chmod(config_path, 0o600)

    return config_path


def delete_config(path: Optional[Path] = None) -> Path:
    config_path = path or default_config_path()
    config_path.unlink(missing_ok=True)
    return config_path
