export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string | null;
  details: unknown;

  constructor(status: number, code: string, message: string, requestId: string | null = null, details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

let csrf = "";

export function rememberSession(token: string) {
  csrf = token;
}

export function clearSession() {
  csrf = "";
}

export function currentCsrf() {
  return csrf;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && csrf) {
    headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(path, { ...init, headers, credentials: "include", signal: init.signal });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.code ?? "REQUEST_FAILED",
      data?.message ?? "请求没有完成。请查看当前页面状态后再试。",
      data?.request_id ?? response.headers.get("x-request-id"),
      data?.details ?? null,
    );
  }
  return data as T;
}

export function problem(error: unknown) {
  if (error instanceof ApiError) {
    const tip = error.requestId ? `（${error.code} · ${error.requestId}）` : `（${error.code}）`;
    return `${error.message}${tip}`;
  }
  return "页面没有拿到数据。请刷新后再看。";
}
