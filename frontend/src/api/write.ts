import type { QueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import { queryKeys } from "./keys";

/** Keep one Idempotency-Key per frozen request body; change body → new key. */
export function createIdempotencyGate() {
  let signature = "";
  let key = "";
  return {
    keyFor(body: unknown) {
      const next = JSON.stringify(body);
      if (signature !== next) {
        signature = next;
        key = crypto.randomUUID();
      }
      return key;
    },
    reset() {
      signature = "";
      key = "";
    },
  };
}

export async function postJson<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  return api<T>(path, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
}

export async function patchJson<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  return api<T>(path, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
}

/** After a successful task write, refresh related engineering queries. */
export async function invalidateEngineering(
  client: QueryClient,
  opts: { engagementId?: string; taskId: string; runId?: string | null },
) {
  const jobs = [
    client.invalidateQueries({ queryKey: queryKeys.task(opts.taskId) }),
    client.invalidateQueries({ queryKey: queryKeys.runs(opts.taskId) }),
    client.invalidateQueries({ queryKey: queryKeys.reviews(opts.taskId) }),
    client.invalidateQueries({ queryKey: queryKeys.taskInputs(opts.taskId) }),
    client.invalidateQueries({ queryKey: queryKeys.taskEvents(opts.taskId) }),
    client.invalidateQueries({ queryKey: queryKeys.taskVersions(opts.taskId) }),
  ];
  if (opts.engagementId) {
    jobs.push(client.invalidateQueries({ queryKey: queryKeys.delivery(opts.engagementId) }));
  }
  if (opts.runId) {
    jobs.push(
      client.invalidateQueries({ queryKey: queryKeys.run(opts.runId) }),
      client.invalidateQueries({ queryKey: queryKeys.runEvents(opts.runId) }),
      client.invalidateQueries({ queryKey: queryKeys.artifacts(opts.runId) }),
      client.invalidateQueries({ queryKey: queryKeys.reviewEvidence(opts.runId) }),
    );
  }
  await Promise.all(jobs);
}

export function conflictMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 409) {
    return `${error.message} 页面将重新读取当前版本，请核对后再操作。`;
  }
  return null;
}
