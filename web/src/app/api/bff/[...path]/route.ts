import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { BACKEND_URL, SESSION_COOKIE, sameOrigin } from "@/lib/server";

// Backend-for-frontend proxy: the session token lives only in an httpOnly cookie and is attached here,
// server-side. Only an allow-list of API paths is reachable.
const ALLOWED = [/^auth\/me$/, /^auth\/password$/, /^overview$/, /^conversations$/, /^conversations\/[\w-]+\/messages$/, /^chat$/, /^admin\/reset$/];

async function handle(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const p = path.join("/");
  if (!ALLOWED.some((r) => r.test(p))) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  if (req.method !== "GET" && !sameOrigin(req)) return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
  const r = await fetch(`${BACKEND_URL}/api/${p}`, {
    method: req.method,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: req.method === "GET" ? undefined : await req.text(),
    cache: "no-store",
  }).catch(() => null);
  if (!r) return NextResponse.json({ detail: "Copilot backend is not reachable" }, { status: 503 });
  const res = new NextResponse(await r.text(), { status: r.status, headers: { "content-type": "application/json" } });
  if (r.status === 401) res.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "strict", path: "/", maxAge: 0 });
  return res;
}

export const GET = handle;
export const POST = handle;
export const maxDuration = 300;
