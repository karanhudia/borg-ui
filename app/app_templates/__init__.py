"""Backup templates for well-known self-hosted apps.

Each app is one JSON file in this folder, plus an optional pre-backup script
next to it. Adding an app means adding files here, no code change.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TEMPLATES_DIR = Path(__file__).parent
APP_ROOT_PLACEHOLDER = "__APP_ROOT__"
# The detected container's name, for scripts that ask the app to write its own
# dump (docker exec). Empty when the folder was picked by hand.
CONTAINER_PLACEHOLDER = "__CONTAINER__"


_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._ -]+(/[A-Za-z0-9._ -]+)*$")


def _check_relative(path: str) -> str:
    """A path inside the app's folder: nested is fine, ".." and stray spaces are not."""
    parts = path.split("/")
    if not _RELATIVE_PATH.match(path) or any(
        part in {".", ".."} or part != part.strip() for part in parts
    ):
        raise ValueError("path must stay inside the app's folder")
    return path


class AppTemplateVerified(BaseModel):
    app_version: str
    date: str
    restore_tested: bool


class AppTemplateDetect(BaseModel):
    # Image repositories the app is published under, without tag or digest.
    images: list[str] = Field(min_length=1)
    # Where the app's folder sits inside the mount, for images that nest it
    # (official Plex: /config/Library/Application Support/Plex Media Server;
    # hotio: /config itself). Images not listed use the mount as is.
    root_subpaths: dict[str, str] = {}

    @field_validator("root_subpaths")
    @classmethod
    def _subpaths_stay_inside(cls, subpaths: dict[str, str]) -> dict[str, str]:
        for subpath in subpaths.values():
            _check_relative(subpath)
        return subpaths

    def root_subpath(self, repository: str) -> str:
        return self.root_subpaths.get(repository, "")

    # Where the app keeps its files inside the container, preferred first.
    # Older installs may still mount an earlier path.
    mount_destinations: list[str] = Field(min_length=1)


class AppTemplateExtraMounts(BaseModel):
    # Any other folder the container mounts (external libraries and the like)
    # is listed and backed up by default under this label.
    label: str
    description: str


class AppTemplateFolder(BaseModel):
    # Relative to the app's root folder. Nested paths are fine (Plex keeps its
    # data under "Library/Application Support/..."); ".." is not.
    path: str
    label: str
    description: str
    # data: always backed up. database: backed up, and its newest file shows
    # how fresh the app's own dump is. rebuildable: skipped by default.
    role: Literal["data", "database", "rebuildable"]
    stale_after_hours: int | None = None
    # For a database folder: which files are the app's dumps (shell glob), so
    # an unrelated newer file can't pass for a fresh dump.
    dump_pattern: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._*?\[\]-]+$")
    # The template's own script writes these dumps before each backup, so a
    # missing or old one is no reason to warn (Jellyfin).
    made_before_backup: bool = False

    @field_validator("path")
    @classmethod
    def _no_parent_segments(cls, path: str) -> str:
        return _check_relative(path)


class AppTemplateScript(BaseModel):
    name: str
    description: str
    content: str
    timeout: int


class AppTemplate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    version: int
    name: str
    description: str
    # The app's official logo as SVG markup, shown in the app pickers.
    logo_svg: str | None = None
    docs_url: str
    verified: AppTemplateVerified
    detect: AppTemplateDetect
    root_hint: str
    extra_mounts: AppTemplateExtraMounts | None = None
    folders: list[AppTemplateFolder]
    pre_backup_script: AppTemplateScript | None = None
    schedule_cron: str
    notes: list[str]


def _load(path: Path) -> AppTemplate:
    raw = json.loads(path.read_text())
    logo = raw.pop("logo", None)
    if logo:
        raw["logo_svg"] = (TEMPLATES_DIR / logo).read_text()
    script = raw.get("pre_backup_script")
    if script:
        script["content"] = (TEMPLATES_DIR / script.pop("file")).read_text()
    return AppTemplate.model_validate(raw)


@lru_cache(maxsize=1)
def load_app_templates() -> tuple[AppTemplate, ...]:
    return tuple(_load(path) for path in sorted(TEMPLATES_DIR.glob("*.json")))


def image_repository(image: str) -> str:
    """`ghcr.io/org/app:tag@sha256:…` → `ghcr.io/org/app`. A colon only starts a
    tag after the last slash; before it, it is a registry port."""
    name = image.split("@", 1)[0]
    slash = name.rfind("/")
    colon = name.rfind(":")
    repository = name[:colon] if colon > slash else name
    # Docker Hub images can be written with or without their registry.
    for hub in ("docker.io/", "index.docker.io/"):
        if repository.startswith(hub):
            return repository[len(hub) :]
    return repository


def match_app_template(
    image: str | None, templates: tuple[AppTemplate, ...]
) -> AppTemplate | None:
    if not image:
        return None
    repository = image_repository(image)
    for template in templates:
        if repository in template.detect.images:
            return template
    return None
