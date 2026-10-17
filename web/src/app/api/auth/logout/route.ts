import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { BACKEND_URL, SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (token) {
    await fetch(`${BACKEND_URL}/api/auth/logout`, { method: "POST", headers: { authorization: `Bearer ${token}` } }).catch(() => null);
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "strict", path: "/", maxAge: 0 });
  return res;
}
