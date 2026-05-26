"""
Embedding-based visualizations for the tag audit.

Produces two figures in editions/tag-audit/practice/:
  1. story-landscape.png      - t-SNE map of all 652 stories, colored by dominant
                                 top-level category (the thematic geography).
  2. practice-tag-similarity.png - clustered heatmap of cosine similarity between
                                 the practice tag centroids (reveals overlap / merge candidates).

Run: python3 tag_viz.py
"""
import os
import csv
import hashlib
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import tag_data
import tag_embeddings
import tag_lexicons
import tag_audit
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "editions", "tag-audit", "practice")
LLM_CACHE = os.path.join(PROJECT_DIR, "editions", "tag-audit", ".cache", "llm-presence.tsv")


def _verdicts_for(tag):
    """Return {story_id: applies(bool)} for a tag from the adjudication cache."""
    definition = tag_lexicons.definition(tag)
    phash = hashlib.md5(tag_audit._presence_prompt(tag, definition).encode()).hexdigest()[:8]
    out = {}
    if not os.path.exists(LLM_CACHE):
        return out
    for r in csv.DictReader(open(LLM_CACHE, encoding="utf-8"), delimiter="\t"):
        if r["tag"] == tag and r["prompt_hash"] == phash:
            out[r["story_id"]] = (r["applies"] == "True")  # opus-cli rows win if duplicated
    return out


def _tsne(mat):
    from sklearn.manifold import TSNE
    return TSNE(n_components=2, metric="cosine", init="pca",
               perplexity=30, random_state=42).fit_transform(mat)


def dominant_top(story):
    tops = [t.split(":")[0] for t in story["tags"]]
    if not tops:
        return "untagged"
    return Counter(tops).most_common(1)[0][0]


def story_landscape(stories, ids, mat, xy):
    doms = [dominant_top(s) for s in stories]
    cats = [c for c, _ in Counter(doms).most_common()]
    cmap = plt.get_cmap("tab20")
    color = {c: cmap(i % 20) for i, c in enumerate(cats)}
    plt.figure(figsize=(13, 10))
    for c in cats:
        idx = [i for i, d in enumerate(doms) if d == c]
        plt.scatter(xy[idx, 0], xy[idx, 1], s=14, color=color[c],
                    label=f"{c} ({len(idx)})", alpha=0.75, linewidths=0)
    plt.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8, frameon=False)
    plt.title("Hasidic-stories corpus — thematic map (t-SNE of story embeddings)\n"
              "652 stories, 9 editions; colour = dominant top-level category")
    plt.xticks([]); plt.yticks([]); plt.tight_layout()
    p = os.path.join(OUT, "story-landscape.png")
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    return p


def tag_similarity(stories, ids, mat, top="practice", min_n=3):
    id2i = {s: i for i, s in enumerate(ids)}
    tags = sorted({t for s in stories for t in s["tags"] if t.split(":")[0] == top})
    cents, labels = [], []
    for t in tags:
        idx = [id2i[s["story_id"]] for s in stories if t in s["tags"]]
        if len(idx) < min_n:
            continue
        c = tag_embeddings.centroid(mat, idx)
        cents.append(c); labels.append(f"{t.split(':')[-1]} ({len(idx)})")
    C = np.array(cents)
    S = C @ C.T  # cosine (centroids normalized)

    # order by hierarchical clustering for block structure
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    D = 1 - S; np.fill_diagonal(D, 0); D = (D + D.T) / 2
    order = leaves_list(linkage(squareform(D, checks=False), method="average"))
    S, labels = S[order][:, order], [labels[i] for i in order]

    plt.figure(figsize=(12, 10))
    im = plt.imshow(S, cmap="viridis", vmin=float(S[~np.eye(len(S),dtype=bool)].min()), vmax=1)
    plt.colorbar(im, fraction=0.046, pad=0.04, label="cosine similarity of tag centroids")
    plt.xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    plt.yticks(range(len(labels)), labels, fontsize=7)
    plt.title(f"`{top}` tag-centroid similarity (clustered)\n"
              "bright off-diagonal blocks = semantically overlapping tags → merge candidates")
    plt.tight_layout()
    p = os.path.join(OUT, f"{top}-tag-similarity.png")
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    return p


def audit_overlay(stories, ids, xy, tags):
    """2xN panel: for each tag, the story map with tagged / newly-found-missed /
    rejected-candidate / other stories marked."""
    id2pos = {s["story_id"]: i for i, s in enumerate(stories)}
    ncol = 2
    nrow = (len(tags) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 6 * nrow))
    axes = np.array(axes).reshape(-1)
    for ax, tag in zip(axes, tags):
        tagged = {s["story_id"] for s in stories if tag in s["tags"]}
        verdicts = _verdicts_for(tag)
        missed = {sid for sid, ok in verdicts.items() if ok and sid not in tagged}
        rejected = {sid for sid, ok in verdicts.items() if not ok and sid not in tagged}
        other = [i for i, s in enumerate(stories)
                 if s["story_id"] not in tagged | missed | rejected]
        def pts(idset):
            return xy[[id2pos[x] for x in idset if x in id2pos]]
        ax.scatter(xy[other, 0], xy[other, 1], s=8, color="#dddddd", linewidths=0)
        rj = pts(rejected)
        if len(rj): ax.scatter(rj[:, 0], rj[:, 1], s=26, marker="x", color="#999999",
                               linewidths=0.8, label=f"rejected candidate ({len(rejected)})")
        tg = pts(tagged)
        if len(tg): ax.scatter(tg[:, 0], tg[:, 1], s=22, color="#1f77b4",
                               alpha=0.8, linewidths=0, label=f"already tagged ({len(tagged)})")
        ms = pts(missed)
        if len(ms): ax.scatter(ms[:, 0], ms[:, 1], s=90, marker="*", color="#ff7f0e",
                               edgecolors="k", linewidths=0.4, label=f"missed → should tag ({len(missed)})")
        ax.set_title(f"practice:{tag.split(':')[-1]}", fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
        ax.legend(loc="upper left", fontsize=7, frameon=True)
    for ax in axes[len(tags):]:
        ax.axis("off")
    fig.suptitle("Audit overlay — missed taggings (orange ★) sit inside the tagged cluster (blue)\n"
                 "grey × = candidates the judge rejected; grey · = other stories", fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    p = os.path.join(OUT, "audit-overlay.png")
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    return p


def main():
    stories = tag_data.load_stories("core")
    ids, mat = tag_embeddings.embed_stories(stories)
    xy = _tsne(mat.story_mean)
    print(story_landscape(stories, ids, mat, xy))
    print(tag_similarity(stories, ids, mat))
    print(audit_overlay(stories, ids, xy,
          ["practice:recitation_of_psalms", "practice:asceticism_fasting",
           "practice:travel_to_the_tsaddik", "practice:dance"]))


if __name__ == "__main__":
    main()
