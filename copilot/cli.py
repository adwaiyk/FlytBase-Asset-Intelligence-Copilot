"""Command line: ask one question, show what was loaded, or run a scenario file
and write a results markdown (for write-up page 2).

  python -m copilot.cli info
  python -m copilot.cli ask --user U-201 "Is WELL-0001 producing oil right now?"
  python -m copilot.cli run eval/examples.json --out results.md [--reset]

Scenario file: a JSON list of turns
  {"user": "U-201", "text": "...", "new_chat": true, "sim_date": "2026-10-16", "reset": false}
"reset": true clears feedback + conversations before that turn ("run on the original data").
"""
from __future__ import annotations

import argparse
import json
import time

from .agent import Agent
from .data import load
from .engine import Engine
from .store import Store
from . import config


def boot(db=None):
    data = load()
    store = Store(db)
    store.seed_users(data.users, config.DEFAULT_PASSWORD)
    eng = Engine(data, store)
    return data, store, eng, Agent(eng)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    a = sub.add_parser("ask")
    a.add_argument("--user", default="U-201")
    a.add_argument("--sim-date", default=None)
    a.add_argument("text")
    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--out", default="results.md")
    r.add_argument("--reset", action="store_true")
    r.add_argument("--db", default=None)
    args = p.parse_args()

    if args.cmd == "info":
        data = load()
        print(json.dumps(data.load_report, indent=1, default=str))
        return
    data, store, eng, agent = boot(getattr(args, "db", None))
    if args.cmd == "ask":
        user = store.get_user(args.user)
        conv = store.conversation(user["user_id"], store.new_conversation(
            user["user_id"], args.sim_date or str(data.as_of.date())))
        out = agent.run(user, conv, args.text)
        print(out["content"])
        if out.get("visual"):
            print(f"\n[visual: {out['visual']['component']}, {len(out['visual']['rows'])} rows]")
        print("[evidence: " + ", ".join(str(s.get("id") or s.get("doc")) for s in out["sources"][:25]) + "]")
        return

    turns = json.load(open(args.file))
    if args.reset:
        store.reset_memory()
    convs: dict[str, dict] = {}
    lines = [f"# Results\n\nData: {', '.join(data.load_report['dirs'])} · today = {data.load_report['as_of']} · "
             f"model: {config.MODEL}\n"]
    for i, t in enumerate(turns, 1):
        if t.get("reset"):
            store.reset_memory()
            eng.refresh(force=True)
            convs.clear()
        user = store.get_user(t["user"])
        if t.get("new_chat") or user["user_id"] not in convs:
            cid = store.new_conversation(user["user_id"], t.get("sim_date") or str(data.as_of.date()))
            convs[user["user_id"]] = store.conversation(user["user_id"], cid)
        t0 = time.time()
        try:
            out = agent.run(user, convs[user["user_id"]], t["text"])
            ans, vis = out["content"], out.get("visual")
            ev = ", ".join(dict.fromkeys(str(s.get("id") or s.get("doc")) for s in out["sources"][:30]))
            writes = ", ".join(f"{w['id']} {w['kind']} ({w['status']})" for w in out["memory_writes"])
            tools = ", ".join(x["tool"] for x in out["trace"])
        except Exception as e:
            ans, vis, ev, writes, tools = f"ERROR: {e}", None, "", "", ""
        lines.append(f"## {t.get('id', i)}. {user['name']}: {t['text']}\n\n{ans}\n\n"
                     f"- Visual: {(vis['component'] + ' (' + str(len(vis['rows'])) + ' rows)') if vis else 'none'}\n"
                     f"- Tools: {tools}\n- Evidence: {ev}\n" + (f"- Memory: {writes}\n" if writes else "")
                     + (f"- Expected: {t['expected']}\n" if t.get("expected") else "")
                     + f"- Time: {time.time() - t0:.1f}s\n")
        print(f"[{i}/{len(turns)}] {t['text'][:70]} … {time.time() - t0:.1f}s")
        open(args.out, "w").write("\n".join(lines))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
