/** Domain types aligned with docs/architecture/openapi.implemented.json. */

export type Session = {
  username: string;
  csrf_token: string;
  expires_at: string;
};

export type Engagement = {
  id: string;
  title: string;
  goal: string;
  is_demo: boolean;
};

export type EngagementPage = {
  items: Engagement[];
  next_cursor: string | null;
};

export type DeliveryTask = {
  id: string;
  state: string;
  title: string;
  objective: string;
  scope: string;
  pending_input_count: number;
  latest_run_id: string | null;
  revision: number;
  spec_version: number;
};

export type Delivery = {
  engagement: Engagement;
  sources_note: string;
  unknowns: string[];
  scheme_summary: string | null;
  tasks: DeliveryTask[];
  latest_checks: string[];
  fixed_version_hint: string | null;
};

export type FdeWorkReport = {
  summary?: string;
  error?: string;
  clarification?: {
    source_message_id: number;
    public_reply: string;
    sent_message_id?: number;
  };
  pending_dispatch?: {
    status: "pending" | "confirmed" | "declined";
    command?: string;
    task_id?: string;
    expected_revision?: number;
    spec_version?: number;
    impact?: string;
    run_id?: string;
    operation_id?: string;
  };
  review_suggestion?: {
    verdict: "accept" | "request_changes" | "needs_human_check";
    run_id: string;
    spec_version: number;
    artifact_sha256: string;
    validation_passed: boolean | null;
    reason: string;
    next_step: string;
  };
};

export type FdeWorkView = {
  id: string;
  engagement_id: string;
  case_id: string | null;
  task_id: string | null;
  goal: string;
  state: "pending" | "processing" | "reported";
  report: FdeWorkReport;
  trace: Record<string, string | number | boolean | null>[];
  calls?: number;
  usage?: Record<string, number>;
};

export type Dependency = {
  task_id: string;
  spec_version: number;
  artifact_ids: string[];
};

export type TaskSpec = {
  title: string;
  objective: string;
  scope: string;
  inputs: string[];
  confirmed_rules: string[];
  completion_criteria: string[];
  dependencies: Dependency[];
  capability_versions: string[];
};

export type Task = {
  id: string;
  engagement_id: string;
  state: string;
  revision: number;
  spec_version: number;
  spec: TaskSpec;
  active_run_id: string | null;
  latest_run_id: string | null;
  pending_input_count: number;
  block_reason: string | null;
  owner_role?: string;
  executor_role?: string;
};

export type InputKind = "clarification" | "change_request" | "question" | "answer";
export type InputStatus = "pending" | "applied" | "rejected";

export type TaskInput = {
  id: string;
  task_id: string;
  sequence: number;
  kind: InputKind;
  text: string;
  evidence_artifact_ids: string[];
  status: InputStatus;
  reply_to_input_id: string | null;
  origin_run_id: string | null;
  author: string;
  applied_spec_version: number | null;
  created_at: string;
  processed_by: string | null;
  processing_reason: string | null;
  processed_at: string | null;
  resolved_by_input_id: string | null;
};

export type TaskInputPage = {
  items: TaskInput[];
  last_sequence: number;
  has_more: boolean;
};

export type Run = {
  id: string;
  task_id: string;
  state: string;
  outcome: string | null;
  task_spec_version: number;
  attempt: number;
  result_summary: string | null;
  error_code: string | null;
  model_profile_revision_id?: string | null;
  created_at?: string;
  applied_input_ids?: string[];
};

export type RunPage = {
  items: Run[];
  next_cursor: string | null;
};

export type RunEvent = {
  id: string;
  sequence: number;
  kind: "state" | "progress" | "check" | "artifact" | "error";
  summary: string;
  created_at: string;
};

export type RunEventPage = {
  items: RunEvent[];
  last_sequence: number;
  has_more: boolean;
};

export type Artifact = {
  id: string;
  engagement_id: string;
  run_id: string | null;
  name: string;
  kind: string;
  sha256: string;
  size_bytes: number;
};

export type ArtifactPage = {
  items: Artifact[];
  next_cursor: string | null;
};

export type ReviewCheck = {
  command: string;
  exit_code: number | null;
  timeout: boolean;
};

export type RunReviewEvidence = {
  artifact_id: string;
  artifact_sha256: string;
  baseline_sha256: string;
  mode: "engineering" | "deterministic";
  design: string;
  diff: string;
  diff_truncated: boolean;
  self_checks: ReviewCheck[];
  validation_checks: ReviewCheck[];
  validation_passed: boolean | null;
  guide_revision?: string | null;
  assembly_revision?: string | null;
  baseline_origin?: "accepted_artifact" | "trusted_starter" | null;
  baseline_artifact_id?: string | null;
  known_differences?: string[];
};

export type Review = {
  id: string;
  task_id?: string;
  run_id?: string;
  task_spec_version?: number;
  artifact_ids?: string[];
  verdict: string;
  reason: string;
  check_evidence: string[];
  reviewer?: string;
  created_at?: string;
};

export type ReviewPage = {
  items: Review[];
  next_cursor: string | null;
};

export type ModelProfile = {
  id: string;
  revision_id: string;
  provider: string;
  protocol: string;
  model: string;
  capabilities: string[];
  integration_status: "configured" | "smoke_passed" | "unavailable";
};

export type ModelProfilePage = {
  items: ModelProfile[];
  next_cursor: string | null;
};

export type TaskCommand =
  | "queue"
  | "start"
  | "retry"
  | "continue"
  | "cancel"
  | "stop_for_update";

export type ActionAccepted = {
  operation_id: string;
  task: Task;
  run: Run | null;
};

export type KnowledgeCallerRole = "business" | "fde" | "engineering";
export type KnowledgePurpose = "delivery" | "internal_research" | "public_marketing";

export type KnowledgeToolResult = {
  tool: "search_assets" | "get_asset" | "record_business_handoff";
  role_revision: string;
  caller_role: KnowledgeCallerRole;
  purpose: KnowledgePurpose;
  actor: string;
  result: Record<string, unknown>;
};

export type KnowledgeListItem = {
  id: string;
  name: string;
  version: string;
  verification_status?: string | null;
  visibility?: string | null;
  type?: string | null;
  reuse_scope?: string | null;
  source_engagement?: string | null;
  implementation_ref?: string | null;
  keywords?: string[];
  public_summary?: string | null;
  problem?: string | null;
};

export type KnowledgeSearchResult = {
  query: string;
  purpose: KnowledgePurpose;
  items: KnowledgeListItem[];
  count: number;
};
