"""Adjudicate the calibration disagreements with an independent judge, so that
'disagrees with the RA' is not mistaken for 'wrong' (the RA is precise but low-recall).

Samples (fixed seed), at tagger confidence >= 2:
  EXTRA   tagger tag not in RA+audit          -> is it really present? (est. tagger precision)
  MISSED  RA+audit tag the tagger did not give -> is it really present? (est. tagger recall)
  AGREE   both have it                         -> sanity check of the reference
Judge: Opus 5.5 via claude -p, the tag audit's own presence prompt (tag_audit._presence_prompt),
one (story, tag) per call, blind to who proposed the tag.
Output: adjudication.tsv + an 'Adjudicated estimate' section appended to calibration-report.md."""
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "Authorities/integration_tool"))
import calibrate as cal  # noqa: E402
from tag_audit import _presence_prompt  # noqa: E402
from tagger import clean_text  # noqa: E402
from common import call_claude  # noqa: E402

OUT = HERE / "adjudication.tsv"
DEF = {r["tag"]: r["definition"] for r in csv.DictReader(open(HERE / "vocab.tsv"), delimiter="\t")}
N = {"extra": 200, "missed": 120, "agree": 60}


def sets():
    stories = cal.sample(100)
    by = {s["story_id"]: s for s in stories}
    ref = {(s["story_id"], t) for s in stories for t in set(s["tags"])}
    pred = set()
    for s in stories:
        r = json.loads((cal.CAL / f"{s['story_id']}.json").read_text())
        for st in r["stories"]:
            for t in st["tags"]:
                if int(t.get("confidence", 2)) >= 2:
                    pred.add((s["story_id"], t["tag"]))
    return by, pred, ref


def judge(job):
    kind, sid, tag, text = job
    d = DEF.get(tag) or tag.split(":")[1].replace("_", " ")
    try:
        v = call_claude(_presence_prompt(tag, d), text[:12000])
        return kind, sid, tag, bool(v.get("applies")), v.get("confidence", ""), v.get("reasoning", "")
    except Exception as e:
        return kind, sid, tag, None, "", f"ERROR {e}"


def main():
    by, pred, ref = sets()
    rng = random.Random(7)
    groups = {"extra": sorted(pred - ref), "missed": sorted(ref - pred), "agree": sorted(pred & ref)}
    done = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT), delimiter="\t"):
            done[(r["kind"], r["story_id"], r["tag"])] = r
    jobs = []
    for k, g in groups.items():
        for sid, tag in rng.sample(g, min(N[k], len(g))):
            if (k, sid, tag) not in done:
                jobs.append((k, sid, tag, clean_text(by[sid]["text"], sid)))
    print(len(jobs), "judgements to run", flush=True)
    new = not OUT.exists()
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if new:
            w.writerow(["kind", "story_id", "tag", "applies", "confidence", "reasoning"])
        with ThreadPoolExecutor(4) as ex:
            for i, row in enumerate(ex.map(judge, jobs)):
                w.writerow(row)
                f.flush()
                if i % 25 == 0:
                    print(i, flush=True)
    rows = list(csv.DictReader(open(OUT), delimiter="\t"))
    rate, cat_rate = {}, defaultdict(Counter)
    for k in N:
        rs = [r for r in rows if r["kind"] == k and r["applies"] in ("True", "False")]
        rate[k] = sum(r["applies"] == "True" for r in rs) / len(rs) if rs else 0
        for r in rs:
            cat_rate[(k, r["tag"].split(":")[0])][r["applies"]] += 1
    A, E, M = len(groups["agree"]), len(groups["extra"]), len(groups["missed"])
    tp = A * rate["agree"] + E * rate["extra"]
    truth = tp + M * rate["missed"]
    L = ["", "## Adjudicated estimate (independent Opus judge, tagger confidence >= 2)", "",
         f"- judge says present: AGREE {rate['agree']:.0%} (n={min(N['agree'], A)}), "
         f"EXTRA {rate['extra']:.0%} (n={min(N['extra'], E)}), MISSED {rate['missed']:.0%} (n={min(N['missed'], M)})",
         f"- estimated tagger precision {tp / (A + E):.2f}, estimated recall {tp / truth:.2f} "
         f"(population: {A} agree, {E} extra, {M} missed)",
         f"- for comparison, the RA+audit reference: estimated precision {rate['agree'] * A / A if A else 0:.2f} on agreed tags; "
         f"estimated recall of the reference {(A * rate['agree'] + M * rate['missed']) / truth:.2f}",
         "", "| category | EXTRA judged present | MISSED judged present |", "|---|---|---|"]
    for c in sorted({c for (_, c) in cat_rate}):
        e, m = cat_rate[("extra", c)], cat_rate[("missed", c)]
        fe = f"{e['True']}/{e['True'] + e['False']}" if e else "-"
        fm = f"{m['True']}/{m['True'] + m['False']}" if m else "-"
        L.append(f"| {c} | {fe} | {fm} |")
    with open(HERE / "calibration-report.md", "a") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
