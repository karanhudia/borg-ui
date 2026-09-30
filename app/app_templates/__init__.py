"""Backup templates for well-known self-hosted apps.

Each app is one JSON file in this folder, plus an optional pre-backup script
next to it. Adding an app means adding files here, no code change.
"""

import json
from functools import lru_cache
from pathlib import Path

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


class AppTemplateExclude(BaseModel):
    # Relative to the app's root folder.
    path: str = Field(pattern=r"^[^/].*")
    default: bool = True
    label: str


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
    excludes: list[AppTemplateExclude]
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
