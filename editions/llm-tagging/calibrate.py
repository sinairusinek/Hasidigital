"""Calibrate the tagger on curated stories before tagging uncurated editions.

Sample: N curated stories (9 RA-curated editions), stratified by edition, twins excluded,
fixed seed. Each is tagged blind (the tagger never sees the existing tags).
Compared against two references:
  RA     = the research assistant's original tags (XML minus every LLM-audit insert)
  ALL    = current corpus tags (RA + audit-confirmed LLM inserts)
Reported: micro precision/recall/F1 per reference, per category, per confidence level,
unit-kind distribution (curated stories should come out as stories), quote-check failures.
Usage: python calibrate.py [N]   (resumable; results in calib/)"""
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
sys.path.insert(0, str(REPO / "editions/tag-audit/scripts"))
from tagger import tag_unit, clean_text, VOCAB_SET  # noqa: E402
from tag_data import load_stories  # noqa: E402

CAL = HERE / "calib"
CAL.mkdir(exist_ok=True)
SEED = 1201


def ra_pairs():
    import remove_verdicts as rv
    return rv.xml_pairs() - rv.load_pairs(rv.OLD_VERDICTS) - rv.load_pairs(rv.PATCHED_ADDS)


def sample(n):
    dups = set()
    for r in csv.DictReader(open(REPO / "editions/story-duplicates.tsv"), delimiter="\t"):
        dups.add(r["story_b"])                     # keep one of each twin pair
    st = [s for s in load_stories("core") if s["story_id"] not in dups and len(s["text"]) < 12000]
    by = defaultdict(list)
    for s in st:
        by[s["edition"]].append(s)
    rng = random.Random(SEED)
    tot = sum(len(v) for v in by.values())
    out = []
    for ed, v in sorted(by.items()):
        k = max(3, round(n * len(v) / tot))
        out += rng.sample(sorted(v, key=lambda s: s["story_id"]), min(k, len(v)))
    return out[:n] if len(out) > n else out


def run_one(s):
    f = CAL / f"{s['story_id']}.json"
    if f.exists():
        return s["story_id"], "cached"
    unit = {"id": s["story_id"], "edition": s["edition"], "label": "story", "text": clean_text(s["text"], s["story_id"])}
    res = tag_unit(unit)
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return s["story_id"], f"{res['unit']['kind']}, {sum(len(x['tags']) for x in res['stories'])} tags"


def score(stories):
    ra = ra_pairs()
    ALL = {(s["story_id"], t) for s in stories for t in s["tags"]}
    ids = {s["story_id"] for s in stories}
    RA = {p for p in ra if p[0] in ids}
    pred, conf, kinds, qfail, nq, missing = {}, {}, Counter(), 0, 0, Counter()
    for s in stories:
        f = CAL / f"{s['story_id']}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        kinds[r["unit"]["kind"]] += 1
        qfail += r["check"]["quotes_not_found"]
        nq += r["check"]["quotes"]
        for st in r["stories"]:
            for t in st["tags"]:
                p = (s["story_id"], t["tag"])
                conf[p] = max(conf.get(p, 0), int(t.get("confidence", 2)))
                pred[p] = 1
            for m in st.get("missing_concepts", []):
                missing[m.lower()] += 1
    done = {p[0] for p in pred} | {s["story_id"] for s in stories if (CAL / f"{s['story_id']}.json").exists()}
    P = set(pred)
    lines = [f"# Tagger calibration on {len(done)} curated stories", "",
             f"unit kinds: {dict(kinds)}", f"quotes not found verbatim: {qfail}/{nq}", ""]

    def prf(Pset, Ref, label):
        Ref = {p for p in Ref if p[0] in done}
        tp = len(Pset & Ref)
        p = tp / len(Pset) if Pset else 0
        r = tp / len(Ref) if Ref else 0
        f1 = 2 * p * r / (p + r) if p + r else 0
        return f"| {label} | {len(Pset)} | {len(Ref)} | {tp} | {p:.2f} | {r:.2f} | {f1:.2f} |"
    lines += ["| set vs reference | predicted | reference | agree | precision | recall | F1 |", "|---|---|---|---|---|---|---|"]
    for c in (1, 2, 3):
        Pc = {p for p in P if conf[p] >= c}
        lines.append(prf(Pc, RA, f"conf>={c} vs RA"))
        lines.append(prf(Pc, ALL, f"conf>={c} vs RA+audit"))
    lines += ["", "| category | predicted | RA+audit | agree | precision | recall |", "|---|---|---|---|---|---|"]
    cats = sorted({t.split(":")[0] for t in VOCAB_SET})
    for c in cats:
        Pc = {p for p in P if p[1].startswith(c + ":") and conf[p] >= 2}
        Rc = {p for p in ALL if p[1].startswith(c + ":") and p[0] in done}
        tp = len(Pc & Rc)
        lines.append(f"| {c} | {len(Pc)} | {len(Rc)} | {tp} | {tp / len(Pc) if Pc else 0:.2f} | {tp / len(Rc) if Rc else 0:.2f} |")
    lines += ["", "Most frequent concepts the tagger found missing from the vocabulary:"]
    lines += [f"- {m} ({n})" for m, n in missing.most_common(25)]
    (HERE / "calibration-report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
    st = sample(n)
    if "--score" not in sys.argv:
        with ThreadPoolExecutor(3) as ex:
            for sid, msg in ex.map(run_one, st):
                print(sid, msg, flush=True)
    score(st)
