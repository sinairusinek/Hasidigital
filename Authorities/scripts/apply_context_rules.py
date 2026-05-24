#!/usr/bin/env python3
"""
apply_context_rules.py — rules-driven per-mention pre-decisions for the Kima review
queue. Generalizes the Maggid-of-Mezritch heuristic so the same mechanism works for
any toponym whose right Kima place is signalled by a word in its context, and keeps
working for future editions (re-run after rebuilding the queue).

Rules live in editions/kimatch/context_rules.json, each:
  { "name_pattern": <regex over the toponym spelling>,
    "context_cue":  <substring that must appear in the mention's context>,
    "kima_id":      <Kima place id to assign>,
    "note":         <human note> }

For every queue item whose name matches a rule's name_pattern, each per-occurrence
mention whose context contains the cue is set to map_to:<kima_id>. Existing
decisions (incl. human ones and other mentions) are preserved.

Output JSON belongs on the Kimatch repo's `data` branch
(data/hasidigital/kima_decisions.json), which the app fetches at load.

Usage:
    python3 Authorities/scripts/apply_context_rules.py \
        --queue /path/to/Kimatch/data/hasidigital/kima_review.tsv \
        --rules editions/kimatch/context_rules.json \
        --decisions existing_kima_decisions.json \
        --out merged_kima_decisions.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

csv.field_size_limit(10**7)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_RULES = os.path.join(PROJECT, "editions", "kimatch", "context_rules.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queue", required=True, help="kima_review.tsv (with mentions column)")
    ap.add_argument("--rules", default=DEFAULT_RULES)
    ap.add_argument("--decisions", default="", help="existing decisions JSON to merge into")
    ap.add_argument("--out", required=True, help="output merged decisions JSON")
    args = ap.parse_args()

    rules = json.load(open(args.rules, encoding="utf-8"))
    for r in rules:
        r["_re"] = re.compile(r["name_pattern"])

    decisions: dict = {}
    if args.decisions and os.path.exists(args.decisions):
        decisions = json.load(open(args.decisions, encoding="utf-8"))

    with open(args.queue, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    n_items = n_mentions = 0
    for row in rows:
        name = row["name"]
        applicable = [r for r in rules if r["_re"].search(name)]
        if not applicable:
            continue
        mentions = json.loads(row.get("mentions", "[]") or "[]")
        hits: dict[str, dict] = {}
        for m in mentions:
            ctx = m.get("ctx") or ""
            for r in applicable:
                if r["context_cue"] in ctx:
                    hits[m["rid"]] = {"action": f"map_to:{r['kima_id']}",
                                      "kima_id": str(r["kima_id"])}
                    break
        if not hits:
            continue
        entry = dict(decisions.get(name, {}))
        merged = dict(entry.get("mentions", {}))
        for rid, d in hits.items():
            merged.setdefault(rid, d)   # never override an existing (human) decision
        entry["mentions"] = merged
        entry.setdefault("reviewer", "auto (context rule)")
        entry.pop("action", None)
        entry.pop("kima_id", None)
        decisions[name] = entry
        n_items += 1
        n_mentions += len(hits)
        print(f"  {name}: {len(hits)} mention(s) matched a context rule")

    json.dump(decisions, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n{n_mentions} mention(s) across {n_items} spelling(s) pre-decided "
          f"by {len(rules)} rule(s)")
    print(f"Merged decisions ({len(decisions)} entries) → {args.out}")


if __name__ == "__main__":
    main()
