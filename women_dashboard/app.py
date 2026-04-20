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
import pandas as pd
import streamlit as st

# ── Path setup (works both locally and on Streamlit Cloud) ────────────────────

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
EDITIONS_DIR = os.path.join(PROJECT_DIR, "editions", "online")
APRIORI_PATH = os.path.join(PROJECT_DIR, "editions", "women-keywords-apriori.json")
EMPIRICAL_PATH = os.path.join(PROJECT_DIR, "editions", "women-keywords-empirical.json")

# ── Data extraction (self-contained, no dependency on integration tool) ───────

TEI = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
# Set to True to show major/minor breakdown; False for binary yes/no
SHOW_MAJOR_MINOR = False

CATEGORY_ORDER = ["no-women", "minor", "major", "major+minor"] if SHOW_MAJOR_MINOR else ["no-women", "women"]
CATEGORY_COLORS = {
    "no-women":    "#5B9BD5",
    "women":       "#ED7D31",
    "minor":       "#ED7D31",
    "major":       "#A9D18E",
    "major+minor": "#FFD966",
}


def _parse_ana(ana_value: str) -> List[str]:
    return [t.strip() for t in ana_value.split(";") if t.strip()]


def _derive_category(topics: List[str]) -> str:
    has_major = any(t == "women:major_character" for t in topics)
    has_minor = any(t == "women:minor_character" for t in topics)
    if has_major and has_minor:
        return "major+minor"
    if has_major:
        return "major"
    if has_minor:
        return "minor"
    return "no-women"


def _collapse_category(cat: str) -> str:
    """Collapse major/minor into single 'women' label when SHOW_MAJOR_MINOR is False."""
    if SHOW_MAJOR_MINOR:
        return cat
    return "no-women" if cat == "no-women" else "women"


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
            rows.append({
                "story_id": story_id,
                "edition": edition,
                "category": category,
                "topics": topics,
            })
    return pd.DataFrame(rows)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _pie(ax, counts: pd.Series, title: str, total: int):
    colors = [CATEGORY_COLORS.get(c, "#ccc") for c in counts.index]
    ax.pie(
        counts,
        labels=counts.index,
        colors=colors,
        startangle=140,
        autopct=lambda p: f"{int(p * total / 100)} ({p:.1f}%)",
        textprops={"fontsize": 9},
    )
    ax.set_title(title, fontsize=11, pad=10)


def show_distribution(df: pd.DataFrame, edition_filter=None):
    if edition_filter:
        df_ed = df[df["edition"] == edition_filter]
        ed_label = edition_filter
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

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    _pie(ax1, all_counts, "All editions", int(all_counts.sum()))
    _pie(ax2, ed_counts, ed_label, int(ed_counts.sum()))
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def show_per_edition_bars(df: pd.DataFrame):
    grouped = (
        df.groupby(["edition", "category"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
    )
    grouped = grouped.sort_values("no-women", ascending=True)
    pct = grouped.div(grouped.sum(axis=1), axis=0) * 100
    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]

    n = len(grouped)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(16, max(5, n * 0.45 + 2)),
        gridspec_kw={"width_ratios": [3, 2]},
    )
    grouped.plot(kind="barh", stacked=True, color=colors, ax=ax1)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.set_xlabel("Unique stories")
    ax1.set_title("Stories per edition — count")
    ax1.legend(title="Category", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)

    pct.plot(kind="barh", stacked=True, color=colors, ax=ax2)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_xlabel("Percentage")
    ax2.set_title("Stories per edition — %")
    ax2.get_legend().remove()

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def show_topic_diff(df: pd.DataFrame, cat_a: str, cat_b: str):
    exploded = df.explode("topics")
    # exclude the women:* tags themselves — they define the category, not a meaningful co-occurrence
    exploded = exploded[~exploded["topics"].str.startswith("women:")]
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
    ax.set_title(f"Topic frequency difference: {cat_a} vs {cat_b}", fontsize=11)
    ax.set_ylabel("Difference in story count")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


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

st.title("Women in Hasidic Stories")
st.markdown(
    "Analysis of 9 annotated editions from the [Hasidigital](https://hasidic-stories.org) corpus. "
    "Stories are categorized by the presence and centrality of women characters."
)

_all = load_stories()
annotated_editions = sorted(_all[_all["category"] != "no-women"]["edition"].unique())
df = _all[_all["edition"].isin(annotated_editions)].copy()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dist, tab_ed, tab_topics, tab_keywords = st.tabs([
    "📊 Distribution",
    "📚 By edition",
    "🏷️ Topic differences",
    "🔑 Keyword exhibit",
])

with tab_dist:
    st.subheader("Women-in-story distribution")
    col_sel, _ = st.columns([1, 2])
    edition_sel = col_sel.selectbox(
        "Compare overall vs:",
        ["(all editions)"] + annotated_editions,
    )
    show_distribution(df, edition_sel if edition_sel != "(all editions)" else None)

    st.markdown("---")
    summary = (
        df.groupby("category")["story_id"].nunique()
        .reindex(CATEGORY_ORDER, fill_value=0)
        .reset_index()
        .rename(columns={"story_id": "unique stories"})
    )
    summary["% of total"] = (
        summary["unique stories"] / summary["unique stories"].sum() * 100
    ).round(1)
    st.dataframe(summary, use_container_width=False, hide_index=True)

with tab_ed:
    st.subheader("Per-edition breakdown")
    show_per_edition_bars(df)

with tab_topics:
    st.subheader("Topic frequency differences")
    st.markdown(
        "Green bars = topics more frequent in the first category. "
        "Red = more frequent in the second. Middle bars removed for clarity."
    )
    if SHOW_MAJOR_MINOR:
        pairs = [("major", "no-women"), ("minor", "no-women"), ("major", "minor")]
    else:
        pairs = [("women", "no-women")]
    labels = [f"{a} vs {b}" for a, b in pairs]
    if len(pairs) > 1:
        choice = st.radio("Comparison", labels, horizontal=True)
        cat_a, cat_b = pairs[labels.index(choice)]
    else:
        cat_a, cat_b = pairs[0]
    show_topic_diff(df, cat_a, cat_b)

with tab_keywords:
    show_keyword_exhibit()
