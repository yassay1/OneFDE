"""Visibility filter for capability manifests."""


def can_list(asset: dict, *, purpose: str) -> bool:
    visibility = asset.get("visibility", "internal")
    if visibility == "restricted":
        return False
    if purpose == "public_marketing":
        return bool(asset.get("public_summary")) and visibility in (
            "public_case",
            "internal",
        )
    return visibility in ("internal", "public_case")


def project_for_list(asset: dict, *, purpose: str) -> dict:
    """Return a safe list projection. Restricted assets must not appear at all."""
    if purpose == "public_marketing":
        return {
            "id": asset["id"],
            "name": asset["name"],
            "version": asset["version"],
            "verification_status": asset.get("verification_status"),
            "public_summary": asset.get("public_summary"),
            "visibility": "public_summary_only",
        }
    return {
        "id": asset["id"],
        "name": asset["name"],
        "version": asset["version"],
        "type": asset.get("type"),
        "verification_status": asset.get("verification_status"),
        "visibility": asset.get("visibility"),
        "reuse_scope": asset.get("reuse_scope"),
        "source_engagement": asset.get("source_engagement"),
        "implementation_ref": asset.get("implementation_ref"),
        "keywords": asset.get("keywords", []),
    }


def project_for_get(asset: dict, *, purpose: str) -> dict | None:
    visibility = asset.get("visibility", "internal")
    if visibility == "restricted":
        return None
    if purpose == "public_marketing":
        if not asset.get("public_summary"):
            return None
        return project_for_list(asset, purpose=purpose)
    # Full internal body for delivery/research (still not restricted).
    data = {k: v for k, v in asset.items() if not str(k).startswith("_")}
    data.pop("body", None)  # body only on restricted fixtures; never echo
    return data
