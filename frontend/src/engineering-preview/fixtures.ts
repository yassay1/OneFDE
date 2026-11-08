export type TaskState = "review" | "running" | "waiting_input" | "succeeded" | "draft";
export type RunState = "submitted" | "running" | "needs_input";
export type Verdict = "accept" | "request_changes";

export type RunEvent = {
  time: string;
  title: string;
  detail: string;
  kind: "state" | "progress" | "check" | "artifact";
};

type Check = { name: string; command: string; exit_code: number | null; timeout: boolean };
type Artifact = { id: string; name: string; kind: string; size: string; sha256: string };

export type Evidence = {
  file: string;
  baseline: string;
  design: string;
  diff: string;
  diff_truncated: boolean;
  self_checks: Check[];
  validation_checks: Check[];
  artifacts: Artifact[];
};

export type Run = {
  id: string;
  attempt: number;
  task_spec_version: number;
  state: RunState;
  summary: string;
  events: RunEvent[];
  evidence?: Evidence;
  question?: string;
};

export type Input = {
  id: string;
  runId: string;
  text: string;
  kind: "answer" | "change_request" | "clarification";
  status: "pending" | "applied";
  appliedVersion?: number;
};

export type Review = {
  runId: string;
  specVersion: number;
  artifactIds: string[];
  verdict: Verdict;
  reason: string;
  check: string;
};

export type Task = {
  id: string;
  title: string;
  handoff: string;
  spec_version: number;
  state: TaskState;
  runs: Run[];
  inputs: Input[];
  reviews: Review[];
};

export const taskLabels: Record<TaskState, string> = {
  review: "待评审",
  running: "执行中",
  waiting_input: "待补充",
  succeeded: "已接受",
  draft: "草稿",
};

export const runLabels: Record<RunState, string> = {
  submitted: "本轮已提交",
  running: "执行中",
  needs_input: "本轮结束，待答",
};

const check = (name: string, command: string): Check => ({
  name, command, exit_code: 0, timeout: false,
});

const submittedEvents: RunEvent[] = [
  { time: "10:48", title: "准备运行环境", detail: "已载入规格 v3 和上一轮的固定源码。", kind: "state" },
  { time: "10:50", title: "更新 CSV 表头处理", detail: "归一化 BOM 与列名两端的空格，仍拒绝重复列名。", kind: "progress" },
  { time: "10:52", title: "固定归档独立复验通过", detail: "标准 CSV、变体表头和缺列回归均通过。", kind: "check" },
  { time: "10:54", title: "提交固定成果", detail: "已登记源码归档与检查报告，等待业务评审。", kind: "artifact" },
];

export const fixtures: Task[] = [
  {
    id: "task-014",
    title: "CSV 表头兼容性修复",
    handoff: "修复 CSV 表头含 BOM 或前后空格时的导入失败。保留缺列、重复列校验和原有报价比较规则。",
    spec_version: 3,
    state: "review",
    inputs: [],
    reviews: [],
    runs: [
      {
        id: "run-014-03", attempt: 3, task_spec_version: 3, state: "submitted",
        summary: "已修复 CSV 表头的 BOM 与前后空格兼容问题。原有报价比较规则保持有效，固定源码已完成独立复验。",
        events: submittedEvents,
        evidence: {
          file: "src/compare.js",
          baseline: "第 2 轮固定源码",
          design: "在校验必填列之前归一化 CSV 表头。只处理文件开头的 BOM 和列名边缘空白，归一化后仍检查重复与缺失列。",
          diff: [
            "  function parseCsv(content) {",
            "    const [header, ...rows] = splitCsv(content);",
            "-   const headers = parseRow(header);",
            "+   const normalizedHeader = header.replace(/^\\uFEFF/, '');",
            "+   const headers = parseRow(normalizedHeader)",
            "+     .map((name) => name.trim());",
            "    assertRequiredColumns(headers);",
            "    return parseRows(rows, headers);",
            "  }",
          ].join("\n"),
          diff_truncated: false,
          self_checks: [check("CSV 核心检查", "node check.mjs")],
          validation_checks: [
            check("标准 CSV 导入", "node check.mjs --case standard"),
            check("BOM 与空格表头", "node check.mjs --case header-variants"),
            check("缺列与重复列回归", "node check.mjs --case invalid-headers"),
          ],
          artifacts: [
            { id: "demo-source-03", name: "quote-compare-run-03.tar.gz", kind: "源码归档", size: "42.6 KB", sha256: "6a5d9c83e147b2f49ca286df291ed302e3d7d449fa1c50590aa61544f8f9e711" },
            { id: "demo-checks-03", name: "validation-report.json", kind: "检查报告", size: "2.4 KB", sha256: "f45d06a7751d2c237219ce042e0c028d873c56ab19a9e7bedc975a152af4c653" },
          ],
        },
      },
      {
        id: "run-014-02", attempt: 2, task_spec_version: 2, state: "submitted",
        summary: "上一轮补齐了缺列提示。此历史运行未登记可展示的差异和检查明细。",
        events: [
          { time: "09:31", title: "补充缺列提示", detail: "缺少必填字段时显示对应列名。", kind: "progress" },
          { time: "09:36", title: "提交上一版", detail: "保留历史运行记录。", kind: "artifact" },
        ],
      },
    ],
  },
  {
    id: "task-015",
    title: "报价结果导出回归",
    handoff: "核对导出文件与页面上的报价比较结果，覆盖可比、待核对和不可比三种状态。",
    spec_version: 1,
    state: "running",
    inputs: [],
    reviews: [],
    runs: [{
      id: "run-015-01", attempt: 1, task_spec_version: 1, state: "running",
      summary: "本轮正在核对报价导出与页面结果的一致性。",
      events: [
        { time: "11:02", title: "开始第 1 轮", detail: "已载入规格 v1 和模拟报价样例。", kind: "state" },
        { time: "11:05", title: "运行导出回归", detail: "核对可比、待核对和不可比三种结果。", kind: "check" },
      ],
    }],
  },
  {
    id: "task-016",
    title: "缺失净重提示完善",
    handoff: "完善净重缺失时的提示文案。没有换算依据的报价仍归入待核对。",
    spec_version: 1,
    state: "waiting_input",
    inputs: [],
    reviews: [],
    runs: [{
      id: "run-016-01", attempt: 1, task_spec_version: 1, state: "needs_input",
      summary: "本轮已停止并保存现场，等待 FDE 确认提示文案。",
      question: "净重缺失时，是否提示「请补充包装净重后再比较」？该记录仍归入待核对。",
      events: [
        { time: "10:42", title: "复核缺失净重样例", detail: "缺少换算依据的报价已归入待核对。", kind: "progress" },
        { time: "10:45", title: "提交待答问题", detail: "已保存现场并停止本轮，等待明确提示文案。", kind: "state" },
      ],
    }],
  },
];
