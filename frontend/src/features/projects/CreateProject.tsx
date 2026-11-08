import { Alert, Button, Checkbox, Form, Input } from "antd";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createIdempotencyGate, postJson, problem, queryKeys, type Engagement } from "../../api";

export function CreateProject() {
  const client = useQueryClient(); const navigate = useNavigate(); const gate = useRef(createIdempotencyGate()).current;
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  return <details className="work-panel"><summary>新建项目</summary><Form layout="vertical" initialValues={{ is_demo: true }} onFinish={async (body) => {
    if (busy) return; setBusy(true); setError("");
    try { const p = await postJson<Engagement>("/api/v1/engagements", body, gate.keyFor(body)); await client.invalidateQueries({ queryKey: queryKeys.engagements }); navigate(`/projects/${p.id}`); }
    catch (e) { setError(problem(e)); } finally { setBusy(false); }
  }}><Form.Item name="title" label="项目名称" rules={[{ required: true, whitespace: true, max: 200 }]}><Input /></Form.Item><Form.Item name="goal" label="交付目标" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} /></Form.Item><Form.Item name="is_demo" valuePropName="checked"><Checkbox>模拟项目（演示数据，非真实客户效果）</Checkbox></Form.Item>{error && <Alert type="error" message={error} />}<Button type="primary" htmlType="submit" loading={busy}>创建项目</Button></Form></details>;
}
