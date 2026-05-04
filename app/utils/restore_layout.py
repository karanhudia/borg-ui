from typing import Dict, Iterable, List, Optional


RESTORE_LAYOUT_PRESERVE_PATH = "preserve_path"
RESTORE_LAYOUT_CONTENTS_ONLY = "contents_only"


def normalize_archive_path(path: str) -> str:
    return "/".join(part for part in path.split("/") if part)


def _path_components(path: str) -> List[str]:
    normalized = normalize_archive_path(path)
    return normalized.split("/") if normalized else []


def _common_prefix(paths: List[List[str]]) -> List[str]:
    if not paths:
        return []

    prefix: List[str] = []
    first_path = paths[0]
    for index, component in enumerate(first_path):
        if all(len(path) > index and path[index] == component for path in paths[1:]):
            prefix.append(component)
        else:
            break
    return prefix


def _metadata_type_by_path(path_metadata: Optional[Iterable[object]]) -> Dict[str, str]:
    types: Dict[str, str] = {}
    for item in path_metadata or []:
        if isinstance(item, dict):
            path = item.get("path")
            item_type = item.get("type")
        else:
            path = getattr(item, "path", None)
            item_type = getattr(item, "type", None)

        if path and item_type in {"file", "directory"}:
            types[normalize_archive_path(path)] = item_type
    return types


def compute_restore_strip_components(
    paths: Optional[List[str]],
    restore_layout: str = RESTORE_LAYOUT_PRESERVE_PATH,
    path_metadata: Optional[Iterable[object]] = None,
) -> Optional[int]:
    if restore_layout != RESTORE_LAYOUT_CONTENTS_ONLY:
        return None

    normalized_paths = [normalize_archive_path(path) for path in paths or []]
    normalized_paths = [path for path in normalized_paths if path]
    if not normalized_paths:
        return None

    type_by_path = _metadata_type_by_path(path_metadata)

    if len(normalized_paths) == 1:
        path = normalized_paths[0]
        components = _path_components(path)
        item_type = type_by_path.get(path, "file")
        strip_components = (
            len(components) if item_type == "directory" else max(len(components) - 1, 0)
        )
        return strip_components or None

    parent_component_paths = [_path_components(path)[:-1] for path in normalized_paths]
    strip_components = len(_common_prefix(parent_component_paths))
    return strip_components or None
