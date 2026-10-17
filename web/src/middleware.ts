import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const hasSession = Boolean(req.cookies.get("ww_session")?.value);
  const { pathname } = req.nextUrl;
  if (!hasSession && pathname === "/") return NextResponse.redirect(new URL("/login", req.url));
  if (hasSession && pathname === "/login") return NextResponse.redirect(new URL("/", req.url));
  return NextResponse.next();
}

export const config = { matcher: ["/", "/login"] };
