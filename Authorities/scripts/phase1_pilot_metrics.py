#!/usr/bin/env python3
"""
Compute retention metrics for Phase 1 pilot outputs.

Compares incoming canonical XML editions against pilot-corrected outputs.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from lxml import etree

ENTITY_TAGS = {"persName", "placeName", "orgName", "date", "name"}


def count_entities(path: Path) -> int:
    tree = etree.parse(str(path))
    total = 0
    for el in tree.getroot().iter():
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el.tag).localname
        if local in ENTITY_TAGS:
            total += 1
    return total


def resolve_pilot_file(pilot_dir: Path, stem: str) -> Path | None:
    candidates = [
        pilot_dir / f"{stem}_corrected.xml",
        pilot_dir / f"{stem}_pilot.xml",
        pilot_dir / f"{stem}.xml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 pilot retention metrics")
    ap.add_argument("--incoming-dir", required=True)
    ap.add_argument("--pilot-dir", required=True)
    ap.add_argument("--editions", nargs="+", required=True, help="Edition stems without .xml")
    ap.add_argument("--output", help="Optional TSV output path")
    args = ap.parse_args()

    incoming_dir = Path(args.incoming_dir)
    pilot_dir = Path(args.pilot_dir)

    rows = []
    for stem in args.editions:
        orig = incoming_dir / f"{stem}.xml"
        pilot = resolve_pilot_file(pilot_dir, stem)

        if not orig.exists():
            rows.append(
                {
                    "edition": stem,
                    "status": "missing_original",
                    "original_entities": "",
                    "pilot_entities": "",
                    "removed": "",
                    "loss_pct": "",
                }
            )
            continue

        if pilot is None:
            rows.append(
                {
                    "edition": stem,
                    "status": "missing_pilot",
                    "original_entities": "",
                    "pilot_entities": "",
                    "removed": "",
                    "loss_pct": "",
                }
            )
            continue

        n_orig = count_entities(orig)
        n_pilot = count_entities(pilot)
        removed = n_orig - n_pilot
        loss_pct = (removed / n_orig * 100.0) if n_orig else 0.0

        rows.append(
            {
                "edition": stem,
                "status": "ok",
                "original_entities": n_orig,
                "pilot_entities": n_pilot,
                "removed": removed,
                "loss_pct": f"{loss_pct:.2f}",
            }
        )

    fieldnames = [
        "edition",
        "status",
        "original_entities",
        "pilot_entities",
        "removed",
        "loss_pct",
    ]

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(rows)

    print("edition\tstatus\toriginal_entities\tpilot_entities\tremoved\tloss_pct")
    for r in rows:
        print(
            f"{r['edition']}\t{r['status']}\t{r['original_entities']}\t"
            f"{r['pilot_entities']}\t{r['removed']}\t{r['loss_pct']}"
        )


if __name__ == "__main__":
    main()
