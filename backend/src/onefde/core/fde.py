"""FDE role tool catalog. Pure constants; no DB/HTTP/SDK."""

ROLE_REVISION = "fde-role-v1"

# Names exposed to an FDE agent loop. Identity and engagement scope are injected
# by trusted code; the model never supplies owner_role or caller username.
TOOL_NAMES = frozenset(
    {
        "read_project",
        "create_task",
        "save_input",
        "adopt_inputs",
        "request_execution",
        "get_task",
        "get_run",
        "propose_review",
    }
)

# Explicit denials for common confused requests (not in TOOL_NAMES).
DENIED_TOOL_NAMES = frozenset(
    {
        "claim_job",
        "register_resource",
        "heartbeat",
        "complete_claim",
        "dispatch",
        "publish_product",
        "grant_permission",
        "run_shell",
        "write_database",
    }
)
