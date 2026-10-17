"use client";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Dot, LabelList } from "recharts";
import { CircleCheck, CircleX, Wrench, StickyNote, TriangleAlert, Gauge, Thermometer } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Row, Visual, Overview } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "oklch(0.75 0.1 180)", "oklch(0.7 0.1 30)"];
const label = (k: string) => k.replaceAll("_", " ").replace(/\bc\b/, "°C").replace(/\busd\b/i, "USD");
const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Array.isArray(v)) return v.join("; ");
  if (typeof v === "object") return JSON.stringify(v);
  const s = String(v);
  return /^\d{4}-\d{2}-\d{2}T/.test(s) ? s.slice(0, 16).replace("T", " ") : s;
}

function Frame({ title, children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mt-3 rounded-xl border bg-card/70 p-4", className)}>
      {title && <div className="mb-3 text-sm font-medium text-muted-foreground">{title}</div>}
      {children}
    </div>
  );
}

export function VisualView({ v, overview }: { v?: Visual | null; overview?: Overview | null }) {
  if (!v || !v.rows?.length) return null;
  switch (v.component) {
    case "status_card": return <StatusCard row={v.rows[0]} />;
    case "line_chart": return <LineViz v={v} />;
    case "bar_chart": return <BarViz v={v} />;
    case "heatmap": return <HeatmapViz v={v} />;
    case "map": return <FieldMap v={v} overview={overview} />;
    default: return <DataTable v={v} />;
  }
}

export function StatusCard({ row: r }: { row: Row }) {
  if (!("producing" in r)) return <DataTable v={{ component: "table", rows: [r] }} />;
  const ok = Boolean(r.producing);
  const delta = Number(r.delta_c), thr = Number(r.threshold_c);
  const pct = Math.max(0, Math.min(100, (delta / Math.max(thr * 2, 1)) * 100));
  return (
    <div className={cn("mt-3 overflow-hidden rounded-xl border", ok ? "border-success/40" : "border-destructive/40")}>
      <div className={cn("flex flex-wrap items-center justify-between gap-3 px-5 py-4", ok ? "bg-success/10" : "bg-destructive/10")}>
        <div className="flex items-center gap-3">
          {ok ? <CircleCheck className="size-7 text-success" /> : <CircleX className="size-7 text-destructive" />}
          <div>
            <div className="text-lg font-semibold">{String(r.asset_id)} · {ok ? "Producing oil" : "Not producing oil"}</div>
            <div className="text-xs text-muted-foreground">{fmt(r.name)} · {fmt(r.well_type)} · {fmt(r.area)}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">Wellhead above air</div>
          <div className={cn("text-2xl font-semibold tabular-nums", ok ? "text-success" : "text-destructive")}>{fmt(r.delta_c)} °C</div>
        </div>
      </div>
      <div className="grid gap-4 p-5 text-sm sm:grid-cols-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Last inspection</div>
          <div className="mt-1 font-medium">{fmt(r.last_inspection_id)}</div>
          <div className="text-muted-foreground">{fmt(r.last_inspected)} · {fmt(r.method)} · {fmt(r.inspector)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Recorded status</div>
          <div className="mt-1 flex items-center gap-2"><code className="rounded bg-muted px-1.5">{fmt(r.recorded_status)}</code>
            {r.recorded_status_out_of_date ? <Badge variant="destructive">out of date</Badge> : <Badge variant="success">matches</Badge>}</div>
        </div>
        <div>
          <div className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground"><Thermometer className="size-3" /> Readings</div>
          <div className="mt-1 tabular-nums">wellhead {fmt(r.wellhead_temp_c)} °C · air {fmt(r.ambient_temp_c)} °C</div>
          <div className="mt-2 h-1.5 rounded-full bg-muted"><div className={cn("h-1.5 rounded-full", ok ? "bg-success" : "bg-destructive")} style={{ width: `${pct}%` }} /></div>
          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><Gauge className="size-3" /> limit {fmt(r.threshold_c)} °C</div>
        </div>
      </div>
      <div className="grid gap-2 border-t px-5 py-4 text-sm">
        {r.reason ? <div><span className="text-muted-foreground">Reason: </span>{String(r.reason)}</div> : null}
        {r.observation ? <div><span className="text-muted-foreground">Inspector observation: </span>“{String(r.observation)}” — suggest a field check</div> : null}
        {r.corrected ? <div className="text-info">Reading corrected ({String(r.corrected)}); original wellhead {fmt(r.original_wellhead_temp_c)} °C kept.</div> : null}
        {(r.open_repairs as string[] | undefined)?.map((o) => <div key={o} className="flex gap-2"><Wrench className="mt-0.5 size-4 shrink-0 text-primary" />{o}</div>)}
        {(r.context as string[] | undefined)?.map((o) => <div key={o} className="flex gap-2"><StickyNote className="mt-0.5 size-4 shrink-0 text-info" />{o}</div>)}
        {(r.conflicts as string[] | undefined)?.map((o) => <div key={o} className="flex gap-2 text-warning"><TriangleAlert className="mt-0.5 size-4 shrink-0" />{o}</div>)}
        <div className="text-xs text-muted-foreground">Rule: {fmt(r.threshold_source)}</div>
      </div>
    </div>
  );
}

export function DataTable({ v }: { v: Visual }) {
  const cols = useMemo(() => {
    const all = Object.keys(v.rows[0] ?? {}).filter((c) => c !== "t");
    const pick = (v.columns ?? []).filter((c) => all.includes(c));
    return pick.length ? pick : all;
  }, [v]);
  return (
    <Frame title={v.title}>
      <div className="max-h-[420px] overflow-auto rounded-md border">
        <Table>
          <TableHeader><TableRow>{cols.map((c) => <TableHead key={c}>{label(c)}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {v.rows.map((r, i) => (
              <TableRow key={i}>
                {cols.map((c) => {
                  const val = r[c];
                  if (c === "producing") return <TableCell key={c}>{val ? <Badge variant="success">producing</Badge> : <Badge variant="destructive">not producing</Badge>}</TableCell>;
                  if (c === "status" && typeof val === "string") return <TableCell key={c}><Badge variant={val === "breach" || /missed|expired|not/i.test(val) ? "destructive" : val === "pending" ? "warning" : val === "met" || /allowed|met/i.test(val) ? "success" : "secondary"}>{val}</Badge></TableCell>;
                  return <TableCell key={c} className={cn(isNum(val) && "tabular-nums text-right", c === "asset_id" && "font-medium text-primary whitespace-nowrap")}>{fmt(val)}</TableCell>;
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{v.rows.length} row{v.rows.length === 1 ? "" : "s"}</div>
    </Frame>
  );
}

function LineViz({ v }: { v: Visual }) {
  const series = (v.hints?.series as string[]) ?? Object.keys(v.rows[0]).filter((k) => isNum(v.rows[0][k])).slice(0, 2);
  const x = (v.hints?.x as string) ?? "date";
  const marker = v.hints?.markers as string | undefined;
  return (
    <Frame title={v.title}>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={v.rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={x} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} unit="°" />
          <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }} />
          <Legend />
          {series.map((s, i) => (
            <Line key={s} type="monotone" dataKey={s} name={label(s)} stroke={PALETTE[i]} strokeWidth={2.2}
              dot={(p: { cx?: number; cy?: number; payload?: Row; index?: number }) => {
                const off = marker && p.payload && p.payload[marker] === false;
                return <Dot key={`${s}-${p.index}`} cx={p.cx} cy={p.cy} r={off ? 6 : 3} fill={off ? "var(--destructive)" : PALETTE[i]} stroke={off ? "white" : "none"} />;
              }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {marker && <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground"><span className="inline-block size-2.5 rounded-full bg-destructive" /> not producing oil</div>}
    </Frame>
  );
}

function BarViz({ v }: { v: Visual }) {
  const rows = v.rows;
  const keys = Object.keys(rows[0]);
  const strCols = keys.filter((k) => typeof rows[0][k] === "string");
  const numCols = keys.filter((k) => isNum(rows[0][k]));
  const x = (v.hints?.x as string) && keys.includes(v.hints?.x as string) ? (v.hints?.x as string) : strCols[0] ?? keys[0];
  // long format (x, series, value) → pivot into stacked bars
  const seriesCol = strCols.find((c) => c !== x && new Set(rows.map((r) => r[c])).size <= 8 && rows.length > new Set(rows.map((r) => r[x])).size);
  let data: Row[] = rows, bars: string[];
  let stacked = Boolean(v.hints?.stacked);
  if (seriesCol) {
    const val = (v.hints?.y as string) && numCols.includes(v.hints?.y as string) ? (v.hints?.y as string) : numCols[0];
    const m = new Map<string, Row>();
    for (const r of rows) {
      const k = String(r[x]);
      const o = m.get(k) ?? { [x]: k };
      o[String(r[seriesCol])] = Number(r[val]);
      m.set(k, o);
    }
    data = Array.from(m.values());
    bars = Array.from(new Set(rows.map((r) => String(r[seriesCol]))));
    stacked = true;
  } else {
    const y = v.hints?.y as string | undefined;
    bars = y && numCols.includes(y) ? [y] : numCols.slice(0, 4);
  }
  return (
    <Frame title={v.title}>
      <ResponsiveContainer width="100%" height={Math.max(280, Math.min(520, 40 + data.length * 6))}>
        <BarChart data={data} margin={{ top: 16, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey={x} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 60 : 30} />
          <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <Tooltip cursor={{ fill: "oklch(1 0 0 / 0.04)" }} contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }} />
          {bars.length > 1 && <Legend />}
          {bars.map((b, i) => (
            <Bar key={b} dataKey={b} name={label(b)} stackId={stacked ? "s" : undefined} fill={PALETTE[i % PALETTE.length]} radius={stacked ? 0 : [4, 4, 0, 0]}>
              {!stacked && bars.length === 1 && <LabelList dataKey={b} position="top" fill="var(--foreground)" fontSize={11} />}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}

function HeatmapViz({ v }: { v: Visual }) {
  const rowKey = (v.hints?.rows_field as string) ?? Object.keys(v.rows[0])[0];
  const cols = Object.keys(v.rows[0]).filter((k) => k !== rowKey && k !== "Total");
  const max = Math.max(1, ...v.rows.flatMap((r) => cols.map((c) => Number(r[c]) || 0)));
  return (
    <Frame title={v.title}>
      <div className="overflow-auto">
        <table className="w-full border-separate border-spacing-1 text-sm">
          <thead><tr><th />{cols.map((c) => <th key={c} className="px-1 text-xs font-medium text-muted-foreground">{c}</th>)}<th className="px-2 text-xs text-muted-foreground">Total</th></tr></thead>
          <tbody>
            {v.rows.map((r) => (
              <tr key={String(r[rowKey])}>
                <td className="whitespace-nowrap pr-2 text-xs text-muted-foreground">{String(r[rowKey])}</td>
                {cols.map((c) => {
                  const n = Number(r[c]) || 0;
                  return <td key={c} className="h-9 min-w-9 rounded-md text-center text-xs font-medium tabular-nums"
                    style={{ background: `oklch(0.79 0.16 ${70 - (n / max) * 45} / ${0.08 + (n / max) * 0.85})`, color: n / max > 0.55 ? "oklch(0.18 0.02 60)" : undefined }}>{n}</td>;
                })}
                <td className="px-2 text-center font-semibold tabular-nums text-primary">{fmt(r.Total ?? cols.reduce((a, c) => a + (Number(r[c]) || 0), 0))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Frame>
  );
}

function FieldMap({ v, overview }: { v: Visual; overview?: Overview | null }) {
  const pts = v.rows.filter((r) => isNum(r.lat) && isNum(r.lon)) as (Row & { lat: number; lon: number })[];
  if (!pts.length) return <DataTable v={v} />;
  // zoom to the result pins, with a margin, and show other wells in that window for context
  const plat = pts.map((p) => p.lat), plon = pts.map((p) => p.lon);
  const mLat = Math.max(0.01, (Math.max(...plat) - Math.min(...plat)) * 0.25), mLon = Math.max(0.01, (Math.max(...plon) - Math.min(...plon)) * 0.25);
  const [minLat, maxLat, minLon, maxLon] = [Math.min(...plat) - mLat, Math.max(...plat) + mLat, Math.min(...plon) - mLon, Math.max(...plon) + mLon];
  const bg = (overview?.well_points ?? []).filter((p) => p.lat >= minLat && p.lat <= maxLat && p.lon >= minLon && p.lon <= maxLon);
  const showLabels = pts.length <= 15;
  const W = 760, H = 420, pad = 28;
  const sx = (lon: number) => pad + ((lon - minLon) / Math.max(maxLon - minLon, 1e-6)) * (W - 2 * pad);
  const sy = (lat: number) => H - pad - ((lat - minLat) / Math.max(maxLat - minLat, 1e-6)) * (H - 2 * pad);
  const size = (r: Row) => (isNum(r.volume_bbl) ? 6 + Math.min(14, Number(r.volume_bbl) * 1.6) : 8);
  return (
    <Frame title={v.title}>
      <div className="relative overflow-hidden rounded-lg border bg-grid bg-[oklch(0.17_0.015_250)]">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
          {bg.map((p) => <circle key={p.asset_id} cx={sx(p.lon)} cy={sy(p.lat)} r={3} fill={p.producing ? "oklch(0.72 0.17 150 / 0.35)" : "oklch(0.64 0.21 25 / 0.45)"} />)}
          {pts.map((p, i) => (
            <g key={i}>
              <circle cx={sx(p.lon)} cy={sy(p.lat)} r={size(p) + 6} fill="oklch(0.79 0.16 70 / 0.15)" />
              <circle cx={sx(p.lon)} cy={sy(p.lat)} r={size(p)} fill="var(--primary)" stroke="var(--background)" strokeWidth={2}>
                <title>{`${p.asset_id ?? ""} ${p.date ?? ""} ${p.volume_bbl ?? ""}`}</title>
              </circle>
              {showLabels && <text x={sx(p.lon) + size(p) + 4} y={sy(p.lat) + 4} fontSize={11} fill="var(--foreground)">{String(p.asset_id ?? "")}</text>}
            </g>
          ))}
        </svg>
        <div className="absolute bottom-2 left-3 flex gap-3 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-primary" /> result</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-success/50" /> producing well</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-destructive/60" /> not producing</span>
        </div>
      </div>
      <DataTable v={{ ...v, title: undefined, columns: Array.from(new Set(["asset_id", "date", "inspection_id", "volume_bbl", "spill_class", ...(v.columns ?? []), "lat", "lon"])) }} />
    </Frame>
  );
}
