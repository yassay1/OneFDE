"""Knowledge tool catalog and visibility rules. Pure constants; no I/O."""

ROLE_REVISION = "knowledge-role-v1"

TOOL_NAMES = frozenset(
    {
        "search_assets",
        "get_asset",
        "record_business_handoff",
        "record_delivery_feedback",
    }
)

DENIED_TOOL_NAMES = frozenset(
    {
        "grant_permission",
        "publish_asset",
        "mark_verified",
        "dispatch_engineering",
        "write_database",
    }
)

CallerRole = ("business", "fde", "engineering")
Purpose = ("delivery", "internal_research", "public_marketing")
