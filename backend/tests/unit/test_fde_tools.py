"""FDE tool catalog and pure denial rules without database."""

import pytest
from pydantic import ValidationError

from onefde.core.errors import ApiException
from onefde.core.fde import DENIED_TOOL_NAMES, ROLE_REVISION, TOOL_NAMES
from onefde.modules.fde import schemas
from onefde.modules.fde.tools import _forbidden


def test_tool_catalog_matches_schema_literal():
    assert TOOL_NAMES == set(schemas.ToolName.__args__)
    assert ROLE_REVISION.startswith("fde-role-")
    assert not (TOOL_NAMES & DENIED_TOOL_NAMES)


def test_denied_tools_are_explicit():
    for name in ("claim_job", "publish_product", "run_shell"):
        with pytest.raises(ApiException) as raised:
            _forbidden(name)
        assert raised.value.status == 403
        assert raised.value.code == "FDE_TOOL_FORBIDDEN"


def test_unknown_tool_is_rejected():
    with pytest.raises(ApiException) as raised:
        _forbidden("invent_roles")
    assert raised.value.code == "FDE_TOOL_UNKNOWN"


def test_fde_task_create_rejects_role_fields():
    with pytest.raises(ValidationError):
        schemas.FdeTaskCreate.model_validate(
            {
                "request_id": "11111111-1111-1111-1111-111111111111",
                "task_key": "x",
                "original_request": "demo",
                "owner_role": "fde",
                "executor_role": "engineering",
                "spec": {
                    "title": "t",
                    "objective": "o",
                    "scope": "s",
                    "inputs": [],
                    "confirmed_rules": [],
                    "completion_criteria": ["done"],
                    "dependencies": [],
                    "capability_versions": [],
                },
            }
        )
