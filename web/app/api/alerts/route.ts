import { NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiListAlerts } from "@/lib/api";

export async function GET() {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const upstream = await apiListAlerts(session);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
