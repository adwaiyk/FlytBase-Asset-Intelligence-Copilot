"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Loader2, LockKeyhole, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PumpJack } from "./pumpjack";

export type LoginUser = { user_id: string; name: string; role: string; team_id: string; team_name: string };

const role = (r: string) => r.replaceAll("_", " ");

export function LoginForm({ users }: { users: LoginUser[] }) {
  const router = useRouter();
  const [userId, setUserId] = useState<string>("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const teams = Array.from(new Set(users.map((u) => u.team_name)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!userId) return setError("Choose who you are.");
    setBusy(true);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: userId, password }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(d.detail ?? "Sign-in failed");
        setPassword("");
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setError("Cannot reach the copilot service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-md flare-glow">
      <CardHeader className="gap-3">
        <div className="flex items-center gap-2 lg:hidden"><PumpJack className="h-8 w-10" /><span className="font-semibold">WellWise</span></div>
        <div className="flex size-11 items-center justify-center rounded-lg bg-primary/15 text-primary"><LockKeyhole className="size-5" /></div>
        <CardTitle className="text-2xl">Sign in to the field</CardTitle>
        <CardDescription>Your conversations are private to you. Facts and corrections you give are shared with the team.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-5" noValidate>
          <div className="grid gap-2">
            <Label htmlFor="user">Who are you?</Label>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger id="user" aria-label="User"><SelectValue placeholder={users.length ? "Select your name" : "Service offline"} /></SelectTrigger>
              <SelectContent>
                {teams.map((t) => (
                  <SelectGroup key={t}>
                    <SelectLabel>{t}</SelectLabel>
                    {users.filter((u) => u.team_name === t).map((u) => (
                      <SelectItem key={u.user_id} value={u.user_id}>
                        {u.name} <span className="text-muted-foreground capitalize">· {role(u.role)}</span>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} aria-invalid={!!error} className="pr-10" required />
              <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
          {error && (
            <Alert variant="destructive"><AlertTriangle /><AlertDescription>{error}</AlertDescription></Alert>
          )}
          <Button type="submit" size="lg" disabled={busy || !users.length} className="w-full">
            {busy ? <><Loader2 className="animate-spin" /> Verifying…</> : "Sign in"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">5 failed attempts lock the account for 15 minutes.</p>
        </form>
      </CardContent>
    </Card>
  );
}
