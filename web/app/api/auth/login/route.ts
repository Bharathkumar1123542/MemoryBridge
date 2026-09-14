/**
 * POST /api/auth/login
 *
 * Demo mode: accepts any email + password "demo" as caregiver.
 * Emails ending in "+today" are treated as the assisted user (Maria's view).
 *
 * In production, replace this with a real DB lookup + bcrypt verify against
 * the caregivers table (implementation.md §5).
 */
import { NextRequest, NextResponse } from "next/server";
import { createSession } from "@/lib/session";
import { randomUUID } from "crypto";

// Fixed demo UUIDs so sessions are consistent within a dev run
const DEMO_CAREGIVER_ID    = "11111111-1111-1111-1111-111111111111";
const DEMO_ASSISTED_USER_ID = "22222222-2222-2222-2222-222222222222";

export async function POST(req: NextRequest) {
  const { email, password } = await req.json();

  if (!email || !password) {
    return NextResponse.json({ error: "Email and password are required." }, { status: 400 });
  }

  // Demo auth: password must be "demo"
  if (password !== "demo") {
    return NextResponse.json(
      { error: "Invalid credentials. Use password 'demo' to explore." },
      { status: 401 }
    );
  }

  const isAssisted = email.includes("+today");

  if (isAssisted) {
    await createSession({
      subjectType: "assisted",
      subjectId: DEMO_ASSISTED_USER_ID,
      caregiverId: DEMO_CAREGIVER_ID,
      assistedUserId: DEMO_ASSISTED_USER_ID,
    });
    return NextResponse.json({ role: "assisted" });
  } else {
    await createSession({
      subjectType: "caregiver",
      subjectId: DEMO_CAREGIVER_ID,
      caregiverId: DEMO_CAREGIVER_ID,
      assistedUserId: DEMO_ASSISTED_USER_ID,
    });
    return NextResponse.json({ role: "caregiver" });
  }
}
