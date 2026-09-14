/**
 * web/lib/session.ts
 * ------------------
 * Session management for the MemoryBridge BFF layer.
 *
 * Uses iron-session to issue and verify httpOnly, Secure, SameSite=Lax
 * signed cookies. The session cookie holds:
 *   - subject_type: "caregiver" | "assisted"
 *   - subject_id:   UUID of the authenticated user
 *   - caregiver_id: UUID of the caregiver (same as subject_id for caregivers;
 *                   set to the linked caregiver_id for assisted users)
 *   - assisted_user_id: UUID of the assisted user (null for pure caregivers
 *                       until they select which assisted user to manage)
 *
 * IMPORTANT: client-side code never sees these values. Only Route Handlers
 * (app/api/**) read the session, compute the internal HMAC token, and
 * forward it to agent-backend. Browser JS has zero access to session data
 * (architecture.md §11.3, implementation.md §11.3).
 *
 * Internal token generation:
 *   token = HMAC-SHA256(session_id, SESSION_SECRET)
 * This matches agent-backend's verify_internal_token middleware exactly.
 */

import { getIronSession, IronSession, SessionOptions } from "iron-session";
import { cookies } from "next/headers";
import { createHmac, randomUUID } from "crypto";

// ---------------------------------------------------------------------------
// Custom error class for authentication failures
// ---------------------------------------------------------------------------
export class UnauthorizedError extends Error {
  constructor(message: string = "Not authenticated") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

// ---------------------------------------------------------------------------
// Session data shape
// ---------------------------------------------------------------------------
export interface SessionData {
  sessionId?: string;
  subjectType?: "caregiver" | "assisted";
  subjectId?: string;
  caregiverId?: string;
  assistedUserId?: string | null;
  isLoggedIn?: boolean;
}


// ---------------------------------------------------------------------------
// iron-session config
// ---------------------------------------------------------------------------
function getSessionSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error(
      "SESSION_SECRET env var is not set or is too short (min 32 chars). " +
      "Use a cryptographically random value: openssl rand -base64 48"
    );
  }
  return secret;
}

export function getSessionOptions(): SessionOptions {
  return {
    password: getSessionSecret(),
    cookieName: "mb_session",
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
  };
}

// ---------------------------------------------------------------------------
// Get the current session (server-only — Route Handlers / Server Components)
// ---------------------------------------------------------------------------
export async function getSession(): Promise<IronSession<SessionData>> {
  const cookieStore = await cookies();
  return getIronSession<SessionData>(cookieStore, getSessionOptions());
}

// ---------------------------------------------------------------------------
// Internal service token — forwarded to agent-backend as X-Internal-Token
// Matches the HMAC computed in agent-backend/app/main.py:verify_internal_token
// ---------------------------------------------------------------------------
export function computeInternalToken(sessionId: string): string {
  if (!sessionId || !sessionId.trim()) {
    throw new Error("sessionId is required for computing internal token");
  }
  return createHmac("sha256", getSessionSecret())
    .update(sessionId)
    .digest("hex");
}

// ---------------------------------------------------------------------------
// Build the auth headers that every agent-backend call must include
// ---------------------------------------------------------------------------
export function buildInternalHeaders(session: IronSession<SessionData>): Record<string, string> {
  if (!session.isLoggedIn || !session.sessionId) {
    throw new UnauthorizedError("Session is not authenticated");
  }
  return {
    "X-Internal-Token": computeInternalToken(session.sessionId),
    "X-Session-Id": session.sessionId,
    "X-Caregiver-Id": session.caregiverId ?? "",
    ...(session.assistedUserId
      ? { "X-Assisted-User-Id": session.assistedUserId }
      : {}),
    "Content-Type": "application/json",
  };
}


// ---------------------------------------------------------------------------
// Create a new session after login
// ---------------------------------------------------------------------------
export async function createSession(params: {
  subjectType: "caregiver" | "assisted";
  subjectId: string;
  caregiverId: string;
  assistedUserId: string | null;
}): Promise<IronSession<SessionData>> {
  const session = await getSession();
  // Note: UUID v4 collision probability is negligible (2^-122) for practical purposes
  session.sessionId = randomUUID();
  session.isLoggedIn = true;
  session.subjectType = params.subjectType;
  session.subjectId = params.subjectId;
  session.caregiverId = params.caregiverId;
  session.assistedUserId = params.assistedUserId ?? null;
  await session.save();
  return session;
}

// ---------------------------------------------------------------------------
// Destroy session (logout)
// ---------------------------------------------------------------------------
export async function destroySession(): Promise<void> {
  const session = await getSession();
  session.destroy();
}
