"""
Women Analysis dashboard — reproduces the notebook charts from XML data directly.
Includes: distribution pies, per-edition bar charts, topic frequency differences,
and the keyword vocabulary exhibit (a priori vs empirical).
"""
import json
import os

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from config import WOMEN_KEYWORDS_APRIORI, WOMEN_KEYWORDS_EMPIRICAL
from women_data import load_stories, extract_empirical_vocabulary

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


@st.cache_data(show_spinner="Loading edition data…")
def _get_stories():
    return load_stories()


def _df(stories):
    return pd.DataFrame(stories)[["story_id", "edition", "category", "topics"]]


# ── Charts ────────────────────────────────────────────────────────────────────

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
    ax.set_title(title, fontsize=10, pad=8)


def _show_distribution(df, edition_filter=None):
    if edition_filter:
        df_ed = df[df["edition"] == edition_filter]
    else:
        df_ed = df

    all_counts = df.groupby("category")["story_id"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
    ed_counts  = df_ed.groupby("category")["story_id"].nunique().reindex(CATEGORY_ORDER, fill_value=0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    _pie(ax1, all_counts[all_counts > 0], "All editions", int(all_counts.sum()))
    label = edition_filter or "selected edition"
    _pie(ax2, ed_counts[ed_counts > 0], label, int(ed_counts.sum()))
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _show_per_edition_bars(df):
    grouped = (
        df.groupby(["edition", "category"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
    )
    year_order = sorted(grouped.index, key=lambda e: EDITION_YEARS.get(e, 9999))
    grouped = grouped.loc[year_order]
    pct = grouped.div(grouped.sum(axis=1), axis=0) * 100

    colors = [CATEGORY_COLORS[c] for c in CATEGORY_ORDER]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, max(5, len(grouped) * 0.5 + 2)),
                                    gridspec_kw={"width_ratios": [3, 2]})

    grouped.plot(kind="barh", stacked=True, color=colors, ax=ax1)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.set_xlabel("Unique stories")
    ax1.set_title("Stories per edition (count)")
    ax1.legend(title="Category", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)

    pct.plot(kind="barh", stacked=True, color=colors, ax=ax2)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_xlabel("Percentage")
    ax2.set_title("Stories per edition (%)")
    ax2.get_legend().remove()

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _show_topic_diff(df, cat_a: str, cat_b: str):
    exploded = df.explode("topics")
    exploded = exploded[~exploded["topics"].str.startswith("women:", na=False)]
    topic_counts = (
        exploded.groupby(["category", "topics"])["story_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    if cat_a not in topic_counts.index or cat_b not in topic_counts.index:
        st.info(f"Not enough data for {cat_a} vs {cat_b}.")
        return

    diff = (topic_counts.loc[cat_a] - topic_counts.loc[cat_b]).sort_values(ascending=False)
    n = len(diff)
    keep = 25
    if n > keep * 2:
        idx = list(range(keep)) + list(range(n - keep, n))
        diff = diff.iloc[idx]

    fig, ax = plt.subplots(figsize=(14, 5))
    diff.plot(kind="bar", ax=ax, color=["#A9D18E" if v >= 0 else "#FF7F7F" for v in diff])
    ax.set_title(f"Topic frequency: {cat_a} vs {cat_b}")
    ax.set_ylabel("Difference in story count")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ── Keyword exhibit ───────────────────────────────────────────────────────────

def _show_keyword_exhibit(stories):
    st.subheader("Keyword vocabulary exhibit")
    st.caption(
        "A priori: what keywords Claude would suggest before reading the texts. "
        "Empirical: words that actually distinguish women-tagged stories. "
        "The gap between the two illustrates why keyword search is insufficient."
    )

    col_prior, col_emp = st.columns(2)

    with col_prior:
        st.markdown("**A priori keywords** (LLM-suggested)")
        if os.path.exists(WOMEN_KEYWORDS_APRIORI):
            with open(WOMEN_KEYWORDS_APRIORI, encoding="utf-8") as f:
                apriori = json.load(f)
            for category, words in apriori.items():
                st.markdown(f"*{category}*")
                st.write(" · ".join(words))
        else:
            st.info("Not yet generated. Use the Women Annotator page → Generate keywords.")

    with col_emp:
        st.markdown("**Empirical vocabulary** (top discriminating words)")
        if os.path.exists(WOMEN_KEYWORDS_EMPIRICAL):
            with open(WOMEN_KEYWORDS_EMPIRICAL, encoding="utf-8") as f:
                empirical = json.load(f)
            rows = [
                {"word": w, "in women-stories": v["women"], "in no-women": v["no_women"],
                 "ratio": round(v["ratio"], 2)}
                for w, v in list(empirical.items())[:60]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)
            tsv = pd.DataFrame(rows).to_csv(sep="\t", index=False)
            st.download_button("Export TSV", tsv, file_name="women-empirical-vocab.tsv")
        else:
            st.info("Not yet generated. Use the Women Annotator page → Generate keywords.")

    if os.path.exists(WOMEN_KEYWORDS_APRIORI) and os.path.exists(WOMEN_KEYWORDS_EMPIRICAL):
        with open(WOMEN_KEYWORDS_APRIORI, encoding="utf-8") as f:
            apriori_data = json.load(f)
        with open(WOMEN_KEYWORDS_EMPIRICAL, encoding="utf-8") as f:
            empirical_data = json.load(f)

        apriori_flat = {w for words in apriori_data.values() for w in words}
        empirical_top = set(list(empirical_data.keys())[:100])

        only_apriori = apriori_flat - empirical_top
        only_empirical = empirical_top - apriori_flat

        st.markdown("---")
        c1, c2 = st.columns(2)
        c1.markdown("**Predicted but rare in texts** (over-estimated by LLM)")
        c1.write(" · ".join(sorted(only_apriori)) or "—")
        c2.markdown("**Common in texts but not predicted** (under-estimated by LLM)")
        c2.write(" · ".join(sorted(only_empirical)) or "—")


# ── Main page ─────────────────────────────────────────────────────────────────

st.title("Women in Hasidic Stories — Analysis")

stories = _get_stories()
df = _df(stories)

annotated_editions = sorted({s["edition"] for s in stories if s["category"] != "no-women"})
df = df[df["edition"].isin(annotated_editions)].copy()

if not SHOW_MAJOR_MINOR:
    df["category"] = df["category"].apply(lambda c: "no-women" if c == "no-women" else "women")

tab_dist, tab_edition, tab_topics, tab_keywords = st.tabs(
    ["Distribution", "Per-edition", "Topic differences", "Keyword exhibit"]
)

with tab_dist:
    st.subheader("Women-in-story distribution")
    col1, col2 = st.columns([1, 2])
    with col1:
        edition_sel = st.selectbox(
            "Compare against edition",
            ["(all editions)"] + annotated_editions,
        )
    _show_distribution(df, edition_sel if edition_sel != "(all editions)" else None)

    st.markdown("---")
    st.subheader("Summary")
    summary = (
        df.groupby("category")["story_id"].nunique()
        .reindex(CATEGORY_ORDER, fill_value=0)
        .reset_index()
        .rename(columns={"story_id": "unique stories"})
    )
    summary["% of total"] = (summary["unique stories"] / summary["unique stories"].sum() * 100).round(1)
    st.dataframe(summary, use_container_width=True, hide_index=True)

with tab_edition:
    st.subheader("Per-edition breakdown")
    _show_per_edition_bars(df)

with tab_topics:
    st.subheader("Topic frequency differences")
    if SHOW_MAJOR_MINOR:
        pairs = [("major", "no-women"), ("minor", "no-women"), ("major", "minor")]
    else:
        pairs = [("women", "no-women")]
    pair_labels = [f"{a} vs {b}" for a, b in pairs]
    if len(pairs) > 1:
        choice = st.radio("Comparison", pair_labels, horizontal=True)
        cat_a, cat_b = pairs[pair_labels.index(choice)]
    else:
        cat_a, cat_b = pairs[0]
    _show_topic_diff(df, cat_a, cat_b)

with tab_keywords:
    _show_keyword_exhibit(stories)
