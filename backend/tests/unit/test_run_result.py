import pytest
from pydantic import ValidationError

from onefde.modules.tasks import schemas as s


@pytest.mark.parametrize(
    "values",
    [
        {"state": "completed"},
        {"state": "failed", "error_code": None},
        {"state": "interrupted", "stopped": True},
        {"state": "completed", "outcome": "submitted"},
        {"state": "completed", "outcome": "needs_input"},
        {"state": "failed", "error_code": "err", "outcome": "submitted"},
    ],
)
def test_internal_result_requires_explicit_valid_end_facts(values):
    with pytest.raises(ValidationError):
        s.RunResult(**({"summary": "SIMULATED", "stopped": True} | values))
