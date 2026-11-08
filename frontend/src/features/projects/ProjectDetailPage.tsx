import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, queryKeys, type Delivery, type DeliveryTask } from "../../api";
import { FdeWorkPanel } from "../fde/FdeWorkPanel";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";
import { label, TASK_STATE } from "../../shared/labels";
import { TaskStatus } from "../../shared/StatusBadge";
import { uuidOrEmpty } from "../../shared/ids";
import { Alert } from "antd";

const PRODUCT_ORIGIN = import.meta.env.VITE_QUOTE_PRODUCT_URL || "http://127.0.0.1:8765/";

const STATE_ORDER = [
  "review",
  "waiting_input",
  "running",
  "queued",
  "draft",
  "blocked",
  "succeeded",
  "cancelled",
] as const;

function groupTasks(tasks: DeliveryTask[]) {
  const groups = new Map<string, DeliveryTask[]>();
  for (const state of STATE_ORDER) groups.set(state, []);
  for (const task of tasks) {
    const bucket = groups.get(task.state) ?? [];
    bucket.push(task);
    groups.set(task.state, bucket);
  }
  return STATE_ORDER.map((state) => ({ state, items: groups.get(state) ?? [] })).filter(
    (group) => group.items.length > 0,
  );
}

export function ProjectDetailPage() {
  const { engagementId: rawEngagementId = "" } = useParams();
  const engagementId = uuidOrEmpty(rawEngagementId);
  const [params] = useSearchParams();
  const caseId = uuidOrEmpty(params.get("case"));
  const highlightTask = uuidOrEmpty(params.get("task"));

  const delivery = useQuery({
    queryKey: queryKeys.delivery(engagementId),
    enabled: Boolean(engagementId),
    queryFn: () => api<Delivery>(`/api/v1/engagements/${engagementId}/delivery`),
    refetchInterval: 8000,
  });

  const groups = useMemo(
    () => (delivery.data ? groupTasks(delivery.data.tasks) : []),
    [delivery.data],
  );

  if (!engagementId) {
    return <div className="page"><Alert type="warning" showIcon message="项目地址无效，请从项目中心选择项目。" /><Link to="/projects">打开项目中心</Link></div>;
  }

  return (
    <div className="page project-page">
      <ContextTrail
        items={[
          { label: "OneFDE", to: "/" },
          { label: "项目中心", to: "/projects" },
          { label: delivery.data?.engagement.title ?? "项目" },
        ]}
      />
      <AsyncState loading={delivery.isLoading} error={delivery.error} onRetry={() => delivery.refetch()}>
        {delivery.data ? (
          <>
            <header className="page-header">
              <h1>{delivery.data.engagement.title}</h1>
              <p>
                {delivery.data.engagement.is_demo ? "模拟项目" : "正式项目"} · {delivery.data.engagement.goal}
              </p>
            </header>

            <p className="project-summary-actions">
              <Link to={`/fde?project=${engagementId}${caseId ? `&case=${caseId}` : ""}`}>FDE 工作台</Link>
              <Link to={`/engineering?project=${engagementId}`}>Engineering</Link>
              {caseId ? <Link to={`/business/${caseId}`}>原 Case</Link> : null}
              <Link to={`/business?project=${engagementId}`}>Business</Link>
            </p>

            <div className="project-grid">
              <section className="project-panel" aria-labelledby="project-facts-heading">
                <h2 id="project-facts-heading">来源与未知项</h2>
                <p>{delivery.data.sources_note || "暂无来源说明。"}</p>
                {delivery.data.unknowns.length ? (
                  <ul className="project-unknowns">
                    {delivery.data.unknowns.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="eng-muted">当前没有登记未知项。</p>
                )}

                <h3>任务目标摘要</h3>
                <p>
                  {delivery.data.scheme_summary ?? "尚无任务目标摘要（来自首个 Task objective，不是独立方案文档）。"}
                </p>

                <h3>最近 Run 摘要</h3>
                {delivery.data.latest_checks.length ? (
                  <ul className="project-checks">
                    {delivery.data.latest_checks.map((item, index) => (
                      <li key={`${index}-${item.slice(0, 24)}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="eng-muted">还没有 Run 结果摘要。这不是结构化检查通过列表。</p>
                )}

                {delivery.data.fixed_version_hint ? (
                  <>
                    <h3>固定版本提示</h3>
                    <p className="eng-muted">{delivery.data.fixed_version_hint}（提示，不是部署链接）</p>
                  </>
                ) : null}

                <h3>交付产品</h3>
                <p>报价页在独立地址打开，工作台不执行那个页面里的脚本。</p>
                <a href={PRODUCT_ORIGIN} target="_blank" rel="noreferrer">
                  打开报价产品
                </a>
              </section>

              <section className="project-panel" aria-labelledby="project-tasks-heading">
                <div className="section-head">
                  <h2 id="project-tasks-heading">任务索引</h2>
                  <span className="eng-muted">按 Task 状态分组 · 正式执行/评审在 Engineering</span>
                </div>
                {!delivery.data.tasks.length ? <p>这个项目还没有任务。</p> : null}
                {highlightTask && !delivery.data.tasks.some((item) => item.id === highlightTask) ? (
                  <p className="eng-muted">URL 中的任务不属于当前项目或已不存在。</p>
                ) : null}
                {groups.map((group) => (
                  <div key={group.state} className="project-task-group">
                    <h3>
                      {label(TASK_STATE, group.state)} · {group.items.length}
                    </h3>
                    <ul className="project-task-list">
                      {group.items.map((item) => (
                        <li
                          key={item.id}
                          className={item.id === highlightTask ? "is-highlight" : undefined}
                        >
                          <div>
                            <strong>{item.title}</strong>
                            <p>{item.objective}</p>
                            <small className="eng-muted">
                              规格 v{item.spec_version} · revision {item.revision}
                              {item.pending_input_count ? ` · 待处理输入 ${item.pending_input_count}` : ""}
                            </small>
                          </div>
                          <div className="project-task-meta">
                            <TaskStatus state={item.state} />
                            <Link to={`/engineering?project=${engagementId}&task=${item.id}`}>
                              {item.state === "review" ? "正式评审" : "打开 Engineering"}
                            </Link>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            </div>

            <FdeWorkPanel engagementId={engagementId} caseId={caseId} />
          </>
        ) : null}
      </AsyncState>
    </div>
  );
}
