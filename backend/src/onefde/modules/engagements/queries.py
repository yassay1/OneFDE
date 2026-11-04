from onefde.core.errors import ApiException
from onefde.infrastructure.db.pagination import page as paginate
from onefde.modules.engagements import models


def require_engagement(db, engagement_id):
    row = db.get(models.Engagement, engagement_id)
    if row is None:
        raise ApiException(404, "NOT_FOUND", "项目不存在")
    return row


def page(db, model, schema, limit, cursor):
    return paginate(db, model, schema, limit, cursor, scope="engagements")
