export type Row = Record<string, unknown>;
export type Visual = {
  component: "status_card" | "table" | "line_chart" | "bar_chart" | "map" | "heatmap";
  title?: string;
  rows: Row[];
  columns?: string[];
  hints?: Record<string, unknown>;
};
export type Source = { kind?: string; id?: string; doc?: string; section?: string; quote?: string; author?: string; text?: string; status?: string; file?: string; date?: string };
export type Payload = {
  visual?: Visual | null;
  sources?: Source[];
  memory_writes?: { id: string; kind: string; status: string; asset_id?: string; conflicts?: string[] }[];
  conflicts?: string[];
  trace?: { tool: string; args?: Row; error?: string }[];
  model?: string;
  unverified_ids?: string[];
};
export type Message = { role: "user" | "assistant"; content: string; payload?: Payload; created_at?: string; pending?: boolean };
export type Conversation = { conv_id: string; title: string; sim_date: string; updated_at: string };
export type Me = { user_id: string; name: string; role: string; team_id: string; team_name: string };
export type Overview = {
  as_of: string; as_of_label: string; wells: number; producing: number; not_producing: number; plugged: number;
  spills_90d: number; spill_bbl_90d: number; open_fines_usd: number; open_repairs: number; model: string;
  well_types: string[];
  areas: { area_id: string; name: string; wells: number; producing: number }[];
  well_points: { asset_id: string; lat: number; lon: number; producing: boolean; area_id: string; well_type: string }[];
};
