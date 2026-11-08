import { Alert, Button, Input, Select } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  adapterLabel,
  ApiError,
  api,
  createIdempotencyGate,
  postJson,
  problem,
  queryKeys,
  type DialoguePage,
  type KnowledgeCallerRole,
  type KnowledgeListItem,
  type KnowledgePurpose,
  type KnowledgeSearchResult,
  type KnowledgeToolResult,
} from "../../api";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";
import { uuidOrEmpty } from "../../shared/ids";
import { bannerTone } from "../../shared/labels";

const ROLES: { value: KnowledgeCallerRole; label: string }[] = [
  { value: "business", label: "Business" },
  { value: "fde", label: "FDE" },
  { value: "engineering", label: "Engineering" },
];

const PURPOSES: { value: KnowledgePurpose; label: string; hint: string }[] = [
  { value: "delivery", label: "交付复用", hint: "内部交付可见字段" },
  { value: "internal_research", label: "内部研究", hint: "内部研究可见字段" },
  { value: "public_marketing", label: "公开营销", hint: "仅公开摘要投影" },
];

function returnPath(params: URLSearchParams) {
  const from = params.get("from");
  const project = uuidOrEmpty(params.get("project"));
  const task = uuidOrEmpty(params.get("task"));
  const caseId = uuidOrEmpty(params.get("case"));
  const run = uuidOrEmpty(params.get("run"));
  const work = uuidOrEmpty(params.get("work"));
  if (from === "engineering" && project) {
    return `/engineering?project=${project}${task ? `&task=${task}` : ""}${run ? `&run=${run}` : ""}`;
  }
  if (from === "fde" && project) {
    return `/fde?project=${project}${caseId ? `&case=${caseId}` : ""}${work ? `&work=${work}` : ""}`;
  }
  if (from === "business" && caseId) return `/business?case=${caseId}`;
  if (from === "business") return "/business";
  if (from === "projects" && project) return `/projects/${project}`;
  if (project) return `/projects/${project}`;
  return "/";
}

function asSearch(result: Record<string, unknown> | undefined): KnowledgeSearchResult {
  if (!result || !Array.isArray(result.items) || typeof result.count !== "number") {
    throw new Error("检索结果与当前契约不一致。");
  }
  return {
    query: String(result.query ?? ""),
    purpose: result.purpose as KnowledgePurpose,
    count: result.count,
    items: result.items as KnowledgeListItem[],
  };
}

function asAsset(result: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!result || typeof result.asset !== "object" || result.asset === null) {
    throw new Error("资产详情与当前契约不一致。");
  }
  return result.asset as Record<string, unknown>;
}

function typeLabel(type: string | null | undefined) {
  if (!type) return "资产";
  const map: Record<string, string> = {
    industry_knowledge: "行业知识",
    business_module: "业务模块",
    engineering_experience: "工程经验",
    sop: "SOP",
    case: "案例",
    skill: "能力",
  };
  return map[type] ?? type;
}

function KnowledgeHero({ status }: { status?: string }) {
  const [sceneFailed, setSceneFailed] = useState(false);

  return (
    <header className="knowledge-hero">
      <div className={`knowledge-hero-scene${!sceneFailed ? " has-art" : ""}`} aria-hidden="true">
        <img
          className="knowledge-hero-scene-img"
          src="/knowledge-hero-scene.png"
          alt=""
          onLoad={() => setSceneFailed(false)}
          onError={(event) => {
            setSceneFailed(true);
            event.currentTarget.style.display = "none";
          }}
        />
        {sceneFailed ? (
          <div className="knowledge-hero-scene-ph">
            <span>场景暂不可用</span>
          </div>
        ) : null}
      </div>
      <div className="knowledge-hero-copy">
        <h1>Knowledge</h1>
        <p>检索结果、来源与版本</p>
        {status ? (
          <p className={`knowledge-status-pill is-${bannerTone(status)}`}>
            <span className="knowledge-status-dot" aria-hidden />
            {status}
          </p>
        ) : null}
      </div>
    </header>
  );
}

function roleFrom(params: URLSearchParams): KnowledgeCallerRole {
  const explicit = params.get("role");
  if (ROLES.some((item) => item.value === explicit)) return explicit as KnowledgeCallerRole;
  const from = params.get("from");
  if (from === "business" || from === "engineering" || from === "fde") return from;
  return "fde";
}

export function KnowledgePage() {
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const searchGate = useRef(createIdempotencyGate()).current;
  const getGate = useRef(createIdempotencyGate()).current;
  const scroller = useRef<HTMLDivElement>(null);

  const validRole = roleFrom(params);
  const purpose = (params.get("purpose") as KnowledgePurpose) || "delivery";
  const query = params.get("q") ?? "";
  const assetId = params.get("asset") ?? "";
  const validPurpose = PURPOSES.some((item) => item.value === purpose) ? purpose : "delivery";
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState<string>();
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string>();
  const askGate = useRef(createIdempotencyGate()).current;

  function patch(next: Record<string, string | null>) {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (!value) updated.delete(key);
      else updated.set(key, value);
    }
    setParams(updated);
  }

  const dialogue = useQuery({
    queryKey: ["knowledge", "dialogue", validRole, validPurpose],
    queryFn: () =>
      api<DialoguePage>(
        `/api/v1/knowledge/dialogue?caller_role=${validRole}&purpose=${validPurpose}`,
      ),
  });

  const search = useQuery({
    queryKey: queryKeys.knowledgeSearch(validRole, validPurpose, query),
    enabled: Boolean(query.trim()),
    queryFn: async () => {
      const body = {
        tool: "search_assets",
        caller_role: validRole,
        purpose: validPurpose,
        arguments: { query: query.trim() },
      };
      const response = await postJson<KnowledgeToolResult>(
        "/api/v1/knowledge/tools",
        body,
        searchGate.keyFor(body),
      );
      return asSearch(response.result);
    },
  });

  const asset = useQuery({
    queryKey: queryKeys.knowledgeAsset(validRole, validPurpose, assetId),
    enabled: Boolean(assetId),
    queryFn: async () => {
      const body = {
        tool: "get_asset",
        caller_role: validRole,
        purpose: validPurpose,
        arguments: { asset_id: assetId },
      };
      try {
        const response = await postJson<KnowledgeToolResult>(
          "/api/v1/knowledge/tools",
          body,
          getGate.keyFor(body),
        );
        return asAsset(response.result);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });

  const retrySearch = useMutation({
    mutationFn: async () => {
      searchGate.reset();
      await client.invalidateQueries({
        queryKey: queryKeys.knowledgeSearch(validRole, validPurpose, query),
      });
    },
  });

  const selectedSummary = useMemo(() => {
    if (!assetId) return null;
    return search.data?.items.find((item) => item.id === assetId) ?? null;
  }, [assetId, search.data]);

  const back = returnPath(params);
  const citation =
    asset.data && typeof asset.data.id === "string" && typeof asset.data.version === "string"
      ? `${asset.data.id}@${asset.data.version}`
      : selectedSummary
        ? `${selectedSummary.id}@${selectedSummary.version}`
        : "";

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [dialogue.data?.turns.length, search.isFetching, asking]);

  async function ask(raw: string) {
    const next = raw.trim();
    if (!next || asking) return;
    const caseId = uuidOrEmpty(params.get("case"));
    const project = uuidOrEmpty(params.get("project"));
    const task = uuidOrEmpty(params.get("task"));
    const run = uuidOrEmpty(params.get("run"));
    const work = uuidOrEmpty(params.get("work"));
    const body = {
      text: next,
      caller_role: validRole,
      purpose: validPurpose,
      ...(caseId ? { case_id: caseId } : {}),
      ...(project ? { engagement_id: project } : {}),
      ...(task ? { task_id: task } : {}),
      ...(run ? { run_id: run } : {}),
      ...(work ? { work_id: work } : {}),
    };
    setAsking(true);
    setAskError(undefined);
    try {
      await postJson<DialoguePage>("/api/v1/knowledge/dialogue", body, askGate.keyFor(body));
      askGate.reset();
      setDraft("");
      searchGate.reset();
      patch({ q: next, asset: null });
      await client.invalidateQueries({
        queryKey: ["knowledge", "dialogue", validRole, validPurpose],
      });
    } catch (error) {
      setAskError(problem(error));
    } finally {
      setAsking(false);
    }
  }

  const status = search.isError || dialogue.isError
    ? "检索失败"
    : search.isFetching || asset.isFetching || asking
      ? "检索中"
      : dialogue.data?.turns.length || query.trim()
        ? "已检索"
        : "待命";

  return (
    <div className="page knowledge-page">
      <ContextTrail items={[{ label: "OneFDE", to: "/" }, { label: "Knowledge" }]} />
      <KnowledgeHero status={status} />

      <div className="eng-studio">
        <section className="eng-chat-col" aria-label="与 Knowledge 对话">
          <header className="eng-chat-head">
            <strong>Knowledge</strong>
            <span className="eng-muted">关键词匹配，不是语义检索</span>
          </header>
          <div className="eng-chat-log" ref={scroller}>
            {!dialogue.data?.turns.length && !asking ? (
              <article className="eng-msg is-engineer">
                <p>提问会按当前身份和用途做关键词匹配，并在刷新后读回。没有命中就说明没有匹配。这不是语义检索。</p>
              </article>
            ) : null}
            {dialogue.data?.turns.map((turn) => (
              <article key={turn.id} className={`eng-msg is-${turn.author === "assistant" ? "engineer" : "user"}`}>
                <p>
                  {turn.author === "assistant" ? `${adapterLabel(turn.adapter)} · 关键词匹配\n` : ""}
                  {turn.text}
                </p>
              </article>
            ))}
            {asking || search.isFetching ? (
              <article className="eng-msg is-engineer">
                <p>正在检索…</p>
              </article>
            ) : null}
            {askError ? <Alert type="error" showIcon message={askError} /> : null}
            {dialogue.isError ? <Alert type="error" showIcon message={problem(dialogue.error)} /> : null}
            {search.isError ? (
              <Alert
                type="error"
                showIcon
                message="检索失败。"
                action={<Button size="small" onClick={() => retrySearch.mutate()}>重试</Button>}
              />
            ) : null}
          </div>
          <form
            className="eng-chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              ask(draft);
            }}
          >
            <Input.TextArea
              value={draft}
              rows={2}
              placeholder="例如：报价、CSV、比较"
              onChange={(event) => setDraft(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  ask(draft);
                }
              }}
            />
            <Button type="primary" htmlType="submit" disabled={!draft.trim() || asking} loading={asking}>
              提问
            </Button>
          </form>
          {params.get("from") || params.get("role") ? (
            <p className="eng-chat-notice">
              按{ROLES.find((item) => item.value === validRole)?.label}、{PURPOSES.find((item) => item.value === validPurpose)?.label}检索。
              {" "}
              <Link to={back}>返回原工作</Link>
            </p>
          ) : (
            <details className="knowledge-scope-fold">
              <summary>检索身份与用途</summary>
              <div className="knowledge-scope">
                <Select
                  size="small"
                  value={validRole}
                  options={ROLES}
                  onChange={(value) => {
                    client.removeQueries({ queryKey: ["knowledge"] });
                    patch({ role: value, asset: null });
                  }}
                />
                <Select
                  size="small"
                  value={validPurpose}
                  options={PURPOSES.map((item) => ({ value: item.value, label: item.label }))}
                  onChange={(value) => {
                    client.removeQueries({ queryKey: ["knowledge"] });
                    patch({ purpose: value, asset: null });
                  }}
                />
              </div>
            </details>
          )}
        </section>

        <section className="eng-code-col knowledge-board" aria-label="知识工作区">
          <header className="eng-code-head">
            <strong>检索结果</strong>
            <p>{query.trim() ? `关键词「${query.trim()}」` : "尚未检索"}</p>
          </header>
          <div className="knowledge-board-body">
            {!query.trim() ? (
              <p className="eng-muted">在左侧提出检索需求后，结果会出现在这里。</p>
            ) : (
              <AsyncState
                loading={search.isLoading}
                error={search.error}
                empty={!search.data?.items.length}
                emptyText={<p>没有可见结果。</p>}
                onRetry={() => retrySearch.mutate()}
              >
                <ul className="knowledge-result-list">
                  {search.data?.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={item.id === assetId ? "is-active" : undefined}
                        onClick={() => {
                          getGate.reset();
                          patch({ asset: item.id });
                        }}
                      >
                        <strong>{item.name}</strong>
                        <span>
                          {item.id}@{item.version}
                          {item.source_engagement ? ` · ${item.source_engagement}` : ""}
                        </span>
                        <small>
                          {validPurpose === "public_marketing"
                            ? item.public_summary || "公开摘要"
                            : [item.problem, item.reuse_scope].filter(Boolean).join(" · ") || typeLabel(item.type)}
                        </small>
                      </button>
                    </li>
                  ))}
                </ul>
              </AsyncState>
            )}

            <div className="knowledge-detail-inline">
              {!assetId ? (
                <p className="eng-muted">选择一条结果后查看内容和固定版本引用。</p>
              ) : (
                <AsyncState
                  loading={asset.isLoading}
                  error={asset.error}
                  empty={asset.data === null}
                  emptyText={<p>资产不存在，或当前用途下不可见。</p>}
                  onRetry={() => {
                    getGate.reset();
                    void client.invalidateQueries({
                      queryKey: queryKeys.knowledgeAsset(validRole, validPurpose, assetId),
                    });
                  }}
                >
                  {asset.data ? (
                    <AssetDetail
                      asset={asset.data}
                      purpose={validPurpose}
                      citation={citation}
                      copied={copied}
                      onCopy={async () => {
                        if (!citation) return;
                        await navigator.clipboard.writeText(citation);
                        setCopied(citation);
                      }}
                    />
                  ) : null}
                </AsyncState>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function AssetDetail({
  asset,
  purpose,
  citation,
  copied,
  onCopy,
}: {
  asset: Record<string, unknown>;
  purpose: KnowledgePurpose;
  citation: string;
  copied?: string;
  onCopy: () => void;
}) {
  const publicOnly = purpose === "public_marketing" || asset.visibility === "public_summary_only";
  const listFields = [
    ["问题", asset.problem],
    ["类型", asset.type ? typeLabel(String(asset.type)) : null],
    ["验证状态", asset.verification_status],
    ["可见性", asset.visibility],
    ["复用范围", asset.reuse_scope],
    ["来源项目", asset.source_engagement],
    ["实现引用", asset.implementation_ref],
  ] as const;

  return (
    <article className="knowledge-asset">
      <header>
        <div className="knowledge-result-top">
          <span className="knowledge-type-badge">{typeLabel(asset.type ? String(asset.type) : null)}</span>
          {asset.verification_status ? (
            <span className="knowledge-verify-badge">{String(asset.verification_status)}</span>
          ) : null}
        </div>
        <h3>{String(asset.name ?? asset.id)}</h3>
        <p className="eng-muted">
          {String(asset.id)}@{String(asset.version ?? "")}
        </p>
      </header>

      {publicOnly ? (
        <>
          <Alert type="info" showIcon message="公开营销用途仅显示公开摘要投影，不含私有实现字段。" />
          <p className="business-message">{String(asset.public_summary ?? "无公开摘要。")}</p>
        </>
      ) : (
        <>
          <dl className="knowledge-facts">
            {listFields.map(([label, value]) =>
              value ? (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{Array.isArray(value) ? value.join("；") : String(value)}</dd>
                </div>
              ) : null,
            )}
          </dl>
          {Array.isArray(asset.inputs) && asset.inputs.length ? (
            <>
              <h4>输入</h4>
              <ul>
                {asset.inputs.map((item, index) => (
                  <li key={`in-${index}`}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.outputs) && asset.outputs.length ? (
            <>
              <h4>输出</h4>
              <ul>
                {asset.outputs.map((item, index) => (
                  <li key={`out-${index}`}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.applicable_when) && asset.applicable_when.length ? (
            <>
              <h4>适用条件</h4>
              <ul>
                {asset.applicable_when.map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.not_applicable_when) && asset.not_applicable_when.length ? (
            <>
              <h4>限制 / 不适用</h4>
              <ul>
                {asset.not_applicable_when.map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.evidence) && asset.evidence.length ? (
            <details open>
              <summary>获准来源 / 证据引用</summary>
              <ul>
                {asset.evidence.map((item) => (
                  <li key={String(item)}>
                    <code>{String(item)}</code>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {Array.isArray(asset.verified_samples) && asset.verified_samples.length ? (
            <details>
              <summary>验证样例</summary>
              <p>{asset.verified_samples.map(String).join("、")}</p>
            </details>
          ) : null}
        </>
      )}

      <div className="knowledge-cite">
        <code>{citation || "无可复制引用"}</code>
        <Button type="primary" disabled={!citation} onClick={onCopy}>
          复制固定版本引用
        </Button>
      </div>
      {copied ? <p className="eng-muted">已复制 {copied}</p> : null}
      <p className="eng-muted">
        版本来自当前清单文件，不是可回溯的历史版本库。复制引用不会自动采用，回到原工作后仍要单独确认。
      </p>
    </article>
  );
}
