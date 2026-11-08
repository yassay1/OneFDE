import { Alert, Select } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  queryKeys,
  type ArtifactPage,
  type Delivery,
  type DeliveryTask,
  type EngagementPage,
  type ReviewPage,
  type Run,
  type RunEventPage,
  type RunPage,
  type RunReviewEvidence,
  type RuntimeStatus,
  type Task,
} from "../../api";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";
import { isUuid, uuidOrEmpty } from "../../shared/ids";
import { bannerTone } from "../../shared/labels";
import { CodeWorkspace } from "./CodeWorkspace";
import { EngineerChat } from "./EngineerChat";
import { ReviewForm } from "./ReviewForm";
import { TaskControls } from "./TaskControls";

function activeRunPolling(state?: string) {
  if (document.hidden) return false;
  return state === "queued" || state === "running" || state === "cancel_requested" ? 2000 : false;
}

function EngHero({ status }: { status?: string }) {
  const [sceneFailed, setSceneFailed] = useState(false);

  return (
    <header className="eng-hero">
      <div className={`eng-hero-scene${!sceneFailed ? " has-art" : ""}`} aria-hidden="true">
        <img
          className="eng-hero-scene-img"
          src="/engineering-hero-scene.png"
          alt=""
          onLoad={() => setSceneFailed(false)}
          onError={(event) => {
            setSceneFailed(true);
            event.currentTarget.style.display = "none";
          }}
        />
        {sceneFailed ? (
          <div className="eng-hero-scene-ph">
            <span>场景暂不可用</span>
          </div>
        ) : null}
      </div>
      <div className="eng-hero-copy">
        <h1>Engineering</h1>
        <p>任务、运行活动与固定补丁</p>
        {status ? (
          <p className={`eng-status-pill is-${bannerTone(status)}`}>
            <span className="eng-status-dot" aria-hidden />
            {status}
          </p>
        ) : null}
      </div>
    </header>
  );
}

function recordedExecution(state: string | undefined, worker?: "running" | "not_running") {
  if (state !== "running" && state !== "queued") return null;
  if (worker === "running") return "执行中";
  if (worker === "not_running") return "记录为执行中，Worker 没有心跳";
  return "读取 Worker 状态";
}

function heroStatus(
  tasks: DeliveryTask[] | undefined,
  loading: boolean,
  selected?: Task,
  worker?: "running" | "not_running",
) {
  if (loading) return "读取中";
  const focus = selected?.state;
  const focused = recordedExecution(focus, worker);
  if (focused) return focused;
  if (focus === "waiting_input") return "待补充";
  if (focus === "review") return "待验收";
  if (focus === "blocked") return "已阻塞";
  const active = tasks?.find((item) => item.state === "running" || item.state === "queued");
  const listed = recordedExecution(active?.state, worker);
  if (listed) return listed;
  if (tasks?.some((item) => item.state === "review" || item.state === "waiting_input")) return "等待处理";
  if (tasks?.some((item) => item.state === "succeeded")) return "有已接受任务";
  if (tasks?.length) return "有工程任务";
  return "待命";
}

export function EngineeringPage() {
  const [params, setParams] = useSearchParams();
  const rawProject = params.get("project") ?? "";
  const rawTask = params.get("task");
  const rawRun = params.get("run");
  const projectId = uuidOrEmpty(rawProject);
  const taskId = uuidOrEmpty(rawTask) || null;
  const runIdParam = uuidOrEmpty(rawRun) || null;
  const badProject = Boolean(rawProject && !isUuid(rawProject));

  useEffect(() => {
    if (!rawProject && !rawTask && !rawRun) return;
    const next = new URLSearchParams(params);
    let changed = false;
    if (rawProject && !isUuid(rawProject)) {
      next.delete("project");
      next.delete("task");
      next.delete("run");
      next.delete("view");
      changed = true;
    } else {
      if (rawTask && !isUuid(rawTask)) {
        next.delete("task");
        changed = true;
      }
      if (rawRun && !isUuid(rawRun)) {
        next.delete("run");
        next.delete("view");
        changed = true;
      }
    }
    if (changed) setParams(next, { replace: true });
  }, [params, rawProject, rawRun, rawTask, setParams]);

  const projects = useQuery({
    queryKey: queryKeys.engagements,
    queryFn: () => api<EngagementPage>("/api/v1/engagements"),
  });

  const delivery = useQuery({
    queryKey: queryKeys.delivery(projectId),
    enabled: Boolean(projectId),
    queryFn: () => api<Delivery>(`/api/v1/engagements/${projectId}/delivery`),
    refetchInterval: 10000,
  });

  const selectedTaskId = useMemo(() => {
    if (!delivery.data?.tasks.length) return "";
    if (taskId) return delivery.data.tasks.some((item) => item.id === taskId) ? taskId : "";
    return delivery.data.tasks[0]?.id ?? "";
  }, [delivery.data, taskId]);

  const task = useQuery({
    queryKey: queryKeys.task(selectedTaskId),
    enabled: Boolean(selectedTaskId),
    queryFn: () => api<Task>(`/api/v1/tasks/${selectedTaskId}`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      const state = query.state.data?.state;
      return state === "running" || state === "queued"
        ? 2000
        : state === "waiting_input" || state === "review"
          ? 10000
          : false;
    },
  });

  const runs = useQuery({
    queryKey: queryKeys.runs(selectedTaskId),
    enabled: Boolean(selectedTaskId),
    queryFn: () => api<RunPage>(`/api/v1/tasks/${selectedTaskId}/runs?limit=50`),
  });

  const selectedRunId = useMemo(() => {
    if (!selectedTaskId || !task.data || !runs.data) return null;
    if (runIdParam) {
      const owned = runs.data?.items.some((item) => item.id === runIdParam);
      return owned ? runIdParam : null;
    }
    return task.data?.active_run_id ?? task.data?.latest_run_id ?? runs.data?.items[0]?.id ?? null;
  }, [runIdParam, runs.data, selectedTaskId, task.data]);

  const historyLocked = Boolean(
    runIdParam &&
      (!selectedRunId || selectedRunId !== (task.data?.active_run_id ?? task.data?.latest_run_id)),
  );

  const run = useQuery({
    queryKey: queryKeys.run(selectedRunId ?? ""),
    enabled: Boolean(selectedRunId),
    queryFn: () => api<Run>(`/api/v1/runs/${selectedRunId}`),
    refetchInterval: (query) => activeRunPolling(query.state.data?.state),
  });

  const events = useQuery({
    queryKey: queryKeys.runEvents(selectedRunId ?? ""),
    enabled: Boolean(selectedRunId),
    queryFn: () => api<RunEventPage>(`/api/v1/runs/${selectedRunId}/events?limit=100`),
    refetchInterval: () => activeRunPolling(run.data?.state),
  });

  const artifacts = useQuery({
    queryKey: queryKeys.artifacts(selectedRunId ?? ""),
    enabled: Boolean(selectedRunId),
    queryFn: () => api<ArtifactPage>(`/api/v1/runs/${selectedRunId}/artifacts`),
  });

  const reviews = useQuery({
    queryKey: queryKeys.reviews(selectedTaskId),
    enabled: Boolean(selectedTaskId),
    queryFn: () => api<ReviewPage>(`/api/v1/tasks/${selectedTaskId}/reviews`),
  });

  const canLoadEvidence = Boolean(
    selectedRunId &&
      run.data &&
      (run.data.outcome === "submitted" || task.data?.state === "review" || task.data?.state === "succeeded"),
  );
  const evidence = useQuery({
    queryKey: queryKeys.reviewEvidence(selectedRunId ?? ""),
    enabled: canLoadEvidence,
    queryFn: () => api<RunReviewEvidence | null>(`/api/v1/runs/${selectedRunId}/review-evidence`),
  });

  useEffect(() => {
    if (!projectId || !selectedTaskId) return;
    if (taskId === selectedTaskId) return;
    const next = new URLSearchParams(params);
    next.set("task", selectedTaskId);
    setParams(next, { replace: true });
  }, [params, projectId, selectedTaskId, setParams, taskId]);

  function patchParams(patch: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next);
  }

  const runtime = useQuery({
    queryKey: queryKeys.runtimeStatus,
    queryFn: () => api<RuntimeStatus>("/api/v1/runtime/status"),
    enabled: Boolean(projectId),
    refetchInterval: () => (document.hidden ? false : 15000),
  });
  const worker = runtime.data?.engineering_worker.state;

  const mayExecute = Boolean(
    task.data?.state === "running" ||
      task.data?.state === "queued" ||
      delivery.data?.tasks.some((item) => item.state === "running" || item.state === "queued"),
  );
  const status = projectId
    ? heroStatus(
        delivery.data?.tasks,
        delivery.isLoading || task.isLoading || (mayExecute && runtime.isLoading),
        task.data,
        worker,
      )
    : projects.isLoading
      ? "读取中"
      : "待命";

  return (
    <div className="page eng-page">
      <ContextTrail items={[{ label: "OneFDE", to: "/" }, { label: "Engineering" }]} />

      <EngHero status={status} />

      {badProject ? (
        <Alert
          type="warning"
          showIcon
          message="地址中的项目参数不是合法 UUID，已忽略。请从下方列表或下拉框选择真实项目。"
        />
      ) : null}

      {taskId && delivery.data && !selectedTaskId ? (
        <Alert type="warning" showIcon message="地址中的任务不属于当前项目，请从任务列表重新选择。" />
      ) : null}
      {runIdParam && runs.data && !selectedRunId ? (
        <Alert type="warning" showIcon message="当前已读取的任务轮次中没有地址指定的 Run，暂不开放操作。请从历史轮次选择或跟随当前。" />
      ) : null}

      <div className="eng-toolbar">
        <label className="eng-project-picker">
          <span>当前项目</span>
          <Select
            showSearch
            optionFilterProp="label"
            style={{ minWidth: 280 }}
            placeholder="选择项目"
            value={projectId || undefined}
            options={(projects.data?.items ?? []).map((item) => ({
              value: item.id,
              label: item.title,
            }))}
            onChange={(value) => patchParams({ project: value, task: null, run: null, view: null })}
          />
        </label>
        {selectedTaskId && (runs.data?.items.length ?? 0) > 0 ? (
          <label className="eng-project-picker">
            <span>轮次</span>
            <select
              value={selectedRunId ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                const latest = task.data?.active_run_id ?? task.data?.latest_run_id ?? "";
                patchParams({ run: value && value !== latest ? value : null });
              }}
            >
              {runs.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  第 {item.attempt} 轮 {item.state}
                  {item.outcome ? ` / ${item.outcome}` : ""} · 规格 v{item.task_spec_version}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {projectId ? (
          <Link
            to={`/knowledge?from=engineering&project=${projectId}${selectedTaskId ? `&task=${selectedTaskId}` : ""}${selectedRunId ? `&run=${selectedRunId}` : ""}&role=engineering&purpose=delivery`}
          >
            查 Knowledge
          </Link>
        ) : null}
      </div>

      {!projectId ? (
        <AsyncState
          loading={projects.isLoading}
          error={projects.error}
          empty={!projects.data?.items.length}
          emptyText={<p>还没有项目。请先在项目中心确认 Engagement。</p>}
          onRetry={() => projects.refetch()}
        >
          <ul className="project-summary-list eng-project-picker-list">
            {projects.data?.items.map((item) => (
              <li key={item.id}>
                <button type="button" className="text-link-button" onClick={() => patchParams({ project: item.id })}>
                  <strong>{item.title}</strong>
                  <span>
                    {item.is_demo ? "模拟" : "正式"} · {item.goal}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </AsyncState>
      ) : (
        <AsyncState
          loading={delivery.isLoading}
          error={delivery.error}
          empty={!delivery.data?.tasks.length}
          emptyText={
            <p>
              这个项目还没有工程任务。可到 <Link to={`/projects/${projectId}`}>项目详情</Link> 或{" "}
              <Link to={`/fde?project=${projectId}`}>FDE</Link> 明确范围。
            </p>
          }
          onRetry={() => delivery.refetch()}
        >
          {(delivery.data?.tasks.length ?? 0) > 1 ? (
            <label className="eng-task-switch">
              <span>当前任务</span>
              <select
                value={selectedTaskId}
                onChange={(event) => patchParams({ task: event.target.value, run: null, view: null })}
              >
                {delivery.data?.tasks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {task.data ? (
            <div className="eng-studio">
              <EngineerChat task={task.data} run={run.data} events={events.data?.items ?? []} readOnly={historyLocked} />
              <div className="eng-code-stack">
                <CodeWorkspace
                  task={task.data}
                  run={run.data}
                  events={events.data?.items ?? []}
                  evidence={canLoadEvidence ? evidence.data : null}
                  evidenceError={evidence.error}
                  onRetryEvidence={() => evidence.refetch()}
                />
                <details className="eng-run-fold">
                  <summary>运行与验收</summary>
                  <TaskControls task={task.data} run={run.data} readOnly={historyLocked} />
                  <section aria-label="产物元数据">
                    <h3>固定产物</h3>
                    {artifacts.data?.items.length ? (
                      <ul className="eng-input-list">
                        {artifacts.data.items.map((item) => (
                          <li key={item.id}>
                            <strong>{item.name}</strong>
                            <p>
                              {item.kind} · {item.size_bytes} 字节 · {item.sha256.slice(0, 12)}
                            </p>
                            <small className="eng-muted">只有元数据，不能下载文件。</small>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="eng-muted">本轮没有产物元数据。</p>
                    )}
                  </section>
                  {run.data && (task.data.state === "review" || task.data.state === "succeeded") ? (
                    <ReviewForm
                      task={task.data}
                      run={run.data}
                      artifacts={artifacts.data?.items ?? []}
                      evidence={evidence.data}
                      readOnly={historyLocked || task.data.state !== "review"}
                    />
                  ) : null}
                  {(reviews.data?.items.length ?? 0) > 0 ? (
                    <ul className="eng-input-list">
                      {reviews.data?.items.map((item) => (
                        <li key={item.id}>
                          <strong>{item.verdict === "accept" ? "已接受" : "要求修改"}</strong>
                          <p>{item.reason}</p>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </details>
              </div>
            </div>
          ) : null}
        </AsyncState>
      )}
    </div>
  );
}
