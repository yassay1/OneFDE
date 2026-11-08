"""Load capability manifests from the repository capability-library tree."""

import json
from functools import lru_cache
from pathlib import Path

ROOT_MARKERS = ("capability-library", "docs", "backend")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if all((parent / name).exists() for name in ROOT_MARKERS):
            return parent
    raise RuntimeError("cannot locate OneFDE repository root")


def library_root() -> Path:
    return repo_root() / "capability-library"


@lru_cache(maxsize=1)
def load_manifests() -> tuple[dict, ...]:
    root = library_root()
    items = []
    paths = list(root.glob("*/manifest.json"))
    paths.extend(root.glob("candidates/*/manifest.json"))
    for path in sorted(set(paths)):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path.relative_to(repo_root())).replace("\\", "/")
        items.append(data)
    return tuple(items)


def clear_cache():
    load_manifests.cache_clear()


def get_manifest(asset_id: str) -> dict | None:
    for item in load_manifests():
        if item.get("id") == asset_id:
            return item
    return None
