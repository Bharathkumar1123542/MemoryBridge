import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiRejectRoutine } from "@/lib/api";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const upstream = await apiRejectRoutine(session, id, body?.reason);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
