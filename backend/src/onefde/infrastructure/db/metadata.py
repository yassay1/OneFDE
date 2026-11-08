"""Explicit model-registration assembly for Alembic; no domain module imports this."""

from onefde.infrastructure import idempotency as idempotency  # noqa: F401
from onefde.infrastructure.db.base import Base as Base
from onefde.modules.auth import models as auth_models  # noqa: F401
from onefde.modules.business import models as business_models  # noqa: F401
from onefde.modules.dialogue import models as dialogue_models  # noqa: F401
from onefde.modules.engagements import models as engagement_models  # noqa: F401
from onefde.modules.fde import agent_models as fde_agent_models  # noqa: F401
from onefde.modules.fde import support_models as fde_support_models  # noqa: F401
from onefde.modules.tasks import models as task_models  # noqa: F401
