"""Deterministic reference check: reproduces the expected answers of the example
questions (Q1-Q11, Q14) straight from the raw files, with no LLM.

Usage: python scripts/golden_check.py <path-to-flytbase-ahc-swe-asset-intelligence-dataset>

This is the seed of the analytics engine (see docs/SYSTEM_DESIGN.md, section 4).
Thresholds are hard-coded here only for the check; the real engine reads them
from the rules registry extracted from fleet/well-types/*.md.
"""
import json, glob, os, re, sys
import pandas as pd

ROOT = sys.argv[1]
A = f"{ROOT}/sample-data/assets"
FLEET = f"{ROOT}/sample-data/fleet"
TODAY = pd.Timestamp("2026-10-16", tz="UTC")
THRESH = {"T200": 15.0, "T350": 20.0}

def jl(p):
    if not os.path.exists(p): return []
    return [json.loads(l) for l in open(p) if l.strip()]

meta, ins, mnt, reg, ctx = [], [], [], [], []
for d in sorted(glob.glob(f"{A}/WELL-*")):
    meta.append(json.load(open(f"{d}/metadata.json")))
    ins += jl(f"{d}/inspections.jsonl"); mnt += jl(f"{d}/maintenance.jsonl")
    reg += jl(f"{d}/regulatory-events.jsonl"); ctx += jl(f"{d}/context.jsonl")
areas = json.load(open(f"{FLEET}/areas.json"))
users = {u["user_id"]: u["name"] for u in json.load(open(f"{FLEET}/users.json"))["users"]}
area_name = {a["area_id"]: a["name"] for a in areas["areas"]}

W = pd.DataFrame([{**{k: m[k] for k in ["asset_id", "well_type", "area_id", "recorded_status", "installed_on"]},
                   "lat": m["location"]["lat"], "lon": m["location"]["lon"]} for m in meta])
I = pd.DataFrame(ins); I["t"] = pd.to_datetime(I.inspected_at)
M = pd.DataFrame(mnt); M["start"] = pd.to_datetime(M.started_at); M["total"] = M.cost_usd.apply(lambda c: c["total"])
C = pd.DataFrame(ctx); R = pd.DataFrame(reg)
I = I.merge(W[["asset_id", "well_type", "area_id"]], on="asset_id")
I["delta"] = I.wellhead_temp_c - I.ambient_temp_c
I["producing"] = I.delta >= I.well_type.map(THRESH)
corrected = set(C[C.note_type == "correction"].inspection_id.dropna())
I["real_spill"] = I.spill_detected & ~I.inspection_id.isin(corrected)

print("counts", len(W), len(I), len(M), len(R), len(C), "corrections", len(corrected))
print("note types", C.note_type.value_counts().to_dict())
print("inspection max date", I.t.max(), "| methods", I.method.value_counts().to_dict())

latest = I.sort_values("t").groupby("asset_id").tail(1).set_index("asset_id")
# Q1
r = latest.loc["WELL-0001"]; print("\nQ1", r.inspection_id, r.t, users[r.inspector_user_id], r.method, round(r.delta, 1), r.producing)
# Q2
print("area ids", sorted(W.area_id.unique()), area_name)
aid = {v: k for k, v in area_name.items()}
def area_wells(n): return set(W[W.area_id == aid[n]].asset_id)
q2 = latest[latest.index.isin(area_wells("Northeast Block 8")) & ~latest.producing]
print("Q2", [(i, round(r.delta, 1), r.notes) for i, r in q2.iterrows()])
open_m = M[(pd.to_datetime(M.completed_at) > TODAY)]
print("  open repairs in Q2 wells:", open_m[open_m.asset_id.isin(q2.index)][["maintenance_id", "issue", "started_at"]].values.tolist())
# Q3
w1 = I[I.asset_id == "WELL-0001"].sort_values("t").tail(13)
print("Q3", w1.t.dt.date.iloc[0], w1.t.dt.date.iloc[-1], "not producing:", w1[~w1.producing].t.dt.date.tolist())
# Q4
s = I[(I.asset_id == "WELL-0001") & I.real_spill]
print("Q4", len(s), round(s.spill_est_volume_bbl.sum(), 1), s.t.dt.date.tolist())
# Q5
d = I[(I.asset_id == "WELL-0001") & (I.t.dt.year == 2025) & ~I.producing]
print("Q5", 7 * len(d), d.t.dt.date.tolist())
# Q6
win = I[(I.t >= TODAY - pd.DateOffset(months=4)) & (I.t <= TODAY + pd.Timedelta(days=1)) & ~I.producing & I.asset_id.isin(area_wells("Northeast Block 7"))]
q6 = (win.groupby("asset_id").size() * 7).sort_values(ascending=False).head(5)
print("Q6 window start", (TODAY - pd.DateOffset(months=4)).date(), q6.to_dict())
# Q7
q7 = I[I.real_spill & (I.t >= TODAY - pd.Timedelta(days=90)) & I.asset_id.isin(area_wells("Northeast Block 8"))]
print("Q7", q7[["asset_id", "inspection_id", "spill_est_volume_bbl"]].values.tolist(), q7.t.dt.date.tolist())
# Q8
s26 = I[I.real_spill & (I.t.dt.year == 2026)]
print("Q8\n", pd.crosstab(s26.area_id.map(area_name), s26.t.dt.month, margins=True))
# Q10 containment from reports
def containment(asset, rel):
    p = f"{A}/{asset}/{rel}"
    if not isinstance(rel, str) or not os.path.exists(p): return None
    m = re.search(r"[Cc]ontained about ([\d.]+) hours", open(p).read())
    return float(m.group(1)) if m else None
sp = I[I.real_spill & (I.t >= TODAY - pd.Timedelta(days=90)) & I.asset_id.isin(area_wells("Southwest Block 24"))]
mm = M.merge(sp[["inspection_id"]], left_on="triggered_by_inspection_id", right_on="inspection_id")
mm["contain_h"] = [containment(a, r) for a, r in zip(mm.asset_id, mm.report_file)]
print("Q10", mm[mm.contain_h > 4][["asset_id", "maintenance_id", "inspection_id", "contain_h"]].values.tolist())
# Q11 costs this year
for w in ["WELL-0121", "WELL-0138", "WELL-0107"]:
    print("Q11", w, M[(M.asset_id == w) & (M.start.dt.year == 2026)].total.sum())
# Q14 RCA pump jack, corrective in last 12 months
yr = M[(M.maintenance_type == "corrective") & (M.equipment_kind == "pump_jack") & (M.start > TODAY - pd.DateOffset(months=12)) & (M.start <= TODAY)]
cnt = yr[yr.asset_id.isin(area_wells("Northeast Block 7"))].groupby("asset_id").size()
print("Q14", cnt[cnt >= 2].to_dict(), W.set_index("asset_id").loc[cnt[cnt >= 2].index].well_type.to_dict())
# Q15 reportable spills NE8 last 90d
print("Q15 max vol NE8 90d", q7.spill_est_volume_bbl.max())
# Q18
print("Q18", C[C.asset_id == "WELL-0101"][["note_id", "author_user_id", "note_type", "inspection_id", "text"]].values.tolist())
print("Q12 INS-0164-0205", I[I.inspection_id == "INS-0164-0205"][["wellhead_temp_c", "ambient_temp_c", "inspector_user_id", "notes"]].values.tolist())
# Disagreement patterns in notes: multiple notes on the same inspection
print("notes w/ inspection_id by type", C.dropna(subset=["inspection_id"]).note_type.value_counts().to_dict())
print("wells with notes:", C.asset_id.nunique())
