import { Alert, Select } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  queryKeys,
  type Delivery,
  type DeliveryTask,
  type EngagementPage,
  type FdeWorkView,
  type RuntimeBeat,
  type RuntimeStatus,
} from "../../api";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";
import { isUuid, uuidOrEmpty } from "../../shared/ids";
import { bannerTone, label, TASK_STATE } from "../../shared/labels";
import { TaskStatus } from "../../shared/StatusBadge";
import { FdeWorkPanel } from "./FdeWorkPanel";

type PipelineStep = {
  id: string;
  label: string;
  state: "done" | "active" | "idle";
  note: string;
};

function FdeHero({ status }: { status?: string }) {
  const [sceneFailed, setSceneFailed] = useState(false);

  return (
    <header className="fde-hero">
      <div className={`fde-hero-scene${!sceneFailed ? " has-art" : ""}`} aria-hidden="true">
        <img
          className="fde-hero-scene-img"
          src="/fde-hero-scene.png"
          alt=""
          onLoad={() => setSceneFailed(false)}
          onError={(event) => {
            setSceneFailed(true);
            event.currentTarget.style.display = "none";
          }}
        />
        {sceneFailed ? (
          <div className="fde-hero-scene-ph">
            <span>场景暂不可用</span>
          </div>
        ) : null}
      </div>
      <div className="fde-hero-copy">
        <h1>FDE</h1>
        <p>需求、方案与交付状态</p>
        {status ? (
          <p className={`fde-status-pill is-${bannerTone(status)}`}>
            <span className="fde-status-dot" aria-hidden />
            {status}
          </p>
        ) : null}
      </div>
    </header>
  );
}

function heroStatus(
  works: FdeWorkView[] | undefined,
  loading: boolean,
  consumer?: RuntimeBeat["state"],
) {
  if (loading) return "读取中";
  if (!works) return undefined;
  if (works.some((item) => item.state === "processing")) {
    if (consumer === "running") return "工作中";
    if (consumer === "not_running") return "有租约，消费者没有心跳";
    return "读取消费者状态";
  }
  if (works.some((item) => item.state === "pending")) {
    return consumer === "running" ? "等待处理" : "待处理，无人认领";
  }
  if (works.some((item) => item.report.review_suggestion)) return "有评审建议";
  if (works.length) return "有工作记录";
  return "待命";
}

function pipeline(
  delivery: Delivery | undefined,
  works: FdeWorkView[],
  consumer?: RuntimeBeat["state"],
): PipelineStep[] {
  const tasks = delivery?.tasks ?? [];
  const hasWork = works.length > 0;
  const pendingWork = works.some((item) => item.state === "pending");
  const processingWork = works.some((item) => item.state === "processing");
  const activeWork = pendingWork || processingWork;
  const reported = works.some((item) => item.state === "reported");
  const hasScope = Boolean(delivery?.scheme_summary || delivery?.sources_note || delivery?.unknowns.length);
  const hasTasks = tasks.length > 0;
  const inReview = tasks.some((item) => item.state === "review");
  const accepted = tasks.some((item) => item.state === "succeeded");
  const engineeringLive = tasks.some((item) =>
    ["queued", "running", "waiting_input", "blocked"].includes(item.state),
  );

  return [
    {
      id: "work",
      label: "交付工作",
      state: activeWork ? "active" : reported || hasWork ? "done" : "idle",
      note: processingWork
        ? consumer === "running"
          ? "处理中"
          : "有租约，消费者没有心跳"
        : pendingWork
          ? consumer === "running"
            ? "待处理，尚未生成报告"
            : "待处理，无人认领"
          : reported
            ? "已有报告"
            : hasWork
              ? "已登记"
              : "尚未登记",
    },
    {
      id: "scope",
      label: "目标与未知项",
      state: hasScope ? "done" : hasWork ? "active" : "idle",
      note: hasScope
        ? `${delivery?.unknowns.length ?? 0} 项未知`
        : hasWork
          ? "待从报告整理"
          : "等待项目资料",
    },
    {
      id: "tasks",
      label: "工程拆解",
      state: hasTasks ? (engineeringLive ? "active" : "done") : reported ? "active" : "idle",
      note: hasTasks ? `${tasks.length} 个 Task` : reported ? "可关联 Engineering" : "尚无 Task",
    },
    {
      id: "accept",
      label: "业务验收",
      state: accepted ? "done" : inReview ? "active" : "idle",
      note: accepted ? "已有接受 Task" : inReview ? "待正式评审" : "不自动视为已交付",
    },
  ];
}

function DeliveryWorkbench({
  projectId,
  caseId,
  workId,
  delivery,
  works,
  consumer,
  loading,
  error,
  onRetry,
}: {
  projectId: string;
  caseId: string | null;
  workId: string | null;
  delivery: Delivery | undefined;
  works: FdeWorkView[];
  consumer?: RuntimeBeat["state"];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const steps = useMemo(() => pipeline(delivery, works, consumer), [consumer, delivery, works]);
  const openUnknowns = delivery?.unknowns ?? [];
  const pendingWorks = works.filter((item) => item.state === "pending" || item.state === "processing");
  const suggestions = works.filter((item) => item.report.review_suggestion);

  return (
    <aside className="fde-side" aria-label="项目方案工作台">
      <AsyncState loading={loading} error={error} onRetry={onRetry}>
        {delivery ? (
          <>
            <section className="fde-panel">
              <div className="section-head">
                <h2>项目目标</h2>
                <span className="fde-scheme-badge">{schemeBadge(delivery.tasks, works, consumer)}</span>
              </div>
              <h3 className="fde-scheme-title">{delivery.engagement.title}</h3>
              <p>{delivery.engagement.goal || "还没有项目目标。"}</p>
              {delivery.scheme_summary && delivery.scheme_summary !== delivery.engagement.goal ? (
                <p className="eng-muted">首个任务目标摘要：{delivery.scheme_summary}</p>
              ) : null}
              {delivery.sources_note ? <p className="eng-muted">来源说明：{delivery.sources_note}</p> : null}
              {openUnknowns.length ? (
                <ul className="fde-output-list">
                  {openUnknowns.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="eng-muted">当前聚合没有待处理问题。这不代表资料已经齐备。</p>
              )}
            </section>

            <section className="fde-panel">
              <h2>任务拆解与工程产出</h2>
              {delivery.tasks.length ? (
                <ul className="fde-output-list">
                  {delivery.tasks.map((item) => (
                    <li key={item.id}>
                      <Link to={`/engineering?project=${projectId}&task=${item.id}`}>
                        <strong>{item.title}</strong>
                        <TaskStatus state={item.state} />
                      </Link>
                      {item.objective && item.objective !== delivery.engagement.goal && item.objective !== delivery.scheme_summary ? (
                        <p>{item.objective}</p>
                      ) : null}
                      <small className="eng-muted">
                        {label(TASK_STATE, item.state)} · spec v{item.spec_version}
                        {item.pending_input_count ? ` · 待处理输入 ${item.pending_input_count}` : ""}
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="eng-muted">还没有工程任务。左侧登记工作并形成报告后，才可能出现任务。</p>
              )}
              <p className="eng-muted">报告正文在左侧选中的工作里，这里只保留任务入口。</p>
            </section>

            <section className="fde-panel">
              <h2>交付状态</h2>
              <ul className="fde-output-list">
                {steps.map((step) => (
                  <li key={step.id}>
                    <strong>{step.label}</strong>
                    <span className="eng-muted">{step.note}</span>
                  </li>
                ))}
              </ul>
              {pendingWorks.length ? (
                <p className="eng-muted">还有 {pendingWorks.length} 项工作未报告。</p>
              ) : null}
              {suggestions.map((item) => {
                const suggestion = item.report.review_suggestion!;
                return (
                  <p key={`sug-${item.id}`}>
                    评审建议：{suggestion.next_step}
                    {item.task_id ? (
                      <>
                        {" "}
                        <Link to={`/engineering?project=${projectId}&task=${item.task_id}&run=${suggestion.run_id}&view=submission`}>
                          去 Engineering 正式评审
                        </Link>
                      </>
                    ) : null}
                  </p>
                );
              })}
              <p className="project-summary-actions">
                <Link to={`/engineering?project=${projectId}`}>打开 Engineering</Link>
                {caseId ? <Link to={`/business/${caseId}`}>原 Case</Link> : null}
                <Link
                  to={`/knowledge?from=fde&project=${projectId}${caseId ? `&case=${caseId}` : ""}${workId ? `&work=${workId}` : ""}&role=fde&purpose=delivery`}
                >
                  查 Knowledge
                </Link>
              </p>
            </section>
          </>
        ) : null}
      </AsyncState>
    </aside>
  );
}

function schemeBadge(
  tasks: DeliveryTask[],
  works: FdeWorkView[],
  consumer?: RuntimeBeat["state"],
) {
  if (tasks.some((item) => item.state === "succeeded")) return "已有接受任务";
  if (tasks.some((item) => item.state === "review")) return "待业务验收";
  if (tasks.some((item) => ["queued", "running", "waiting_input"].includes(item.state))) {
    return "工程进行中";
  }
  if (works.some((item) => item.state === "processing")) {
    return consumer === "running" ? "处理中" : "有租约，消费者没有心跳";
  }
  if (works.some((item) => item.state === "pending")) {
    return consumer === "running" ? "待处理，尚未生成报告" : "待处理，无人认领";
  }
  if (tasks.length) return "已拆解工程";
  if (works.some((item) => item.state === "reported")) return "已有工作报告";
  return "待启动工作";
}

export function FdePage() {
  const [params, setParams] = useSearchParams();
  const rawProject = params.get("project") ?? "";
  const projectId = uuidOrEmpty(rawProject);
  const caseId = uuidOrEmpty(params.get("case")) || null;
  const workId = uuidOrEmpty(params.get("work")) || null;
  const badProject = Boolean(rawProject && !isUuid(rawProject));

  useEffect(() => {
    const rawCase = params.get("case");
    const rawWork = params.get("work");
    if (!rawProject && !rawCase && !rawWork) return;
    const next = new URLSearchParams(params);
    let changed = false;
    if (rawProject && !isUuid(rawProject)) {
      next.delete("project");
      next.delete("work");
      changed = true;
    }
    if (rawCase && !isUuid(rawCase)) {
      next.delete("case");
      changed = true;
    }
    if (rawWork && !isUuid(rawWork)) {
      next.delete("work");
      changed = true;
    }
    if (changed) setParams(next, { replace: true });
  }, [params, rawProject, setParams]);

  const projects = useQuery({
    queryKey: queryKeys.engagements,
    queryFn: () => api<EngagementPage>("/api/v1/engagements"),
  });

  const delivery = useQuery({
    queryKey: queryKeys.delivery(projectId),
    enabled: Boolean(projectId),
    queryFn: () => api<Delivery>(`/api/v1/engagements/${projectId}/delivery`),
    refetchInterval: 8000,
  });

  const works = useQuery({
    queryKey: queryKeys.fdeWork(projectId),
    enabled: Boolean(projectId),
    queryFn: () => api<FdeWorkView[]>(`/api/v1/engagements/${projectId}/fde/work`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      const items = query.state.data ?? [];
      return items.some((item) => item.state === "pending" || item.state === "processing") ? 4000 : false;
    },
  });

  function setProject(value: string) {
    const next = new URLSearchParams(params);
    next.set("project", value);
    next.delete("work");
    next.delete("case");
    setParams(next);
  }

  const runtime = useQuery({
    queryKey: queryKeys.runtimeStatus,
    queryFn: () => api<RuntimeStatus>("/api/v1/runtime/status"),
    enabled: Boolean(projectId),
    refetchInterval: () => (document.hidden ? false : 15000),
  });
  const consumer = runtime.data?.fde_agent.state;

  const mayWork = Boolean(
    works.data?.some((item) => item.state === "pending" || item.state === "processing"),
  );
  const status = projectId
    ? heroStatus(
        works.data,
        works.isLoading || delivery.isLoading || (mayWork && runtime.isLoading),
        consumer,
      )
    : projects.isLoading
      ? "读取中"
      : "待命";

  return (
    <div className="page fde-page">
      <ContextTrail items={[{ label: "OneFDE", to: "/" }, { label: "FDE" }]} />
      <FdeHero status={status} />

      {badProject ? (
        <Alert
          type="warning"
          showIcon
          message="地址中的项目参数不是合法 UUID，已忽略。请从下方列表或下拉框选择真实项目。"
        />
      ) : null}

      <div className="fde-toolbar">
        <label className="eng-project-picker">
          <span>当前项目</span>
          <Select
            showSearch
            optionFilterProp="label"
            style={{ minWidth: 280 }}
            placeholder="选择项目"
            value={projectId || undefined}
            options={(projects.data?.items ?? []).map((item) => ({ value: item.id, label: item.title }))}
            onChange={setProject}
          />
        </label>
        <p className="eng-muted">
          FDE 负责方案与交付组织；Business 管经营会话，Engineering 管实现与正式评审。
        </p>
      </div>

      {!projectId ? (
        <AsyncState
          loading={projects.isLoading}
          error={projects.error}
          empty={!projects.data?.items.length}
          emptyText={<p>还没有项目。先从项目中心或 Business 交接创建。</p>}
          onRetry={() => projects.refetch()}
        >
          <ul className="project-summary-list fde-project-picker-list">
            {projects.data?.items.map((item) => (
              <li key={item.id}>
                <Link to={`/fde?project=${item.id}`}>
                  <strong>{item.title}</strong>
                  <span>{item.goal}</span>
                </Link>
              </li>
            ))}
          </ul>
        </AsyncState>
      ) : (
        <div className="eng-studio">
          <FdeWorkPanel engagementId={projectId} caseId={caseId} selectedWorkId={workId} />
          <div className="eng-code-stack fde-delivery-stack">
          <DeliveryWorkbench
            projectId={projectId}
            caseId={caseId}
            workId={workId}
            delivery={delivery.data}
            works={works.data ?? []}
            consumer={consumer}
            loading={delivery.isLoading}
            error={delivery.error}
            onRetry={() => delivery.refetch()}
          />
          </div>
        </div>
      )}
    </div>
  );
}
