import { Alert, Button, Select, Space } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  api,
  conflictMessage,
  createIdempotencyGate,
  invalidateEngineering,
  postJson,
  problem,
  queryKeys,
  type ActionAccepted,
  type ModelProfile,
  type Run,
  type Task,
  type TaskCommand,
} from "../../api";

type Props = {
  task: Task;
  run: Run | null | undefined;
  readOnly: boolean;
};

export function TaskControls({ task, run, readOnly }: Props) {
  const client = useQueryClient();
  const gate = useRef(createIdempotencyGate()).current;
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState<TaskCommand | null>(null);
  const [modelRevision, setModelRevision] = useState<string>();

  const profiles = useQuery({
    queryKey: queryKeys.modelProfiles,
    queryFn: () => api<ModelProfile[]>("/api/v1/model-profiles"),
  });

  const usable = (profiles.data ?? []).filter((item) => item.integration_status !== "unavailable");
  const selected = modelRevision ?? usable[0]?.revision_id;

  async function act(command: TaskCommand) {
    if (readOnly || busy) return;
    const needsModel = command === "start" || command === "retry" || command === "continue";
    if (needsModel && !selected) {
      setNotice("请先选择可用的模型修订。");
      return;
    }

    let expectedRunId: string | null = null;
    if (command === "queue" || command === "start") {
      expectedRunId = null;
    } else if (command === "cancel") {
      expectedRunId = task.active_run_id;
    } else {
      expectedRunId = run?.id ?? task.active_run_id;
      if (!expectedRunId) {
        setNotice("当前没有可引用的 Run，无法执行该命令。");
        return;
      }
    }

    const body: Record<string, unknown> = {
      command,
      expected_revision: task.revision,
      expected_run_id: expectedRunId,
    };
    if (needsModel) body.model_profile_revision_id = selected;

    setBusy(command);
    setNotice(undefined);
    try {
      const result = await postJson<ActionAccepted>(
        `/api/v1/tasks/${task.id}/actions`,
        body,
        gate.keyFor(body),
      );
      gate.reset();
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: result.run?.id ?? run?.id,
      });
      setNotice(
        command === "start" || command === "continue" || command === "retry"
          ? "已接单。请等待 Run 状态更新。"
          : command === "stop_for_update"
            ? "已请求停止本轮以处理修改。"
            : command === "cancel"
              ? "已登记取消。"
              : "任务已排队。",
      );
    } catch (error) {
      const conflict = conflictMessage(error);
      if (conflict) {
        await invalidateEngineering(client, {
          engagementId: task.engagement_id,
          taskId: task.id,
          runId: run?.id,
        });
        setNotice(conflict);
      } else {
        setNotice(problem(error));
      }
    } finally {
      setBusy(null);
    }
  }

  if (readOnly) {
    return <p className="eng-muted">历史轮次只读，运行命令已禁用。</p>;
  }

  const state = task.state;
  const runState = run?.state;
  const canQueue = state === "draft";
  const canStart = state === "queued";
  const canContinue = state === "waiting_input" && task.pending_input_count === 0;
  const canRetry = state === "blocked" && runState !== "interrupted";
  const canStop =
    Boolean(task.active_run_id) &&
    (runState === "queued" || runState === "running");
  const stopping = runState === "cancel_requested" || runState === "interrupted";
  const canCancel = state !== "succeeded" && state !== "cancelled" && !stopping;

  return (
    <section className="eng-controls" aria-label="运行命令">
      <div className="eng-controls-row">
        <label>
          <span>模型修订</span>
          <Select
            style={{ minWidth: 260 }}
            placeholder={profiles.isLoading ? "读取模型…" : "选择模型修订"}
            value={selected}
            options={usable.map((item) => ({
              value: item.revision_id,
              label: `${item.provider}/${item.model} · ${item.integration_status}`,
            }))}
            onChange={setModelRevision}
            disabled={!usable.length}
          />
        </label>
        <Space wrap>
          {canQueue ? (
            <Button loading={busy === "queue"} onClick={() => act("queue")}>
              准备任务
            </Button>
          ) : null}
          {canStart ? (
            <Button type="primary" loading={busy === "start"} onClick={() => act("start")}>
              开始执行
            </Button>
          ) : null}
          {canContinue ? (
            <Button type="primary" loading={busy === "continue"} onClick={() => act("continue")}>
              继续执行
            </Button>
          ) : null}
          {canRetry ? (
            <Button type="primary" loading={busy === "retry"} onClick={() => act("retry")}>
              重试
            </Button>
          ) : null}
          {canStop ? (
            <Button loading={busy === "stop_for_update"} onClick={() => act("stop_for_update")}>
              停止本轮处理修改
            </Button>
          ) : null}
          {canCancel ? (
            <Button danger loading={busy === "cancel"} onClick={() => act("cancel")}>
              取消任务
            </Button>
          ) : null}
        </Space>
      </div>
      {state === "waiting_input" && task.pending_input_count > 0 ? (
        <p className="eng-muted">还有待采用输入，采用后再继续执行。</p>
      ) : null}
      {runState === "interrupted" ? (
        <Alert type="warning" showIcon message="现场不明。现有接口不提供强制恢复，请运维核查后再读事实。" />
      ) : null}
      {runState === "cancel_requested" ? (
        <Alert type="info" showIcon message="停止请求已登记，等待执行侧确认。不能显示为已停止。" />
      ) : null}
      {!usable.length && !profiles.isLoading ? (
        <p className="eng-muted">没有可用模型修订。配置就绪不等于当前 Worker 可执行。</p>
      ) : null}
      {notice ? <Alert type="info" showIcon message={notice} /> : null}
    </section>
  );
}
