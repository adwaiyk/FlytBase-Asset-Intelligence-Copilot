import "server-only";

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
export const SESSION_COOKIE = "ww_session";

/** Rejects cross-site state-changing requests (defence in depth on top of SameSite=Strict). */
export function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return true; // same-origin fetches from older browsers / server calls
  try {
    return new URL(origin).host === (req.headers.get("x-forwarded-host") ?? req.headers.get("host"));
  } catch {
    return false;
  }
}
