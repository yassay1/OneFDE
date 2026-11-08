import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, queryKeys, type EngagementPage } from "../../api";
import { AsyncState } from "../../shared/AsyncState";
import { label, RUN_STATE, TASK_STATE } from "../../shared/labels";
import { OfficeScene } from "./OfficeScene";
import { deriveRoleStatuses, type OfficeFeedItem } from "./roleStatus";

const PROJECT_LIST_LIMIT = 8;

type OfficeCoverage = {
  description: string;
  scanned_cases: number;
  scanned_tasks: number;
  scanned_fde_works: number;
  scanned_runs: number;
  scanned_reviews: number;
};

type OfficeFeedPage = {
  items: OfficeFeedItem[];
  next_cursor: string | null;
  read_at: string;
  coverage: OfficeCoverage;
};

const ROLE_LABEL: Record<string, string> = {
  business: "Business",
  engineering: "Engineering",
  fde: "FDE",
  knowledge: "Knowledge",
};

const OFFICE_STATE: Record<string, string> = {
  ...TASK_STATE,
  open: "待跟进",
  clarifying: "待客户补充",
  founder_queue: "待创始人接手",
  fde_queue: "待 FDE 接手",
  handling: "处理中",
  awaiting_retest: "待客户复试",
  closed: "已关闭",
  pending: "待处理",
  processing: "处理中",
  reported: "已报告",
};

const VERDICT: Record<string, string> = {
  accept: "已接受",
  request_changes: "要求修改",
  submitted: "已提交",
  succeeded: "已完成",
  failed: "失败",
};

const WORKFLOW: Record<string, string> = {
  inquiry: "客户咨询",
  support: "售后",
  outreach: "演示邀请",
};

function officeState(state: string) {
  if (state.includes("/")) {
    const [run, outcome] = state.split("/");
    const outcomeLabel = VERDICT[outcome] ?? label(OFFICE_STATE, outcome);
    return `${label(RUN_STATE, run)} · ${outcomeLabel}`;
  }
  return VERDICT[state] ?? label(OFFICE_STATE, state);
}

function officeReason(reason: string) {
  return reason.replaceAll("此结果由确定性登记写入，未调用模型。", "").trim();
}

function officeTitle(item: OfficeFeedItem) {
  const parts = item.title.split(" · ");
  const tail = parts.at(-1) ?? "";
  if (item.kind === "fde_work" || (parts[0] === "FDE 工作" && tail.includes("-"))) return "FDE 工作";
  if (parts[0] === "Run") return "工程运行";
  if (parts[0] === "评审") return `评审 · ${officeState(parts[1] ?? item.state)}`;
  if (/^[0-9a-f-]{8}-/.test(tail) && parts.length > 1) {
    return WORKFLOW[parts[0]] ?? parts[0];
  }
  return item.title;
}

function dayGreeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "夜深了";
  if (hour < 12) return "上午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

export function OfficePage() {
  const projects = useQuery({
    queryKey: queryKeys.engagements,
    queryFn: () => api<EngagementPage>(`/api/v1/engagements?limit=${PROJECT_LIST_LIMIT}`),
  });

  const actionable = useQuery({
    queryKey: queryKeys.officeActionable(""),
    queryFn: () => api<OfficeFeedPage>("/api/v1/office/actionable?limit=30"),
  });

  const activity = useQuery({
    queryKey: queryKeys.officeActivity(""),
    queryFn: () => api<OfficeFeedPage>("/api/v1/office/activity?limit=20"),
  });

  const feedLoading =
    (actionable.isLoading && !actionable.data) || (activity.isLoading && !activity.data);
  const feedHardError =
    Boolean(actionable.error && !actionable.data) && Boolean(activity.error && !activity.data);
  const feedPartialError = Boolean(actionable.error || activity.error) && !feedHardError;
  const statuses = deriveRoleStatuses({
    actionable: actionable.data?.items,
    activity: activity.data?.items,
    loading: feedLoading,
    error: feedHardError,
  });

  return (
    <div className="page office-page">
      <header className="office-hero">
        <div className="office-hero-copy">
          <h1>
            {dayGreeting()}，创始人
          </h1>
          <p>你的 AI 团队正在协作，推进客户项目的交付。</p>
        </div>
        {(feedHardError || feedPartialError) && (
          <p className="office-partial-fail" role="alert">
            {feedHardError ? "员工状态读取失败" : "部分状态源读取失败"}
            {actionable.error ? "（待办）" : ""}
            {activity.error ? "（动态）" : ""}
            。气泡只反映已读事实。
            <button
              type="button"
              className="linkish"
              onClick={() => {
                void actionable.refetch();
                void activity.refetch();
              }}
            >
              重试
            </button>
          </p>
        )}
      </header>

      <div className="office-layout">
        <section className="office-brand-panel" aria-label="AI 员工入口">
          <OfficeScene statuses={statuses} />
        </section>

        <aside className="office-side" aria-label="待办与动态">
          <section className="office-action-panel" aria-labelledby="office-actions-heading">
            <div className="section-head">
              <h2 id="office-actions-heading">需要你处理</h2>
            </div>
            <AsyncState
              loading={actionable.isLoading}
              error={actionable.error}
              empty={!actionable.data?.items.length}
              emptyText={<p>当前派生范围内没有待处理事项。</p>}
              onRetry={() => actionable.refetch()}
            >
              <ul className="office-action-list">
                {actionable.data?.items.map((item) => (
                  <li key={item.id}>
                    <Link to={item.href}>
                      <div className="office-action-head">
                        <strong>{officeTitle(item)}</strong>
                        <span className="status-badge">{officeState(item.state)}</span>
                      </div>
                      <p>{officeReason(item.reason)}</p>
                      <small className="eng-muted">
                        {ROLE_LABEL[item.role] ?? item.role} ·{" "}
                        {new Date(item.occurred_at).toLocaleString("zh-CN")}
                      </small>
                    </Link>
                  </li>
                ))}
              </ul>
            </AsyncState>
            {actionable.data?.next_cursor ? (
              <p className="muted-note">还有更多待办，请到对应员工页面继续处理。</p>
            ) : null}
          </section>

          <section className="office-activity" aria-labelledby="office-activity-heading">
            <div className="section-head">
              <h2 id="office-activity-heading">团队动态</h2>
            </div>
            <AsyncState
              loading={activity.isLoading}
              error={activity.error}
              empty={!activity.data?.items.length}
              emptyText={<p>暂无动态条目。</p>}
              onRetry={() => activity.refetch()}
            >
              <ul className="office-activity-list">
                {activity.data?.items.map((item) => (
                  <li key={item.id}>
                    <Link to={item.href}>
                      <strong>{officeTitle(item)}</strong>
                      <span>
                        {officeState(item.state)} · {officeReason(item.reason)}
                      </span>
                      <small className="eng-muted">
                        {ROLE_LABEL[item.role] ?? item.role} ·{" "}
                        {new Date(item.occurred_at).toLocaleString("zh-CN")}
                      </small>
                    </Link>
                  </li>
                ))}
              </ul>
            </AsyncState>
          </section>
        </aside>
      </div>

      <section className="office-projects" aria-labelledby="office-projects-heading">
        <div className="section-head">
          <h2 id="office-projects-heading">在推进的项目</h2>
          <Link to="/projects">全部项目</Link>
        </div>
        <AsyncState
          loading={projects.isLoading}
          error={projects.error}
          empty={!projects.data?.items.length}
          emptyText={<p>还没有项目。</p>}
          onRetry={() => projects.refetch()}
        >
          <ul className="project-summary-list office-project-rail">
            {projects.data?.items.map((item) => (
              <li key={item.id}>
                <Link className="office-project-card" to={`/projects/${item.id}`}>
                  <div>
                    <strong>{item.title}</strong>
                    <span>
                      {item.is_demo ? "模拟" : "正式"}
                      {item.goal ? ` · ${item.goal}` : ""}
                    </span>
                  </div>
                  <span className="office-project-cta">进入项目</span>
                </Link>
                <div className="project-summary-actions">
                  <Link to={`/engineering?project=${item.id}`}>Engineering</Link>
                  <Link to={`/fde?project=${item.id}`}>FDE</Link>
                </div>
              </li>
            ))}
          </ul>
        </AsyncState>
      </section>
    </div>
  );
}
