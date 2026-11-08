from onefde.modules.knowledge.schemas import KnowledgeToolCall
from onefde.modules.knowledge.tools import invoke as invoke


def consult_delivery(actor, question, asset_ids):
    """Summarize permitted, versioned options using the existing catalog."""
    options = []
    for asset_id in dict.fromkeys(asset_ids):
        asset = invoke(
            actor,
            KnowledgeToolCall(
                tool="get_asset",
                caller_role="fde",
                purpose="delivery",
                arguments={"asset_id": asset_id},
            ),
        ).result["asset"]
        options.append(
            {
                "reference": f"{asset['id']}@{asset['version']}",
                "problem": asset.get("problem"),
                "applicable_when": asset.get("applicable_when", []),
                "not_applicable_when": asset.get("not_applicable_when", []),
                "reuse_scope": asset.get("reuse_scope"),
                "verification_status": asset.get("verification_status"),
                "verified_samples": asset.get("verified_samples", []),
                "evidence": asset.get("evidence", []),
            }
        )
    return {
        "question": question,
        "options": options,
        "follow_up": "核对当前项目的规则与输入，按选定版本在项目样例中重新检查。",
    }
