/**
 * POST /api/routines — create a new routine through the agent pipeline
 * GET  /api/routines — list all routines for this caregiver's assisted user
 */
import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiCreateRoutine, apiListRoutines } from "@/lib/api";

export async function POST(req: NextRequest) {
  const session = await getSession();
  if (!session.isLoggedIn) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }
  const { raw_request } = await req.json();
  if (!raw_request?.trim()) {
    return NextResponse.json({ error: "raw_request is required." }, { status: 400 });
  }
  const assisted_user_id = session.assistedUserId ?? "";
  const caregiver_id = session.caregiverId ?? "";

  const upstream = await apiCreateRoutine(session, { raw_request, assisted_user_id, caregiver_id });
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.ok ? 201 : upstream.status });
}

export async function GET() {
  const session = await getSession();
  if (!session.isLoggedIn) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }
  const assisted_user_id = session.assistedUserId ?? "";
  const upstream = await apiListRoutines(session, assisted_user_id);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
