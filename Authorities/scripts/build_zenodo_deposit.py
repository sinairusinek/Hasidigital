#!/usr/bin/env python3
"""Build a Zenodo deposit for the Hasidigital story corpus.

Two versions of ONE Zenodo concept record (same concept DOI, separate
version DOIs), per the project decision that the women-article dataset is a
subset and first version of the general Hasidic-stories dataset:

  v1  "women-9ed"  -- the 9 editions analysed in Mandel-Edrei / Rusinek /
                      Sagiv, "Rethinking Women in Hasidic Literature", with
                      the 5-tier women annotation. Frozen to match the
                      article's text and figures.
  v2  "corpus"     -- the full annotated corpus (all editions in
                      editions/online/). Built later, as a NEW VERSION of the
                      same concept record, so the article's citation keeps
                      resolving to v1.

Everything numeric is recomputed from editions/online/*.xml at build time via
the same extractor that produces the article's figures
(topics/women_and_topics/figures/generate_figures.py), so the deposit cannot
silently disagree with the article.

Usage:
  python build_zenodo_deposit.py --version v1
  python build_zenodo_deposit.py --version v2     # when the general corpus is ready
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIGURES = REPO / "topics/women_and_topics/figures"
EDITIONS_DIR = REPO / "editions" / "online"

# Reuse the article's own extractor so the deposit and the figures can never
# diverge. generate_figures.py exposes the per-story extraction we need.
sys.path.insert(0, str(FIGURES))

# ---------------------------------------------------------------- authors
# ORCIDs verified against the ORCID public registry (pub.orcid.org), 2026-10-06.
CREATORS = [
    {
        "name": "Mandel-Edrei, Chen",
        "affiliation": "The Hebrew University of Jerusalem",
        "orcid": "0009-0006-8787-8220",
    },
    {
        "name": "Rusinek, Sinai",
        "affiliation": "The Open University of Israel",
        "orcid": "0000-0003-1043-7954",
    },
    {
        "name": "Sagiv, Gadi",
        "affiliation": "The Open University of Israel",
        "orcid": "0000-0002-3289-0429",
    },
]

ARTICLE_TITLE = "Rethinking Women in Hasidic Literature: Between Close and Distant Reading"

# The 9 editions of the article corpus: deposit filename -> source XML stem.
V1_EDITIONS = {
    "Adat-Zadikim": "Adat-Zadikim",
    "Khal-Hasidim": "Khal-Hasidim",
    "Khal-Kdoshim": "Khal-Kdoshim",
    "Maase-Zadikim": "maase-zadikim",
    "Mifalot-HaZadikim": "Mifalot-HaZadikim",
    "Peer-MiKdoshim": "PeerMikdoshim",
    "Shivhei-Habesht": "Shivhei-Habesht",
    "Shivhei-Harav": "Shivhei-Harav",
    "Sipurei-Zadikim": "Sipurei-Zadikim",
}

# Human-readable edition names + imprint, as the article cites them.
EDITION_LABELS = {
    "Adat-Zadikim": ("Adat Tsadikim", "Lemberg, 1864"),
    "Khal-Hasidim": ("Kehal Hasidim", "Warsaw, 1866"),
    "Khal-Kdoshim": ("Kehal Kdoshim", "Lemberg, 1865"),
    "Maase-Zadikim": ("Ma'ase Tsadikim", "Lemberg, 1864"),
    "Mifalot-HaZadikim": ("Mif'alot ha-Tsadikim", "Lemberg, 1866"),
    "Peer-MiKdoshim": ("Pe'er mi-Kdoshim", "Lemberg, 1865"),
    "Shivhei-Habesht": ("Shivhei ha-Besht", "Kopys, 1814"),
    "Shivhei-Harav": ("Shivhei ha-Rav", "Lemberg, 1864"),
    "Sipurei-Zadikim": ("Sipurei Tsadikim", "Lemberg, 1864"),
}

# TSV edition key -> deposit edition name (the TSV uses the source stems).
TSV_KEY_TO_NAME = {src: name for name, src in V1_EDITIONS.items()}

CHAR_TIERS = ("major", "catalyst", "minor")
ANY_TIERS = CHAR_TIERS + ("mention_only",)

TIER_ANA = {
    "major": "women:major_character",
    "catalyst": "women:catalyst_character",
    "minor": "women:minor_character",
    "mention_only": "women:mention_only",
}


# generate_figures.extract() encodes the tier as an int: major=4 … mention=1,
# none=0. Map it back to the label we publish.
TIER_FROM_RANK = {4: "major", 3: "catalyst", 2: "minor", 1: "mention_only", 0: "none"}


def extract_stories(edition_stems: list[str] | None = None) -> list[dict]:
    """Per-story extraction via the article's own figure generator.

    generate_figures.extract() yields {id, edition, tier:int, tags:set}; we
    normalise to {story_id, edition, women_tier:str, tags:set} and, for v2,
    widen its hardcoded CORE_EDITIONS to the requested edition list.
    """
    import generate_figures as gf

    if edition_stems is not None:
        gf.CORE_EDITIONS = list(edition_stems)

    stories = []
    for rec in gf.extract():
        stories.append({
            "story_id": rec["id"],
            "edition": rec["edition"],
            "women_tier": TIER_FROM_RANK[rec["tier"]],
            "tags": set(rec["tags"]),
        })
    return stories


def pct(num: int, den: int) -> str:
    return f"{100 * num / den:.1f}%" if den else "—"


def summarize(stories: list[dict]) -> dict:
    n = len(stories)
    any_n = sum(1 for s in stories if s["women_tier"] in ANY_TIERS)
    char_n = sum(1 for s in stories if s["women_tier"] in CHAR_TIERS)
    tiers = Counter(s["women_tier"] for s in stories)
    per_edition = {}
    for ed in sorted({s["edition"] for s in stories}):
        sel = [s for s in stories if s["edition"] == ed]
        per_edition[ed] = {
            "n": len(sel),
            "any": sum(1 for s in sel if s["women_tier"] in ANY_TIERS),
            "char": sum(1 for s in sel if s["women_tier"] in CHAR_TIERS),
        }
    return {
        "n_stories": n,
        "any": any_n,
        "char": char_n,
        "tiers": dict(tiers),
        "per_edition": per_edition,
    }


# ---------------------------------------------------------------- writers
def write_story_women_tsv(path: Path, stories: list[dict]) -> None:
    """Per-story 5-tier label, the ana tag that carries it, and both binaries."""
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow([
            "story_id", "edition", "women_tier", "women_ana_tag",
            "women_present", "women_graded_character",
        ])
        for s in sorted(stories, key=lambda r: r["story_id"]):
            tier = s["women_tier"]
            w.writerow([
                s["story_id"],
                TSV_KEY_TO_NAME.get(s["edition"], s["edition"]),
                tier,
                TIER_ANA.get(tier, ""),
                "yes" if tier in ANY_TIERS else "no",
                "yes" if tier in CHAR_TIERS else "no",
            ])


def write_story_tags_tsv(path: Path, stories: list[dict]) -> None:
    """Long-format (story, tag) rows -- one row per tag, the analysis unit."""
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow([
            "story_id", "edition", "top_tag", "sub_tag", "full_tag",
            "women_tier", "women_present", "women_graded_character",
        ])
        for s in sorted(stories, key=lambda r: r["story_id"]):
            tier = s["women_tier"]
            ed = TSV_KEY_TO_NAME.get(s["edition"], s["edition"])
            any_v = "yes" if tier in ANY_TIERS else "no"
            char_v = "yes" if tier in CHAR_TIERS else "no"
            for full in sorted(t for t in s["tags"] if t):
                top, _, sub = full.partition(":")
                w.writerow([s["story_id"], ed, top, sub, full, tier, any_v, char_v])


def write_tag_summary_tsv(path: Path, stories: list[dict]) -> None:
    """Per-tag women rates -- the table behind the article's Figures 2 and 3."""
    by_tag: dict[str, list[dict]] = {}
    for s in stories:
        for full in s["tags"]:
            if full:
                by_tag.setdefault(full, []).append(s)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow([
            "full_tag", "top_tag", "sub_tag", "n_stories",
            "n_women_present", "pct_women_present",
            "n_women_graded_character", "pct_women_graded_character",
        ])
        for full in sorted(by_tag):
            sel = by_tag[full]
            n = len(sel)
            a = sum(1 for s in sel if s["women_tier"] in ANY_TIERS)
            c = sum(1 for s in sel if s["women_tier"] in CHAR_TIERS)
            top, _, sub = full.partition(":")
            w.writerow([
                full, top, sub, n,
                a, f"{100 * a / n:.1f}", c, f"{100 * c / n:.1f}",
            ])


def copy_editions(out_dir: Path, editions: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, stem in editions.items():
        src = EDITIONS_DIR / f"{stem}.xml"
        if not src.exists():
            raise SystemExit(f"missing edition XML: {src}")
        shutil.copy2(src, out_dir / f"{name}.xml")


# ---------------------------------------------------------------- metadata
def build_metadata(version: str, summary: dict) -> dict:
    if version == "v1":
        title = (
            "Rethinking Women in Hasidic Literature — Annotated Corpus of "
            "Nine Hasidic Story Editions (Hasidigital)"
        )
        description = (
            f"Annotated TEI-XML editions and story-level thematic tag data for the "
            f"{summary['n_stories']} stories in nine nineteenth-century Hasidic hagiographic "
            f"collections, as analysed in Mandel-Edrei, Rusinek and Sagiv, "
            f"“{ARTICLE_TITLE}”. "
            "Each story carries manually curated thematic tags (about 15 top-level categories "
            "and about 120 sub-tags) and an annotation of women's presence. The article's "
            "measure is presence alone (`women_present`): whether a story refers to a woman at "
            "all, whether she acts, serves as a catalyst or appears only in passing. An earlier "
            "attempt to grade women's involvement on a five-tier scale did not reach sufficient "
            "agreement between annotators, human or LLM, and was abandoned; those labels are "
            "retained here for transparency rather than as the article's measure. "
            "Derived tables give per-story labels, long-format "
            "(story, tag) rows, and per-tag women rates, so every statistic and figure in the "
            "article can be recomputed from this deposit. "
            "This is version 1 of the Hasidigital story-corpus dataset and covers the nine "
            "editions of the article; later versions extend it to the full corpus."
        )
        keywords = [
            "Hasidism", "Hasidic stories", "hagiography", "TEI", "digital humanities",
            "gender in literature", "women's history", "Hebrew", "Jewish studies",
            "topic annotation", "distant reading",
        ]
        notes = (
            "The article's measure of women's presence is the `women_present` column: whether "
            "a story refers to a woman at all, whether she acts, serves as a catalyst or "
            "appears only in passing. An earlier attempt to grade involvement on a five-tier "
            "scale did not reach sufficient agreement between annotators (human or LLM) and "
            "was abandoned; those labels are shipped as `women_tier` and "
            "`women_graded_character` for transparency and reuse, and should not be quoted as "
            "the corpus's women rate. See CHANGES.md and README.md for the full history and "
            "the annotation caveats."
        )
    else:
        title = "Hasidigital — Annotated Corpus of Hasidic Story Editions"
        description = (
            f"Annotated TEI-XML editions and story-level thematic tag data for "
            f"{summary['n_stories']} stories across the Hasidigital corpus of Hasidic "
            "hagiographic collections. Extends version 1, which covered the nine editions "
            "analysed in Mandel-Edrei, Rusinek and Sagiv, "
            f"“{ARTICLE_TITLE}”."
        )
        keywords = [
            "Hasidism", "Hasidic stories", "hagiography", "TEI", "digital humanities",
            "Hebrew", "Jewish studies", "topic annotation", "distant reading",
        ]
        notes = (
            "Version 2 extends the nine-edition version-1 dataset to the wider corpus. "
            "Statistics in the article correspond to version 1."
        )

    return {
        "title": title,
        "upload_type": "dataset",
        "creators": CREATORS,
        "description": description,
        "keywords": keywords,
        "license": "CC-BY-4.0",
        "language": "heb",
        "version": "1.0.0" if version == "v1" else "2.0.0",
        "related_identifiers": [
            {
                "relation": "isSupplementTo",
                "identifier": "TBD-article-DOI",
                "resource_type": "publication-article",
            },
            {
                "relation": "isSupplementedBy",
                "identifier": "https://github.com/sinairusinek/Hasidigital",
                "resource_type": "software",
            },
            {
                "relation": "isDerivedFrom",
                "identifier": "https://www.hasidic-stories.org/",
                "resource_type": "dataset",
            },
        ],
        "notes": notes,
    }


def render_readme(version: str, summary: dict, editions: dict[str, str]) -> str:
    s = summary
    t = s["tiers"]
    n_ed = len(summary["per_edition"])
    if version == "v1":
        head = [
            "# Rethinking Women in Hasidic Literature — Annotated Corpus",
            "",
            "Companion dataset to:",
            "",
            f"> Mandel-Edrei, Chen; Rusinek, Sinai; Sagiv, Gadi. *{ARTICLE_TITLE}* (forthcoming).",
            "",
            "Part of the **Hasidigital** project — <https://www.hasidic-stories.org/>.",
            "",
            "## Versioning",
            "",
            "This is **version 1** of the Hasidigital story-corpus dataset. It covers the nine "
            "editions analysed in the article above. The annotated corpus continues to grow; "
            "later versions of this same Zenodo record extend it to further editions.",
            "",
            "Cite the **version DOI** to reproduce the article's statistics; cite the "
            "**concept DOI** to point at the dataset in general.",
        ]
    else:
        head = [
            "# Hasidigital — Annotated Corpus of Hasidic Story Editions",
            "",
            "Part of the **Hasidigital** project — <https://www.hasidic-stories.org/>.",
            "",
            "## Versioning",
            "",
            "This is **version 2** of the Hasidigital story-corpus dataset. Version 1 covered "
            "the nine editions analysed in Mandel-Edrei, Rusinek and Sagiv, "
            f"*{ARTICLE_TITLE}*; this version extends the dataset to the wider corpus.",
            "",
            "The statistics reported in that article correspond to **version 1**, which remains "
            "citable at its own version DOI.",
        ]
    lines = head + [
        "",
        "## Contents",
        "",
        "```",
        f"editions/                   The {n_ed} annotated TEI-XML editions",
        "story_women.tsv             Per-story women annotation (5-tier + both binaries)",
        "story_tags.tsv              Long format: one row per (story, tag)",
        "tag_women_summary.tsv       Per-tag story counts and women rates",
        "README.md",
        "CHANGES.md",
        "```",
        "",
        "## The corpus",
        "",
        f"**{s['n_stories']} stories** across {n_ed} editions.",
        "",
        "| Edition | Imprint | Stories | Women (any) | Women (character) |",
        "|---|---|---|---|---|",
    ]
    for name in editions:
        stem = editions[name]
        st = s["per_edition"].get(stem)
        if not st:
            continue
        # v2 covers editions that have no curated label/imprint yet.
        label, imprint = EDITION_LABELS.get(name, (name.replace("-", " "), "—"))
        lines.append(
            f"| {label} (`{name}.xml`) | {imprint} | {st['n']} | "
            f"{st['any']} ({pct(st['any'], st['n'])}) | {st['char']} ({pct(st['char'], st['n'])}) |"
        )
    lines += [
        f"| **Total** | | **{s['n_stories']}** | **{s['any']} ({pct(s['any'], s['n_stories'])})** "
        f"| **{s['char']} ({pct(s['char'], s['n_stories'])})** |",
        "",
        "## Annotation",
        "",
        "### Thematic tags",
        "",
        "Each story carries story-level thematic tags — about 15 top-level categories "
        "(`practice`, `ethics-and-emotions`, `social`, …) and about 120 sub-tags "
        "(`pidyon_nefesh`, `poverty`, `agunah`, …), written as `top-tag:sub-tag`. Tags mark "
        "the **presence of a theme in a story**, not the frequency of its textual occurrences. "
        "In the XML they are `<span ana=\"…\">` elements on the story `<div>`.",
        "",
        "### Women's presence — the article's measure",
        "",
        "The article records **presence alone**: whether a story refers to a woman at all, "
        "whether she acts in the narrative, serves as a catalyst, or appears only in passing. "
        "That is the `women_present` column, and it is the measure behind every figure and "
        "statistic in the article:",
        "",
        f"- **women present: {s['any']} / {s['n_stories']} ({pct(s['any'], s['n_stories'])})**",
        "",
        "This is a deliberately modest measure. It does not claim to capture how much narrative "
        "weight a woman carries — that is recovered by close reading, not by counting. It is, "
        "however, the one judgement independent readers of these stories proved able to agree "
        "on, and it can be checked by anyone who consults the corpus.",
        "",
        "### The graded scheme — a superseded attempt, retained for transparency",
        "",
        "The project first tried to record not merely whether a woman is present but how "
        "substantially, on the five-tier scale below. **That attempt did not succeed**: "
        "sufficient agreement could not be reached between human annotators, nor between LLM "
        "annotators, and the article reports it as a negative methodological result rather "
        "than using it.",
        "",
        "The tier labels are nevertheless shipped here — as `women_tier`, and collapsed into "
        "`women_graded_character` (major + catalyst + minor, excluding mention-only) — so that "
        "the failure is inspectable rather than merely asserted, and so the labels can be "
        "reused by anyone who wants to attack the boundary problem differently. "
        "**They are not the article's measure, and `women_graded_character` should not be "
        "quoted as the corpus's women rate.**",
        "",
        "| Tier | `ana` tag | Meaning | Stories |",
        "|---|---|---|---|",
        f"| major | `women:major_character` | A woman is a central actor with her own agency | {t.get('major', 0)} |",
        f"| catalyst | `women:catalyst_character` | A woman triggers the plot or is the reason for events, without being a central actor | {t.get('catalyst', 0)} |",
        f"| minor | `women:minor_character` | A woman appears in a small or peripheral role | {t.get('minor', 0)} |",
        f"| mention-only | `women:mention_only` | A woman is referred to but does not act in the narrative | {t.get('mention_only', 0)} |",
        f"| none | *(no `women:` tag)* | No women in the story | {t.get('none', 0)} |",
        "",
        f"Collapsing the tiers to `women_graded_character` would give "
        f"{s['char']} / {s['n_stories']} ({pct(s['char'], s['n_stories'])}) — reported here "
        "only for completeness, and **not** the article's figure.",
        "",
        "## Table schemas",
        "",
        "### `story_women.tsv`",
        "",
        "| Column | Description |",
        "|---|---|",
        "| `story_id` | Story id; matches `<div xml:id=\"…\">` in the edition XML |",
        "| `edition` | Edition short name |",
        "| `women_tier` | `major` / `catalyst` / `minor` / `mention_only` / `none` |",
        "| `women_ana_tag` | The `ana` value carrying the tier in the XML; blank for `none` |",
        "| `women_present` | **The article's measure.** `yes` if the story refers to a woman at all |",
        "| `women_graded_character` | From the superseded graded scheme: `yes` if major, catalyst or minor. Not the article's measure |",
        "",
        "### `story_tags.tsv`",
        "",
        "One row per (story, tag) — the unit of the article's tag-level analysis.",
        "",
        "| Column | Description |",
        "|---|---|",
        "| `story_id`, `edition` | As above |",
        "| `top_tag`, `sub_tag`, `full_tag` | The tag, split and joined (`top-tag:sub-tag`) |",
        "| `women_tier`, `women_present`, `women_graded_character` | The story's women annotation, repeated for convenience |",
        "",
        "### `tag_women_summary.tsv`",
        "",
        "Per-tag aggregate — the table behind the article's Figures 2 and 3.",
        "",
        "| Column | Description |",
        "|---|---|",
        "| `full_tag`, `top_tag`, `sub_tag` | The tag |",
        "| `n_stories` | Stories carrying the tag |",
        "| `n_women_present`, `pct_women_present` | **The article's measure**: count and % of the tag's stories that refer to a woman |",
        "| `n_women_graded_character`, `pct_women_graded_character` | The same under the superseded graded scheme; not the article's measure |",
        "",
        "## Reproducing the article's figures",
        "",
        "`tag_women_summary.tsv` reproduces the per-tag rates directly. For example, the "
        "economic finding (article §Step 2) reads off the `poverty`, `business_advice` and "
        "`pidyon_nefesh` rows; the under-representation cases read off "
        "`coping_with_alien_thoughts`, `trembling`, `awe` and "
        "`inter_hasidic_master_disciple_relationship`.",
        "",
        "Figure-generating code lives in the project repository "
        "(`topics/women_and_topics/figures/generate_figures.py`), which reads the same edition "
        "XMLs included here.",
        "",
        "## Caveats",
        "",
        "Please read these before quoting any statistic:",
        "",
        "- Tag counts are **floors, not exact censuses**. The LLM-assisted tagging pass had an "
        "estimated candidate-retrieval recall of **87–93% per category**, so a tag's story "
        "count may understate its true extent.",
        "- The adjudication pass was benchmarked against a 100-story human anchor but was "
        "**not fully human-validated**.",
        "- Several category definitions were patched mid-audit; affected tags were audited "
        "under the patched definitions.",
        "- The five-tier graded labels are LLM-produced with human curation, and the "
        "**mention-only boundary is their least stable distinction** — which is why the graded "
        "scheme was abandoned and the article counts presence alone. Treat `women_tier` and "
        "`women_graded_character` as exploratory.",
        "- A small number of anomalous tag tokens from the taxonomy-consolidation backlog are "
        "excluded from the article's figures.",
        "",
        "## License",
        "",
        "**CC-BY 4.0.** The underlying edition texts are nineteenth-century works in the public "
        "domain; the annotation layer, encoding and derived tables are the contribution licensed "
        "here. Please cite both the article and this dataset.",
        "",
        "## Citation",
        "",
        "> Mandel-Edrei, Chen; Rusinek, Sinai; Sagiv, Gadi. "
        + (f"*{ARTICLE_TITLE} — Annotated Corpus*. Version 1.0.0. "
           if version == "v1"
           else "*Hasidigital — Annotated Corpus of Hasidic Story Editions*. Version 2.0.0. ")
        + "Zenodo. https://doi.org/TBD",
        "",
    ]
    return "\n".join(lines)


def render_changes(version: str, summary: dict) -> str:
    s = summary
    t = s["tiers"]
    return "\n".join([
        "# Changes and corpus history",
        "",
        "## Version 1.0.0 — nine editions",
        "",
        "First published version. Covers the nine editions analysed in Mandel-Edrei, Rusinek "
        f"and Sagiv, \"{ARTICLE_TITLE}\": {s['n_stories']} stories.",
        "",
        "### How this snapshot was produced",
        "",
        "1. **Manual thematic annotation.** Research assistants tagged every story with "
        "story-level thematic tags from a schema developed jointly by historians and literary "
        "scholars (~15 top-level categories, ~120 sub-tags).",
        "2. **Tag audit (2026-06).** An LLM-assisted sweep proposed additional tags for stories "
        "where the manual pass had missed a theme, followed by an adjudication pass over the "
        "candidates.",
        "3. **Precision audit (2026-06-30).** Every LLM-proposed insertion was re-judged; "
        "**789 insertions were removed** as false positives. The dominant source of "
        "over-tagging was automatic propagation to near-duplicate stories (64% reject rate) "
        "rather than direct proposal (9%).",
        "4. **Five-tier women re-annotation.** The earlier binary major/minor women tags were "
        "replaced by the five-tier scheme below, which distinguishes women who act in a "
        "narrative from women who are merely referred to.",
        "",
        "### Women tiers in this version",
        "",
        "| Tier | Stories |",
        "|---|---|",
        f"| major | {t.get('major', 0)} |",
        f"| catalyst | {t.get('catalyst', 0)} |",
        f"| minor | {t.get('minor', 0)} |",
        f"| mention-only | {t.get('mention_only', 0)} |",
        f"| none | {t.get('none', 0)} |",
        f"| **total** | **{s['n_stories']}** |",
        "",
        f"Derived: **any** = {s['any']} ({pct(s['any'], s['n_stories'])}), "
        f"**character** = {s['char']} ({pct(s['char'], s['n_stories'])}).",
        "",
        "> Earlier internal drafts of this dataset (unpublished) reported a women rate of "
        "roughly 26–27%. That figure came from the pre-audit corpus under the old binary "
        "scheme. The current numbers differ because of both the audited tag layer and the "
        "five-tier re-annotation, which identified more stories containing women overall.",
        "",
        "### Relation to the article's text",
        "",
        "Every count in the article was recomputed from the edition XMLs included in this "
        "deposit, using the same extractor that generates the article's figures. The deposit "
        "and the article are built from one source.",
        "",
        "## Planned: version 2.0.0 — full corpus",
        "",
        "A later version of this record will extend the dataset beyond the nine editions to "
        "the wider Hasidigital corpus. Version 1.0.0 remains citable at its own version DOI, "
        "so the article's statistics stay reproducible.",
        "",
    ])


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", choices=["v1", "v2"], default="v1")
    args = ap.parse_args()

    if args.version == "v1":
        deposit = REPO / "zenodo/women-9ed"
        editions = V1_EDITIONS
    else:
        deposit = REPO / "zenodo/corpus"
        editions = {p.stem: p.stem for p in sorted(EDITIONS_DIR.glob("*.xml"))}

    stories = extract_stories(list(editions.values()))
    if not stories:
        raise SystemExit("no stories extracted -- check editions/online/")
    summary = summarize(stories)

    # Guard: an edition with no women:* tag at all is almost certainly
    # un-annotated rather than genuinely womanless, and would silently deflate
    # every rate in the deposit. Refuse to build a version on top of it.
    unannotated = [
        ed for ed, st in summary["per_edition"].items() if st["any"] == 0
    ]
    if unannotated:
        print(f"  {len(unannotated)} edition(s) carry NO women annotation:")
        for ed in sorted(unannotated):
            print(f"    - {ed} ({summary['per_edition'][ed]['n']} stories)")
        raise SystemExit(
            "Refusing to build: these editions have not been annotated for women's\n"
            "presence, so corpus-wide women rates would be meaningless. Annotate them\n"
            "first, or restrict this version to the annotated editions."
        )

    deposit.mkdir(parents=True, exist_ok=True)

    print(f"Building {args.version} deposit in {deposit.relative_to(REPO)}")
    print(f"  {summary['n_stories']} stories; "
          f"any {summary['any']} ({pct(summary['any'], summary['n_stories'])}); "
          f"char {summary['char']} ({pct(summary['char'], summary['n_stories'])})")

    copy_editions(deposit / "editions", editions)
    print(f"  copied {len(editions)} edition XMLs")

    write_story_women_tsv(deposit / "story_women.tsv", stories)
    write_story_tags_tsv(deposit / "story_tags.tsv", stories)
    write_tag_summary_tsv(deposit / "tag_women_summary.tsv", stories)
    print("  wrote story_women.tsv, story_tags.tsv, tag_women_summary.tsv")

    (deposit / "README.md").write_text(
        render_readme(args.version, summary, editions), encoding="utf-8")
    (deposit / "CHANGES.md").write_text(
        render_changes(args.version, summary), encoding="utf-8")
    (deposit / "zenodo.json").write_text(
        json.dumps(build_metadata(args.version, summary), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("  wrote README.md, CHANGES.md, zenodo.json")

    # Cross-check against the article's own numbers file.
    numbers = FIGURES / "numbers-for-article.md"
    if args.version == "v1" and numbers.exists():
        txt = numbers.read_text(encoding="utf-8")
        expect = [
            (str(summary["n_stories"]), "story total"),
            (f"{summary['any']} ({pct(summary['any'], summary['n_stories'])[:-1]}", "any count"),
            (f"{summary['char']} ({pct(summary['char'], summary['n_stories'])[:-1]}", "char count"),
        ]
        bad = [lbl for frag, lbl in expect if frag not in txt]
        if bad:
            print(f"  WARNING: not found in numbers-for-article.md: {', '.join(bad)}")
        else:
            print("  cross-check OK: matches numbers-for-article.md")


if __name__ == "__main__":
    main()
