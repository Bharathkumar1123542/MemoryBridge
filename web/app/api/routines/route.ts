/**
 * POST /api/routines — create a new routine through the agent pipeline
 * GET  /api/routines — list all routines for this caregiver's assisted user
 */
import { NextRequest, NextResponse } from "next/server";
import { getSession, UnauthorizedError } from "@/lib/session";
import { apiCreateRoutine, apiListRoutines } from "@/lib/api";

// Maximum length for raw_request to prevent token waste
const MAX_REQUEST_LENGTH = 1000;

export async function POST(req: NextRequest) {
  try {
    const session = await getSession();
    if (!session.isLoggedIn) {
      return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
    }
    
    const body = await req.json();
    const { raw_request } = body;
    
    // Validate raw_request
    if (!raw_request?.trim()) {
      return NextResponse.json({ error: "raw_request is required." }, { status: 400 });
    }
    
    if (raw_request.length > MAX_REQUEST_LENGTH) {
      return NextResponse.json(
        { error: `Request text is too long. Maximum ${MAX_REQUEST_LENGTH} characters allowed.` },
        { status: 400 }
      );
    }
    
    // Validate session has required IDs
    const assisted_user_id = session.assistedUserId?.trim() ?? "";
    const caregiver_id = session.caregiverId?.trim() ?? "";
    
    if (!assisted_user_id || !caregiver_id) {
      return NextResponse.json(
        { error: "Session is missing required user IDs." },
        { status: 401 }
      );
    }

    const upstream = await apiCreateRoutine(session, { raw_request, assisted_user_id, caregiver_id });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      return NextResponse.json({ error: error.message }, { status: 401 });
    }
    console.error("POST /api/routines error:", error);
    return NextResponse.json(
      { error: "Failed to create routine" },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const session = await getSession();
    if (!session.isLoggedIn) {
      return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
    }
    
    const assisted_user_id = session.assistedUserId?.trim() ?? "";
    if (!assisted_user_id) {
      return NextResponse.json(
        { error: "Session is missing assisted user ID." },
        { status: 401 }
      );
    }
    
    const upstream = await apiListRoutines(session, assisted_user_id);
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      return NextResponse.json({ error: error.message }, { status: 401 });
    }
    console.error("GET /api/routines error:", error);
    return NextResponse.json(
      { error: "Failed to list routines" },
      { status: 500 }
    );
  }
}
