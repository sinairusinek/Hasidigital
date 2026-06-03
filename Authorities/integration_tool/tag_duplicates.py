"""Build a story near-duplicate index for the tag-audit propagation pass.

Uses the cached chunk embeddings at editions/tag-audit/.cache/story-chunks-e5base.npz.
For each pair of stories with cosine similarity ≥ threshold on max-pooled chunks,
emits one row with id_a, id_b, similarity, and short evidence snippets.

CLI:
    python3 tag_duplicates.py build [--threshold 0.93] [--sample 50]
    python3 tag_duplicates.py sample N   # print N random pairs for spot-check

Output: editions/tag-audit/story-duplicates.tsv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "editions" / "tag-audit" / ".cache"
CHUNKS_CACHE = CACHE_DIR / "story-chunks-e5base.npz"
OUT_PATH = PROJECT_ROOT / "editions" / "tag-audit" / "story-duplicates.tsv"
EDITIONS_DIR = PROJECT_ROOT / "editions" / "online"

TEI = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

ANNOTATED_EDITIONS = {
    "Adat-Zadikim", "Khal-Hasidim", "Khal-Kdoshim", "Mifalot-HaZadikim",
    "PeerMikdoshim", "Shivhei-Habesht", "Shivhei-Harav", "Sipurei-Zadikim",
    "maase-zadikim",
}


def _story_url(sid: str, edition: str) -> str:
    return f"https://www.hasidic-stories.org/Story/{edition}/{sid}"


def _load_story_texts() -> dict[str, dict]:
    """Return {story_id: {edition, head, opening}} for the 9 annotated editions."""
    out = {}
    for fn in sorted(os.listdir(EDITIONS_DIR)):
        if not fn.endswith(".xml"):
            continue
        ed = fn[:-4]
        if ed not in ANNOTATED_EDITIONS:
            continue
        try:
            tree = ET.parse(EDITIONS_DIR / fn)
        except ET.ParseError:
            continue
        for div in tree.iter(f"{{{TEI}}}div"):
            if div.get("type") != "story":
                continue
            sid = div.get(XML_ID, "")
            if not sid:
                continue
            text = " ".join("".join(div.itertext()).split())
            # Use first 240 chars after the story-head tag noise
            opening = text[:300]
            out[sid] = {"edition": ed, "opening": opening}
    return out


def build_index(threshold: float = 0.93) -> None:
    if not CHUNKS_CACHE.exists():
        sys.exit(f"Missing chunk-embedding cache: {CHUNKS_CACHE}\n"
                 f"Run tag_embeddings first to regenerate it.")

    data = np.load(CHUNKS_CACHE, allow_pickle=True)
    ids = list(data["ids"])
    mean = data["story_mean"]    # (n, 768) — already cached per-story mean of chunk embeddings
    print(f"Loaded {len(ids)} stories", file=sys.stderr)

    # Story-mean cosine: simple and well-calibrated for textual twins. Chunk-max is
    # too permissive (any shared formulaic passage triggers a match); the corpus
    # baseline mean similarity is ~0.92, so we need a high threshold.
    mean_norm = mean / np.clip(np.linalg.norm(mean, axis=1, keepdims=True), 1e-9, None)
    sims = mean_norm @ mean_norm.T

    n = len(ids)
    rows: list[dict] = []
    for a in range(n):
        # Vectorized scan over b > a.
        sl = sims[a, a + 1:]
        for off, score in enumerate(sl):
            if score >= threshold:
                rows.append({"a": ids[a], "b": ids[a + 1 + off], "sim": round(float(score), 4)})

    print(f"Pairs above {threshold}: {len(rows)}", file=sys.stderr)

    texts = _load_story_texts()
    rows.sort(key=lambda r: -r["sim"])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, delimiter="\t",
            fieldnames=["story_a", "edition_a", "url_a",
                        "story_b", "edition_b", "url_b",
                        "sim", "opening_a", "opening_b"],
        )
        w.writeheader()
        for r in rows:
            a = texts.get(r["a"], {})
            b = texts.get(r["b"], {})
            w.writerow({
                "story_a": r["a"], "edition_a": a.get("edition", ""),
                "url_a": _story_url(r["a"], a.get("edition", "")),
                "story_b": r["b"], "edition_b": b.get("edition", ""),
                "url_b": _story_url(r["b"], b.get("edition", "")),
                "sim": r["sim"],
                "opening_a": a.get("opening", "")[:200],
                "opening_b": b.get("opening", "")[:200],
            })
    print(f"Wrote {OUT_PATH} ({len(rows)} pairs)")


def print_sample(n: int = 50) -> None:
    if not OUT_PATH.exists():
        sys.exit(f"Run `tag_duplicates.py build` first; missing {OUT_PATH}")
    import random
    rows = list(csv.DictReader(open(OUT_PATH, encoding="utf-8"), delimiter="\t"))
    random.seed(0)
    sample = random.sample(rows, min(n, len(rows)))
    sample.sort(key=lambda r: -float(r["sim"]))
    for r in sample:
        print(f"sim={r['sim']}  {r['story_a']}  ↔  {r['story_b']}")
        print(f"   a: {r['opening_a'][:120]}…")
        print(f"   b: {r['opening_b'][:120]}…")
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Build the duplicate index")
    b.add_argument("--threshold", type=float, default=0.98,
                   help="Story-mean cosine threshold (default 0.98 — calibrated against "
                        "the 5 known KH ↔ PM/SHB twin pairs, all of which sit at 0.98+).")
    s = sub.add_parser("sample", help="Print a random sample for spot-check")
    s.add_argument("n", type=int, nargs="?", default=50)
    args = ap.parse_args()
    if args.cmd == "build":
        build_index(args.threshold)
    elif args.cmd == "sample":
        print_sample(args.n)


if __name__ == "__main__":
    main()
