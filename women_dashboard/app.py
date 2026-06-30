"""
Women in Hasidic Stories — Public Analysis Dashboard

Standalone Streamlit app, no authentication required.
Reads data directly from the edition XML files in this repository.

Deploy as a separate Streamlit Cloud app:
  Main file: women_dashboard/app.py
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd
import streamlit as st

# ── Path setup (works both locally and on Streamlit Cloud) ────────────────────

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
EDITIONS_DIR = os.path.join(PROJECT_DIR, "editions", "online")
APRIORI_PATH = os.path.join(PROJECT_DIR, "editions", "women-keywords-apriori.json")
EMPIRICAL_PATH = os.path.join(PROJECT_DIR, "editions", "women-keywords-empirical.json")
V2_TSV_PATH = os.path.join(PROJECT_DIR, "editions", "women-5tier-9editions-summary.tsv")
# Tag-audit provenance: (story, tag) pairs inserted by the LLM audit, so the
# dashboard can show RA-only vs RA+LLM-audited topics.
TAG_AUDIT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit")
LLM_VERDICT_FILES = [
    os.path.join(TAG_AUDIT_DIR, "llm-confirmed-verdicts.tsv"),          # old inserts
    os.path.join(TAG_AUDIT_DIR, "llm-confirmed-verdicts-patched.tsv"),  # patched adds
]
# Precision-audit removals — subtracted so the provenance set reflects the tags
# currently in the corpus, not every tag ever inserted.
LLM_REMOVAL_FILES = [
    os.path.join(TAG_AUDIT_DIR, "old-inserts-removals.tsv"),
    os.path.join(TAG_AUDIT_DIR, "patched-propagated-removals.tsv"),
]

# ── Data extraction (self-contained, no dependency on integration tool) ───────

TEI = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
# Set to True to show major/minor breakdown; False for binary yes/no
SHOW_MAJOR_MINOR = False

CATEGORY_ORDER = ["no", "minor", "major", "major+minor"] if SHOW_MAJOR_MINOR else ["no", "yes"]
CATEGORY_COLORS = {
    "no":          "#5B9BD5",
    "yes":         "#ED7D31",
    "minor":       "#ED7D31",
    "major":       "#A9D18E",
    "major+minor": "#FFD966",
}

EDITION_YEARS = {
    "Shivhei-Habesht": 1814,
    "Mifalot-HaZadikim": 1856,
    "Adat-Zadikim": 1864,
    "Shivhei-Harav": 1864,
    "Sipurei-Zadikim": 1864,
    "maase-zadikim": 1864,
    "Khal-Kdoshim": 1865,
    "PeerMikdoshim": 1865,
    "Khal-Hasidim": 1866,
    "Sipurei-Kdoshim": 1866,
    "tmimei_derech": 1871,
    "Shlosha-edrei-zon": 1874,
    "Sefer-Moraim-Gdolim": 1876,
    "shivheiZadikim": 1883,
    "Smichat-Moshe": 1886,
    "Kokhvei-Or": 1896,
    "Maasiot-Pliot": 1896,
    "Maasiot-veSihot-Zadikim": 1894,
    "Buzina_Denehora": 1879,
    "Hitgalut-HaZadikim": 1901,
    "MaasiyotUmaamarimYekarim": 1902,
    "MaasyiotMzadikeiYesodeiOlam": 1903,
    "SipureiAnsheiShem": 1903,
    "Sipurim-Nehmadim": 1903,
    "SipurimUmaamarimYekarim": 1903,
    "Dvarim-Yekarim": 1905,
    "Shemen-Hatov": 1905,
}


def _parse_ana(ana_value: str) -> List[str]:
    return [t.strip() for t in ana_value.split(";") if t.strip()]


def _derive_category(topics: List[str]) -> str:
    has_major = any(t == "women:major_character" for t in topics)
    has_minor = any(t == "women:minor_character" for t in topics)
    has_any_women = any(t.startswith("women:") and t != "women:collective" for t in topics)
    if SHOW_MAJOR_MINOR:
        if has_major and has_minor:
            return "major+minor"
        if has_major:
            return "major"
        if has_minor:
            return "minor"
        return "no"
    # Binary mode: any women:* token (mention_only / minor / catalyst / major) counts as "yes".
    return "yes" if has_any_women else "no"


def _collapse_category(cat: str) -> str:
    """Collapse major/minor into yes/no when SHOW_MAJOR_MINOR is False."""
    if SHOW_MAJOR_MINOR:
        return cat
    return "no" if cat == "no" else "yes"


@st.cache_data(show_spinner="Loading edition data…")
def load_stories() -> pd.DataFrame:
    rows = []
    for fname in sorted(os.listdir(EDITIONS_DIR)):
        if not fname.endswith(".xml"):
            continue
        edition = fname[:-4]
        try:
            tree = ET.parse(os.path.join(EDITIONS_DIR, fname))
        except ET.ParseError:
            continue
        root = tree.getroot()
        for div in root.iter(f"{{{TEI}}}div"):
            if div.get("type") != "story":
                continue
            story_id = div.get(XML_ID, "")
            topics = []
            for span in div.iter(f"{{{TEI}}}span"):
                ana = span.get("ana", "")
                topics.extend(_parse_ana(ana))
            topics = [t for t in topics if ":" in t and not t.startswith("TBD")]
            category = _collapse_category(_derive_category(topics))
            n_words = len("".join(div.itertext()).split())
            rows.append({
                "story_id": story_id,
                "edition": edition,
                "category": category,
                "topics": topics,
                "n_words": n_words,
            })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Loading Version 2 (5-tier) categorization…")
def load_v2_categories() -> dict:
    """Map story_id → binary 'yes'/'no' based on the 5-tier Claude TSV.
    Anything not 'no-women' (i.e. mention-only / minor / catalyst / major) counts as 'yes'.
    """
    if not os.path.exists(V2_TSV_PATH):
        return {}
    df = pd.read_csv(V2_TSV_PATH, sep="\t", dtype=str).fillna("")
    return {
        row["story_id"]: ("no" if row["new_claude_5tier"] == "no-women" else "yes")
        for _, row in df.iterrows()
    }


@st.cache_data(show_spinner=False)
def load_llm_inserted() -> set:
    """Set of (story_id, tag) pairs the LLM tag-audit added and that still
    survive in the corpus (verdict-file inserts minus precision-audit removals)."""
    def _pairs(paths):
        out = set()
        for path in paths:
            if not os.path.exists(path):
                continue
            d = pd.read_csv(path, sep="\t", dtype=str).fillna("")
            if {"story_id", "tag"}.issubset(d.columns):
                out.update(zip(d["story_id"], d["tag"]))
        return out
    return _pairs(LLM_VERDICT_FILES) - _pairs(LLM_REMOVAL_FILES)


def apply_provenance(base_df: pd.DataFrame, ra_only: bool) -> pd.DataFrame:
    """When ra_only, strip LLM-audit-inserted tags from each story's topics.
    `category` is derived from women:* tags (never in the verdict files), so it
    is unaffected — only the thematic topic co-occurrence changes."""
    if not ra_only:
        return base_df
    inserted = load_llm_inserted()
    if not inserted:
        return base_df
    out = base_df.copy()
    out["topics"] = [
        [t for t in tops if (sid, t) not in inserted]
        for sid, tops in zip(out["story_id"], out["topics"])
    ]
    return out


def build_v2_df(base_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of base_df whose `category` column is overridden by the V2 binary mapping.
    Stories missing from the TSV keep their original (XML-derived) category."""
    mapping = load_v2_categories()
    if not mapping:
        return base_df.copy()
    out = base_df.copy()
    out["category"] = out["story_id"].map(mapping).fillna(out["category"])
    return out


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _pie(ax, counts: pd.Series, title: str, total: int):
    colors = [CATEGORY_COLORS.get(c, "#ccc") for c in counts.index]
    ax.pie(
        counts,
        labels=counts.index,
        colors=colors,
        startangle=140,
        autopct=lambda p: f"{int(p * total / 100)} ({p:.1f}%)",
        textprops={"fontsize": 7},
        labeldistance=1.12,
        pctdistance=0.75,
    )
    ax.set_title(title, fontsize=10, pad=6)


def show_distribution(df: pd.DataFrame, edition_filter=None):
    if edition_filter:
        df_ed = df[df["edition"] == edition_filter]
        year = EDITION_YEARS.get(edition_filter, "")
        ed_label = f"{edition_filter} ({year})" if year else edition_filter
    else:
        df_ed = df
        ed_label = "all editions"

    all_counts = (
        df.groupby("category")["story_id"].nunique()
        .reindex(CATEGORY_ORDER, fill_value=0)
    )
    ed_counts = (
        df_ed.groupby("category")["story_id"].nunique()
        .reindex(CATEGORY_ORDER, fill_value=0)
    )
    all_counts = all_counts[all_counts > 0]
    ed_counts  = ed_counts[ed_counts > 0]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 2.8))
    handles = [Patch(color=CATEGORY_COLORS[c], label=c.capitalize()) for c in CATEGORY_ORDER]
    fig.legend(handles=handles, title="Women present", loc="upper center",
               ncol=len(CATEGORY_ORDER), fontsize=6, title_fontsize=6,
               bbox_to_anchor=(0.5, 1.0), frameon=False,
               handlelength=0.8, handleheight=0.6, handletextpad=0.3, columnspacing=0.6)
    plt.subplots_adjust(top=0.82)
    _pie(ax1, ed_counts, ed_label, int(ed_counts.sum()))
    _pie(ax2, all_counts, "All editions", int(all_counts.sum()))
    st.pyplot(fig)
    plt.close(fig)


def show_per_edition_bars(df: pd.DataFrame):
    grouped = (
        df.groupby(["edition", "category"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
    )
    year_order = sorted(grouped.index, key=lambda e: EDITION_YEARS.get(e, 9999))
    grouped = grouped.loc[year_order]
    pct_df = grouped.div(grouped.sum(axis=1), axis=0) * 100
    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]

    n = len(grouped)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(14, max(3.5, n * 0.35 + 1.2)),
        gridspec_kw={"width_ratios": [3, 2]},
    )
    grouped.plot(kind="barh", stacked=True, color=colors, ax=ax1)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.set_xlabel("Unique stories")
    ax1.set_title("Stories per edition — count")
    ax1.legend(title="Women present\nin stories", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)

    # Count labels inside each segment
    for container in ax1.containers:
        labels = [f"{int(bar.get_width())}" if bar.get_width() >= 8 else "" for bar in container]
        ax1.bar_label(container, labels=labels, label_type="center", fontsize=7, color="white")

    # Total stories per edition to the right of each bar
    totals = grouped.sum(axis=1)
    max_val = totals.max()
    ax1.set_xlim(0, max_val * 1.18)
    for j, total in enumerate(totals):
        ax1.text(total + max_val * 0.02, j, str(int(total)), va="center", ha="left", fontsize=8)

    pct_df.plot(kind="barh", stacked=True, color=colors, ax=ax2)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_xlabel("Percentage")
    ax2.set_title("Stories per edition — %")
    ax2.get_legend().remove()

    # Percentage labels inside each segment
    for container in ax2.containers:
        labels = [f"{bar.get_width():.0f}%" if bar.get_width() >= 8 else "" for bar in container]
        ax2.bar_label(container, labels=labels, label_type="center", fontsize=7, color="white")

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def show_topic_diff(df: pd.DataFrame, cat_a: str, cat_b: str):
    exploded = df.explode("topics")
    # exclude the women:* tags themselves — they define the category, not a meaningful co-occurrence
    exploded = exploded[~exploded["topics"].str.startswith("women:", na=False)]
    topic_counts = (
        exploded.groupby(["category", "topics"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    if cat_a not in topic_counts.index or cat_b not in topic_counts.index:
        st.info(f"Not enough annotated data for {cat_a} vs {cat_b}.")
        return

    diff = (topic_counts.loc[cat_a] - topic_counts.loc[cat_b]).sort_values(ascending=False)
    n = len(diff)
    keep = 25
    if n > keep * 2:
        idx = list(range(keep)) + list(range(n - keep, n))
        diff = diff.iloc[idx]

    fig, ax = plt.subplots(figsize=(14, 5))
    diff.plot(
        kind="bar", ax=ax,
        color=["#A9D18E" if v >= 0 else "#FF8080" for v in diff],
    )
    ax.set_title("Topic frequency difference: stories with vs stories without women", fontsize=11)
    ax.set_ylabel("Difference in story count")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    plt.subplots_adjust(left=0.08, bottom=0.3)
    st.pyplot(fig)
    plt.close(fig)


def show_topic_diff_normalized(df: pd.DataFrame, cat_a: str, cat_b: str,
                               min_stories: int = 5, keep: int = 25):
    """Length-normalized topic difference: tagged-stories per 1,000 words of
    text in each group, so the comparison isn't dominated by women stories
    being longer (and therefore accumulating more tags)."""
    words = df.groupby("category")["n_words"].sum()
    if cat_a not in words.index or cat_b not in words.index or \
            words.get(cat_a, 0) == 0 or words.get(cat_b, 0) == 0:
        st.info(f"Not enough annotated data for {cat_a} vs {cat_b}.")
        return
    exploded = df.explode("topics")
    exploded = exploded[~exploded["topics"].str.startswith("women:", na=False)]
    exploded = exploded[exploded["topics"].str.contains(":", na=False)]
    counts = (
        exploded.groupby(["category", "topics"])["story_id"]
        .nunique().unstack(fill_value=0)
    )
    if cat_a not in counts.index or cat_b not in counts.index:
        st.info(f"Not enough annotated data for {cat_a} vs {cat_b}.")
        return
    # tagged stories per 1,000 words within each group
    rate_a = counts.loc[cat_a] / words[cat_a] * 1000
    rate_b = counts.loc[cat_b] / words[cat_b] * 1000
    total = counts.loc[cat_a] + counts.loc[cat_b]
    diff = (rate_a - rate_b)[total >= min_stories].sort_values(ascending=False)
    if diff.empty:
        st.info("Not enough data.")
        return
    n = len(diff)
    if n > keep * 2:
        diff = diff.iloc[list(range(keep)) + list(range(n - keep, n))]

    fig, ax = plt.subplots(figsize=(14, 5))
    diff.plot(kind="bar", ax=ax,
              color=["#A9D18E" if v >= 0 else "#FF8080" for v in diff])
    ax.set_title("Length-normalized topic difference: women vs non-women "
                 "(tagged stories per 1,000 words)", fontsize=11)
    ax.set_ylabel("Δ tagged-stories / 1,000 words")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    plt.subplots_adjust(left=0.08, bottom=0.3)
    st.pyplot(fig)
    plt.close(fig)


def show_relative_frequency_all(df: pd.DataFrame, min_stories: int = 5):
    exploded = df.explode("topics").dropna(subset=["topics"])
    exploded = exploded[~exploded["topics"].str.startswith("women:", na=False)]
    exploded = exploded[exploded["topics"].str.contains(":", na=False)]

    counts = (
        exploded.groupby(["topics", "category"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
    )
    counts = counts[counts.sum(axis=1) >= min_stories]
    if counts.empty:
        st.info("Not enough data.")
        return

    rel = counts.div(counts.sum(axis=1), axis=0)
    sort_idx = rel.sort_values("yes", ascending=True).index
    counts = counts.loc[sort_idx]
    rel = rel.loc[sort_idx]

    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]
    fig, ax = plt.subplots(figsize=(12, max(4, len(rel) * 0.2 + 1.5)))
    rel.plot(kind="barh", stacked=True, color=colors, ax=ax)
    ax.set_xlabel("Relative frequency")
    ax.set_title("Women presence by topic — relative frequency (all topics)")
    ax.set_xlim(0, 1.18)
    ax.legend(title="Women present", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)

    # Count labels inside each segment
    for i, container in enumerate(ax.containers):
        cat = CATEGORY_ORDER[i]
        labels = [str(int(counts.iloc[j][cat])) if bar.get_width() >= 0.08 else ""
                  for j, bar in enumerate(container)]
        ax.bar_label(container, labels=labels, label_type="center", fontsize=7, color="white")

    # Total to the right of each bar
    totals = counts.sum(axis=1)
    for j, total in enumerate(totals):
        ax.text(1.01, j, str(int(total)), va="center", ha="left", fontsize=8)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def show_relative_frequency_by_category(df: pd.DataFrame, top_category: str, min_stories: int = 3):
    exploded = df.explode("topics").dropna(subset=["topics"])
    exploded = exploded[~exploded["topics"].str.startswith("women:", na=False)]
    exploded = exploded[exploded["topics"].str.startswith(top_category + ":", na=False)]

    counts = (
        exploded.groupby(["topics", "category"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
    )
    counts = counts[counts.sum(axis=1) >= min_stories]
    if counts.empty:
        st.info(f"No topics with ≥{min_stories} stories in '{top_category}'.")
        return

    rel = counts.div(counts.sum(axis=1), axis=0)
    sort_idx = rel.sort_values("yes", ascending=False).index
    counts = counts.loc[sort_idx]
    rel = rel.loc[sort_idx]
    clean_labels = [t.split(":", 1)[1].replace("_", " ") if ":" in t else t for t in rel.index]
    rel.index = clean_labels
    counts.index = clean_labels

    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]
    n = len(rel)
    fig, ax = plt.subplots(figsize=(max(9, n * 0.5 + 2), 4.5))
    rel.plot(kind="bar", stacked=True, color=colors, ax=ax)
    ax.set_ylabel("Relative frequency")
    ax.set_title(f"Women presence by sub-topic — {top_category}")
    ax.set_ylim(0, 1.15)
    ax.tick_params(axis="x", rotation=40, labelsize=8)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    ax.legend(title="Women present", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)

    # Count labels inside each segment
    for i, container in enumerate(ax.containers):
        cat = CATEGORY_ORDER[i]
        labels = [str(int(counts.iloc[j][cat])) if bar.get_height() >= 0.08 else ""
                  for j, bar in enumerate(container)]
        ax.bar_label(container, labels=labels, label_type="center", fontsize=7, color="white")

    # Total above each bar
    totals = counts.sum(axis=1)
    for j, total in enumerate(totals):
        ax.text(j, 1.02, str(int(total)), ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ── 5-tier "agency" layer (Refining women presence) ───────────────────────────

TIER_RAW = {"no-women": "no", "mention-only": "mention", "minor-character": "minor",
            "catalyst-character": "catalyst", "major-character": "major"}
TIER_ORDER = ["no", "mention", "minor", "catalyst", "major"]
TIER_LABEL = {"no": "no women", "mention": "mention-only", "minor": "minor",
              "catalyst": "catalyst", "major": "major"}
TIER_COLORS = {"no": "#D9D9D9", "mention": "#FFE0B2", "minor": "#FDB45C",
               "catalyst": "#F57C00", "major": "#BF360C"}
AGENT_TIERS = {"catalyst", "major"}
WOMEN_TIERS = ["mention", "minor", "catalyst", "major"]


@st.cache_data(show_spinner=False)
def load_tiers() -> dict:
    """story_id → {tier, collective(bool), confidence} from the 5-tier TSV."""
    out = {}
    if not os.path.exists(V2_TSV_PATH):
        return out
    d = pd.read_csv(V2_TSV_PATH, sep="\t", dtype=str).fillna("")
    for _, r in d.iterrows():
        out[r["story_id"]] = {
            "tier": TIER_RAW.get(r.get("new_claude_5tier", ""), "no"),
            "collective": str(r.get("new_collective", "")).strip().lower() == "true",
            "confidence": (r.get("new_confidence", "") or "").strip().lower(),
        }
    return out


def build_tier_df(base_df: pd.DataFrame, high_only: bool = False) -> pd.DataFrame:
    tiers = load_tiers()
    rows = base_df[base_df["story_id"].isin(tiers)].copy()
    rows["tier"] = rows["story_id"].map(lambda s: tiers[s]["tier"])
    rows["collective"] = rows["story_id"].map(lambda s: tiers[s]["collective"])
    rows["confidence"] = rows["story_id"].map(lambda s: tiers[s]["confidence"])
    if high_only:
        rows = rows[rows["confidence"] == "high"]
    return rows


def _explode_themes(tdf: pd.DataFrame) -> pd.DataFrame:
    e = tdf.explode("topics").dropna(subset=["topics"])
    e = e[e["topics"].str.contains(":", na=False)]
    return e[~e["topics"].str.startswith("women:", na=False)]


def show_agency_funnel(tdf: pd.DataFrame):
    counts = tdf["tier"].value_counts()
    total = len(tdf)
    present = int(sum(counts.get(t, 0) for t in WOMEN_TIERS))
    agents = int(sum(counts.get(t, 0) for t in AGENT_TIERS))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stories", total)
    c2.metric("Women present", present, f"{present/total*100:.0f}%")
    c3.metric("Women as agents", agents,
              f"{agents/present*100:.0f}% of present" if present else "")
    c4.metric("Women as major char.", int(counts.get("major", 0)))
    # single stacked horizontal composition bar
    fig, ax = plt.subplots(figsize=(12, 1.6))
    left = 0
    for t in TIER_ORDER:
        n = int(counts.get(t, 0))
        if not n:
            continue
        ax.barh(0, n, left=left, color=TIER_COLORS[t], edgecolor="white")
        if n >= total * 0.03:
            ax.text(left + n / 2, 0, f"{TIER_LABEL[t]}\n{n}", ha="center",
                    va="center", fontsize=8,
                    color="white" if t in ("catalyst", "major") else "#333")
        left += n
    ax.set_xlim(0, total); ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    ax.set_title("The agency gradient — most “women presence” is incidental",
                 fontsize=11)
    plt.tight_layout(); st.pyplot(fig); plt.close(fig)


def show_agency_by_topic(tdf: pd.DataFrame, min_stories: int = 6, top_n: int = 18):
    """For each theme, the tier composition among its women-present stories,
    sorted by agency share (catalyst+major). Shows where women ACT vs are named."""
    e = _explode_themes(tdf)
    e = e[e["tier"] != "no"]  # women-present only
    comp = (e.groupby(["topics", "tier"])["story_id"].nunique()
            .unstack(fill_value=0).reindex(columns=WOMEN_TIERS, fill_value=0))
    comp = comp[comp.sum(axis=1) >= min_stories]
    if comp.empty:
        st.info(f"No themes with ≥{min_stories} women-present stories.")
        return
    totals = comp.sum(axis=1)
    agency = (comp["catalyst"] + comp["major"]) / totals
    order = agency.sort_values(ascending=True).index
    if len(order) > top_n:
        order = list(order[:top_n // 2]) + list(order[-top_n // 2:])
    comp, totals = comp.loc[order], totals.loc[order]
    rel = comp.div(totals, axis=0)
    fig, ax = plt.subplots(figsize=(12, max(4, len(order) * 0.32 + 1)))
    left = pd.Series(0.0, index=order)
    for t in WOMEN_TIERS:
        ax.barh(range(len(order)), rel[t], left=left, color=TIER_COLORS[t],
                edgecolor="white", label=TIER_LABEL[t])
        left += rel[t]
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{i}  (n={int(totals[i])})" for i in order], fontsize=8)
    ax.set_xlim(0, 1); ax.set_xlabel("share of the theme's women-present stories")
    ax.set_title("Women's role by theme — bottom = women named, top = women act",
                 fontsize=11)
    ax.legend(ncol=4, bbox_to_anchor=(0.5, -0.08), loc="upper center", fontsize=8,
              frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout(); st.pyplot(fig); plt.close(fig)


def show_diachronic_agency(tdf: pd.DataFrame):
    """% women-present and % women-agent per edition, ordered by year."""
    rows = []
    for ed, g in tdf.groupby("edition"):
        n = len(g)
        if n < 5:
            continue
        present = (g["tier"] != "no").sum()
        agent = g["tier"].isin(AGENT_TIERS).sum()
        rows.append((ed, EDITION_YEARS.get(ed, 0), n,
                     present / n * 100, agent / n * 100))
    rows.sort(key=lambda r: r[1])
    if not rows:
        st.info("Not enough data.")
        return
    labels = [f"{r[0]}\n{r[1]}" for r in rows]
    x = range(len(rows))
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(x, [r[3] for r in rows], "-o", color="#ED7D31", label="% women present")
    ax.plot(x, [r[4] for r in rows], "-o", color="#BF360C", label="% women as agents")
    ax.fill_between(x, [r[4] for r in rows], color="#BF360C", alpha=0.08)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=8, rotation=30, ha="right")
    ax.set_ylabel("% of edition's stories"); ax.set_ylim(0, None)
    ax.set_title("Women presence vs women agency across the editions (by year)",
                 fontsize=11)
    for i, r in enumerate(rows):
        ax.annotate(f"n={r[2]}", (i, max(r[3], r[4])), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=7, color="#888")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout(); st.pyplot(fig); plt.close(fig)


def show_agency_length(tdf: pd.DataFrame):
    """Story length by tier — do substantive women roles need narrative space?"""
    data = [tdf[tdf["tier"] == t]["n_words"].values for t in TIER_ORDER]
    fig, ax = plt.subplots(figsize=(11, 4))
    bp = ax.boxplot(data, showfliers=False, patch_artist=True,
                    medianprops=dict(color="black"))
    ax.set_xticks(range(1, len(TIER_ORDER) + 1))
    ax.set_xticklabels([TIER_LABEL[t] for t in TIER_ORDER])
    for patch, t in zip(bp["boxes"], TIER_ORDER):
        patch.set_facecolor(TIER_COLORS[t])
    medians = [int(pd.Series(d).median()) if len(d) else 0 for d in data]
    for i, m in enumerate(medians, 1):
        ax.text(i, m, f" {m}w", va="bottom", ha="center", fontsize=8, color="#333")
    ax.set_ylabel("words per story"); ax.set_title(
        "Story length by women's role (median labelled)", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout(); st.pyplot(fig); plt.close(fig)


def show_collective_spotlight(tdf: pd.DataFrame, min_stories: int = 3):
    coll = tdf[tdf["collective"]]
    if coll.empty:
        st.info("No collective-women stories under the current filter.")
        return
    st.caption(f"{len(coll)} stories depict women as a **collective** "
               "(a group — wives, daughters, the women of a town) rather than individuals.")
    # tier split of collective vs individual women-present
    present = tdf[tdf["tier"] != "no"]
    indiv = present[~present["collective"]]
    rows = []
    for label, g in [("collective", coll[coll["tier"] != "no"]), ("individual", indiv)]:
        n = len(g)
        if n:
            rows.append({"group": f"{label} (n={n})",
                         **{TIER_LABEL[t]: (g["tier"] == t).sum() / n for t in WOMEN_TIERS}})
    c1, c2 = st.columns(2)
    if rows:
        comp = pd.DataFrame(rows).set_index("group")
        fig, ax = plt.subplots(figsize=(6, 2.4))
        comp.plot(kind="barh", stacked=True, ax=ax,
                  color=[TIER_COLORS[t] for t in WOMEN_TIERS])
        ax.set_xlim(0, 1); ax.set_xlabel("share"); ax.set_title("Role: collective vs individual", fontsize=10)
        ax.legend(ncol=4, bbox_to_anchor=(0.5, -0.25), loc="upper center", fontsize=7, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        plt.tight_layout(); c1.pyplot(fig); plt.close(fig)
    # top themes among collective stories
    e = _explode_themes(coll)
    top = e.groupby("topics")["story_id"].nunique().sort_values(ascending=False)
    top = top[top >= min_stories].head(12)
    if not top.empty:
        fig, ax = plt.subplots(figsize=(6, 2.4 + len(top) * 0.18))
        top.sort_values().plot(kind="barh", ax=ax, color="#F57C00")
        ax.set_xlabel("collective-women stories"); ax.set_title("Themes with collective women", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        plt.tight_layout(); c2.pyplot(fig); plt.close(fig)


def show_keyword_exhibit():
    st.subheader("Keyword vocabulary exhibit")
    st.markdown(
        """
        This exhibit compares two vocabularies:
        - **A priori**: words an AI suggests *before* reading the texts (what seems "obvious")
        - **Empirical**: words that actually distinguish women-tagged stories in the corpus

        The gap between them illustrates why keyword-based search is methodologically unreliable
        for identifying women in historical Hebrew/Yiddish narrative.
        """,
        unsafe_allow_html=False,
    )

    col_prior, col_emp = st.columns(2)

    with col_prior:
        st.markdown("### A priori keywords")
        st.caption("Generated by Claude before reading any texts")
        if os.path.exists(APRIORI_PATH):
            with open(APRIORI_PATH, encoding="utf-8") as f:
                apriori = json.load(f)
            for category, words in apriori.items():
                st.markdown(f"**{category}**")
                st.write(" · ".join(words))
        else:
            st.info("Not yet generated. Run the integration tool → Women Annotator → Generate keywords.")

    with col_emp:
        st.markdown("### Empirical vocabulary")
        st.caption("Words most associated with women-tagged stories (frequency ratio)")
        if os.path.exists(EMPIRICAL_PATH):
            with open(EMPIRICAL_PATH, encoding="utf-8") as f:
                empirical = json.load(f)
            rows = [
                {
                    "word": w,
                    "women stories": v["women"],
                    "no-women stories": v["no_women"],
                    "ratio": round(v["ratio"], 2),
                }
                for w, v in list(empirical.items())[:60]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=450, hide_index=True)
            tsv = pd.DataFrame(rows).to_csv(sep="\t", index=False)
            st.download_button("⬇ Export as TSV", tsv, file_name="women-empirical-vocab.tsv")
        else:
            st.info("Not yet generated. Run the integration tool → Women Annotator → Generate keywords.")

    if os.path.exists(APRIORI_PATH) and os.path.exists(EMPIRICAL_PATH):
        with open(APRIORI_PATH, encoding="utf-8") as f:
            apriori_data = json.load(f)
        with open(EMPIRICAL_PATH, encoding="utf-8") as f:
            empirical_data = json.load(f)

        apriori_flat = {w for words in apriori_data.values() for w in words}
        empirical_top = set(list(empirical_data.keys())[:100])

        only_apriori   = apriori_flat - empirical_top
        only_empirical = empirical_top - apriori_flat

        st.markdown("---")
        st.markdown("### The gap")
        c1, c2 = st.columns(2)
        c1.markdown("**Predicted but not prominent in texts**")
        c1.markdown("*(the LLM over-estimated these)*")
        c1.write(" · ".join(sorted(only_apriori)) or "—")
        c2.markdown("**Prominent in texts but not predicted**")
        c2.markdown("*(the LLM missed these)*")
        c2.write(" · ".join(sorted(only_empirical)) or "—")


# ── Page layout ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Women in Hasidic Stories",
    page_icon="📖",
    layout="wide",
)

st.markdown("""
<style>
/* Sticky tab bar */
[data-baseweb="tab-list"] {
    position: sticky;
    top: 2.875rem;
    background-color: white;
    z-index: 999;
    padding-bottom: 4px;
    border-bottom: 1px solid #e8e8e8;
}
</style>
""", unsafe_allow_html=True)

st.title("Women in Hasidic Stories")
st.markdown(
    "Analysis of 9 annotated editions from the [HASIDIC STORIES Project](https://hasidic-stories.org) corpus. "
    "Stories are categorized by the presence and centrality of women characters.\n\n"
    "To read the actual stories in each thematic category or sub-category, visit "
    "[hasidic-stories.org](https://hasidic-stories.org) and use the **Themes** filter together with "
    "the **Women** category filter to browse stories by topic."
)

_all = load_stories()
annotated_editions = sorted(_all[_all["category"] != "no"]["edition"].unique())
df = _all[_all["edition"].isin(annotated_editions)].copy()

# ── Tag provenance toggle ─────────────────────────────────────────────────────
_inserted = load_llm_inserted()
_n_audit_in_df = sum(
    1 for sid, tops in zip(df["story_id"], df["topics"]) for t in tops
    if (sid, t) in _inserted
)
with st.sidebar:
    st.markdown("### 🏷️ Tag provenance")
    _prov = st.radio(
        "Which thematic tags to count in the topic charts:",
        ["RA + LLM-audited", "RA only"],
        index=0,
        help="The RA annotator's original tags, optionally enriched by the LLM "
             "tag audit (multi-signal lexical+embedding+Sonnet/Opus). "
             "Switches the Topics charts only; the women-presence categories are "
             "unchanged. Removals from the precision audit apply once complete.",
    )
    st.caption(
        f"{len(_inserted):,} LLM-audited (story,tag) pairs in the corpus · "
        f"{_n_audit_in_df:,} fall in the displayed editions."
    )

ra_only = _prov == "RA only"
df = apply_provenance(df, ra_only)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dist, tab_ed, tab_topics, tab_bycat, tab_v2 = st.tabs([
    "📊 Distribution",
    "📚 By edition",
    "🏷️ Women and other Topics",
    "📂 By topic category",
    "👤 Refining women presence",
])

with tab_dist:
    col_title, col_table = st.columns([3, 1])
    col_title.subheader("Women presence in stories, across the editions")
    summary = (
        df.groupby("category")["story_id"].nunique()
        .reindex(CATEGORY_ORDER, fill_value=0)
        .reset_index()
        .rename(columns={"story_id": "stories", "category": "Women present"})
    )
    summary["% of total"] = (
        summary["stories"] / summary["stories"].sum() * 100
    ).round(1)
    col_table.dataframe(summary, use_container_width=True, hide_index=True)

    col_sel, _ = st.columns([1, 2])
    _default_ed = "Shivhei-Habesht"
    _opts = ["(all editions)"] + annotated_editions
    _default_idx = (_opts.index(_default_ed) if _default_ed in _opts else 1)
    edition_sel = col_sel.selectbox(
        "The left chart shows one edition; the right shows all 9 editions combined. "
        "Select an edition for comparison:",
        _opts,
        index=_default_idx,
        format_func=lambda e: e if e == "(all editions)"
            else f"{e} ({EDITION_YEARS[e]})" if e in EDITION_YEARS else e,
    )
    show_distribution(df, edition_sel if edition_sel != "(all editions)" else None)

with tab_ed:
    st.subheader("Per-edition breakdown")
    show_per_edition_bars(df)

with tab_topics:
    if ra_only:
        st.info("Showing **RA-only** tags — LLM-audited tags excluded from the topic charts.")
    else:
        st.success(f"Showing **RA + LLM-audited** tags — {_n_audit_in_df:,} audit-added "
                   "tag instances included. Switch to *RA only* in the sidebar to compare.")
    st.subheader("Topic frequency difference")
    st.markdown(
        "This chart shows which topics are **disproportionately associated** with women-present stories "
        "(green bars, above zero) versus stories without women (red bars, below zero). "
        "**The number on each bar is a story-count difference**: +15 means that topic appears in 15 more "
        "women-present stories than women-absent stories; −10 means it appears in 10 more women-absent stories."
    )
    show_topic_diff(df, "yes", "no")

    st.markdown("---")
    st.subheader("Length-normalized topic difference")
    st.markdown(
        "The chart above counts stories, so it is sensitive to **story length**: women-present "
        "stories are longer on average and accumulate more tags (especially after the LLM audit, "
        "which adds proportionally more to longer stories). This chart controls for that by "
        "measuring **tagged stories per 1,000 words** of text within each group, then taking the "
        "difference. Topics that stay strongly positive here are women-associated *beyond* what "
        "story length alone would explain."
    )
    show_topic_diff_normalized(df, "yes", "no")

    st.markdown("---")
    st.subheader("Women presence by topic — relative frequency")
    st.markdown(
        "Each bar represents one topic. The bar shows the **proportion** of stories tagged with that topic "
        "in which women are present (orange) versus absent (blue). "
        "Topics are sorted from highest to lowest women presence. "
        "Only topics appearing in at least 5 stories are included. "
        "Compare with the chart above: a topic may have a large absolute difference yet a modest relative proportion, "
        "or vice versa, depending on how common the topic is overall."
    )
    show_relative_frequency_all(df)

with tab_bycat:
    st.subheader("Women presence by topic category")
    st.markdown(
        "The corpus topics are organized into thematic categories (e.g. *practice*, *social relations*, "
        "*supernatural*, *ethics*). Select a category below to see how women presence varies "
        "across its sub-topics. "
        "Bars are sorted from highest to lowest proportion of women-present stories. "
        "Sub-topics with fewer than 3 stories are excluded."
    )
    # Only include categories that have at least one sub-topic with ≥3 stories
    all_topic_vals = [t for row in df["topics"] for t in (row if isinstance(row, list) else [])]
    from collections import Counter
    subtopic_counts = Counter(t for t in all_topic_vals if ":" in t and not t.startswith("women:"))
    top_cats = sorted({t.split(":")[0] for t, n in subtopic_counts.items() if n >= 3})
    if top_cats:
        _default_cat = "practice" if "practice" in top_cats else top_cats[0]
        cat_sel = st.selectbox(
            "Topic category",
            top_cats,
            index=top_cats.index(_default_cat),
            key="topic_cat_sel",
        )
        show_relative_frequency_by_category(df, cat_sel)

with tab_v2:
    st.subheader("Refining women presence — the agency gradient")
    st.markdown(
        "The other tabs use a **binary** women / no-women split (the collapse of a finer scheme). "
        "But binary presence hides *what women actually do*. The "
        "[5-tier annotation](https://hasidic-stories.org) "
        "(`editions/women-5tier-9editions-summary.tsv`, 652 stories) grades each story:\n\n"
        "- **no women** — no women in the story.\n"
        "- **mention-only** — a woman is named or referred to, but does nothing in the plot.\n"
        "- **minor** — a woman acts, but at the margins of the story.\n"
        "- **catalyst** — a woman drives the plot without being its main subject (the spark).\n"
        "- **major** — a woman is a central character.\n\n"
        "Collapsed to yes/no these tabs match the binary view exactly. The charts below instead "
        "**keep the gradient**, to ask: *in which stories, themes, and periods do women act rather "
        "than merely appear?* **mention-only + minor are presence; catalyst + major are agency.**"
    )

    high_only = st.toggle(
        "High-confidence annotations only",
        value=False,
        help="Restrict to the 499 stories the 5-tier annotator marked high-confidence.",
    )
    tdf = build_tier_df(df, high_only=high_only)

    st.markdown("### 1 · The agency gradient")
    st.caption("Most “women presence” is incidental: of all women-present stories, only ~30% give a "
               "woman agency (catalyst or major).")
    show_agency_funnel(tdf)

    st.markdown("---")
    st.markdown("### 2 · Women's role by theme")
    st.caption("For each theme, the composition of its women-present stories across the gradient, sorted "
               "by agency share. Themes at the **bottom** feature women who are merely named; themes at "
               "the **top** feature women who act.")
    show_agency_by_topic(tdf)

    st.markdown("---")
    st.markdown("### 3 · Agency across time")
    st.caption("Does women's *presence* and *agency* shift across the 19th-century editions? Each point is "
               "an edition, ordered by publication year.")
    show_diachronic_agency(tdf)

    st.markdown("---")
    st.markdown("### 4 · Role and story length")
    st.caption("Do substantive women roles need narrative space? Story length by tier — also a control for "
               "the length confound behind the raw topic-association charts.")
    show_agency_length(tdf)

    st.markdown("---")
    st.markdown("### 5 · Women as a collective")
    show_collective_spotlight(tdf)
