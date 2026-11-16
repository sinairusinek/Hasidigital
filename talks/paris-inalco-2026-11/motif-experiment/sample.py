"""Draw the pilot sample: 20 core stories, stratified by edition, 600-4000 chars,
not part of any cross-edition duplicate pair. Fixed seed."""
import csv
import random
from collections import defaultdict

from common import REPO, SAMPLE_TSV
from tag_data import load_stories

QUOTA = {"Khal-Hasidim": 5, "Shivhei-Habesht": 6, "Mifalot-HaZadikim": 2, "maase-zadikim": 2,
         "Adat-Zadikim": 1, "Shivhei-Harav": 1, "PeerMikdoshim": 1, "Sipurei-Zadikim": 1,
         "Khal-Kdoshim": 1}
SEED = 20261201

dups = set()
with open(REPO / "editions" / "story-duplicates.tsv") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        dups.update([r["story_a"], r["story_b"]])

by_ed = defaultdict(list)
for s in load_stories("core"):
    if 600 <= len(s["text"]) <= 4000 and s["story_id"] not in dups:
        by_ed[s["edition"]].append(s)

rng = random.Random(SEED)
rows = []
for ed, k in QUOTA.items():
    pool = sorted(by_ed[ed], key=lambda s: s["story_id"])
    for s in rng.sample(pool, min(k, len(pool))):
        types = [t.split(":", 1)[1] for t in s["tags"] if t.startswith("folkloristics:")]
        rows.append({"story_id": s["story_id"], "edition": ed, "chars": len(s["text"]),
                     "our_story_types": ";".join(types), "our_tags": ";".join(s["tags"]),
                     "text": " ".join(s["text"].split())})

with open(SAMPLE_TSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
    w.writeheader()
    w.writerows(rows)
print(len(rows), "stories ->", SAMPLE_TSV)
for r in rows:
    print(r["story_id"], r["chars"], r["our_story_types"])
