#!/usr/bin/env python3
"""Bookkeeping for /agent-loop:run.

init    record the run start (session, base branch, plan-usage snapshot) in <dir>/run.json
report  print the markdown token/cost report, read from Claude Code's own transcripts
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
PRICES = Path(__file__).with_name("prices.json")
ROLES = ("planner", "executor", "reviewer")
RESULT_FILE = {"executor": "exec", "reviewer": "review"}
KINDS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def rates_for(model, prices):
    keys = [k for k in prices if model.startswith(k)]
    return prices[max(keys, key=len)] if keys else None


def tokens(usage):
    cc = usage.get("cache_creation") or {}
    w5, w1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:  # older transcripts carry only the total
        w5, w1 = usage.get("cache_creation_input_tokens", 0), 0
    return {
        "input": usage.get("input_tokens", 0),
        "cache_write_5m": w5 or 0,
        "cache_write_1h": w1 or 0,
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "output": usage.get("output_tokens", 0),
    }


def cost(tok, usage, rates):
    if rates is None:
        return None
    above = rates.get("above")
    # tiered models price each request by its whole prompt, cache reads and writes included
    if above and sum(tok.values()) - tok["output"] > above["prompt_tokens"]:
        rates = {**rates, **above}
    mult = rates.get("fast_multiplier", 1) if usage.get("speed") == "fast" else 1
    return sum(tok[k] * rates[k] for k in KINDS) * mult / 1e6


def read_call(path, prices, since=None):
    """Sum one transcript. Returns None when it holds nothing at or after `since`."""
    msgs, start, end = {}, None, None
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
            t = ts(d["timestamp"])
        except (ValueError, KeyError, TypeError):
            continue
        if since and t < since:
            continue
        start, end = start or t, t
        m = d.get("message") or {}
        if d.get("type") == "assistant" and m.get("usage") and m.get("model", "<").startswith("claude"):
            # one API response spans several lines, each repeating its usage: keep the last
            msgs[m.get("id") or d.get("uuid")] = m
    if start is None:
        return None
    call = {"start": start, "end": end, "model": "", "cost": 0.0, **dict.fromkeys(KINDS, 0)}
    for m in msgs.values():
        tok = tokens(m["usage"])
        c = cost(tok, m["usage"], rates_for(m["model"], prices))
        call["model"] = m["model"]
        call["cost"] = None if c is None or call["cost"] is None else call["cost"] + c
        for k in KINDS:
            call[k] += tok[k]
    return call


def snapshot():
    try:
        return json.loads((CONFIG / "agent-loop-statusline.json").read_text()).get("rate_limits")
    except (OSError, ValueError):
        return None


def init(a):
    f = Path(a.dir) / "run.json"
    run = json.loads(f.read_text()) if f.exists() else {"sessions": []}
    run["base"] = a.base
    run["sessions"].append({"id": a.session, "start": datetime.now(timezone.utc).isoformat()})
    run["rate_limits"] = snapshot()
    f.write_text(json.dumps(run, indent=2))


def collect(run, prices):
    calls = []
    for s in run["sessions"]:
        since = ts(s["start"])
        for main in (CONFIG / "projects").glob(f"*/{s['id']}.jsonl"):
            c = read_call(main, prices, since)
            if c:
                calls.append({**c, "role": "dispatcher"})
            for meta in (main.with_suffix("") / "subagents").glob("agent-*.meta.json"):
                role = json.loads(meta.read_text()).get("agentType", "").split(":")[-1]
                if role not in ROLES:
                    continue
                c = read_call(meta.with_name(meta.name.replace(".meta.json", ".jsonl")), prices)
                if c and c["start"] >= since:
                    calls.append({**c, "role": role})
    return sorted(calls, key=lambda c: c["start"])


def result(d, role, k):
    f = d / f"{RESULT_FILE.get(role)}-{k}.md"
    if not f.exists():
        return ""
    lines = f.read_text().splitlines() or [""]
    return lines[0].split(":")[-1].strip()


def usd(c):
    return "n/a" if c is None else f"${c:.2f}" if c >= 1 else f"${c:.3f}"


def cells(c):
    return [f"{c['input']:,}", f"{c['cache_write_5m'] + c['cache_write_1h']:,}", f"{c['cache_read']:,}", f"{c['output']:,}", usd(c["cost"])]


def total(calls):
    t = {"cost": 0.0, **dict.fromkeys(KINDS, 0)}
    for c in calls:
        for k in KINDS:
            t[k] += c[k]
        t["cost"] = None if c["cost"] is None or t["cost"] is None else t["cost"] + c["cost"]
    return t


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def plan_usage(before):
    after, parts = snapshot(), []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        b, a = (before or {}).get(key), (after or {}).get(key)
        if b and a and b.get("resets_at") == a.get("resets_at"):  # a reset mid-run voids the delta
            parts.append(f"{label} {a['used_percentage'] - b['used_percentage']:+.1f}%")
    return parts


def report(a):
    d = Path(a.dir)
    run = json.loads((d / "run.json").read_text())
    calls = collect(run, json.loads(PRICES.read_text())["models"])
    agents = [c for c in calls if c["role"] != "dispatcher"]

    out = [f"## Agent loop report: issue #{d.resolve().name}", "", f"**Outcome:** {a.outcome}", "", "### Timeline", ""]
    seen, rows = {}, []
    for i, c in enumerate(agents, 1):
        k = seen[c["role"]] = seen.get(c["role"], 0) + 1
        secs = int((c["end"] - c["start"]).total_seconds())
        rows.append([str(i), f"{c['role']} {k}", c["model"], f"{c['start']:%H:%M:%S}", f"{secs // 60}m {secs % 60:02d}s", result(d, c["role"], k)] + cells(c))
    out += table(["#", "Agent", "Model", "Start (UTC)", "Duration", "Result", "Input", "Cache write", "Cache read", "Output", "Cost"], rows)

    out += ["", "### Per role", ""]
    rows = []
    for role in ROLES + ("dispatcher",):
        mine = [c for c in calls if c["role"] == role]
        if mine:
            rows.append([role, str(len(mine)) if role in ROLES else "-"] + cells(total(mine)))
    grand = total(calls)
    rows.append(["**Total**", str(len(agents))] + cells(grand))
    out += table(["Role", "Calls", "Input", "Cache write", "Cache read", "Output", "Cost"], rows)

    usage = plan_usage(run.get("rate_limits"))
    if usage:
        out += ["", f"Plan usage: {', '.join(usage)} (account-wide, approximate)."]
    out += ["", "Cost is an API-equivalent estimate at list prices. The dispatcher's calls that post this report are not counted.", ""]
    out.append(f"Total: {usd(grand['cost'])} API-equivalent, {sum(grand[k] for k in KINDS):,} tokens, {len(agents)} agent calls, outcome {a.outcome}")
    print("\n".join(out))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--dir", required=True)
    i.add_argument("--session", required=True)
    i.add_argument("--base", required=True)
    i.set_defaults(fn=init)
    r = sub.add_parser("report")
    r.add_argument("--dir", required=True)
    r.add_argument("--outcome", required=True)
    r.set_defaults(fn=report)
    args = p.parse_args()
    args.fn(args)
