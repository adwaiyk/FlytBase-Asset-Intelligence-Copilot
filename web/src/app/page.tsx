import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { BACKEND_URL, SESSION_COOKIE } from "@/lib/server";
import { AppShell } from "@/components/copilot/app-shell";
import type { Me } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) redirect("/login");
  const r = await fetch(`${BACKEND_URL}/api/auth/me`, { headers: { authorization: `Bearer ${token}` }, cache: "no-store" }).catch(() => null);
  if (!r || !r.ok) redirect("/login");
  const me = (await r.json()) as Me;
  return <AppShell me={me} />;
}
