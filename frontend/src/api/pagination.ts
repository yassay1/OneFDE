import { api } from "./client";

export async function readPages<T>(path: string, signal?: AbortSignal): Promise<{ items: T[]; next_cursor: null }> {
  const items: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  do {
    const url = `${path}${path.includes("?") ? "&" : "?"}limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const page: { items: T[]; next_cursor: string | null } = await api(url, { signal });
    items.push(...page.items); cursor = page.next_cursor;
    if (cursor && seen.has(cursor)) throw new Error("分页游标未推进");
    if (cursor) seen.add(cursor);
  } while (cursor);
  return { items, next_cursor: null };
}

export async function readSequence<T>(path: string, signal?: AbortSignal): Promise<{ items: T[]; last_sequence: number; has_more: false }> {
  const items: T[] = [];
  let after = 0;
  let more = true;
  while (more) {
    const page: { items: T[]; last_sequence: number; has_more: boolean } = await api(`${path}?limit=100&after_sequence=${after}`, { signal });
    items.push(...page.items); more = page.has_more;
    if (more && page.last_sequence <= after) throw new Error("事件水位未推进");
    after = page.last_sequence;
  }
  // Full reads also refresh processing status on older input sequences.
  return { items, last_sequence: after, has_more: false };
}

export const visibleInterval = (milliseconds: number) => document.hidden ? false : milliseconds;
