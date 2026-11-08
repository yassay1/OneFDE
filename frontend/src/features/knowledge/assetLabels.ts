const labels: Record<string, string> = {
  limited: "有限验证", verified: "已验证", unverified: "未验证",
  internal: "内部可见", public_summary_only: "仅公开摘要",
  cross_project_internal: "跨项目内部复用", project_only: "仅来源项目",
};
export function assetLabel(value: unknown) { return typeof value === "string" ? labels[value] ?? value : value; }
