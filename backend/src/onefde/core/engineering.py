"""Pure Engineering context constants and check derivation. No I/O or SDK."""

from __future__ import annotations

import hashlib
import json
import re

ROLE_REVISION = "engineering-role-v1"
CONTEXT_REVISION = "engineering-context-v1"
COMMAND_PREFIX = re.compile(r"^\[(?:auto|check)\]\s*(.+)$", re.IGNORECASE | re.DOTALL)
REVIEW_PREFIX = re.compile(r"^\[review\]\s*(.+)$", re.IGNORECASE | re.DOTALL)


def check_revision(checks: list[dict]) -> str:
    payload = json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def derive_checks(spec: dict) -> list[dict]:
    """Map completion_criteria to typed check slots. Unknown forms stay review."""
    checks = []
    for index, raw in enumerate(spec.get("completion_criteria") or []):
        text = str(raw).strip()
        auto = COMMAND_PREFIX.match(text)
        review = REVIEW_PREFIX.match(text)
        if auto:
            checks.append(
                {
                    "id": f"auto-{index + 1}",
                    "kind": "automatic",
                    "source": "completion_criteria",
                    "criterion": text,
                    "command": auto.group(1).strip(),
                    "cwd": "/workspace",
                }
            )
        else:
            checks.append(
                {
                    "id": f"review-{index + 1}",
                    "kind": "business_review",
                    "source": "completion_criteria",
                    "criterion": review.group(1).strip() if review else text,
                }
            )
    return checks
