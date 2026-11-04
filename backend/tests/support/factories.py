from uuid import uuid4

ENGAGEMENT = {"title": "模拟交付", "is_demo": True, "goal": "验证项目持久化"}


def task_payload():
    return {
        "request_id": str(uuid4()),
        "task_key": "engineering-first",
        "original_request": "创建模拟工具草稿，不执行",
        "owner_role": "fde",
        "executor_role": "engineering",
        "spec": {
            "title": "工程草稿",
            "objective": "验证控制接口",
            "scope": "本地模拟",
            "inputs": ["明确标注的模拟输入"],
            "confirmed_rules": [],
            "completion_criteria": ["通过 HTTP 查回草稿"],
            "dependencies": [],
            "capability_versions": [],
        },
    }


def create_engagement(client, auth, key="engagement"):
    response = client.post(
        "/api/v1/engagements", json=ENGAGEMENT, headers={**auth, "Idempotency-Key": key}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_task(client, auth, eid, data=None, key="task"):
    return client.post(
        f"/api/v1/engagements/{eid}/tasks",
        json=data or task_payload(),
        headers={**auth, "Idempotency-Key": key},
    )
