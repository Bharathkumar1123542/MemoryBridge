import { NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { apiGetToday } from "@/lib/api";

export async function GET() {
  const session = await getSession();
  if (!session.isLoggedIn) return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  const assisted_user_id = session.assistedUserId ?? "";
  const upstream = await apiGetToday(session, assisted_user_id);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
