"""Test-only ORM aggregation; production modules use their own model definitions."""

from onefde.core.clock import now as now
from onefde.infrastructure.idempotency import IdempotencyRecord as IdempotencyRecord
from onefde.modules.auth.models import AuthSession as AuthSession
from onefde.modules.auth.models import LoginAttempt as LoginAttempt
from onefde.modules.engagements.models import Engagement as Engagement
from onefde.modules.tasks.models import Artifact as Artifact
from onefde.modules.tasks.models import DispatchJob as DispatchJob
from onefde.modules.tasks.models import ModelProfileRevision as ModelProfileRevision
from onefde.modules.tasks.models import Run as Run
from onefde.modules.tasks.models import RunEvent as RunEvent
from onefde.modules.tasks.models import Task as Task
from onefde.modules.tasks.models import TaskEvent as TaskEvent
from onefde.modules.tasks.models import TaskInput as TaskInput
from onefde.modules.tasks.models import TaskReview as TaskReview
from onefde.modules.tasks.models import TaskVersion as TaskVersion
