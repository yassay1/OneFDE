import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, clearSession, privateQueryPrefixes, queryKeys, rememberSession, type Session } from "../api";

export function useSession() {
  const client = useQueryClient();
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: async () => {
      try {
        const session = await api<Session>("/api/v1/auth/session");
        rememberSession(session.csrf_token);
        return session;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearSession();
          for (const prefix of privateQueryPrefixes()) {
            // Let this request settle as an error so RequireSession can show login.
            if (prefix === queryKeys.session[0]) continue;
            client.removeQueries({ queryKey: [prefix] });
          }
        }
        throw error;
      }
    },
    retry: false,
  });
}

export async function logout(client: ReturnType<typeof useQueryClient>) {
  try {
    await api("/api/v1/auth/logout", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
  } catch {
    // Still clear local session on logout failure.
  }
  clearSession();
  for (const prefix of privateQueryPrefixes()) {
    client.removeQueries({ queryKey: [prefix] });
  }
}
