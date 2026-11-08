export const TASK_STATE: Record<string, string> = {
  draft: "草稿",
  queued: "已排队",
  running: "执行中",
  waiting_input: "待补充",
  review: "待评审",
  blocked: "已阻塞",
  succeeded: "已接受",
  cancelled: "已取消",
};

export const RUN_STATE: Record<string, string> = {
  queued: "待认领",
  running: "执行中",
  cancel_requested: "正在停止",
  completed: "已结束",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "现场不明",
};

export const RUN_EVENT_KIND: Record<string, string> = {
  state: "状态",
  progress: "进展",
  check: "检查",
  artifact: "产物",
  error: "错误",
};

export function label(map: Record<string, string>, value: string) {
  return map[value] ?? value;
}

const BANNER_LIVE = new Set(["工作中", "执行中", "检索中", "处理中"]);
const BANNER_WAIT = new Set([
  "等待处理",
  "待补充",
  "待验收",
  "有评审建议",
  "待跟进",
  "待客户补充",
  "待创始人接手",
  "待 FDE 接手",
  "待客户复试",
]);

export function bannerTone(status: string) {
  if (BANNER_LIVE.has(status)) return "live";
  if (BANNER_WAIT.has(status)) return "wait";
  if (status === "已阻塞") return "blocked";
  return "idle";
}
