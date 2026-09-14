/**
 * web/lib/api.ts
 * ---------------
 * Typed fetch wrapper for calling agent-backend from Route Handlers.
 *
 * IMPORTANT: This module is server-only. It imports from lib/session which
 * reads cookies — it must never be imported by client components.
 *
 * The INTERNAL_API_BASE_URL env var is set to:
 *   - Docker local:  http://agent-backend:8000
 *   - Fargate:       internal ALB DNS name
 *
 * No browser ever calls these URLs. All calls happen server-side in
 * Next.js Route Handlers (app/api/**).
 */

import { IronSession } from "iron-session";
import { buildInternalHeaders, SessionData } from "./session";

const BASE_URL =
  process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

// Validate BASE_URL in production
if (process.env.NODE_ENV === "production" && !process.env.INTERNAL_API_BASE_URL) {
  throw new Error(
    "INTERNAL_API_BASE_URL environment variable is required in production"
  );
}

// ---------------------------------------------------------------------------
// Core fetch helper with error context
// ---------------------------------------------------------------------------
async function agentFetch(
  session: IronSession<SessionData>,
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = buildInternalHeaders(session);
  const url = `${BASE_URL}/internal${path}`;
  
  try {
    const res = await fetch(url, {
      ...options,
      headers: { ...headers, ...(options.headers ?? {}) },
    });
    return res;
  } catch (error) {
    // Wrap network errors with endpoint context for easier debugging
    const errorMessage = error instanceof Error ? error.message : String(error);
    throw new Error(
      `Failed to call agent-backend endpoint ${path}: ${errorMessage}`
    );
  }
}

// ---------------------------------------------------------------------------
// Typed API methods — one per agent-backend endpoint
// ---------------------------------------------------------------------------

export async function apiCreateRoutine(
  session: IronSession<SessionData>,
  body: { raw_request: string; assisted_user_id: string; caregiver_id: string }
) {
  const res = await agentFetch(session, "/routines", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res;
}

export async function apiListRoutines(
  session: IronSession<SessionData>,
  assistedUserId: string
) {
  const params = new URLSearchParams({ assisted_user_id: assistedUserId });
  return agentFetch(session, `/routines?${params}`);
}

export async function apiApproveRoutine(
  session: IronSession<SessionData>,
  routineId: string
) {
  return agentFetch(session, `/routines/${routineId}/approve`, { method: "POST" });
}

export async function apiRejectRoutine(
  session: IronSession<SessionData>,
  routineId: string,
  reason?: string
) {
  return agentFetch(session, `/routines/${routineId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export async function apiGetToday(
  session: IronSession<SessionData>,
  assistedUserId: string
) {
  const params = new URLSearchParams({ assisted_user_id: assistedUserId });
  return agentFetch(session, `/today?${params}`);
}

export async function apiCompleteRoutine(
  session: IronSession<SessionData>,
  routineId: string,
  occurrenceDate: string
) {
  return agentFetch(session, `/routines/${routineId}/complete`, {
    method: "POST",
    body: JSON.stringify({ occurrence_date: occurrenceDate }),
  });
}

export async function apiHelp(
  session: IronSession<SessionData>,
  body: { note?: string; routine_title?: string }
) {
  return agentFetch(session, "/help", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function apiListAlerts(session: IronSession<SessionData>) {
  return agentFetch(session, "/alerts");
}

export async function apiAcknowledgeAlert(
  session: IronSession<SessionData>,
  alertId: string
) {
  return agentFetch(session, `/alerts/${alertId}/acknowledge`, { method: "POST" });
}
