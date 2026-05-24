#!/usr/bin/env python3
"""
spotcheck_grade_a.py — turn the 105 grade-A auto-links into a *prioritized* review
sheet, and (after review) convert decisions into durable feedback for re-runs.

The matcher grades A deterministically from Kima data, so the risky auto-links
recur on every re-run. Three verdicts, three durable channels:
  • keep         → confirmed_priors.tsv  (name + kima_id) → matcher --prior-resolutions
  • not_a_place  → reject_stoplist.tsv    (names) → build_kimatch_inventory.py drops the
                                          tokens so they never re-enter matching
  • wrong_match  → wrong_matches.tsv      (name + wrong kima_id) → NOT stoplisted (the
                                          spelling is a real place, just not this Kima
                                          pick); excluded from donations, pre-marked on
                                          the next sheet build so it isn't re-reviewed

Modes
-----
  build  (default)  read auto_confirmed.tsv + auto_reclassify/auto_linked.tsv →
                    write spotcheck_grade_a.tsv (risk-ranked; reviewer fills
                    `decision` = keep|not_a_place|wrong_match, + correct_kima_id)
  apply             read the reviewed spotcheck_grade_a.tsv → emit
                    confirmed_priors.tsv + reject_stoplist.tsv + wrong_matches.tsv

Run:
    python3 Authorities/scripts/spotcheck_grade_a.py            # build the sheet
    # …review spotcheck_grade_a.tsv, fill decision/correct_kima_id…
    python3 Authorities/scripts/spotcheck_grade_a.py apply      # emit feedback files
"""
from __future__ import annotations

import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(PROJECT, "editions", "kimatch")

AUTO = os.path.join(KDIR, "auto_confirmed.tsv")
AUTO_LINKED = os.path.join(KDIR, "auto_reclassify", "auto_linked.tsv")
SHEET = os.path.join(KDIR, "spotcheck_grade_a.tsv")
PRIORS = os.path.join(KDIR, "confirmed_priors.tsv")
STOPLIST = os.path.join(KDIR, "reject_stoplist.tsv")
WRONG_MATCHES = os.path.join(KDIR, "wrong_matches.tsv")   # real place, wrong Kima pick

KIMA_URL = "https://data.geo-kima.org/Places/Details/"

# Hebrew letters only (drop niqqud, gershayim, punctuation) for length scoring.
_HEB_LETTERS = re.compile(r"[א-ת]")

# Curated homographs: common nouns / person-names that also equal a real place name.
# A grade-A name_exact hit on one of these is high-risk (the text usually means the
# word, not the town). Extend as review surfaces more.
KNOWN_HOMOGRAPHS = {
    "גליל",    # "district/region" (also Galilee)
    "יהודה",   # personal name Judah (also Judea)
    "ירדן",    # also the Jordan river
    "חרן",     # biblical Haran — usually a scriptural allusion, not a lived place
    "מדינה",   # "country/state"
    "כפר",     # "village"
    "עיר",     # "city"
    "מבוא",    # "approach/entry"
    "באר",     # "well" (also Be'er…)
    "גן",      # "garden"
}


def heb_len(s: str) -> int:
    return len(_HEB_LETTERS.findall(s or ""))


# Regions/countries implausible for an 18th–19th c. Ashkenazi-Hasidic corpus. A
# grade-A exact-name hit landing in one of these is almost certainly a same-name
# collision with the wrong continent (Minas, Uruguay; Harer, Ethiopia; Menasha, Wis.).
IMPLAUSIBLE_REGIONS = [
    "uruguay", "ethiopia", "wis.", "wisconsin", "n.m.", "new mexico", "iraq",
    "iran", "brazil", "mexico", "argentina", "india", "indonesia", "u.s.",
    "(usa", "united states", "australia", "china", "japan", "philippines",
    "nigeria", "syria", "(tex", "texas", "ohio", "pa.)", "pennsylvania",
]


def implausible_region(kima_rom: str) -> str | None:
    low = (kima_rom or "").lower()
    for tok in IMPLAUSIBLE_REGIONS:
        if tok in low:
            return tok.strip("(.")
    return None


def score(row) -> tuple[str, str]:
    """Return (risk, reason). risk ∈ {HIGH, MED, LOW}."""
    name_heb = (row.get("name_heb") or "").strip()
    name = name_heb or (row.get("name_rom") or "").strip()
    method = (row.get("match_method") or "").lower()
    kima_rom = row.get("kima_name_rom") or ""

    bad = implausible_region(kima_rom)
    if bad:
        return "HIGH", f"implausible region for the corpus ({bad}) — likely wrong_match (real place, wrong Kima pick)"
    if name_heb and name_heb in KNOWN_HOMOGRAPHS:
        return "HIGH", "common-word / name homograph — text likely means the word, not the town"
    if "wikidata" in method:
        return "LOW", "matched by Wikidata QID (strong identity)"
    # Short *Hebrew* spelling is the homograph risk; romanized-only authority names
    # matched to the same Kima romanized name are generally safe.
    if name_heb and heb_len(name_heb) <= 4:
        return "HIGH", f"very short Hebrew spelling ({heb_len(name_heb)} letters) — homograph / wrong-town risk"
    if not name_heb and "name_exact" in method:
        return "LOW", "romanized authority name = Kima romanized name (strong)"
    if "name_exact" in method:
        return "MED", "exact-name match on a single Kima place — confirm it's the right same-name place"
    return "MED", "review the pick"


RISK_RANK = {"HIGH": 0, "MED": 1, "LOW": 2}

SHEET_FIELDS = ["rank", "risk", "tier", "reason", "name_heb", "name_rom", "occurrences",
                "match_method", "confidence", "kima_id", "kima_name_rom", "kima_url",
                # reviewer fills:
                "decision", "correct_kima_id", "notes"]


def _load_tier(path, tier, method_default):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        r.setdefault("match_method", method_default)
        if not r.get("match_method"):
            r["match_method"] = method_default
        r["_tier"] = tier
    return rows


def build():
    # grade-A auto-links + confident-fuzzy auto-links both need the same glance.
    rows = (_load_tier(AUTO, "grade_a", "name_exact")
            + _load_tier(AUTO_LINKED, "fuzzy_autolink", "fuzzy"))

    # Durable pre-marking: rows already judged wrong_match on a prior run stay marked
    # so they aren't re-reviewed (the spelling is still matched fresh each run).
    known_wrong = set()
    if os.path.exists(WRONG_MATCHES):
        with open(WRONG_MATCHES, encoding="utf-8") as f:
            known_wrong = {(r.get("name", ""), r.get("kima_id", ""))
                           for r in csv.DictReader(f, delimiter="\t")}

    scored = []
    for r in rows:
        risk, reason = score(r)
        scored.append((risk, reason, r))
    # sort: risk first, then by occurrence (impact) within risk
    scored.sort(key=lambda t: (RISK_RANK[t[0]], -int(t[2].get("occurrences") or 0)))

    with open(SHEET, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_FIELDS, delimiter="\t")
        w.writeheader()
        for i, (risk, reason, r) in enumerate(scored, 1):
            kid = (r.get("kima_id") or "").strip()
            prefilled = "wrong_match" if (r.get("name_heb", ""), kid) in known_wrong else ""
            w.writerow({
                "rank": i, "risk": risk, "tier": r.get("_tier", ""), "reason": reason,
                "name_heb": r.get("name_heb", ""), "name_rom": r.get("name_rom", ""),
                "occurrences": r.get("occurrences", ""),
                "match_method": r.get("match_method", ""),
                "confidence": r.get("confidence", ""),
                "kima_id": kid, "kima_name_rom": r.get("kima_name_rom", ""),
                "kima_url": (KIMA_URL + kid) if kid else "",
                "decision": prefilled, "correct_kima_id": "", "notes": "",
            })

    n_high = sum(1 for s, _, _ in scored if s == "HIGH")
    n_med = sum(1 for s, _, _ in scored if s == "MED")
    n_low = sum(1 for s, _, _ in scored if s == "LOW")
    print(f"Spot-check sheet: {len(scored)} grade-A rows "
          f"(HIGH {n_high}, MED {n_med}, LOW {n_low})")
    print(f"  → {SHEET}")
    print(f"\nReview the HIGH rows first ({n_high} rows). For each, set decision =")
    print(f"  keep         — link is correct  (set correct_kima_id if keeping a wrong pick)")
    print(f"  not_a_place  — the spelling is not a place at all → reject_stoplist (dropped)")
    print(f"  wrong_match  — it IS a place but not this Kima pick → stays matchable, logged")
    print(f"Then: python3 {os.path.relpath(__file__, PROJECT)} apply")


def apply():
    if not os.path.exists(SHEET):
        sys.exit(f"No reviewed sheet at {SHEET} — run `build` first.")
    with open(SHEET, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    # Three verdicts (see header): keep / not_a_place / wrong_match.
    # "reject" is accepted as a backward-compat alias for not_a_place.
    keeps, not_places, wrong_matches, undecided = [], [], [], 0
    for r in rows:
        dec = (r.get("decision") or "").strip().lower()
        name = (r.get("name_heb") or "").strip()
        if not name:
            undecided += 1
            continue
        if dec == "keep":
            kid = (r.get("correct_kima_id") or "").strip() or (r.get("kima_id") or "").strip()
            if kid:
                keeps.append((name, kid))
        elif dec in ("not_a_place", "reject"):
            not_places.append(name)
        elif dec == "wrong_match":
            # the spelling IS a place, just not this Kima pick — keep it matchable
            wrong_matches.append((name, (r.get("kima_id") or "").strip()))
        else:
            undecided += 1

    with open(PRIORS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "kima_id"], delimiter="\t")
        w.writeheader()
        for name, kid in keeps:
            w.writerow({"name": name, "kima_id": kid})

    # not_a_place → reject_stoplist (dropped from matcher input). Merge + dedup.
    existing = []
    if os.path.exists(STOPLIST):
        with open(STOPLIST, encoding="utf-8") as f:
            existing = [r["name"] for r in csv.DictReader(f, delimiter="\t") if r.get("name")]
    merged = list(dict.fromkeys(existing + not_places))
    with open(STOPLIST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name"], delimiter="\t")
        w.writeheader()
        for name in merged:
            w.writerow({"name": name})

    # wrong_match → wrong_matches log (NOT stoplisted; excluded from donations,
    # and pre-marked on the next sheet build so it isn't re-reviewed).
    wexisting = {}
    if os.path.exists(WRONG_MATCHES):
        with open(WRONG_MATCHES, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("name"):
                    wexisting[(r["name"], r.get("kima_id", ""))] = True
    for nm, kid in wrong_matches:
        wexisting[(nm, kid)] = True
    with open(WRONG_MATCHES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "kima_id"], delimiter="\t")
        w.writeheader()
        for (nm, kid) in wexisting:
            w.writerow({"name": nm, "kima_id": kid})

    print(f"Decisions: {len(keeps)} keep, {len(not_places)} not_a_place, "
          f"{len(wrong_matches)} wrong_match, {undecided} undecided")
    print(f"  confirmed_priors.tsv → feed to matcher: "
          f"`kimatch match -c jobs/hasidigital.json ... --prior-resolutions {PRIORS}`")
    print(f"  reject_stoplist.tsv  → used automatically by build_kimatch_inventory.py")
    if undecided:
        print(f"\n⚠ {undecided} rows still undecided — they keep their grade-A pick.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "build":
        build()
    elif mode == "apply":
        apply()
    else:
        sys.exit("usage: spotcheck_grade_a.py [build|apply]")
