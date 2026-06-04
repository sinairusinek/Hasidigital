"""
Find near-duplicate stories across all editions/online/*.xml using e5-base embeddings.

Strategy:
  - Embed each story with intfloat/multilingual-e5-base, chunked at ~1000 chars
    with 200 overlap (consistent with tag_embeddings.py).
  - Per-story vector = L2-normalized mean of its chunk vectors.
  - Pairwise cosine similarity over story_mean. A pair is a "duplicate candidate"
    if sim >= THRESHOLD and the two stories come from different editions.
  - Union-find over candidate pairs -> clusters.

Outputs:
  editions/story-duplicates.tsv   one row per duplicate pair (cross-edition)
  editions/story-duplicate-clusters.tsv  one row per cluster
  editions/.cache/story-dup-emb.npz  cached embeddings (keyed by story-id set)

Prints summary: total stories, # duplicate pairs at each threshold, # clusters,
# stories involved in any duplicate cluster.
"""
import os
import sys
import hashlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Authorities", "integration_tool"))

from tag_data import load_stories  # noqa: E402

CACHE_DIR = os.path.join(HERE, ".cache")
CACHE_PATH = os.path.join(CACHE_DIR, "story-dup-emb.npz")
PAIRS_TSV = os.path.join(HERE, "story-duplicates.tsv")
CLUSTERS_TSV = os.path.join(HERE, "story-duplicate-clusters.tsv")

MODEL_NAME = "intfloat/multilingual-e5-base"
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 200

# Thresholds we report on. Higher = stricter "duplicate".
THRESHOLDS = [0.999, 0.995, 0.99, 0.985, 0.98, 0.97, 0.96, 0.95]
MAIN_THRESHOLD = 0.99  # tight cutoff: below this, formulaic genre overlap starts
                       # creating spurious transitive clusters (a 25-story blob
                       # appears at 0.985). Above 0.99, all clusters are pairs
                       # of stories that share the opening sentence verbatim.

# The 9 editions named in Chen / Sagiv / Rusinek article.
NINE_EDITIONS = {
    "Adat-Zadikim", "Khal-Hasidim", "Khal-Kdoshim", "maase-zadikim",
    "Mifalot-HaZadikim", "PeerMikdoshim", "Shivhei-Habesht",
    "Shivhei-Harav", "Sipurei-Zadikim",
}


def _chunk(text):
    text = text or ""
    if len(text) <= CHUNK_CHARS:
        return [(0, text)]
    out, i, step = [], 0, CHUNK_CHARS - CHUNK_OVERLAP
    while i < len(text):
        out.append((i, text[i:i + CHUNK_CHARS]))
        i += step
    return out


def embed_all(stories):
    keys = [f"{s['edition']}::{s['story_id']}" for s in stories]
    key_hash = hashlib.sha1("\n".join(keys).encode("utf-8")).hexdigest()
    if os.path.exists(CACHE_PATH):
        d = np.load(CACHE_PATH, allow_pickle=True)
        if str(d.get("key")) == key_hash:
            print(f"[cache hit] {CACHE_PATH}")
            return list(d["keys"]), d["story_mean"]
    print(f"[cache miss] embedding {len(stories)} stories ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    passages, owner = [], []
    for i, s in enumerate(stories):
        for _, sub in _chunk(s["text"]):
            passages.append(f"passage: {sub}")
            owner.append(i)
    print(f"  {len(passages)} chunks total")
    chunks = model.encode(
        passages, batch_size=32, normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    ).astype("float32")
    owner = np.array(owner)
    dim = chunks.shape[1]
    story_mean = np.zeros((len(stories), dim), dtype="float32")
    for i in range(len(stories)):
        g = np.where(owner == i)[0]
        if not len(g):
            continue
        v = chunks[g].mean(axis=0)
        n = np.linalg.norm(v)
        story_mean[i] = v / n if n else v
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez(CACHE_PATH, key=key_hash, keys=np.array(keys), story_mean=story_mean)
    return keys, story_mean


class UF:
    def __init__(self, n):
        self.p = list(range(n))
    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def main():
    stories = load_stories("online")
    print(f"loaded {len(stories)} stories from {len({s['edition'] for s in stories})} editions")
    keys, vecs = embed_all(stories)
    n = len(stories)
    editions = [s["edition"] for s in stories]
    ids = [s["story_id"] for s in stories]
    text_chars = [len(s["text"]) for s in stories]

    # Pairwise similarity. 1376x1376 float32 is fine in memory.
    print("computing pairwise sim ...")
    sim = vecs @ vecs.T  # cosine since rows are L2-normalized

    # Mask diagonal + lower triangle by setting to -inf, then threshold.
    iu = np.triu_indices(n, k=1)
    sims = sim[iu]
    ia, ib = iu

    # Skip near-empty stories — they produce meaningless high sims with each other.
    MIN_CHARS = 100
    keep = (np.array([text_chars[i] for i in ia]) >= MIN_CHARS) & \
           (np.array([text_chars[i] for i in ib]) >= MIN_CHARS)

    # Cross-edition mask (we ignore intra-edition near-duplicates for "how many
    # of the 1376 are repeats across editions" — those are noise from boilerplate
    # or formula-stories within a single book and not what the user asked about).
    cross = np.array([editions[a] != editions[b] for a, b in zip(ia, ib)])

    print()
    print(f"{'thr':>6}  {'pairs':>7}  {'cross-edition pairs':>22}")
    for t in THRESHOLDS:
        mask = (sims >= t) & keep
        cmask = mask & cross
        print(f"{t:>6.3f}  {int(mask.sum()):>7d}  {int(cmask.sum()):>22d}")
    print()

    # Build clusters at MAIN_THRESHOLD using cross-edition edges only.
    mask = (sims >= MAIN_THRESHOLD) & keep & cross
    pairs = list(zip(ia[mask].tolist(), ib[mask].tolist(), sims[mask].tolist()))
    uf = UF(n)
    for a, b, _ in pairs:
        uf.union(a, b)

    from collections import defaultdict
    clusters = defaultdict(list)
    for i in range(n):
        clusters[uf.find(i)].append(i)
    nontrivial = [c for c in clusters.values() if len(c) >= 2 and
                  any(editions[c[0]] != editions[x] for x in c)]

    stories_in_dup_clusters = sum(len(c) for c in nontrivial)
    unique_groups = len(nontrivial)

    def report(label, idx_set):
        sub_clusters = [[i for i in c if i in idx_set] for c in nontrivial]
        sub_clusters = [c for c in sub_clusters if len(c) >= 2 and
                        any(editions[c[0]] != editions[x] for x in c)]
        n_sub = len(idx_set)
        in_dup = sum(len(c) for c in sub_clusters)
        extra = sum(len(c) - 1 for c in sub_clusters)
        print(f"--- {label} ---")
        print(f"  total stories                              {n_sub}")
        print(f"  duplicate clusters                         {len(sub_clusters)}")
        print(f"  stories appearing in a duplicate cluster   {in_dup}")
        print(f"  duplicate copies (extra beyond first)      {extra}")
        print(f"  unique-story count                         {n_sub - extra}")
        print()

    print(f"=== summary at threshold {MAIN_THRESHOLD} (cross-edition) ===")
    report("ALL 27 editions", set(range(n)))
    nine_idx = {i for i in range(n) if editions[i] in NINE_EDITIONS}
    report("9 article editions", nine_idx)

    # Write per-pair TSV (sorted by sim desc).
    pairs.sort(key=lambda r: -r[2])
    with open(PAIRS_TSV, "w") as f:
        f.write("sim\tedition_a\tstory_a\tedition_b\tstory_b\tchars_a\tchars_b\n")
        for a, b, s in pairs:
            f.write(f"{s:.4f}\t{editions[a]}\t{ids[a]}\t{editions[b]}\t{ids[b]}"
                    f"\t{text_chars[a]}\t{text_chars[b]}\n")
    print(f"wrote {PAIRS_TSV} ({len(pairs)} pairs)")

    # Write cluster TSV.
    with open(CLUSTERS_TSV, "w") as f:
        f.write("cluster_id\tsize\tn_editions\tmembers\n")
        for cid, c in enumerate(sorted(nontrivial, key=lambda c: -len(c))):
            eds = sorted({editions[i] for i in c})
            members = "; ".join(f"{editions[i]}/{ids[i]}" for i in c)
            f.write(f"{cid}\t{len(c)}\t{len(eds)}\t{members}\n")
    print(f"wrote {CLUSTERS_TSV} ({unique_groups} clusters)")


if __name__ == "__main__":
    main()
