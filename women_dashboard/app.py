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
    if has_major and has_minor:
        return "major+minor"
    if has_major:
        return "major"
    if has_minor:
        return "minor"
    return "no"


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

    fig, ax = plt.subplots(figsize=(12, 4))
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
    rel = rel.sort_values("yes", ascending=True)

    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]
    fig, ax = plt.subplots(figsize=(12, max(4, len(rel) * 0.2 + 1.5)))
    rel.plot(kind="barh", stacked=True, color=colors, ax=ax)
    ax.set_xlabel("Relative frequency")
    ax.set_title("Relative frequency of women presence — all topics")
    ax.set_xlim(0, 1)
    ax.legend(title="Women present", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
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
    rel = rel.sort_values("yes", ascending=False)
    rel.index = [t.split(":", 1)[1].replace("_", " ") if ":" in t else t for t in rel.index]

    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]
    n = len(rel)
    fig, ax = plt.subplots(figsize=(max(8, n * 0.45 + 1.5), 4))
    rel.plot(kind="bar", stacked=True, color=colors, ax=ax)
    ax.set_ylabel("Relative frequency")
    ax.set_title(f"Relative frequency of women presence — {top_category}")
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.legend(title="Women present", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
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
    "Stories are categorized by the presence and centrality of women characters."
)

_all = load_stories()
annotated_editions = sorted(_all[_all["category"] != "no"]["edition"].unique())
df = _all[_all["edition"].isin(annotated_editions)].copy()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dist, tab_ed, tab_topics = st.tabs([
    "📊 Distribution",
    "📚 By edition",
    "🏷️ Topics",
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
    st.subheader("Relative frequency of women presence — all topics")
    st.caption("Topics sorted by proportion of stories with women present (highest at top). Min. 5 stories per topic.")
    show_relative_frequency_all(df)

    st.markdown("---")
    st.subheader("By topic category")
    all_topic_vals = [t for row in df["topics"] for t in (row if isinstance(row, list) else [])]
    top_cats = sorted({t.split(":")[0] for t in all_topic_vals
                       if ":" in t and not t.startswith("women:")})
    if top_cats:
        cat_sel = st.selectbox("Select topic category", top_cats, key="topic_cat_sel")
        show_relative_frequency_by_category(df, cat_sel)

    st.markdown("---")
    st.subheader("Topic frequency difference (yes vs no)")
    st.caption("Green = topics more frequent in women-present stories. Red = more frequent in stories without women.")
    show_topic_diff(df, "yes", "no")
