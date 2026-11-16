"""Aggregate steps 1-3 into numbers for the talk.
- talks/.../motif-experiment/results-summary.md : aggregate numbers only (committable)
- private/motif-experiment/results-detail.tsv     : per-event rows with motif titles (copyrighted, private)"""
import csv
import json
import statistics as st
from collections import Counter

from common import HERE, OUT, SAMPLE_TSV, STEP1_DIR, STEP3_DIR, LEVELS, LEVEL_NAMES, event_level

META = {m["id"]: m for m in json.loads((OUT / "motif_meta.json").read_text())}
CH = {"A": "Mythological", "B": "Animals", "C": "Tabu", "D": "Magic", "E": "The dead",
      "F": "Marvels", "G": "Ogres", "H": "Tests", "J": "Wise and foolish", "K": "Deceptions",
      "L": "Reversal of fortune", "M": "Ordaining the future", "N": "Chance and fate",
      "P": "Society", "Q": "Rewards and punishments", "R": "Captives and fugitives",
      "S": "Unnatural cruelty", "T": "Sex", "U": "Nature of life", "V": "Religion",
      "W": "Traits of character", "X": "Humor", "Z": "Miscellaneous"}

rows = {r["story_id"]: r for r in csv.DictReader(open(SAMPLE_TSV), delimiter="\t")}
ev_cov, picks, detail, fits, funcs, forced, proposals, branches = Counter(), [], [], [], Counter(), Counter(), [], Counter()
per_story = []
for sid, r in rows.items():
    f1, f3 = STEP1_DIR / f"{sid}.json", STEP3_DIR / f"{sid}.json"
    if not (f1.exists() and f3.exists()):
        continue
    d1, d3 = json.loads(f1.read_text()), json.loads(f3.read_text())
    p = d1["propp"]
    fits.append(p["fit"])
    for fn in p["functions"]:
        funcs[fn["name"].split(",")[0]] += 1
        forced[fn["strength"]] += 1
    evs = {e["n"]: e for e in d1["events"]}
    cov_s = Counter()
    for e in d3["events"]:
        cov = e.get("coverage", "none")
        ev_cov[cov] += 1
        cov_s[cov] += 1
        for pk in e["picks"]:
            m = META[pk["code"]]
            picks.append((pk["grade"], m))
        if cov != "exact" and e.get("proposed_motif"):
            proposals.append((sid, e["n"], e["proposed_motif"], e.get("proposed_branch", "")))
            branches[(e.get("proposed_branch") or "?")[:1]] += 1
        detail.append([sid, e["n"], evs.get(e["n"], {}).get("event", ""), cov,
                       " | ".join(f"{pk['code']} [{pk['grade']}] {META[pk['code']]['title']}" for pk in e["picks"]),
                       e.get("proposed_motif", "")])
    per_story.append((sid, len(d3["events"]), cov_s["exact"], cov_s["broader"], cov_s["none"], p["fit"],
                      d1.get("genre_free", ""), r["our_story_types"] or "-",
                      ", ".join(t.split(":", 1)[1] for t in r["our_tags"].split(";") if t and not t.startswith("folkloristics:")) or "-"))

with open(OUT / "results-detail.tsv", "w", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["story_id", "event_n", "event", "coverage", "picked_motifs", "proposed_motif"])
    w.writerows(detail)

N = sum(ev_cov.values())
pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "-"
uniq = {m["id"]: (g, m) for g, m in picks}
exact = [m for g, m in picks if g == "exact"]
L = []
L.append(f"# Motif & Propp pilot — {len(per_story)} stories, {N} events (model: Opus 5.5)\n")
L.append("## Motif coverage per event (Thompson TMI + Noy, best grade)")
for k in ("exact", "broader", "none"):
    L.append(f"- {k}: {ev_cov[k]} ({pct(ev_cov[k], N)})")
L.append(f"\n## Picked motifs: {len(picks)} picks, {len(uniq)} distinct")
for lab, sub in (("all picks", [m for g, m in picks]), ("exact picks", exact)):
    n = len(sub)
    L.append(f"- {lab}: {n}; Jewish-flagged (Neuman flag or Noy) {pct(sum(m['jewish'] for m in sub), n)}; "
             f"Noy-only (not in Thompson) {pct(sum(m['origin'] != 'tmi' for m in sub), n)}")
nc = [m["n_cultures"] for g, m in picks if m["origin"] == "tmi" and m["n_cultures"] is not None]
if nc:
    L.append(f"- Thompson picks: median number of attesting cultures {st.median(nc)}; "
             f"attested in ≤1 culture {pct(sum(x <= 1 for x in nc), len(nc))}")
L.append("\nThompson chapters of picks: " + ", ".join(
    f"{CH.get(c, c)} ({c}) {n}" for c, n in Counter(m["id"].replace("Noy ", "")[0] for g, m in picks).most_common()))
L.append("\nChapters where proposed new motifs would go: " + ", ".join(f"{c} {n}" for c, n in branches.most_common()))
L.append(f"\n## Propp\n- fit (1-5): distribution {dict(sorted(Counter(fits).items()))}, mean {st.mean(fits):.1f}")
L.append(f"- functions assigned: {sum(funcs.values())}, of which forced {pct(forced['forced'], sum(forced.values()))}")
L.append("- most frequent: " + ", ".join(f"{k} {v}" for k, v in funcs.most_common(10)))
L.append("\n## Per story\n| story | events | exact | broader | none | Propp fit | Opus genre | our story_type | our other tags |\n|---|---|---|---|---|---|---|---|---|")
for s in per_story:
    L.append("| " + " | ".join(map(str, s)) + " |")
L.append("\n## Proposed motifs for uncovered events (our drafts, not index text)")
for sid, n, t, b in proposals:
    L.append(f"- {sid} #{n}: {t}  _({b})_")
(HERE / "results-summary.md").write_text("\n".join(L) + "\n")
print("\n".join(L[:30]))

# ---- step 4: our tags vs motifs ----
S4 = OUT / "step4"
rel, cat, mot = Counter(), Counter(), Counter()
tagless_ch = Counter()
for f in sorted(S4.glob("*.json")):
    d = json.loads(f.read_text())
    seen = set()
    for t in d["tags"]:
        if t["tag"] in seen:
            continue
        seen.add(t["tag"])
        rel[t["relation"]] += 1
        cat[(t["tag"].split(":")[0], t["relation"] == "no_counterpart")] += 1
    for m in d["motifs"]:
        mot["no tag" if not m["tags"] else "tagged"] += 1
        if not m["tags"]:
            tagless_ch[CH.get(m["code"].replace("Noy ", "")[0], "?")] += 1
T = sum(rel.values())
L2 = [f"\n## Our tags vs the motifs (step 4, {T} story-tag pairs)"]
for k in ("same", "ours_broader", "motif_broader", "no_counterpart"):
    L2.append(f"- {k}: {rel[k]} ({pct(rel[k], T)})")
L2.append(f"- picked motifs with no counterpart among our tags: {mot['no tag']} of {sum(mot.values())} "
          f"(chapters: " + ", ".join(f"{k} {v}" for k, v in tagless_ch.most_common()) + ")")
L2.append("\n| our category | tags with no motif counterpart |\n|---|---|")
for c in sorted({c for c, _ in cat}, key=lambda c: -(cat[(c, True)] + cat[(c, False)])):
    n = cat[(c, True)] + cat[(c, False)]
    L2.append(f"| {c} | {cat[(c, True)]} / {n} ({pct(cat[(c, True)], n)}) |")
with open(HERE / "results-summary.md", "a") as fh:
    fh.write("\n".join(L2) + "\n")
print("\n".join(L2))

# ---- recall check
RD = OUT / "recall"
if RD.exists() and any(RD.glob("*.json")):
    rc = Counter()
    for f in RD.glob("*.json"):
        for e in json.loads(f.read_text())["events"]:
            rc[e.get("coverage", "none") if e.get("picks") else "none"] += 1
    R = sum(rc.values())
    after = {"exact": ev_cov["exact"] + rc["exact"], "broader": ev_cov["broader"] + rc["broader"], "none": rc["none"]}
    L3 = [f"\n## Recall check (wider shortlist: e5-large top-60 + e5-base top-40, minus the 25 already shown)",
          f"- of the {R} 'none' events: exact {rc['exact']}, broader {rc['broader']}, still none {rc['none']}",
          f"- coverage after the check: exact {after['exact']} ({pct(after['exact'], N)}), broader {after['broader']} "
          f"({pct(after['broader'], N)}), none {after['none']} ({pct(after['none'], N)})",
          "- the new finds are mostly very general index headings (e.g. 'Religious services', 'Rude retorts', 'Slanders'); "
          "the judge saw only the uncovered events, which may make it more lenient than in step 3"]
    with open(HERE / "results-summary.md", "a") as fh:
        fh.write("\n".join(L3) + "\n")
    print("\n".join(L3))


# ---- four-level regrade (after the recall check)
lv, how = Counter(), Counter()
for f in sorted(STEP3_DIR.glob("*.json")):
    d3 = json.loads(f.read_text())
    fr = OUT / "recall" / f.name
    rec = {e["n"]: e for e in json.loads(fr.read_text())["events"]} if fr.exists() else {}
    for e in d3["events"]:
        picks = e["picks"] or (rec.get(e["n"], {}).get("picks") or [])
        l, h = event_level(picks, e.get("proposed_branch", ""))
        lv[l] += 1
        how[h] += 1
L4 = [f"\n## Four-level coverage (after the recall check; heading = Thompson tens heading, e.g. V220 Saints)"]
for i, k in enumerate(LEVELS, 1):
    L4.append(f"{i}. {LEVEL_NAMES[k]}: {lv[k]} ({pct(lv[k], N)})")
L4.append(f"- heading-only events: {how['picked']} matched a heading among the candidates, {how['named']} got a heading only "
          "as the place where the judge would file its proposed new motif")
L4.append("- rule caveat: a few tens codes read like motifs (e.g. D1450 'Magic object furnishes treasure') and are counted as headings")
with open(HERE / "results-summary.md", "a") as fh:
    fh.write("\n".join(L4) + "\n")
print("\n".join(L4))
