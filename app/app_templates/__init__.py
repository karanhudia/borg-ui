"""Backup templates for well-known self-hosted apps.

Each app is one JSON file in this folder, plus an optional pre-backup script
next to it. Adding an app means adding files here, no code change.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

TEMPLATES_DIR = Path(__file__).parent
APP_ROOT_PLACEHOLDER = "__APP_ROOT__"


class AppTemplateVerified(BaseModel):
    app_version: str
    date: str
    restore_tested: bool


class AppTemplateDetect(BaseModel):
    image_prefix: str
    mount_destination: str


class AppTemplateFolder(BaseModel):
    # Relative to the app's root folder, one level deep.
    path: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    label: str
    description: str
    # data: always backed up. database: backed up, and its newest file shows
    # how fresh the app's own dump is. rebuildable: skipped by default.
    role: Literal["data", "database", "rebuildable"]
    stale_after_hours: int | None = None


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


def match_app_template(
    image: str | None, templates: tuple[AppTemplate, ...]
) -> AppTemplate | None:
    if not image:
        return None
    for template in templates:
        if image.startswith(template.detect.image_prefix):
            return template
    return None
