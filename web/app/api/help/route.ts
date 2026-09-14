import { NextRequest, NextResponse } from "next/server";
import { getSession, UnauthorizedError } from "@/lib/session";
import { apiHelp } from "@/lib/api";

export async function POST(req: NextRequest) {
  try {
    const session = await getSession();
    if (!session.isLoggedIn) {
      return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
    }
    
    // Validate session has required IDs for caregiver
    if (!session.caregiverId || !session.assistedUserId) {
      return NextResponse.json(
        { error: "Session is missing required IDs for help request." },
        { status: 403 }
      );
    }
    
    const body = await req.json().catch(() => ({}));
    const upstream = await apiHelp(session, {
      note: body?.note ?? null,
      routine_title: body?.routine_title ?? null,
    });
    
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      return NextResponse.json({ error: error.message }, { status: 401 });
    }
    console.error("POST /api/help error:", error);
    return NextResponse.json(
      { error: "Failed to process help request" },
      { status: 500 }
    );
  }
}
