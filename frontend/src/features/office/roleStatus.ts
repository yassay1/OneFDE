/** Derive short Office bubble copy from F6 actionable / activity items. */

export type OfficeFeedItem = {
  id: string;
  kind: string;
  role: string;
  title: string;
  reason: string;
  state: string;
  href: string;
  occurred_at: string;
};

export type OfficeRoleId = "business" | "fde" | "engineering" | "knowledge";

export type RoleTone = "attention" | "active" | "done" | "idle" | "loading" | "error";

export type RoleStatus = {
  role: OfficeRoleId;
  label: string;
  tone: RoleTone;
  sourceId?: string;
};

const FOUNDER_CASE = new Set(["founder_queue"]);
const FOUNDER_TASK = new Set(["review", "waiting_input"]);

function forRole(items: OfficeFeedItem[] | undefined, role: string) {
  return (items ?? []).filter((item) => item.role === role);
}

function businessLabel(item: OfficeFeedItem, kind: "attention" | "active" | "done"): string {
  if (kind === "attention") return "等待创始人确认";
  if (kind === "done") return "最近有完成记录";
  switch (item.state) {
    case "clarifying":
      return "澄清客户需求";
    case "fde_queue":
      return "交接 FDE 中";
    case "awaiting_retest":
      return "等待客户复试";
    case "handling":
      return "跟进客户需求";
    case "open":
      return "跟进客户需求";
    default:
      return item.reason?.slice(0, 12) || `Case · ${item.state}`;
  }
}

function fdeLabel(item: OfficeFeedItem, kind: "attention" | "active" | "done"): string {
  if (kind === "attention") {
    return item.state.includes("错误") ? "方案报告待处理" : "等待创始人确认";
  }
  if (kind === "done") return "最近有完成记录";
  if (item.state === "processing") return "方案设计中";
  if (item.state === "pending") return "方案待处理";
  return item.reason?.slice(0, 12) || `FDE · ${item.state}`;
}

function engineeringLabel(item: OfficeFeedItem, kind: "attention" | "active" | "done"): string {
  if (kind === "attention") {
    if (item.state === "review") return "等待创始人评审";
    if (item.state === "waiting_input") return "等待创始人补充";
    return "等待创始人处理";
  }
  if (kind === "done") return "最近有完成记录";
  switch (item.state) {
    case "running":
      return "开发实现中";
    case "queued":
      return "任务排队中";
    case "blocked":
      return "工程已阻塞";
    default:
      if (item.state.includes("/")) return "最近有完成记录";
      return item.reason?.slice(0, 12) || `工程 · ${item.state}`;
  }
}

function pickRole(
  role: "business" | "fde" | "engineering",
  actionable: OfficeFeedItem[] | undefined,
  activity: OfficeFeedItem[] | undefined,
): Omit<RoleStatus, "role"> {
  const open = forRole(actionable, role);
  const done = forRole(activity, role);

  const attention = open.find((item) => {
    if (role === "business") return FOUNDER_CASE.has(item.state);
    if (role === "engineering") return FOUNDER_TASK.has(item.state);
    return item.state.includes("错误");
  });
  if (attention) {
    const label =
      role === "business"
        ? businessLabel(attention, "attention")
        : role === "fde"
          ? fdeLabel(attention, "attention")
          : engineeringLabel(attention, "attention");
    return { label, tone: "attention", sourceId: attention.id };
  }

  const active = open[0];
  if (active) {
    const label =
      role === "business"
        ? businessLabel(active, "active")
        : role === "fde"
          ? fdeLabel(active, "active")
          : engineeringLabel(active, "active");
    return { label, tone: "active", sourceId: active.id };
  }

  const recent = done[0];
  if (recent) {
    const label =
      role === "business"
        ? businessLabel(recent, "done")
        : role === "fde"
          ? fdeLabel(recent, "done")
          : engineeringLabel(recent, "done");
    return { label, tone: "done", sourceId: recent.id };
  }

  return { label: "暂无可确认动态", tone: "idle" };
}

export function deriveRoleStatuses(input: {
  actionable?: OfficeFeedItem[];
  activity?: OfficeFeedItem[];
  loading?: boolean;
  error?: boolean;
}): RoleStatus[] {
  if (input.loading) {
    return (["business", "fde", "engineering", "knowledge"] as const).map((role) => ({
      role,
      label: "读取中…",
      tone: "loading",
    }));
  }
  if (input.error) {
    return (["business", "fde", "engineering", "knowledge"] as const).map((role) => ({
      role,
      label: "状态读取失败",
      tone: "error",
    }));
  }

  return [
    { role: "business", ...pickRole("business", input.actionable, input.activity) },
    { role: "fde", ...pickRole("fde", input.actionable, input.activity) },
    { role: "engineering", ...pickRole("engineering", input.actionable, input.activity) },
    {
      role: "knowledge",
      label: "暂无实时动态 · 待命",
      tone: "idle",
    },
  ];
}
