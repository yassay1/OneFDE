/** Compatibility barrel for feature imports (`from "../../api"`). */
export {
  ApiError,
  api,
  clearSession,
  currentCsrf,
  problem,
  rememberSession,
} from "./api/client";
export { adapterLabel } from "./api/dialogue";
export type { DialoguePage, RuntimeBeat, RuntimeStatus, StaffTurn } from "./api/dialogue";
export { privateQueryPrefixes, queryKeys } from "./api/keys";
export {
  conflictMessage,
  createIdempotencyGate,
  invalidateEngineering,
  patchJson,
  postJson,
} from "./api/write";
export type * from "./api/types";
