export const queryKeys = {
  session: ["session"] as const,
  engagements: ["engagements"] as const,
  engagement: (id: string) => ["engagement", id] as const,
  delivery: (engagementId: string) => ["delivery", engagementId] as const,
  task: (taskId: string) => ["task", taskId] as const,
  runs: (taskId: string) => ["runs", taskId] as const,
  run: (runId: string) => ["run", runId] as const,
  runEvents: (runId: string) => ["run-events", runId] as const,
  artifacts: (runId: string) => ["artifacts", runId] as const,
  reviewEvidence: (runId: string) => ["review-evidence", runId] as const,
  reviews: (taskId: string) => ["reviews", taskId] as const,
  taskInputs: (taskId: string) => ["task-inputs", taskId] as const,
  taskEvents: (taskId: string) => ["task-events", taskId] as const,
  taskVersions: (taskId: string) => ["task-versions", taskId] as const,
  modelProfiles: ["model-profiles"] as const,
  fdeWork: (engagementId: string) => ["fde-work", engagementId] as const,
  knowledgeSearch: (role: string, purpose: string, query: string) =>
    ["knowledge", "search", role, purpose, query] as const,
  knowledgeAsset: (role: string, purpose: string, assetId: string) =>
    ["knowledge", "asset", role, purpose, assetId] as const,
  businessCases: (cursor: string, workflow = "", state = "", owner = "") =>
    ["business", "cases", cursor, workflow, state, owner] as const,
  businessCase: (caseId: string) => ["business", "case", caseId] as const,
  officeActionable: (cursor: string) => ["office", "actionable", cursor] as const,
  officeActivity: (cursor: string) => ["office", "activity", cursor] as const,
  runtimeStatus: ["runtime", "status"] as const,
};

/** Clear private caches after 401 / logout. */
export function privateQueryPrefixes() {
  return [
    "session",
    "engagements",
    "engagement",
    "delivery",
    "task",
    "runs",
    "run",
    "run-events",
    "artifacts",
    "review-evidence",
    "reviews",
    "task-inputs",
    "task-events",
    "task-versions",
    "model-profiles",
    "fde-work",
    "knowledge",
    "business",
    "office",
    "runtime",
  ] as const;
}
