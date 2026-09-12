import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiAcknowledgeAlert } from "@/lib/api";

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const { id } = await params;
  const upstream = await apiAcknowledgeAlert(session, id);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
