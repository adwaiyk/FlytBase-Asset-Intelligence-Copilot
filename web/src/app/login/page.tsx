import { BACKEND_URL } from "@/lib/server";
import { LoginForm, type LoginUser } from "@/components/copilot/login-form";
import { PumpJack } from "@/components/copilot/pumpjack";
import { ShieldCheck, Flame, Droplets, Satellite } from "lucide-react";

export const dynamic = "force-dynamic";

async function getUsers(): Promise<LoginUser[]> {
  try {
    const r = await fetch(`${BACKEND_URL}/api/users`, { cache: "no-store" });
    return r.ok ? await r.json() : [];
  } catch {
    return [];
  }
}

async function getHealth(): Promise<{ as_of?: string; wells?: number }> {
  try {
    const r = await fetch(`${BACKEND_URL}/api/health`, { cache: "no-store" });
    return r.ok ? await r.json() : {};
  } catch {
    return {};
  }
}

export default async function LoginPage() {
  const [users, health] = await Promise.all([getUsers(), getHealth()]);
  return (
    <main className="min-h-dvh grid lg:grid-cols-[1.15fr_1fr]">
      <section className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r bg-grid p-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,oklch(0.79_0.16_70/0.22),transparent_60%)]" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black/60 to-transparent" />
        <div className="relative flex items-center gap-3">
          <PumpJack className="h-10 w-12" />
          <div>
            <div className="text-lg font-semibold tracking-tight">WellWise</div>
            <div className="text-xs text-muted-foreground">Asset Intelligence Copilot</div>
          </div>
        </div>
        <div className="relative max-w-xl">
          <PumpJack className="h-44 w-56 drop-shadow-[0_0_30px_oklch(0.79_0.16_70/0.35)]" />
          <h1 className="mt-6 text-4xl font-semibold tracking-tight leading-tight">
            Every well, every inspection, <span className="text-primary">answered with evidence.</span>
          </h1>
          <p className="mt-4 text-muted-foreground leading-relaxed">
            Ask in plain English. WellWise reads the drone inspections, repair reports, regulator events, manuals and
            your team&apos;s notes, computes the answer in code, and shows you the records it used.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-3 text-sm">
            {[
              { icon: Droplets, k: `${health.wells ?? "—"}`, v: "wells monitored" },
              { icon: Flame, k: "Gemma 4", v: "open-weight model" },
              { icon: Satellite, k: health.as_of ?? "—", v: "data as of" },
            ].map(({ icon: Icon, k, v }) => (
              <div key={v} className="rounded-lg border bg-card/60 p-3 backdrop-blur">
                <Icon className="size-4 text-primary" />
                <div className="mt-2 font-semibold">{k}</div>
                <div className="text-xs text-muted-foreground">{v}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="size-4 text-success" /> httpOnly sessions · PBKDF2-SHA256 · rate-limited sign-in · private chats per user
        </div>
      </section>
      <section className="flex items-center justify-center p-6">
        <LoginForm users={users} />
      </section>
    </main>
  );
}
