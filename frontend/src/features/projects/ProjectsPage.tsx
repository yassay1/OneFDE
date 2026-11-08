import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, queryKeys, type EngagementPage } from "../../api";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";

export function ProjectsPage() {
  const projects = useQuery({
    queryKey: queryKeys.engagements,
    queryFn: () => api<EngagementPage>("/api/v1/engagements"),
  });
  const items = projects.data?.items ?? [];
  const duplicateTitles = new Set(
    items
      .map((item) => item.title.trim())
      .filter((title, index, all) => title && all.indexOf(title) !== index),
  );

  return (
    <div className="page">
      <ContextTrail items={[{ label: "OneFDE", to: "/" }, { label: "项目中心" }]} />
      <header className="page-header">
        <h1>项目中心</h1>
        <p>每个项目是一条独立记录。从这里进入四位员工时，会带上同一个项目。</p>
      </header>
      {duplicateTitles.size ? (
        <p className="muted-note">
          有 {duplicateTitles.size} 个标题出现了不止一次。它们是不同的项目记录，没有被合并或隐藏。
        </p>
      ) : null}
      <AsyncState
        loading={projects.isLoading}
        error={projects.error}
        empty={!items.length}
        emptyText={<p>还没有项目。</p>}
        onRetry={() => projects.refetch()}
      >
        <ul className="project-summary-list">
          {items.map((item) => (
            <li key={item.id}>
              <Link className="office-project-card" to={`/projects/${item.id}`}>
                <div>
                  <strong>{item.title}</strong>
                  <span>
                    {item.is_demo ? "模拟项目" : "正式项目"}
                    {item.goal ? ` · ${item.goal}` : ""}
                  </span>
                </div>
                <span className="office-project-cta">进入项目</span>
              </Link>
              <div className="project-summary-actions">
                <Link to={`/business?project=${item.id}`}>Business</Link>
                <Link to={`/fde?project=${item.id}`}>FDE</Link>
                <Link to={`/engineering?project=${item.id}`}>Engineering</Link>
                <Link to={`/knowledge?project=${item.id}&from=fde&role=fde&purpose=delivery`}>Knowledge</Link>
              </div>
            </li>
          ))}
        </ul>
      </AsyncState>
    </div>
  );
}
