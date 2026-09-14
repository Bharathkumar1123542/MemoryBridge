import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiHelp } from "@/lib/api";

export async function POST(req: NextRequest) {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const upstream = await apiHelp(session, {
    note: body?.note ?? null,
    routine_title: body?.routine_title ?? null,
  });
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
