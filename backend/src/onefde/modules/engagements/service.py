from onefde.modules.engagements import models, schemas


def create_engagement(db, data):
    row = models.Engagement(**data.model_dump())
    db.add(row)
    db.flush()
    return schemas.Engagement.model_validate(row)
