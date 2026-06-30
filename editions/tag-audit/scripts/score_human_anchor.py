#!/usr/bin/env python3
"""Score Opus (and Sonnet) against the human-adjudication anchor.

Run AFTER an expert fills the `human_applies (yes/no)` column of
editions/tag-audit/human-adjudication-anchor.tsv. Joins it to the key and
reports each model's accuracy against the human gold, plus the confusion
breakdown — i.e. whether Opus errs by over- or under-tagging.

Usage:  python3 score_human_anchor.py
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"
ANCHOR = AUDIT / "human-adjudication-anchor.tsv"
KEY = AUDIT / "human-adjudication-key.tsv"


def _yn(v):
    v = (v or "").strip().lower()
    if v in ("yes", "y", "true", "1", "applies"):
        return True
    if v in ("no", "n", "false", "0"):
        return False
    return None


def main():
    key = {r["case_id"]: r for r in csv.DictReader(open(KEY), delimiter="\t")}
    human = {}
    for r in csv.DictReader(open(ANCHOR), delimiter="\t"):
        h = _yn(r.get("human_applies (yes/no)"))
        if h is not None:
            human[r["case_id"]] = h

    n = len(human)
    if not n:
        print("No human verdicts filled in yet. Fill the "
              "'human_applies (yes/no)' column of human-adjudication-anchor.tsv.")
        return

    def score(model_col, cast):
        agree = 0
        # confusion vs human gold
        tp = tn = fp = fn = 0
        for cid, h in human.items():
            m = cast(key[cid][model_col])
            if m is None:
                continue
            agree += (m == h)
            if m and h: tp += 1
            elif (not m) and (not h): tn += 1
            elif m and not h: fp += 1
            else: fn += 1
        return agree, tp, tn, fp, fn

    print(f"Human verdicts: {n}/100 filled\n")
    for label, col, cast in [
        ("Opus", "opus_applies", lambda v: v == "True"),
        ("Sonnet", "sonnet_applies", lambda v: v == "True" if v in ("True", "False") else None),
    ]:
        agree, tp, tn, fp, fn = score(col, cast)
        graded = tp + tn + fp + fn
        if not graded:
            print(f"{label}: no comparable verdicts")
            continue
        print(f"{label} vs human gold: accuracy {agree}/{graded} = {agree/graded*100:.0f}%")
        print(f"   over-tags (model yes, human no):  {fp}")
        print(f"   under-tags (model no, human yes): {fn}")
        print(f"   correct yes {tp} · correct no {tn}\n")


if __name__ == "__main__":
    main()
