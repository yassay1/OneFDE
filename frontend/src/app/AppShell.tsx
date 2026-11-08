import { Button } from "antd";
import { useQueryClient } from "@tanstack/react-query";
import { Fragment } from "react";
import { Link, NavLink, Outlet, useMatch, useSearchParams } from "react-router-dom";
import { uuidOrEmpty } from "../shared/ids";
import { logout, useSession } from "./session";

const NAV = [
  { to: "/", end: true, label: "办公室", hint: "公司总览" },
  { to: "/projects", label: "项目中心", hint: "目标与任务" },
  { to: "/business", label: "客户与经营", hint: "Business" },
  { to: "/fde", label: "方案与交付", hint: "FDE" },
  { to: "/engineering", label: "软件开发", hint: "Engineering" },
  { to: "/knowledge", label: "知识与能力", hint: "Knowledge" },
] as const;

function withProject(path: string, project: string | null) {
  const id = uuidOrEmpty(project);
  if (!id || path === "/" || path === "/projects") return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}project=${id}`;
}

function founderInitials(username: string | undefined) {
  const raw = (username ?? "创始人").trim();
  if (!raw) return "OPC";
  const ascii = raw.replace(/[^A-Za-z0-9]/g, "");
  if (ascii.length >= 2) return ascii.slice(0, 3).toUpperCase();
  return raw.slice(0, 2);
}

export function AppShell() {
  const session = useSession();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const projectRoute = useMatch("/projects/:engagementId");
  const fdeRoute = useMatch("/fde");
  const businessRoute = useMatch("/business");
  const businessCaseRoute = useMatch("/business/:caseId");
  const engineeringRoute = useMatch("/engineering");
  const knowledgeRoute = useMatch("/knowledge");
  const rolePreview = Boolean(fdeRoute || businessRoute || businessCaseRoute || engineeringRoute || knowledgeRoute);
  const project = uuidOrEmpty(projectRoute?.params.engagementId) || uuidOrEmpty(params.get("project")) || null;

  if (session.isLoading) {
    return (
      <main className="shell-loading" role="status">
        正在确认登录。
      </main>
    );
  }
  if (session.isError) {
    return <Outlet />;
  }

  const username = session.data?.username ?? "创始人";

  return (
    <div className={rolePreview ? "shell shell-role-preview" : "shell"}>
      <aside className="shell-rail" aria-label="主导航">
        <Link className="shell-brand" to="/">
          <span className="shell-mark" aria-hidden="true" />
          <span className="shell-brand-text">
            <strong>OneFDE</strong>
            <small>AI 技术服务公司</small>
          </span>
        </Link>
        <nav className="shell-nav">
          {NAV.map((item, index) => (
            <Fragment key={item.to}>
              {rolePreview && index === 2 ? <span className="shell-nav-group">AI 员工</span> : null}
              <NavLink
                to={withProject(item.to, project)}
                end={"end" in item ? item.end : false}
                className={({ isActive }) => (isActive ? "shell-link is-active" : "shell-link")}
              >
                {rolePreview && index >= 2 ? (
                  <img className="shell-role-avatar" src={`/avatars/${item.to.slice(1)}.png`} alt="" />
                ) : null}
                <span>{item.label}</span>
                <small>{item.hint}</small>
              </NavLink>
            </Fragment>
          ))}
        </nav>
        <div className="shell-user">
          <div className="shell-user-meta">
            <span className="shell-avatar" aria-hidden="true">
              {founderInitials(username)}
            </span>
            <div>
              <p>{username}</p>
              <small>创始人</small>
            </div>
          </div>
          <Button
            size="small"
            onClick={async () => {
              await logout(client);
              location.hash = "#/login";
              location.reload();
            }}
          >
            退出
          </Button>
        </div>
      </aside>
      <div className="shell-main">
        <Outlet />
      </div>
    </div>
  );
}
