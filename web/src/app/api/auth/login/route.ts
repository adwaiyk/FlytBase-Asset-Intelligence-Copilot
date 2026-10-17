import { NextResponse } from "next/server";
import { BACKEND_URL, SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  const body = await req.json().catch(() => null);
  if (!body?.user_id || typeof body.password !== "string")
    return NextResponse.json({ detail: "User and password are required" }, { status: 400 });
  const fwd = req.headers.get("x-forwarded-for") ?? "local";
  const r = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-forwarded-for": fwd },
    body: JSON.stringify({ user_id: String(body.user_id), password: body.password }),
    cache: "no-store",
  });
  const data = await r.json().catch(() => ({ detail: "Login service unavailable" }));
  if (!r.ok) return NextResponse.json({ detail: data.detail ?? "Login failed" }, { status: r.status });
  const res = NextResponse.json({ user: data.user });
  res.cookies.set(SESSION_COOKIE, data.token, {
    httpOnly: true,
    // Secure whenever the app is served over HTTPS (directly or behind a proxy)
    secure: (req.headers.get("x-forwarded-proto") ?? new URL(req.url).protocol.replace(":", "")) === "https",
    sameSite: "strict",
    path: "/",
    maxAge: data.expires_in ?? 60 * 60 * 24 * 7,
  });
  return res;
}
