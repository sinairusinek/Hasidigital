#!/usr/bin/env python3
"""
export_kima_donations.py — Stage 2 of the Kimatch workflow: curate a donation
file to hand to the Kima team (manually; the Kima API is read-only).

Donation types (per the kimatch skill):
  1. New variant       — a Hebrew/Yiddish spelling Kima doesn't yet have for a place
  2. External-ID gap   — a Wikidata QID we hold; emitted for human gap-fill review
  3. Attestation       — occurrences + editions + a sample context per variant

Confirmed sources (a row is "confirmed" when it has a chosen kima_id):
  - auto_confirmed.tsv                 grade-A auto-links (seed; light spot-check)
  - openrefine_review_queue.tsv        rows where decision ∈ {confirm, map_to} and
                                       chosen_kima_id (or kima_id) is set
  - kima_review_report.tsv             rows where action == "map_to:<kima_id>"

NOTHING is donated for unconfirmed/rejected rows. This produces the file; it does
NOT push to Kima.

Outputs (under editions/kimatch/donations/)
  donations_variants.tsv
  donations_external_ids_NEEDS_REVIEW.tsv
  donations.json            (grouped per Kima place)

Run:
    python3 Authorities/scripts/export_kima_donations.py
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(PROJECT, "editions", "kimatch")
DON = os.path.join(KDIR, "donations")

INPUT_TSV = os.path.join(KDIR, "kimatch_input.tsv")
AUTO = os.path.join(KDIR, "auto_confirmed.tsv")
AUTO_LINKED = os.path.join(KDIR, "auto_reclassify", "auto_linked.tsv")
PRIORS = os.path.join(KDIR, "confirmed_priors.tsv")   # spot-check keeps (gate)
OPENREFINE = os.path.join(KDIR, "openrefine_review_queue.tsv")
SL_REPORT = os.path.join(KDIR, "kima_review_report.tsv")

SOURCE = "Hasidic Tales digital edition (hasidic-stories.org)"


def _read(path, delim="\t"):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delim))


def _is_heb(s: str) -> bool:
    return bool(re.search(r"[֐-׿]", s or ""))


def collect_confirmed() -> list[dict]:
    """Return confirmed {kima_id, variant, wikidata, local_id, source_tag} records.

    Auto-links (grade-A + confident fuzzy) are only treated as confirmed once they
    pass the spot-check (confirmed_priors.tsv). Verification showed raw auto-links
    contain false positives (e.g. לויצק→Drahichyn), so they are NOT donated unchecked.
    """
    out = []

    if os.path.exists(PRIORS):
        # 1. spot-check-confirmed auto-links (the gate)
        for r in _read(PRIORS):
            kid = (r.get("kima_id") or "").strip()
            var = (r.get("name") or "").strip()
            if kid and var:
                out.append({"kima_id": kid, "variant": var, "wikidata": "",
                            "local_id": "", "via": "spotcheck"})
    else:
        print("⚠ No confirmed_priors.tsv yet — auto-links are UNVERIFIED. Run the "
              "spot-check (spotcheck_grade_a.py → apply) before donating.\n"
              "  Emitting raw auto-links as a provisional seed only.")
        for r in _read(AUTO) + _read(AUTO_LINKED):
            kid = (r.get("kima_id") or "").strip()
            var = (r.get("name_heb") or "").strip()
            if kid and var:
                out.append({"kima_id": kid, "variant": var,
                            "wikidata": (r.get("wikidata_qid") or "").strip(),
                            "local_id": r.get("local_id", ""), "via": "auto_UNVERIFIED"})

    # 2. OpenRefine confirmed decisions
    for r in _read(OPENREFINE):
        dec = (r.get("decision") or "").strip().lower()
        if dec not in ("confirm", "map_to", "accept", "yes"):
            continue
        kid = (r.get("chosen_kima_id") or r.get("kima_id") or "").strip()
        var = (r.get("name_heb") or "").strip()
        if kid and var:
            out.append({"kima_id": kid, "variant": var,
                        "wikidata": (r.get("wikidata_qid") or "").strip(),
                        "local_id": r.get("local_id", ""), "via": "openrefine"})

    # 3. Streamlit map_to:<id> decisions
    for r in _read(SL_REPORT):
        act = (r.get("action") or "").strip()
        m = re.match(r"map_to:(\d+)", act)
        if not m:
            continue
        var = (r.get("name") or "").strip()
        if var and _is_heb(var):
            out.append({"kima_id": m.group(1), "variant": var,
                        "wikidata": "", "local_id": "", "via": "streamlit"})
    return out


def load_attestations() -> dict[str, dict]:
    """Index attestations by BOTH local_id and name_heb (priors carry only the name)."""
    att = {}
    for r in _read(INPUT_TSV):
        rec = {
            "occurrences": r.get("occurrences", ""),
            "n_editions": r.get("n_editions", ""),
            "editions": r.get("editions", ""),
            "context": (r.get("context", "") or "").split(" ⟦SEP⟧ ")[0],
        }
        if r.get("local_id"):
            att[r["local_id"]] = rec
        if r.get("name_heb"):
            att.setdefault(r["name_heb"], rec)
    return att


def main():
    os.makedirs(DON, exist_ok=True)
    confirmed = collect_confirmed()
    att = load_attestations()

    # group per Kima place; dedup variants by (kima_id, variant)
    grouped: dict[str, dict] = defaultdict(lambda: {"variants": {}, "wikidata": set()})
    for c in confirmed:
        g = grouped[c["kima_id"]]
        a = att.get(c["local_id"]) or att.get(c["variant"], {})
        v = c["variant"]
        if v not in g["variants"]:
            g["variants"][v] = {
                "variant": v, "source": SOURCE, "via": c["via"],
                "occurrences": a.get("occurrences", ""),
                "n_editions": a.get("n_editions", ""),
                "editions": a.get("editions", ""),
                "context": a.get("context", ""),
            }
        if c["wikidata"]:
            g["wikidata"].add(c["wikidata"])

    # variants TSV
    var_path = os.path.join(DON, "donations_variants.tsv")
    vfields = ["kima_id", "variant", "source", "via", "occurrences", "n_editions",
               "editions", "context"]
    n_var = 0
    with open(var_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=vfields, delimiter="\t")
        w.writeheader()
        for kid, g in sorted(grouped.items(), key=lambda kv: kv[0]):
            for v in g["variants"].values():
                w.writerow({"kima_id": kid, **v})
                n_var += 1

    # external-id gap-fill (NEEDS_REVIEW — verify Kima isn't already holding it)
    ext_path = os.path.join(DON, "donations_external_ids_NEEDS_REVIEW.tsv")
    n_ext = 0
    with open(ext_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kima_id", "id_type", "id_value", "source"],
                           delimiter="\t")
        w.writeheader()
        for kid, g in sorted(grouped.items()):
            for qid in sorted(g["wikidata"]):
                w.writerow({"kima_id": kid, "id_type": "wikidata",
                            "id_value": qid, "source": SOURCE})
                n_ext += 1

    # grouped JSON
    json_path = os.path.join(DON, "donations.json")
    payload = {
        "source": SOURCE,
        "note": "Manual hand-off to the Kima team. Variants are new spellings; "
                "external_ids need gap-fill verification (do not overwrite existing).",
        "places": {
            kid: {
                "variants": list(g["variants"].values()),
                "wikidata": sorted(g["wikidata"]),
            } for kid, g in sorted(grouped.items())
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Confirmed records: {len(confirmed)} (auto_A + reviewer decisions)")
    print(f"Kima places touched: {len(grouped)}")
    print(f"Variant donations:   {n_var} → {var_path}")
    print(f"External-ID gap-fill: {n_ext} → {ext_path}")
    print(f"Grouped JSON:        {json_path}")
    if not confirmed:
        print("\n(No confirmed rows yet — re-run after review to populate donations.)")


if __name__ == "__main__":
    main()
