"""Semantic layer: the deterministic tools the agent calls.

Every number in an answer comes from here, computed over the *effective view*:
raw records with applied corrections overlaid (originals kept). Rules
(thresholds, deadlines) come from the rules registry, so they follow the
manuals and any scoped rule a user has given.

Each tool returns a dict: {tool, summary, rows, columns, sources, suggested_visual, hints}.
"""
from __future__ import annotations

import re
from datetime import timedelta

import duckdb
import pandas as pd

from .data import Data, Rule
from .store import Store

UTC = "UTC"
SHUTDOWN_WORDS = re.compile(r"shut|workover|maintenance|repair|replac|offline|waiting|down for|stopped|tie-in|outage",
                            re.I)
NOT_RUNNING_WORDS = re.compile(r"not moving|no stroke|not running|stopped|idle|not pumping|shut", re.I)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_date(t) -> str:
    if t is None or (not isinstance(t, str) and pd.isna(t)):
        return ""
    ts = pd.Timestamp(t)
    return f"{ts.day} {ts.strftime('%b %Y')}"


def _ts(s) -> pd.Timestamp | None:
    if s is None or s == "" or (not isinstance(s, str) and pd.isna(s)):
        return None
    t = pd.Timestamp(s)
    return t.tz_localize(UTC) if t.tzinfo is None else t.tz_convert(UTC)


def _clean(v):
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def result(tool, summary, rows=None, sources=None, visual=None, columns=None, **hints):
    rows = [{k: _clean(v) for k, v in r.items()} for r in (rows or [])]
    if columns is None and rows:
        columns = list(rows[0].keys())
    seen, src = set(), []
    for s in sources or []:
        key = (s.get("kind"), s.get("id") or s.get("doc"), s.get("section"))
        if key not in seen:
            seen.add(key)
            src.append(s)
    return {"tool": tool, "summary": summary, "rows": rows, "columns": columns or [], "sources": src,
            "suggested_visual": visual, "hints": hints}


class Engine:
    def __init__(self, data: Data, store: Store):
        self.d = data
        self.store = store
        self._v = None
        self.wells = data.wells.set_index("asset_id", drop=False)
        self.refresh()

    # ------------------------------------------------------------------ helpers
    @property
    def as_of(self) -> pd.Timestamp:
        return self.d.as_of

    def name(self, uid):
        return self.d.user_name(uid)

    def resolve_area(self, area: str | None) -> str | None:
        if not area:
            return None
        a = area.strip().lower().replace("_", " ")
        for aid, v in self.d.areas.items():
            if a in (aid.lower(), v.get("name", "").lower()):
                return aid
        compact = re.sub(r"[^a-z0-9]", "", a)
        for aid, v in self.d.areas.items():
            if compact in (re.sub(r"[^a-z0-9]", "", aid.lower()), re.sub(r"[^a-z0-9]", "", v.get("name", "").lower())):
                return aid
        m = re.search(r"(north|south)\s*(east|west)\D*(\d+)", a)
        if m:
            code = f"{m.group(1)[0]}{m.group(2)[0]}-{int(m.group(3)):02d}".upper()
            if code in self.d.areas:
                return code
        raise ValueError(f"Unknown area '{area}'. Known: " + ", ".join(v["name"] for v in self.d.areas.values()))

    def resolve_well(self, w: str) -> str:
        if w is None:
            raise ValueError("asset_id is required")
        m = re.search(r"(\d+)", str(w))
        if not m:
            raise ValueError(f"Unknown well '{w}'")
        aid = f"WELL-{int(m.group(1)):04d}"
        if aid not in self.wells.index:
            raise ValueError(f"Unknown well '{w}'")
        return aid

    def scope_wells(self, area=None, asset_ids=None, well_type=None) -> list[str]:
        w = self.d.wells
        if asset_ids:
            if isinstance(asset_ids, str):
                asset_ids = re.split(r"[,\s]+", asset_ids)
            ids = {self.resolve_well(a) for a in asset_ids if a}
            w = w[w.asset_id.isin(ids)]
        if area:
            w = w[w.area_id == self.resolve_area(area)]
        if well_type:
            w = w[w.well_type.str.upper() == str(well_type).upper()]
        return w.asset_id.tolist()

    def period(self, period=None, start=None, end=None):
        as_of = self.as_of
        end_x = as_of + timedelta(days=1)  # today inclusive
        if start or end:
            s = _ts(start) or self.d.ins.t.min()
            e = (_ts(end) + timedelta(days=1)) if end else end_x
            return s, e, f"{fmt_date(s)} – {fmt_date(e - timedelta(days=1))}"
        p = (period or "all").strip().lower().replace(" ", "_").replace("-", "_")
        if m := re.fullmatch(r"(?:last|past)_?(\d+)_?(day|week|month|year)s?", p):
            n, u = int(m.group(1)), m.group(2)
            s = as_of - (pd.DateOffset(days=n) if u == "day" else pd.DateOffset(weeks=n) if u == "week"
                         else pd.DateOffset(months=n) if u == "month" else pd.DateOffset(years=n))
            return s, end_x, f"{fmt_date(s)} – {fmt_date(as_of)}"
        if m := re.fullmatch(r"(?:year:?_?)?(\d{4})", p):
            y = int(m.group(1))
            s, e = pd.Timestamp(f"{y}-01-01", tz=UTC), pd.Timestamp(f"{y + 1}-01-01", tz=UTC)
            return s, min(e, end_x), str(y)
        if p in ("this_year", "ytd", "year_to_date"):
            s = pd.Timestamp(f"{as_of.year}-01-01", tz=UTC)
            return s, end_x, f"{as_of.year} (to {fmt_date(as_of)})"
        if m := re.fullmatch(r"month:?_?(\d{4})_(\d{2})", p):
            s = pd.Timestamp(f"{m.group(1)}-{m.group(2)}-01", tz=UTC)
            return s, s + pd.DateOffset(months=1), s.strftime("%b %Y")
        s = self.d.ins.t.min()
        return s, end_x, f"all records ({fmt_date(s)} – {fmt_date(as_of)})"

    # ------------------------------------------------------------------ rules (manual + scoped user rules)
    def rule(self, key, asset_id=None, well_type=None, equipment_kind=None) -> tuple[float | None, dict]:
        area = None
        if asset_id:
            w = self.wells.loc[asset_id]
            well_type, area = w.well_type, w.area_id
        best, best_rank = None, -1
        for a in self._user_rules:
            if a["rule_key"] != key:
                continue
            if a.get("equipment_kind") and equipment_kind and a["equipment_kind"] != equipment_kind:
                continue
            if a.get("equipment_kind") and not equipment_kind:
                continue
            rank = None
            if a.get("asset_id"):
                rank = 3 if a["asset_id"] == asset_id else None
            elif a.get("area_id"):
                rank = 2 if a["area_id"] == area else None
            elif a.get("well_type"):
                rank = 1 if (well_type or "").upper() == a["well_type"].upper() else None
            else:
                rank = 0
            if rank is not None and rank >= best_rank:
                best, best_rank = a, rank
        if best:
            src = {"kind": "feedback", "id": best["id"], "author": self.name(best["author_user_id"]),
                   "text": best["text"], "created_at": best["created_at"]}
            return float(best["new_value"]), {"source": "user", "label":
                                              f"{src['author']}'s rule ({best['id']}), not the manual", **src}
        for r in self.d.rules:
            if r.key == key and (not r.scope or r.scope.get("well_type") == well_type):
                return r.value, {"source": r.source, "kind": "doc", "doc": r.doc, "section": r.section,
                                 "quote": r.quote, "label": f"{r.doc} §{r.section}"}
        return None, {"source": "missing", "label": f"no rule '{key}' for {well_type}"}

    def doc_src(self, key, well_type=None, asset_id=None):
        _, s = self.rule(key, asset_id=asset_id, well_type=well_type)
        return {k: v for k, v in s.items() if k in ("kind", "doc", "section", "quote", "id", "author", "text")}

    # ------------------------------------------------------------------ effective view
    def refresh(self, force=False):
        if not force and self._v == self.store.version:
            return
        self._v = self.store.version
        A = self.store.assertions()
        self.feedback = A
        self._user_rules = [a for a in A if a["kind"] == "scoped_rule" and a["status"] == "applied"]
        I = self.d.ins.merge(self.d.wells[["asset_id", "well_type", "area_id", "lat", "lon"]], on="asset_id",
                             how="left").copy()
        I["orig_wellhead_temp_c"] = I.wellhead_temp_c
        I["orig_ambient_temp_c"] = I.ambient_temp_c
        I["orig_spill_est_volume_bbl"] = I.spill_est_volume_bbl
        I["corrected_by"] = None
        I = I.set_index("inspection_id", drop=False)
        notes = self.d.notes
        formal = notes[(notes.note_type == "correction") & notes.inspection_id.notna()]
        not_spill = {r.inspection_id: r.note_id for r in formal.itertuples()}
        for a in A:
            if a["status"] != "applied" or not a.get("inspection_id") or a["inspection_id"] not in I.index:
                continue
            iid, by = a["inspection_id"], f"{a['id']} by {self.name(a['author_user_id'])}"
            if a["kind"] in ("correction_raw", "correction_ai") and a.get("field") in I.columns:
                I.at[iid, a["field"]] = float(a["new_value"])
                I.at[iid, "corrected_by"] = by
            elif a["kind"] == "not_a_spill":
                not_spill[iid] = a["id"]
                I.at[iid, "corrected_by"] = by
        thr = {aid: self.rule("producing_delta_c", asset_id=aid)[0] for aid in self.d.wells.asset_id}
        I["threshold_c"] = I.asset_id.map(thr)
        I["delta_c"] = (I.wellhead_temp_c - I.ambient_temp_c).round(1)
        I["producing"] = I.delta_c >= I.threshold_c
        I["corrected_not_spill"] = I.inspection_id.map(not_spill)
        I["real_spill"] = I.spill_detected.fillna(False).astype(bool) & I.corrected_not_spill.isna()
        I["spill_class"] = [self.spill_class(v) if s else None for v, s in zip(I.spill_est_volume_bbl, I.real_spill)]
        self.I = I.reset_index(drop=True).sort_values(["asset_id", "t"])
        self.latest = self.I.groupby("asset_id").tail(1).set_index("asset_id", drop=False)

    def spill_class(self, vol):
        if vol is None or pd.isna(vol):
            return None
        minor = self.rule("spill_minor_below_bbl")[0]
        rep = self.rule("spill_reportable_bbl")[0]
        major = self.rule("spill_major_bbl")[0]
        return "minor" if vol < minor else "moderate" if vol < rep else "reportable" if vol < major else "major"

    # ------------------------------------------------------------------ evidence helpers
    def src_ins(self, r):
        return {"kind": "inspection", "id": r["inspection_id"], "asset_id": r["asset_id"],
                "date": fmt_date(r["t"]), "file": f"assets/{r['asset_id']}/inspections.jsonl"}

    def src_mnt(self, r):
        s = {"kind": "repair", "id": r["maintenance_id"], "asset_id": r["asset_id"],
             "file": f"assets/{r['asset_id']}/maintenance.jsonl"}
        return s

    def src_report(self, mnt_id):
        rep = self.d.reports[self.d.reports.maintenance_id == mnt_id]
        if rep.empty:
            return None
        r = rep.iloc[0]
        return {"kind": "report", "id": mnt_id, "file": r.report_file, "asset_id": r.asset_id}

    def src_note(self, n):
        return {"kind": "note", "id": n["note_id"], "asset_id": n["asset_id"], "author": self.name(n["author_user_id"]),
                "text": n["text"], "file": f"assets/{n['asset_id']}/context.jsonl"}

    def src_fb(self, a):
        return {"kind": "feedback", "id": a["id"], "asset_id": a.get("asset_id"), "author": self.name(a["author_user_id"]),
                "text": a["text"], "status": a["status"], "created_at": a["created_at"]}

    def src_reg(self, e):
        return {"kind": "regulator_event", "id": e["event_id"], "asset_id": e["asset_id"],
                "file": f"assets/{e['asset_id']}/regulatory-events.jsonl"}

    # ------------------------------------------------------------------ context: notes + feedback about a well
    def context_items(self, asset_id, on: pd.Timestamp | None = None, status_only=False):
        """Human knowledge about a well valid on a date: dataset notes + shared feedback from users."""
        on = on or self.as_of
        out = []
        N = self.d.notes[(self.d.notes.asset_id == asset_id) & (self.d.notes.note_type != "correction")]
        for n in N.to_dict("records"):
            vf, vt = _ts(n.get("valid_from")), _ts(n.get("valid_to"))
            if vf and vf > on + timedelta(days=1):
                continue
            if vt is not None and vt < on.normalize():
                continue
            if status_only and (vt is None and not SHUTDOWN_WORDS.search(n["text"] or "")):
                continue
            if status_only and n.get("linked_inspection_id") and not SHUTDOWN_WORDS.search(n["text"] or ""):
                continue
            out.append({"type": "note", "id": n["note_id"], "author": self.name(n["author_user_id"]),
                        "text": n["text"], "status": "on record", "valid_from": n.get("valid_from"),
                        "valid_to": n.get("valid_to"), "src": self.src_note(n)})
        for a in self.feedback:
            if a.get("asset_id") != asset_id or a["kind"] not in ("well_fact", "status_claim"):
                continue
            vf, vt = _ts(a.get("valid_from")), _ts(a.get("valid_to"))
            if vf and vf > on + timedelta(days=1) and status_only:
                continue
            if vt is not None and vt < on.normalize():
                continue
            out.append({"type": "feedback", "id": a["id"], "author": self.name(a["author_user_id"]), "text": a["text"],
                        "status": a["status"], "valid_from": a.get("valid_from"), "valid_to": a.get("valid_to"),
                        "src": self.src_fb(a)})
        return out

    def open_repairs(self, asset_id, on=None):
        on = on or self.as_of
        M = self.d.mnt
        m = M[(M.asset_id == asset_id) & (M.start <= on + timedelta(days=1)) & (M.end > on)]
        return m.to_dict("records")

    def reason(self, ins_row) -> tuple[str, list[dict], str | None]:
        """Why is this well not producing at this inspection? Never invents a cause."""
        aid, t = ins_row["asset_id"], ins_row["t"]
        srcs = []
        ctx = [c for c in self.context_items(aid, on=t, status_only=True) if c["status"] in ("applied", "on record")]
        if ctx:
            c = ctx[-1]
            srcs.append(c["src"])
            return f"{c['text']} (note {c['id']} by {c['author']})", srcs, None
        M = self.d.mnt
        cand = M[(M.asset_id == aid) & (
            (M.triggered_by_inspection_id == ins_row["inspection_id"]) |
            ((M.start <= t + timedelta(hours=12)) & (M.end >= t)) |
            ((M.start > t) & (M.start <= t + timedelta(days=7)) & (M.maintenance_type == "corrective")))]
        if not cand.empty:
            m = cand.sort_values("start").iloc[0]
            still_open = m["end"] > self.as_of
            srcs.append(self.src_mnt(m))
            txt = (f"Repair {m.maintenance_id}: {m.issue.lower() if m.issue else m.equipment_kind}, "
                   f"started {fmt_date(m.start)}" + (", still open" if still_open else f", finished {fmt_date(m.end)}"))
            return txt, srcs, None
        obs = ins_row.get("notes") or None
        return "No recorded reason", srcs, obs

    # ================================================================== TOOLS
    def well_snapshot(self, asset_id: str):
        aid = self.resolve_well(asset_id)
        w = self.wells.loc[aid]
        r = self.latest.loc[aid]
        thr, thr_src = self.rule("producing_delta_c", asset_id=aid)
        computed = "active" if r.producing else "down"
        stale = (w.recorded_status or "") != computed
        reason, rsrc, obs = (None, [], None) if r.producing else self.reason(r)
        ctx = self.context_items(aid)
        conflicts = []
        if r.corrected_by and r.notes and NOT_RUNNING_WORDS.search(r.notes) and r.producing:
            conflicts.append(f"The inspector's remark on {r.inspection_id} says \"{r.notes}\" "
                             f"({self.name(r.inspector_user_id)}), which disagrees with the corrected reading.")
        for c in ctx:
            if c["status"] in ("unconfirmed", "disputed"):
                conflicts.append(f"{c['author']} said \"{c['text']}\" ({c['id']}), marked {c['status']}.")
        opens = self.open_repairs(aid)
        row = {
            "asset_id": aid, "name": w["name"], "well_type": w.well_type, "area": self.d.area_name(w.area_id),
            "producing": bool(r.producing), "computed_status": computed,
            "wellhead_temp_c": r.wellhead_temp_c, "ambient_temp_c": r.ambient_temp_c, "delta_c": r.delta_c,
            "threshold_c": thr, "threshold_source": thr_src["label"],
            "last_inspection_id": r.inspection_id, "last_inspected": fmt_date(r.t),
            "inspected_at": r.t.isoformat(), "inspector": self.name(r.inspector_user_id), "method": r.method,
            "inspector_remark": r.notes or None,
            "recorded_status": w.recorded_status, "recorded_status_out_of_date": stale,
            "reason": reason, "observation": obs,
            "corrected": r.corrected_by, "original_wellhead_temp_c": r.orig_wellhead_temp_c
            if r.corrected_by and r.orig_wellhead_temp_c != r.wellhead_temp_c else None,
            "open_repairs": [f"{m['maintenance_id']} ({m['issue']}, started {fmt_date(m['start'])})" for m in opens],
            "context": [f"{c['id']} ({c['author']}, {c['status']}): {c['text']}" for c in ctx],
            "conflicts": conflicts,
        }
        sources = [self.src_ins(r), {k: v for k, v in thr_src.items() if k != "label"}] + rsrc + \
                  [c["src"] for c in ctx] + [self.src_mnt(m) for m in opens]
        verdict = "producing oil" if r.producing else "NOT producing oil"
        summary = (f"{aid} ({w.well_type}) is {verdict} as of its latest inspection {r.inspection_id} on "
                   f"{fmt_date(r.t)} ({r.method}, by {row['inspector']}): wellhead {r.wellhead_temp_c} °C vs air "
                   f"{r.ambient_temp_c} °C = {r.delta_c} °C above air; rule: producing if ≥ {thr} °C "
                   f"({thr_src['label']}). Recorded status '{w.recorded_status}'"
                   f"{' is OUT OF DATE' if stale else ' matches'}.")
        if reason:
            summary += f" Reason: {reason}."
            if obs:
                summary += f" Inspector observation: \"{obs}\". Suggest a field check."
        if row["corrected"]:
            summary += f" Reading corrected ({r.corrected_by}); original wellhead {r.orig_wellhead_temp_c} °C."
        if opens:
            summary += " Open repairs: " + "; ".join(row["open_repairs"]) + "."
        if ctx:
            summary += " Shared notes/feedback about this well (cite author by name): " + " | ".join(
                f"{c['id']} by {c['author']} [{c['status']}] valid {c['valid_from'] or '?'}→{c['valid_to'] or 'open'}: \"{c['text']}\""
                for c in ctx) + "."
        if conflicts:
            summary += " CONFLICTS: " + " ".join(conflicts)
        return result("well_snapshot", summary, [row], sources, "status_card")

    def fleet_status(self, area: str | None = None, well_type: str | None = None, producing: bool | None = None,
                     asset_ids: list[str] | None = None):
        ids = self.scope_wells(area, asset_ids, well_type)
        L = self.latest[self.latest.asset_id.isin(ids)]
        if producing is not None:
            L = L[L.producing == bool(producing)]
        rows, sources = [], []
        for r in L.to_dict("records"):
            w = self.wells.loc[r["asset_id"]]
            reason, rsrc, obs = (None, [], None) if r["producing"] else self.reason(r)
            computed = "active" if r["producing"] else "down"
            stale = (w.recorded_status or "") != computed
            rows.append({
                "asset_id": r["asset_id"], "well_type": w.well_type, "area": self.d.area_name(w.area_id),
                "producing": r["producing"], "delta_c": r["delta_c"], "threshold_c": r["threshold_c"],
                "wellhead_temp_c": r["wellhead_temp_c"], "ambient_temp_c": r["ambient_temp_c"],
                "last_inspection_id": r["inspection_id"], "last_inspected": fmt_date(r["t"]),
                "inspector": self.name(r["inspector_user_id"]),
                "recorded_status": w.recorded_status + (" (out of date)" if stale else ""),
                "reason": reason, "inspector_remark": r["notes"] or None,
                "corrected": r["corrected_by"],
                "lat": w.lat, "lon": w.lon,
            })
            sources += [self.src_ins(r)] + rsrc
        tag = f"area {self.d.area_name(self.resolve_area(area))}" if area else "selected wells"
        summ = f"{len(rows)} wells in {tag}" + (
            f" {'producing' if producing else 'NOT producing'}" if producing is not None else "") + \
               f" as of each well's latest inspection (today = {fmt_date(self.as_of)})."
        for r in rows[:40]:
            summ += (f"\n- {r['asset_id']} ({r['well_type']}): {r['delta_c']} °C above air "
                     f"(limit {r['threshold_c']}), recorded {r['recorded_status']}, last {r['last_inspected']}"
                     + (f"; reason: {r['reason']}" if r['reason'] else "")
                     + (f"; inspector remark: \"{r['inspector_remark']}\"" if r['inspector_remark'] else "")
                     + (f"; reading corrected {r['corrected']}" if r['corrected'] else ""))
        no_reason = [r["asset_id"] for r in rows if r["reason"] == "No recorded reason"]
        if no_reason:
            summ += f"\nNo recorded reason for: {', '.join(no_reason)} → say so and suggest a field check; do not invent a cause."
        sources += [self.doc_src("producing_delta_c", wt) for wt in sorted({r["well_type"] for r in rows})]
        cols = ["asset_id", "well_type", "delta_c", "recorded_status", "reason", "inspector_remark", "last_inspected"]
        return result("fleet_status", summ, rows, sources, "table", columns=cols)

    def timeseries(self, asset_id: str, period: str = "last_13_weeks", start=None, end=None):
        aid = self.resolve_well(asset_id)
        s, e, label = self.period(period, start, end)
        X = self.I[(self.I.asset_id == aid) & (self.I.t >= s) & (self.I.t < e)]
        rows = [{"date": fmt_date(r.t), "t": r.t, "inspection_id": r.inspection_id,
                 "wellhead_temp_c": r.wellhead_temp_c, "ambient_temp_c": r.ambient_temp_c,
                 "delta_c": r.delta_c, "threshold_c": r.threshold_c, "producing": bool(r.producing)}
                for r in X.itertuples()]
        off = [r["date"] for r in rows if not r["producing"]]
        summ = (f"{aid}: {len(rows)} weekly readings, {label}. Not producing on: {', '.join(off) or 'none'}. "
                f"Rule: producing if wellhead − air ≥ {rows[0]['threshold_c'] if rows else '?'} °C.")
        src = [self.src_ins(r) for r in X.to_dict("records")] + [self.doc_src("producing_delta_c", asset_id=aid)]
        return result("timeseries", summ, rows, src, "line_chart", x="date",
                      series=["wellhead_temp_c", "ambient_temp_c"], markers="producing")

    def downtime(self, area=None, asset_ids=None, well_type=None, period="last_4_months", start=None, end=None,
                 top_n: int | None = None):
        ids = self.scope_wells(area, asset_ids, well_type)
        s, e, label = self.period(period, start, end)
        X = self.I[self.I.asset_id.isin(ids) & (self.I.t >= s) & (self.I.t < e)]
        down = X[~X.producing]
        g = down.groupby("asset_id")
        rows = []
        for aid in ids:
            d = down[down.asset_id == aid]
            rows.append({"asset_id": aid, "well_type": self.wells.loc[aid].well_type,
                         "area": self.d.area_name(self.wells.loc[aid].area_id),
                         "downtime_days": 7 * len(d), "not_producing_inspections": len(d),
                         "inspections_in_period": int((X.asset_id == aid).sum()),
                         "dates": ", ".join(fmt_date(t) for t in d.t)})
        rows.sort(key=lambda r: (-r["downtime_days"], r["asset_id"]))
        nxt = None
        if top_n and len(rows) > top_n:
            cut = rows[top_n - 1]["downtime_days"]
            keep = [r for r in rows if r["downtime_days"] >= cut]
            rest = [r for r in rows if r["downtime_days"] < cut]
            nxt = rest[0] if rest else None
            rows = keep
        detail = []
        if len(ids) == 1:
            for r in down.to_dict("records"):
                why, rs, obs = self.reason(r)
                detail.append({"date": fmt_date(r["t"]), "inspection_id": r["inspection_id"],
                               "wellhead_temp_c": r["wellhead_temp_c"], "ambient_temp_c": r["ambient_temp_c"],
                               "delta_c": r["delta_c"], "threshold_c": r["threshold_c"], "cause": why,
                               "inspector_remark": obs})
        summ = (f"Downtime = 7 days × each weekly inspection where the well was not producing (missed inspections add "
                f"nothing; repair downtime_hours not used). Period {label}.")
        for r in rows[:30]:
            summ += f"\n- {r['asset_id']} ({r['well_type']}): {r['downtime_days']} days ({r['not_producing_inspections']} inspections: {r['dates']})"
        if top_n and len(rows) > top_n:
            summ += f"\nNote: tie at the cut-off, {len(rows)} wells shown for top {top_n}."
        if nxt:
            summ += f"\nNext: {nxt['asset_id']} with {nxt['downtime_days']} days."
        for dt in detail:
            summ += (f"\n  · {dt['date']} {dt['inspection_id']}: wellhead {dt['wellhead_temp_c']} °C, air "
                     f"{dt['ambient_temp_c']} °C → {dt['delta_c']} °C above air (< {dt['threshold_c']}); cause: {dt['cause']}")
        src = [self.src_ins(r) for r in down.to_dict("records")][:60] + \
              [self.doc_src("producing_delta_c", wt) for wt in sorted({r["well_type"] for r in rows})]
        vis = "bar_chart" if (top_n or len(rows) <= 12) and len(ids) > 1 else ("table" if len(ids) > 1 else None)
        return result("downtime", summ, rows if len(ids) > 1 else detail, src, vis, x="asset_id", y="downtime_days")

    def spills(self, area=None, asset_ids=None, well_type=None, period="all", start=None, end=None,
               min_volume: float | None = None, group_by: str | None = None):
        ids = self.scope_wells(area, asset_ids, well_type)
        s, e, label = self.period(period, start, end)
        X = self.I[self.I.asset_id.isin(ids) & (self.I.t >= s) & (self.I.t < e) & self.I.spill_detected.fillna(False)]
        real = X[X.real_spill]
        if min_volume is not None:
            real = real[real.spill_est_volume_bbl >= float(min_volume)]
        excluded = X[~X.real_spill]
        N = self.d.notes
        rows, src = [], []
        for r in real.to_dict("records"):
            disputes = N[(N.linked_inspection_id == r["inspection_id"]) & (N.note_type != "correction")]
            rows.append({"asset_id": r["asset_id"], "date": fmt_date(r["t"]), "inspection_id": r["inspection_id"],
                         "volume_bbl": r["spill_est_volume_bbl"], "spill_class": r["spill_class"],
                         "area_pct": r["spill_area_pct"], "area": self.d.area_name(r["area_id"]),
                         "month": MONTHS[r["t"].month - 1], "year": r["t"].year,
                         "lat": r["lat"], "lon": r["lon"], "inspector_remark": r["notes"] or None,
                         "ai_estimate_bbl": r["orig_spill_est_volume_bbl"] if r["corrected_by"] else None,
                         "corrected": r["corrected_by"],
                         "disputed_by_notes": "; ".join(f"{n.note_id} ({self.name(n.author_user_id)}): {n.text}"
                                                        for n in disputes.itertuples()) or None})
            src.append(self.src_ins(r))
            src += [self.src_note(n) for n in disputes.to_dict("records")]
        summ = (f"{len(rows)} real spills, {round(sum(r['volume_bbl'] or 0 for r in rows), 1)} bbl total, period {label}"
                f"{', min volume ' + str(min_volume) + ' bbl' if min_volume is not None else ''}. ")
        if len(excluded):
            summ += f"{len(X)} detections, {len(excluded)} excluded as corrected (not spills): "
            for r in excluded.to_dict("records"):
                cid = r["corrected_not_spill"]
                note = N[N.note_id == cid]
                why = note.text.iloc[0] if len(note) else cid
                summ += f"{r['inspection_id']} ({fmt_date(r['t'])}) by {cid}: {why}; "
                if len(note):
                    src.append(self.src_note(note.iloc[0].to_dict()))
        vis, hints = ("table", {})
        if group_by in ("area_month", "month_area"):
            areas = sorted({self.d.area_name(self.wells.loc[a].area_id) for a in ids})
            months = sorted({(r["year"], MONTHS.index(r["month"])) for r in rows})
            grid = []
            for a in areas:
                row = {"area": a}
                for y, m in months:
                    row[MONTHS[m] + ("" if len({y for y, _ in months}) == 1 else f" {y}")] = sum(
                        1 for r in rows if r["area"] == a and r["year"] == y and MONTHS.index(r["month"]) == m)
                row["Total"] = sum(v for k, v in row.items() if k not in ("area",))
                grid.append(row)
            summ += "\nCounts by area × month:\n" + "\n".join(str(g) for g in grid)
            return result("spills", summ, grid, src[:80], "heatmap", rows_field="area", value="count")
        if group_by in ("well", "asset", "area", "month"):
            key = {"well": "asset_id", "asset": "asset_id", "area": "area", "month": "month"}[group_by]
            agg = {}
            for r in rows:
                a = agg.setdefault(r[key], {key: r[key], "spills": 0, "volume_bbl": 0.0})
                a["spills"] += 1
                a["volume_bbl"] = round(a["volume_bbl"] + (r["volume_bbl"] or 0), 1)
            grid = sorted(agg.values(), key=lambda x: -x["spills"])
            summ += "\n" + "\n".join(str(g) for g in grid[:40])
            return result("spills", summ, grid, src[:80], "bar_chart", x=key, y="spills")
        for r in rows[:60]:
            summ += (f"\n- {r['asset_id']} {r['date']} {r['inspection_id']}: {r['volume_bbl']} bbl ({r['spill_class']})"
                     + (f", corrected {r['corrected']} (AI estimate {r['ai_estimate_bbl']})" if r['corrected'] else "")
                     + (f"; DISPUTED in notes: {r['disputed_by_notes']}" if r['disputed_by_notes'] else ""))
        cols = ["asset_id", "date", "inspection_id", "volume_bbl", "spill_class", "lat", "lon", "corrected"]
        return result("spills", summ, rows, src[:120], "table", columns=cols, lat="lat", lon="lon")

    def repairs(self, area=None, asset_ids=None, well_type=None, period="this_year", start=None, end=None,
                maintenance_type: str | None = None, equipment_kind: str | None = None):
        ids = self.scope_wells(area, asset_ids, well_type)
        s, e, label = self.period(period, start, end)
        M = self.d.mnt
        X = M[M.asset_id.isin(ids) & (M.start >= s) & (M.start < e)]
        if maintenance_type:
            X = X[X.maintenance_type == maintenance_type]
        if equipment_kind:
            X = X[X.equipment_kind == equipment_kind]
        rows = [{"asset_id": r.asset_id, "maintenance_id": r.maintenance_id, "started": fmt_date(r.start),
                 "type": r.maintenance_type, "equipment_kind": r.equipment_kind, "issue": r.issue,
                 "cost_usd": r.cost_total, "still_open": bool(r.end > self.as_of)}
                for r in X.sort_values("start").itertuples()]
        per = X.groupby("asset_id").cost_total.agg(["sum", "count"])
        summ = f"Repairs started in {label} (a repair belongs to the period by its start date): {len(rows)} jobs, USD {int(X.cost_total.sum()):,}."
        for aid in ids:
            if aid in per.index:
                summ += f"\n- {aid}: USD {int(per.loc[aid, 'sum']):,} over {int(per.loc[aid, 'count'])} repairs"
            elif len(ids) <= 10:
                summ += f"\n- {aid}: no repairs in period"
        src = [self.src_mnt(r) for r in X.to_dict("records")][:80]
        if 1 < len(ids) <= 12:
            grid = [{"asset_id": a, "cost_usd": int(per.loc[a, "sum"]) if a in per.index else 0,
                     "repairs": int(per.loc[a, "count"]) if a in per.index else 0} for a in ids]
            return result("repairs", summ, grid, src, "bar_chart", x="asset_id", y="cost_usd", detail=rows[:50])
        return result("repairs", summ, rows, src, "table")

    def rca_candidates(self, area=None, asset_ids=None, well_type=None, equipment_kind: str | None = None):
        ids = self.scope_wells(area, asset_ids, well_type)
        s = self.as_of - pd.DateOffset(months=12)
        M = self.d.mnt
        X = M[M.asset_id.isin(ids) & (M.maintenance_type == "corrective") & (M.start > s) &
              (M.start <= self.as_of + timedelta(days=1))]
        if equipment_kind:
            X = X[X.equipment_kind == equipment_kind]
        rows, near, src, rules_used = [], [], [], {}
        for (aid, kind), g in X.groupby(["asset_id", "equipment_kind"]):
            thr, ts = self.rule("rca_corrective_count", asset_id=aid, equipment_kind=kind)
            rules_used[ts["label"]] = ts
            row = {"asset_id": aid, "well_type": self.wells.loc[aid].well_type, "equipment_kind": kind,
                   "corrective_repairs_12m": len(g), "threshold": int(thr), "rule": ts["label"],
                   "repairs": ", ".join(g.maintenance_id)}
            if len(g) >= thr:
                rows.append(row)
                src += [self.src_mnt(r) for r in g.to_dict("records")]
            elif len(g) == thr - 1:
                near.append(row)
        rows.sort(key=lambda r: r["asset_id"])
        summ = (f"Wells needing a root-cause analysis (corrective repairs on the same equipment kind in the 12 months "
                f"since {fmt_date(s)}): {len(rows)}.")
        for r in rows:
            summ += f"\n- {r['asset_id']} ({r['well_type']}) {r['equipment_kind']}: {r['corrective_repairs_12m']} repairs ≥ {r['threshold']} per {r['rule']} [{r['repairs']}]"
        if near:
            summ += "\nOne below threshold: " + "; ".join(
                f"{r['asset_id']} ({r['well_type']}) {r['equipment_kind']} {r['corrective_repairs_12m']}/{r['threshold']} per {r['rule']}" for r in near[:15])
        for lab, ts in rules_used.items():
            src.append({k: v for k, v in ts.items() if k in ("kind", "doc", "section", "quote", "id", "author", "text")})
        return result("rca_candidates", summ, rows, src, "table")

    # ------------------------------------------------------------------ compliance
    def compliance_audit(self, asset_id=None, area=None, period="last_12_months", start=None, end=None,
                         protocol: str | None = None, status: str | None = None):
        ids = self.scope_wells(area, [asset_id] if asset_id else None)
        s, e, label = self.period(period, start, end)
        now = self.as_of + timedelta(days=1)
        R, REP = self.d.reg, self.d.reports
        rows, src = [], []

        def add(aid, proto, st, detail, deadline=None, evidence=None, spill=None):
            rows.append({"asset_id": aid, "protocol": proto, "status": st, "detail": detail,
                         "deadline": fmt_date(deadline) if deadline is not None else None,
                         "spill_inspection": spill, "evidence": ", ".join(evidence or [])})

        sp = self.I[self.I.asset_id.isin(ids) & self.I.real_spill & (self.I.t >= s) & (self.I.t < e)]
        h24 = self.rule("sr01_report_hours")[0]
        h2 = self.rule("sr01_major_report_hours")[0]
        h4 = self.rule("sr02_containment_hours")[0]
        d60 = self.rule("sr03_verification_days")[0]
        for r in sp.to_dict("records"):
            iid, aid, t, cls, vol = r["inspection_id"], r["asset_id"], r["t"], r["spill_class"], r["spill_est_volume_bbl"]
            tag = f"{fmt_date(t)} spill {vol} bbl ({cls})" + (f", corrected {r['corrected_by']} from AI estimate {r['orig_spill_est_volume_bbl']}" if r["corrected_by"] else "")
            src.append(self.src_ins(r))
            ev = R[R.related_inspection_id == iid]
            src += [self.src_reg(x) for x in ev.to_dict("records")]
            mnts = self.d.mnt[self.d.mnt.triggered_by_inspection_id == iid]
            rep = REP[REP.maintenance_id.isin(mnts.maintenance_id)]
            for m in mnts.to_dict("records"):
                src.append(self.src_mnt(m))
            for x in rep.itertuples():
                src.append(self.src_report(x.maintenance_id))
            # SR-01
            if cls in ("reportable", "major"):
                limit = h2 if cls == "major" else h24
                filed = ev[ev.event_type == "spill_report_filed"]
                if len(filed):
                    f = filed.iloc[0]
                    hrs = f.hours_to_report
                    add(aid, "SR-01", "breach" if hrs > limit else "met",
                        f"{tag}: written notice after {hrs:g} h (limit {limit:g} h)", t + timedelta(hours=limit),
                        [f.event_id, iid], iid)
                else:
                    due = t + timedelta(hours=limit)
                    due_s = f"{due.day} {due.strftime('%b %Y %H:%M')}"
                    add(aid, "SR-01", "breach" if due < now else "pending",
                        f"{tag}: reportable, but NO written notice on record (due {due_s} UTC)"
                        + (" — overdue" if due < now else ""), due, [iid], iid)
                # SR-03
                due = t + timedelta(days=d60)
                ver = ev[(ev.protocol_id == "SR-03")]
                closed = len(ver) and (ver.status == "closed").all() and (ver.event_type == "site_inspection").any()
                if closed:
                    add(aid, "SR-03", "met", f"{tag}: clean-up verified by agency", due, list(ver.event_id), iid)
                else:
                    add(aid, "SR-03", "breach" if due < now else "pending",
                        f"{tag}: agency verification of clean-up {'still open' if len(ver) else 'not on record'}; due within {d60:g} days, by {fmt_date(due)}",
                        due, list(ver.event_id) + [iid], iid)
            # SR-02 (containment only exists in report text)
            for x in rep.itertuples():
                if x.containment_hours is not None and not pd.isna(x.containment_hours):
                    add(aid, "SR-02", "breach" if x.containment_hours > h4 else "met",
                        f"{tag}: contained after about {x.containment_hours:g} h (limit {h4:g} h), per report {x.maintenance_id}",
                        t + timedelta(hours=h4), [x.maintenance_id, iid], iid)
                if x.stated_class and cls and x.stated_class != cls:
                    add(aid, "Report class", "superseded",
                        f"Report {x.maintenance_id} classed the spill as '{x.stated_class}' using the old estimate; "
                        f"with the effective volume {vol} bbl it is '{cls}', so the report's reporting conclusion no longer holds",
                        None, [x.maintenance_id], iid)
        # NOVs (RC-04) and open regulator items
        d30 = self.rule("rc04_nov_response_days")[0]
        RE = R[R.asset_id.isin(ids)]
        for n in RE[(RE.event_type == "notice_of_violation") & (RE.d >= s) & (RE.d < e)].to_dict("records"):
            due = n["d"] + timedelta(days=d30)
            resp = RE[(RE.event_type == "nov_response_filed") & (RE.d >= n["d"]) &
                      ((RE.related_inspection_id == n.get("related_inspection_id")) | (RE.asset_id == n["asset_id"]))]
            src.append(self.src_reg(n))
            if len(resp):
                add(n["asset_id"], "RC-04", "met", f"NOV {n['event_id']} answered ({resp.iloc[0].event_id})", due,
                    [n["event_id"], resp.iloc[0].event_id])
            else:
                add(n["asset_id"], "RC-04", "breach" if due < now else "pending",
                    f"Notice of violation {n['event_id']} ({n['detail']}; fine USD {n['fine_usd']:,.0f}, {n['status']}) "
                    f"needed a response within {d30:g} days, by {fmt_date(due)}; none recorded", due, [n["event_id"]])
        fines_open = RE[(RE.status == "open")].fine_usd.fillna(0).sum()
        # RCA (manual §10 or user rule) — pending action, not a breach
        rca = self.rca_candidates(asset_ids=ids)
        for rr in rca["rows"]:
            add(rr["asset_id"], "RCA (manual §10)", "pending",
                f"Root-cause analysis due on {rr['equipment_kind']}: {rr['corrective_repairs_12m']} corrective repairs in 12 months "
                f"[{rr['repairs']}] (threshold {rr['threshold']}, {rr['rule']})", None, rr["repairs"].split(", "))
        src += rca["sources"]
        if len(ids) <= 3:
            M = self.d.mnt
            for aid in ids:
                # RC-02 annual flowline integrity test, this calendar year
                y0 = pd.Timestamp(f"{self.as_of.year}-01-01", tz=UTC)
                test = M[(M.asset_id == aid) & M.issue.str.contains("integrity test", case=False, na=False) & (M.start >= y0)]
                if len(test):
                    add(aid, "RC-02", "met", f"Annual flowline integrity test done {fmt_date(test.start.iloc[0])} ({test.maintenance_id.iloc[0]})",
                        None, [test.maintenance_id.iloc[0]])
                else:
                    add(aid, "RC-02", "pending", f"No annual flowline integrity test recorded in {self.as_of.year} yet",
                        pd.Timestamp(f"{self.as_of.year}-12-31", tz=UTC))
                # planned work noted by people but not in the maintenance system (manual §4)
                for c in self.context_items(aid):
                    if re.search(r"not (yet )?in the maintenance system", c["text"], re.I):
                        add(aid, "Manual §4 shut-in record", "pending",
                            f"Planned shut-in noted in {c['id']} ({c['author']}) is not yet recorded in the maintenance system, "
                            "which the manual requires before work starts", None, [c["id"]])
                        src.append(c["src"])
        for k in ("sr01_report_hours", "sr02_containment_hours", "sr03_verification_days", "rc04_nov_response_days",
                  "spill_reportable_bbl"):
            src.append(self.doc_src(k))
        if protocol:
            rows = [r for r in rows if r["protocol"].upper().startswith(protocol.upper())]
        if status:
            rows = [r for r in rows if r["status"] == status]
        breaches = [r for r in rows if r["status"] == "breach"]
        summ = (f"Compliance audit, period {label}, today {fmt_date(self.as_of)}. {len(sp)} real spills in period. "
                f"{len(breaches)} breaches (deadline passed and requirement not met); 'pending' = deadline not passed or work under way. "
                f"Open fines on record: USD {fines_open:,.0f}.")
        for r in rows:
            summ += f"\n- [{r['status'].upper()}] {r['asset_id']} {r['protocol']}: {r['detail']}" + \
                    (f" (deadline {r['deadline']})" if r['deadline'] else "") + (f" [{r['evidence']}]" if r['evidence'] else "")
        return result("compliance_audit", summ, rows, [x for x in src if x], "table",
                      columns=["asset_id", "protocol", "status", "detail", "deadline", "evidence"])

    # ------------------------------------------------------------------ documents, notes, rules, sql
    def search_docs(self, query: str, asset_id: str | None = None, k: int = 5):
        aid = self.resolve_well(asset_id) if asset_id else None
        hits = self.d.search(query, k=k, asset_id=aid)
        summ = "\n\n".join(f"[{h['doc']} § {h['section']}]\n{h['text'][:1200]}" for h in hits) or "No matches."
        src = [{"kind": "doc" if h["kind"] != "report" else "report", "doc": h["doc"], "section": h["section"],
                "quote": h["text"][:300], "id": h["doc"].split("/")[-1].replace(".md", "") if h["kind"] == "report" else None}
               for h in hits]
        return result("search_docs", summ, [], src, None)

    def get_rules(self, well_type: str | None = None):
        rows = []
        for r in self.d.rules:
            if well_type and r.scope and r.scope.get("well_type") != well_type:
                continue
            rows.append({"rule": r.key, "scope": r.scope.get("well_type", "all wells"), "value": r.value,
                         "source": f"{r.doc} §{r.section}", "quote": r.quote[:200]})
        for a in self._user_rules:
            rows.append({"rule": a["rule_key"], "scope": ", ".join(f"{k}={a[k]}" for k in ("well_type", "area_id", "asset_id", "equipment_kind") if a.get(k)),
                         "value": a["new_value"], "source": f"{self.name(a['author_user_id'])} ({a['id']}, {a['created_at'][:10]})",
                         "quote": a["text"]})
        summ = "\n".join(f"- {r['rule']} [{r['scope']}] = {r['value']} ({r['source']})" for r in rows)
        return result("get_rules", summ, rows, [], "table")

    def well_notes(self, asset_id: str):
        aid = self.resolve_well(asset_id)
        N = self.d.notes[self.d.notes.asset_id == aid]
        rows = [{"id": n.note_id, "date": n.created_at[:10], "author": self.name(n.author_user_id), "type": n.note_type,
                 "inspection": n.linked_inspection_id, "text": n.text, "valid_from": n.valid_from,
                 "valid_to": n.valid_to, "status": "formal correction" if n.note_type == "correction" else "on record"}
                for n in N.itertuples()]
        for a in self.feedback:
            if a.get("asset_id") == aid:
                rows.append({"id": a["id"], "date": a["created_at"][:10], "author": self.name(a["author_user_id"]),
                             "type": a["kind"], "inspection": a.get("inspection_id"), "text": a["text"],
                             "valid_from": a.get("valid_from"), "valid_to": a.get("valid_to"), "status": a["status"]})
        summ = f"{len(rows)} notes/feedback for {aid}:\n" + "\n".join(
            f"- {r['id']} {r['date']} {r['author']} [{r['type']}, {r['status']}]{' on ' + r['inspection'] if r['inspection'] else ''}: {r['text']}"
            for r in rows)
        src = [self.src_note(n) for n in N.to_dict("records")] + [self.src_fb(a) for a in self.feedback if a.get("asset_id") == aid]
        return result("well_notes", summ, rows, src, "table")

    def sql_tables(self) -> dict[str, pd.DataFrame]:
        I = self.I.drop(columns=["evidence_images"], errors="ignore")
        W = self.d.wells.drop(columns=["equipment"]).assign(area_name=lambda x: x.area_id.map(self.d.area_name))
        M = self.d.mnt.drop(columns=["cost_usd"])
        REP = self.d.reports.drop(columns=["text", "compliance"], errors="ignore")
        return {"wells": W, "inspections": I, "repairs": M, "regulator_events": self.d.reg, "notes": self.d.notes,
                "reports": REP, "feedback": pd.DataFrame(self.feedback) if self.feedback else pd.DataFrame(columns=["id"])}

    SQL_SCHEMA = (
        "wells(asset_id, name, well_type, area_id, area_name, team_id, in_charge_user_id, lat, lon, installed_on, recorded_status); "
        "inspections(inspection_id, asset_id, t TIMESTAMP, inspector_user_id, method, ambient_temp_c, wellhead_temp_c [effective, after corrections], "
        "orig_wellhead_temp_c, delta_c, threshold_c, producing BOOL, spill_detected, real_spill BOOL [excludes corrected], spill_est_volume_bbl [effective], "
        "spill_class, spill_area_pct, notes, well_type, area_id, lat, lon); "
        "repairs(maintenance_id, asset_id, start TIMESTAMP, \"end\" TIMESTAMP, maintenance_type, equipment_kind, issue, action_taken, "
        "technician_user_id, contractor, downtime_hours, cost_total, cost_labor, cost_parts, triggered_by_inspection_id, report_file); "
        "regulator_events(event_id, asset_id, d TIMESTAMP, agency, event_type, protocol_id, related_inspection_id, hours_to_report, detail, fine_usd, status); "
        "notes(note_id, asset_id, created_at, author_user_id, note_type, inspection_id, linked_inspection_id, text, valid_from, valid_to); "
        "reports(maintenance_id, asset_id, containment_hours, stated_class, hse_notice_hours, report_written, in_progress, root_cause, action_required)")

    def run_sql(self, query: str):
        q = query.strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with)\b", q) or re.search(
                r"(?i)\b(insert|update|delete|drop|create|alter|attach|copy|pragma|install|load|export)\b", q):
            raise ValueError("Only read-only SELECT queries are allowed")
        con = duckdb.connect()
        for n, df in self.sql_tables().items():
            con.register(n, df)
        df = con.execute(f"SELECT * FROM ({q}) LIMIT 500").fetchdf()
        con.close()
        rows = df.to_dict("records")
        src = []
        for r in rows[:50]:
            for v in r.values():
                if isinstance(v, str) and re.fullmatch(r"(INS|MNT|REG|CTX)-\d{4}-\d{3,5}", v):
                    kind = {"INS": "inspection", "MNT": "repair", "REG": "regulator_event", "CTX": "note"}[v[:3]]
                    src.append({"kind": kind, "id": v, "asset_id": f"WELL-{v[4:8]}"})
        summ = f"{len(rows)} rows. " + df.head(40).to_string(index=False)[:4000]
        return result("run_sql", summ, rows, src, "table")
