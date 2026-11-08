"""Reviewed, packaged Engineering skills. No SDK, network or workspace discovery."""

import hashlib
import json
from pathlib import Path

from onefde.core.execution import RuntimeUnavailable

BUNDLE_ROOT = Path(__file__).with_name("engineering_skills")
BUNDLE_REVISION = "engineering-skills-v1"
SKILL_NAMES = (
    "systematic-debugging",
    "verification-before-completion",
    "webapp-testing",
    "frontend-design",
    "onefde-engineering-closeout",
)


def load_bundle() -> tuple[dict, list[tuple[dict, Path]]]:
    """Verify all bundled bytes before constructing an Agent or reading secrets."""
    try:
        raw = (BUNDLE_ROOT / "manifest.json").read_bytes()
        manifest = json.loads(raw)
        if (
            manifest["revision"] != BUNDLE_REVISION
            or tuple(row["name"] for row in manifest["skills"]) != SKILL_NAMES
        ):
            raise ValueError("Unexpected skill catalog")
        for name, expected in manifest["files"].items():
            path = BUNDLE_ROOT / name
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(BUNDLE_ROOT.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("Skill bundle digest mismatch")
        rows = []
        for row in manifest["skills"]:
            name = row["name"] + "/SKILL.md"
            if manifest["files"].get(name) != row["sha256"]:
                raise ValueError("Unverified skill file")
            content = (BUNDLE_ROOT / name).read_text(encoding="utf-8")
            if "!`" in content:
                raise ValueError("Dynamic skill commands are not allowed")
            rows.append((row, BUNDLE_ROOT / name))
        return {**manifest, "manifest_sha256": hashlib.sha256(raw).hexdigest()}, rows
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeUnavailable(
            "Reviewed Engineering skill bundle is invalid"
        ) from exc


def successful_invocation(observation, names: set[str]) -> str | None:
    """Only an SDK tool observation can establish an invocation, not model prose."""
    if type(observation).__name__ != "InvokeSkillObservation":
        return None
    name = getattr(observation, "skill_name", None)
    if name in names and not getattr(observation, "is_error", True):
        return name
    return None


if __name__ == "__main__":
    manifest, _ = load_bundle()
    print(json.dumps({"valid": True, "model_calls": 0, **manifest}, indent=2))
