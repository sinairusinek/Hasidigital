#!/usr/bin/env python3
"""
prefill_maggid_mezritch.py — auto-decide per-mention Kima links for Mezritch
spellings: any occurrence in the context of the *Maggid of Mezritch* maps to Kima
19737 (Mezhyrichi, Volhynia — the Maggid's town), not Międzyrzec Podlaski.

Reads the Hasidigital review queue (with per-occurrence `mentions`), tags each
Maggid-context mention, and MERGES the result into a decisions JSON (preserving
existing decisions and any non-Maggid mention decisions already made).

The merged JSON belongs on the Kimatch repo's `data` branch
(data/hasidigital/kima_decisions.json), which the app fetches at load.

Usage:
    python3 Authorities/scripts/prefill_maggid_mezritch.py \
        --queue /path/to/Kimatch/data/hasidigital/kima_review.tsv \
        --decisions existing_kima_decisions.json \
        --out merged_kima_decisions.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re

csv.field_size_limit(10**7)

MEZRITCH_RE = re.compile(r"מעזרי|מזערי|מעזער|מעזריט")  # spelling variants
MAGGID_CUE = "מגיד"                                    # "the Maggid (of Mezritch)"
KIMA_ID = "19737"                                       # Mezhyrichi (Volhynia)
REVIEWER = "auto (Maggid-of-Mezritch heuristic)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queue", required=True, help="kima_review.tsv (with mentions column)")
    ap.add_argument("--decisions", default="", help="existing decisions JSON to merge into")
    ap.add_argument("--out", required=True, help="output merged decisions JSON")
    args = ap.parse_args()

    decisions: dict = {}
    if args.decisions:
        try:
            with open(args.decisions, encoding="utf-8") as fh:
                decisions = json.load(fh)
        except FileNotFoundError:
            pass

    with open(args.queue, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    n_items = n_mentions = 0
    for r in rows:
        name = r["name"]
        if not MEZRITCH_RE.search(name):
            continue
        mentions = json.loads(r.get("mentions", "[]") or "[]")
        hits = {m["rid"]: {"action": f"map_to:{KIMA_ID}", "kima_id": KIMA_ID}
                for m in mentions if MAGGID_CUE in (m.get("ctx") or "")}
        if not hits:
            continue
        entry = dict(decisions.get(name, {}))
        merged = dict(entry.get("mentions", {}))
        merged.update(hits)               # add Maggid mentions; keep any existing ones
        entry["mentions"] = merged
        entry.setdefault("reviewer", REVIEWER)
        entry.pop("action", None)         # per-mention item, not flat-decided
        entry.pop("kima_id", None)
        decisions[name] = entry
        n_items += 1
        n_mentions += len(hits)
        print(f"  {name}: {len(hits)} Maggid mention(s) → Kima {KIMA_ID}")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, ensure_ascii=False, indent=2)
    print(f"\n{n_mentions} mention(s) across {n_items} spelling(s) → Kima {KIMA_ID}")
    print(f"Merged decisions ({len(decisions)} entries) → {args.out}")


if __name__ == "__main__":
    main()
