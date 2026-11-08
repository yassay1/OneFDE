"""Idempotently seed only our dedicated demo DB through real domain services."""

import json
from secrets import token_hex
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from onefde.core.config import Settings
from onefde.infrastructure.db.session import make_engine
from onefde.modules.business import (
    leads,
    operations,
)
from onefde.modules.business import (
    models as bm,
)
from onefde.modules.business import (
    schemas as bs,
)
from onefde.modules.business import (
    service as business,
)
from onefde.modules.engagements import (
    models as em,
)
from onefde.modules.engagements import (
    schemas as es,
)
from onefde.modules.engagements import (
    service as engagements,
)
from onefde.modules.fde import agent_schemas, agent_work
from onefde.modules.tasks import models as tm
from onefde.modules.tasks import schemas as ts
from onefde.modules.tasks import service as tasks
from scripts.local_demo import ENV, load


def identifier(name):
    return uuid5(NAMESPACE_URL, f"onefde:product-demo:v1:{name}")


def main():
    load()
    settings = Settings()
    url = settings.database_url.get_secret_value()
    if not url.endswith("/onefde_product_demo"):
        raise SystemExit("拒绝初始化：仅允许本工具的独立onefde_product_demo库。")
    engine = make_engine(url)
    with Session(engine) as db, db.begin():
        project = db.scalar(
            select(em.Engagement).where(
                em.Engagement.title == "模拟 · 鲜果门店报价协作"
            )
        )
        if not project:
            created = engagements.create_engagement(
                db,
                es.EngagementCreate(
                    title="模拟 · 鲜果门店报价协作",
                    is_demo=True,
                    goal="核对同口径报价比较的范围，组织工程任务并保留客户来源。",
                ),
            )
            project = db.get(em.Engagement, created.id)
        task = db.scalar(
            select(tm.Task).where(
                tm.Task.engagement_id == project.id, tm.Task.task_key == "demo-initial"
            )
        )
        if not task:
            saved = tasks.create_task(
                db,
                project.id,
                ts.TaskCreate(
                    request_id=identifier("task-request"),
                    task_key="demo-initial",
                    original_request="模拟门店希望报价结果中保留供应商备注，并明确不可比较的原因。",
                    owner_role="fde",
                    executor_role="engineering",
                    spec=ts.TaskSpec(
                        title="模拟 · 报价说明与待核对原因",
                        objective="保留备注并解释需要核对的报价",
                        scope="仅CSV同口径比较；不自动换算箱价，不自动选供应商或部署",
                        inputs=[
                            "明确标注的模拟客户说明",
                            "能力fresh-quote-compare-csv@1.1.0",
                        ],
                        confirmed_rules=[
                            "商品、等级、规格、单位相同才比较",
                            "信息不足显示待核对",
                        ],
                        completion_criteria=[
                            "CSV备注保持原文",
                            "不可比较项显示原因",
                            "保持既有比较与导出行为",
                        ],
                        dependencies=[],
                        capability_versions=["fresh-quote-compare-csv@1.1.0"],
                    ),
                ),
                "founder",
            )
            task = db.get(tm.Task, saved.id)
            tasks.append_input(
                db,
                task.id,
                ts.TaskInputCreate(
                    expected_revision=task.revision,
                    kind="clarification",
                    text="模拟补充：备注只展示，不参与最低价计算；请负责人核对后采用。",
                    evidence_artifact_ids=[],
                ),
                "founder",
            )
        case = db.get(bm.Case, identifier("case"))
        if not case:
            token = token_hex(32)
            case = business.start(
                db,
                identifier("case"),
                token,
                bs.StartConversation(
                    request_id=identifier("message"),
                    text="模拟需求：希望报价比较结果保留供应商备注，并标明不可比较的原因。",
                    willing_to_continue=True,
                    version_hint="demo-supplier-quotes@1.1.0",
                ),
            )
            if case.state != "fde_queue":
                operations.handle(
                    db,
                    case,
                    bs.HandoffCommand(
                        action="handoff",
                        title="模拟报价需求交接",
                        goal=task.spec["objective"],
                        confirmed_facts=["客户希望保留供应商备注"],
                        unknowns=["备注是否参与价格计算待负责人核对"],
                    ),
                    "founder",
                )
            operations.handle(
                db,
                case,
                bs.AcceptHandoff(
                    action="accept_handoff", engagement_id=project.id, task_id=task.id
                ),
                "founder",
            )
            agent_work.start(
                db,
                project.id,
                agent_schemas.StartWork(case_id=case.id),
                "founder",
                preserve_existing_task=True,
            )
            # Keep customer continuation capability private, never in shared evidence.
            (ENV.parent / "product-demo-customer.json").write_text(
                json.dumps({"case_id": str(case.id), "token": token}), encoding="utf-8"
            )
        if not db.scalar(select(bm.Candidate.id).limit(1)):
            leads.search(db, None, bs.SearchDistrict(adcode="440106", sample=True))
        if not db.scalar(
            select(em.Engagement.id).where(
                em.Engagement.title == "模拟 · 第二次能力复用"
            )
        ):
            engagements.create_engagement(
                db,
                es.EngagementCreate(
                    title="模拟 · 第二次能力复用",
                    is_demo=True,
                    goal="核对既有CSV比较能力的适用条件，保留独立复用与重新检查记录。",
                ),
            )
        result = {
            "engagement_id": str(project.id),
            "task_id": str(task.id),
            "case_id": str(case.id),
            "data_kind": "模拟输入；真实业务服务/数据库；未执行模型/工程，未登记成功",
        }
    engine.dispose()
    (ENV.parent / "product-demo-objects.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
