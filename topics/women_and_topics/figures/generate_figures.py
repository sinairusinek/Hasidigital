"""
Generate publication-quality figures for the women × topics article
(Mandel-Edrei, Rusinek, Sagiv).

Output: ../figures/figure_N_<slug>.{pdf,png} at 300 dpi.

Design choices (consistent across all figures):
  * Okabe-Ito palette (colorblind-safe; lightness values separated so
    figures stay legible when printed in greyscale).
  * Fixed semantic legend used everywhere:
      - bluish green (#009E73) = women OVER-represented (above corpus baseline)
      - vermillion   (#D55E00) = women UNDER-represented (below corpus baseline)
      - orange       (#E69F00) = Shivhei Habesht highlight (Besht corpus / earliest)
      - grey         (#777777) = neutral/context
      - dashed black line       = corpus baseline (27% of all stories)
  * Source TSV: topics/data/10HasidicEditionsTopics.tsv (binary "Yes"/"No Women").
  * Edition years follow the corrected metadata: Mifalot-HaZadikim = 1866.
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
TSV = ROOT / "topics" / "data" / "10HasidicEditionsTopics.tsv"
EDITIONS_DIR = ROOT / "editions" / "online"
OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- palette
OKABE_ITO = {
    "black": "#000000",
    "orange": "#E69F00",
    "skyblue": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
}
C_OVER = OKABE_ITO["green"]
C_UNDER = OKABE_ITO["vermillion"]
C_HILITE = OKABE_ITO["orange"]
C_NEUTRAL = "#777777"
C_BASELINE = "#000000"

# ---------------------------------------------------------------- style
mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#DDDDDD",
    "grid.linestyle": ":",
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# ---------------------------------------------------------------- metadata
EDITION_YEARS = {
    "Shivhei-Habesht": 1814,
    "Mifalot-HaZadikim": 1866,  # corrected from 1856 per commit 9095067
    "Maase-Zadikim": 1864,
    "Adat-Zadikim": 1864,
    "Sipurei-Zadikim": 1864,
    "Shivhei-Harav": 1864,
    "Peer-MiKdoshim": 1865,
    "Khal-Kdoshim": 1865,
    "Khal-Hasidim": 1866,
}

# Pretty topic labels (sub-tag → display)
TOPIC_RENAME = {
    "virtues_poverty": "poverty as virtue",
    "pidyon_nefesh": "pidyon nefesh",
    "pidyon_monetary_gift": "pidyon (monetary gift)",
    "redemption_of_captives": "redemption of captives",
    "business_advice": "business advice",
    "contraction_of_the_road": "contraction of the road",
    "resisting_temptation": "resisting temptation",
    "the_family_of_the_tsaddik": "family of the tsaddik",
    "mystical_vision": "mystical vision",
    "coping_with_alien_thoughts": "coping with alien thoughts",
    "angel_of_death": "angel of death",
    "journey_to_heaven": "journey to heaven",
    "institutions_beth_midrash": "institutions: beth midrash",
    "institutions_hassidic_court": "institutions: hasidic court",
    "reception_of_hasidim": "reception of hasidim",
    "story_type_death_of_the_tsaddik": "story type: death of the tsaddik",
    "story_type_virtues": "story type: virtues",
    "inter_hasidic_master_disciple_relationship":
        "inter-hasidic master–disciple relationship",
    "hidden_righteous": "hidden righteous",
    "historical_event": "historical event",
    "with_non_jews": "interaction with non-Jews",
}

def pretty_topic(sub: str) -> str:
    return TOPIC_RENAME.get(sub, sub.replace("_", " "))

# ---------------------------------------------------------------- data load
def load_story_table() -> pd.DataFrame:
    """One row per (story, tag); also a story-level frame with women flag."""
    df = pd.read_csv(TSV, sep="\t", dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "div - xml:id": "div_id",
        "full tag": "full_tag",
        "top-tag": "top_tag",
        "sub-tag": "sub_tag",
        "women-in-story": "women",
    })
    # Story id is in "Story"; edition is constant per story (only filled on first row)
    # Forward-fill edition within each story
    df["Edition"] = df["Edition"].replace("", pd.NA)
    df["Edition"] = df.groupby("Story")["Edition"].transform(lambda s: s.ffill().bfill())
    df["women_flag"] = df["women"].map({"Yes": 1, "No Women": 0})
    # Forward/back-fill women_flag within story (set on first row only)
    df["women_flag"] = df.groupby("Story")["women_flag"].transform(lambda s: s.ffill().bfill())
    return df


def story_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates("Story")[["Story", "Edition", "women_flag"]].copy()


# Wilson score CI
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# ---------------------------------------------------------------- save helper
def save(fig: plt.Figure, slug: str) -> None:
    pdf = OUT / f"{slug}.pdf"
    png = OUT / f"{slug}.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=300)
    plt.close(fig)
    print(f"  wrote {pdf.name}, {png.name}")


# ================================================================ FIG 2
def fig2_per_edition(df: pd.DataFrame) -> None:
    sf = story_frame(df)
    rows = []
    for ed, g in sf.groupby("Edition"):
        n = len(g)
        k = int(g["women_flag"].sum())
        lo, hi = wilson_ci(k, n)
        rows.append((ed, n, k, k / n, lo, hi))
    R = pd.DataFrame(rows, columns=["edition", "n", "k", "p", "lo", "hi"])
    R = R.sort_values("p", ascending=True).reset_index(drop=True)

    baseline = sf["women_flag"].mean()

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ypos = range(len(R))
    colors = [C_HILITE if e == "Shivhei-Habesht" else C_NEUTRAL for e in R["edition"]]
    ax.barh(ypos, R["p"] * 100, color=colors, edgecolor="white", height=0.7)
    # error bars
    err_lo = (R["p"] - R["lo"]) * 100
    err_hi = (R["hi"] - R["p"]) * 100
    ax.errorbar(R["p"] * 100, ypos, xerr=[err_lo, err_hi],
                fmt="none", ecolor="#444", elinewidth=0.8, capsize=2)
    labels = [f"{e}  ({EDITION_YEARS.get(e,'?')}, n={n})" for e, n in zip(R["edition"], R["n"])]
    ax.set_yticks(list(ypos))
    ax.set_yticklabels(labels)
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1,
               label=f"Corpus baseline ({baseline*100:.0f}%)")
    for i, p in enumerate(R["p"]):
        ax.text(R["hi"].iloc[i] * 100 + 1, i, f"{p*100:.0f}%", va="center", fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of stories with women present  (Wilson 95% CI)")
    ax.set_title("Women presence per edition")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    save(fig, "figure_2_per_edition")


# ================================================================ FIG 3
def fig3_economic_triad(df: pd.DataFrame) -> None:
    # Cluster: pidyon_nefesh, business_advice, poverty_as_virtue,
    # redemption_of_captives.  (pidyon_monetary_gift was merged into pidyon_nefesh.)
    cluster = [
        "pidyon_monetary_gift",
        "pidyon_nefesh",
        "virtues_poverty",
        "business_advice",
        "redemption_of_captives",
    ]
    sf = story_frame(df)
    baseline = sf["women_flag"].mean()
    rows = []
    for tag in cluster:
        stories = df[df["sub_tag"] == tag]["Story"].unique()
        sub = sf[sf["Story"].isin(stories)]
        n = len(sub)
        k = int(sub["women_flag"].sum())
        if n > 0:
            rows.append((tag, n, k, k / n))
    R = pd.DataFrame(rows, columns=["tag", "n", "k", "p"]).sort_values("p")

    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    y = range(len(R))
    ax.barh(y, R["p"] * 100, color=C_OVER, edgecolor="white", height=0.65)
    for i, (p, k, n) in enumerate(zip(R["p"], R["k"], R["n"])):
        ax.text(p * 100 + 1.5, i, f"{p*100:.0f}%  ({k}/{n})", va="center", fontsize=9)
    ax.set_yticks(list(y))
    ax.set_yticklabels([pretty_topic(t) for t in R["tag"]])
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1,
               label=f"Corpus baseline ({baseline*100:.0f}%)")
    ax.set_xlim(0, 110)
    ax.set_xlabel("% of stories on this topic that include women")
    ax.set_title("Women and economic practice — a coherent cluster\n"
                 "All money-and-tsaddik topics far exceed the corpus baseline",
                 fontsize=10.5)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    save(fig, "figure_3_economic_triad")


# ================================================================ FIG 4
def fig4_cooccurrence(df: pd.DataFrame, top_k: int = 15, min_n: int = 6) -> None:
    """Topic-pair co-occurrences most loaded with women (excluding trivially
    gendered tags)."""
    EXCLUDED = {
        "tsaddik_wife", "the_family_of_the_tsaddik", "agunah", "releasing_agunot",
        "marital_relationship", "marriage", "marriage_matchmaking",
        "divorce", "birth", "story_type_birth_of_the_tsaddik",
        "Women in Story",
    }
    sf = story_frame(df)
    baseline = sf["women_flag"].mean()

    # tag -> set(stories)
    tag_stories: dict[str, set[str]] = defaultdict(set)
    tag_top: dict[str, str] = {}
    for _, r in df[(df["sub_tag"] != "") & (~df["sub_tag"].isin(EXCLUDED))].iterrows():
        tag_stories[r["sub_tag"]].add(r["Story"])
        tag_top[r["sub_tag"]] = r["top_tag"]

    women_set = set(sf[sf["women_flag"] == 1]["Story"])
    tags = sorted(tag_stories.keys())

    pairs = []
    for i, a in enumerate(tags):
        for b in tags[i + 1:]:
            inter = tag_stories[a] & tag_stories[b]
            n = len(inter)
            if n < min_n:
                continue
            k = len(inter & women_set)
            pairs.append((a, b, n, k, k / n))
    P = pd.DataFrame(pairs, columns=["a", "b", "n", "k", "p"])
    P = P.sort_values(["p", "n"], ascending=[False, False]).head(top_k)

    fig, ax = plt.subplots(figsize=(10.0, 8.5))
    labels = [f"{pretty_topic(a)}  ×  {pretty_topic(b)}"
              for a, b in zip(P["a"], P["b"])]
    y = list(range(len(P)))[::-1]
    ax.barh(y, P["p"] * 100, color=C_OVER, edgecolor="white", height=0.7)
    for i, (p, k, n) in zip(y, zip(P["p"], P["k"], P["n"])):
        ax.text(p * 100 + 1, i, f"{p*100:.0f}%  ({k}/{n})", va="center", fontsize=9.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1,
               label=f"Corpus baseline ({baseline*100:.0f}%)")
    ax.set_xlim(0, 115)
    ax.set_xlabel("% of stories with this topic-pair that include women")
    ax.set_title(f"Topic co-occurrences most loaded with women (n≥{min_n}, top {top_k})\n"
                 "Trivially gendered tags excluded "
                 "(tsaddik_wife, family_of_the_tsaddik, agunah, marriage, divorce, birth)",
                 fontsize=10)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    save(fig, "figure_4_cooccurrence")


# ================================================================ FIG 5
def fig5_within_edition(df: pd.DataFrame, min_n_in_ed: int = 1) -> None:
    """Small multiples: signature women-loaded topics, by edition."""
    signature = [
        ("pidyon_nefesh", "economic"),
        ("virtues_poverty", "economic"),
        ("business_advice", "economic"),
        ("redemption_of_captives", "economic"),
        ("solitude", "other"),
        ("lust", "other"),
        ("resisting_temptation", "other"),
        ("contraction_of_the_road", "other"),
    ]
    sf = story_frame(df)
    baseline = sf["women_flag"].mean()

    fig, axes = plt.subplots(2, 4, figsize=(13, 6.5), sharex=True)
    axes = axes.ravel()

    # Order editions chronologically (oldest at bottom)
    ed_order = sorted(EDITION_YEARS.keys(),
                      key=lambda e: -EDITION_YEARS.get(e, 9999))

    for ax, (tag, cluster) in zip(axes, signature):
        color = C_OVER if cluster == "economic" else OKABE_ITO["blue"]
        stories = set(df[df["sub_tag"] == tag]["Story"])
        n_corpus = len(stories)
        k_corpus = sum(1 for s in stories if s in set(sf[sf["women_flag"] == 1]["Story"]))
        rows = []
        for ed in ed_order:
            ed_stories = set(sf[sf["Edition"] == ed]["Story"])
            inter = stories & ed_stories
            n = len(inter)
            if n < min_n_in_ed:
                rows.append((ed, 0, 0, None))
                continue
            k = sum(1 for s in inter
                    if sf[(sf["Edition"] == ed) & (sf["Story"] == s)]["women_flag"].iloc[0] == 1)
            rows.append((ed, n, k, k / n))
        R = pd.DataFrame(rows, columns=["edition", "n", "k", "p"])

        present = R[R["p"].notna()]
        y = range(len(present))
        ax.barh(list(y), present["p"] * 100, color=color, edgecolor="white", height=0.7)
        for i, (p, n) in enumerate(zip(present["p"], present["n"])):
            ax.text(p * 100 + 2, i, f"{p*100:.0f}%", va="center", fontsize=8)
        ax.set_yticks(list(y))
        ax.set_yticklabels([f"{e} (n={n})" for e, n in zip(present["edition"], present["n"])],
                           fontsize=8)
        ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=0.8)
        ax.set_xlim(0, 110)
        ax.set_title(f"{pretty_topic(tag)}\n(corpus: {k_corpus}/{n_corpus})", fontsize=9)

    for ax in axes[4:]:
        ax.set_xlabel("% women present", fontsize=9)
    fig.suptitle("Does the women-loading replicate within editions?  "
                 "Small multiples for signature topics  "
                 f"(dashed = corpus baseline {baseline*100:.0f}%)",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save(fig, "figure_5_within_edition")


# ================================================================ FIG 6
def fig6_low_women(df: pd.DataFrame, min_n: int = 5, top_k: int = 18) -> None:
    sf = story_frame(df)
    baseline = sf["women_flag"].mean()
    women_set = set(sf[sf["women_flag"] == 1]["Story"])

    rows = []
    for sub, g in df[df["sub_tag"] != ""].groupby("sub_tag"):
        stories = set(g["Story"])
        n = len(stories)
        if n < min_n:
            continue
        k = len(stories & women_set)
        top = g["top_tag"].iloc[0]
        rows.append((sub, top, n, k, k / n))
    R = pd.DataFrame(rows, columns=["sub", "top", "n", "k", "p"])
    R = R.sort_values(["p", "n"], ascending=[True, False]).head(top_k)

    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    y = range(len(R))[::-1]
    ax.barh(list(y), R["p"] * 100, color=C_UNDER, edgecolor="white", height=0.7)
    for i, (p, k, n) in zip(y, zip(R["p"], R["k"], R["n"])):
        ax.text(p * 100 + 0.8, i, f"{p*100:.0f}%  ({k}/{n})", va="center", fontsize=8.5)
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{pretty_topic(s)}  [{t}]" for s, t in zip(R["sub"], R["top"])],
                       fontsize=8.5)
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1,
               label=f"Corpus baseline ({baseline*100:.0f}%)")
    ax.set_xlim(0, max(R["p"].max() * 100 + 12, 40))
    ax.set_xlabel("% of stories on this topic that include women")
    ax.set_title("Topics LEAST associated with women\n"
                 "Masculine theological–elite cluster: pride, awe, "
                 "mystical_vision, reception_of_hasidim",
                 fontsize=10.5)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    save(fig, "figure_6_low_women")


# ================================================================ FIG 7
_STORY_SNIPPET_CACHE: dict[str, str] = {}

def _extract_snippet(story_id: str) -> str:
    if story_id in _STORY_SNIPPET_CACHE:
        return _STORY_SNIPPET_CACHE[story_id]
    edition = story_id.rsplit("_", 1)[0]
    path = EDITIONS_DIR / f"{edition}.xml"
    if not path.exists():
        _STORY_SNIPPET_CACHE[story_id] = ""
        return ""
    try:
        x = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        _STORY_SNIPPET_CACHE[story_id] = ""
        return ""
    m = re.search(rf'xml:id="{re.escape(story_id)}"[^>]*>(.*?)</div>', x, re.S)
    if not m:
        _STORY_SNIPPET_CACHE[story_id] = ""
        return ""
    body = m.group(1)
    p = re.search(r"<p[^>]*>(.*?)</p>", body, re.S)
    if not p:
        _STORY_SNIPPET_CACHE[story_id] = ""
        return ""
    txt = re.sub(r"<[^>]+>", " ", p.group(1))
    txt = re.sub(r"\s+", " ", txt).strip()
    _STORY_SNIPPET_CACHE[story_id] = txt
    return txt


def fig7_exemplars(df: pd.DataFrame, per_topic: int = 3) -> None:
    sf = story_frame(df)
    signature_topics = [
        "pidyon_nefesh",
        "pidyon_monetary_gift",
        "virtues_poverty",
        "business_advice",
        "redemption_of_captives",
        "solitude",
        "contraction_of_the_road",
    ]
    fig, ax = plt.subplots(figsize=(10.5, 8.5))
    ax.set_axis_off()
    y = 1.0
    line_h = 0.034

    ax.text(0.0, y, "Exemplar stories by signature topic",
            fontsize=13, fontweight="bold", transform=ax.transAxes)
    y -= line_h * 1.4

    women_set = set(sf[sf["women_flag"] == 1]["Story"])
    for tag in signature_topics:
        stories = list(df[df["sub_tag"] == tag]["Story"].unique())
        women_stories = [s for s in stories if s in women_set]
        n_total = len(stories)
        n_women = len(women_stories)
        pct = (n_women / n_total * 100) if n_total else 0
        header = f"{pretty_topic(tag)}  —  {pct:.0f}% women  ({n_women}/{n_total})"
        ax.text(0.0, y, header, fontsize=11, fontweight="bold",
                color=C_OVER, transform=ax.transAxes)
        y -= line_h * 1.05

        picks = women_stories[:per_topic]
        if not picks:
            ax.text(0.02, y, "(no examples)", fontsize=9,
                    color=C_NEUTRAL, transform=ax.transAxes)
            y -= line_h
        else:
            for sid in picks:
                snip = _extract_snippet(sid)
                snip = snip[:140] + ("…" if len(snip) > 140 else "")
                ax.text(0.02, y, f"• {sid}", fontsize=9, fontweight="bold",
                        transform=ax.transAxes)
                y -= line_h * 0.85
                # Hebrew snippet: render right-to-left by wrapping with RTL marks
                ax.text(0.04, y, "‫" + snip + "‬", fontsize=8.5,
                        color="#333", transform=ax.transAxes)
                y -= line_h
        y -= line_h * 0.4

    fig.suptitle("Figure 7 · Story exemplars by signature women-loaded topic",
                 fontsize=11, y=0.99)
    save(fig, "figure_7_exemplars")


# ================================================================ main
def main() -> None:
    print(f"Loading {TSV.relative_to(ROOT)} …")
    df = load_story_table()
    sf = story_frame(df)
    n_stories = len(sf)
    n_women = int(sf["women_flag"].sum())
    baseline = n_women / n_stories
    print(f"  {n_stories} stories total, {n_women} with women "
          f"({baseline*100:.1f}% baseline)")

    print("Figure 2 — per-edition women presence with CIs …")
    fig2_per_edition(df)
    print("Figure 3 — economic-practice triad …")
    fig3_economic_triad(df)
    print("Figure 4 — topic co-occurrence pairs …")
    fig4_cooccurrence(df)
    print("Figure 5 — within-edition replication …")
    fig5_within_edition(df)
    print("Figure 6 — topics LEAST associated with women …")
    fig6_low_women(df)
    print("Figure 7 — exemplar stories …")
    fig7_exemplars(df)

    print("\nDone. Outputs in:", OUT.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
