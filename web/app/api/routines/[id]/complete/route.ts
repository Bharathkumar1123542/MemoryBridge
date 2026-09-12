import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiCompleteRoutine } from "@/lib/api";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const today = new Date().toISOString().slice(0, 10);
  const upstream = await apiCompleteRoutine(session, id, body?.occurrence_date ?? today);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
