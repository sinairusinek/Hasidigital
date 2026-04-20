"""
Women Annotator — two-mode page:

Mode A (Evaluate): 9 annotated editions — compare human vs Claude vs Gemini,
  show disagreements, allow revising annotation, refine criteria.

Mode B (Annotate): 18 unannotated editions — run both models, auto-accept
  where they agree, queue disagreements for brief human review.
"""
import json
import os
from collections import Counter

import pandas as pd
import streamlit as st

from config import WOMEN_KEYWORDS_APRIORI, WOMEN_KEYWORDS_EMPIRICAL
from women_data import load_stories, update_women_tag, extract_empirical_vocabulary
from women_llm import (
    annotate_batch, annotate_story, get_cached_results,
    generate_apriori_keywords, load_criteria, save_criteria,
    criteria_hash, update_human_category, DEFAULT_CRITERIA,
)

CATEGORIES = ["no-women", "minor", "major", "major+minor"]
HEBREW_KEYWORDS = [
    "אשה", "נשים", "אשתו", "אמו", "בתו", "כלה", "אלמנה", "בת", "אשת", "נשי",
    "מטרונה", "גבירה", "רעיה", "צניעות", "בנות", "ביתו",
]


@st.cache_data(show_spinner="Loading edition data…")
def _get_stories():
    return load_stories()


def _stories_by_edition(stories, edition):
    return [s for s in stories if s["edition"] == edition]


def _keyword_highlight(text: str) -> str:
    """Wrap Hebrew keywords in markdown bold for display."""
    for kw in HEBREW_KEYWORDS:
        text = text.replace(kw, f"**{kw}**")
    return text


def _agreement_badge(row: dict) -> str:
    cc = row.get("claude_category", "")
    gc = row.get("gemini_category", "")
    hc = row.get("human_category", "")
    if not cc and not gc:
        return "⬜ not run"
    if cc == gc:
        if hc and cc != hc:
            return "🔶 models agree, differ from human"
        return "✅ agree"
    return "❌ disagree"


# ── Criteria editor (sidebar) ─────────────────────────────────────────────────

def _criteria_sidebar():
    with st.sidebar.expander("📋 Annotation criteria", expanded=False):
        current = load_criteria()
        new_text = st.text_area("Edit criteria prompt", value=current, height=300,
                                key="criteria_editor")
        col1, col2 = st.columns(2)
        if col1.button("Save criteria", use_container_width=True):
            save_criteria(new_text)
            st.success("Saved.")
            st.rerun()
        if col2.button("Reset to default", use_container_width=True):
            save_criteria(DEFAULT_CRITERIA)
            st.rerun()
        chash = criteria_hash(load_criteria())
        st.caption(f"Criteria hash: `{chash}`")


# ── Keyword generation ────────────────────────────────────────────────────────

def _keyword_section(stories):
    with st.expander("🔑 Generate keyword vocabulary files"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**A priori keywords** (LLM-suggested, before reading texts)")
            if st.button("Generate a priori keywords (Claude)", use_container_width=True):
                with st.spinner("Asking Claude…"):
                    data = generate_apriori_keywords()
                with open(WOMEN_KEYWORDS_APRIORI, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                st.success(f"Saved to {WOMEN_KEYWORDS_APRIORI}")
            if os.path.exists(WOMEN_KEYWORDS_APRIORI):
                with open(WOMEN_KEYWORDS_APRIORI, encoding="utf-8") as f:
                    st.json(json.load(f))
        with c2:
            st.markdown("**Empirical vocabulary** (from annotated editions)")
            if st.button("Compute empirical vocabulary", use_container_width=True):
                with st.spinner("Extracting…"):
                    vocab = extract_empirical_vocabulary(stories)
                    # keep top 200 by ratio
                    top = dict(list(vocab.items())[:200])
                with open(WOMEN_KEYWORDS_EMPIRICAL, "w", encoding="utf-8") as f:
                    json.dump(top, f, ensure_ascii=False, indent=2)
                st.success(f"Saved to {WOMEN_KEYWORDS_EMPIRICAL}")
            if os.path.exists(WOMEN_KEYWORDS_EMPIRICAL):
                with open(WOMEN_KEYWORDS_EMPIRICAL, encoding="utf-8") as f:
                    emp = json.load(f)
                rows = [{"word": w, "women": v["women"], "no_women": v["no_women"],
                         "ratio": round(v["ratio"], 2)} for w, v in list(emp.items())[:20]]
                st.dataframe(pd.DataFrame(rows), hide_index=True)


# ── Story detail panel ────────────────────────────────────────────────────────

def _story_detail(story: dict, result: dict, mode: str):
    """Show full story text + model results + decision panel."""
    st.markdown(f"### {story['story_id']}")
    st.caption(f"Edition: {story['edition']}  |  Human annotation: **{story['category']}**")

    with st.expander("Story text", expanded=True):
        # RTL Hebrew display
        text = story.get("text", "")
        highlighted = _keyword_highlight(text)
        st.markdown(
            f'<div dir="rtl" style="font-size:1.05em; line-height:1.7">{highlighted}</div>',
            unsafe_allow_html=True,
        )

    col_c, col_g = st.columns(2)
    with col_c:
        st.markdown("**Claude**")
        st.markdown(f"Category: `{result.get('claude_category', '—')}`")
        st.caption(result.get("claude_reasoning", ""))
    with col_g:
        st.markdown("**Gemini**")
        st.markdown(f"Category: `{result.get('gemini_category', '—')}`")
        st.caption(result.get("gemini_reasoning", ""))

    st.markdown("---")
    st.markdown("**Your decision**")
    current = story["category"] if mode == "evaluate" else (
        result.get("claude_category") or result.get("gemini_category") or "no-women"
    )
    chosen = st.radio(
        "Category",
        CATEGORIES,
        index=CATEGORIES.index(current) if current in CATEGORIES else 0,
        horizontal=True,
        key=f"decision_{story['story_id']}",
    )
    if st.button("Save decision", key=f"save_{story['story_id']}"):
        ok = update_women_tag(story["xml_path"], story["story_id"], chosen)
        update_human_category(story["story_id"], chosen)
        if ok:
            st.success(f"Updated XML: {story['story_id']} → {chosen}")
        else:
            st.warning("No change made (category already set or story not found).")
        # clear cache so list refreshes
        _get_stories.clear()

    # Re-run LLM with current criteria
    if st.button("Re-run LLM on this story", key=f"rerun_{story['story_id']}"):
        criteria = load_criteria()
        with st.spinner("Calling models…"):
            r = annotate_story(story, criteria=criteria, force=True)
        st.rerun()


# ── Mode A: Evaluate ──────────────────────────────────────────────────────────

def _mode_evaluate(stories):
    annotated_editions = sorted({s["edition"] for s in stories if s["category"] != "no-women"})

    st.subheader("Mode A — Evaluate annotated editions")
    st.caption("Run Claude + Gemini on the 9 benchmark editions. Disagreements surface for review.")

    edition = st.selectbox("Edition", annotated_editions, key="eval_edition")
    ed_stories = _stories_by_edition(stories, edition)

    criteria = load_criteria()
    chash = criteria_hash(criteria)

    col_run, col_filter = st.columns([1, 2])
    with col_run:
        if st.button("▶ Run both models on this edition", use_container_width=True):
            progress = st.progress(0)
            def _cb(i, total):
                progress.progress(i / total)
            with st.spinner("Annotating…"):
                annotate_batch(ed_stories, criteria=criteria,
                               progress_callback=_cb)
            progress.empty()
            st.rerun()

    cached = {r["story_id"]: r for r in get_cached_results(edition)}
    rows = []
    for s in ed_stories:
        r = cached.get(s["story_id"], {})
        rows.append({
            "story_id": s["story_id"],
            "human": s["category"],
            "claude": r.get("claude_category", ""),
            "gemini": r.get("gemini_category", ""),
            "status": _agreement_badge(r),
        })

    df = pd.DataFrame(rows)

    with col_filter:
        show = st.radio("Show", ["All", "Disagreements only", "Models agree, differ from human"],
                        horizontal=True, key="eval_filter")

    if show == "Disagreements only":
        df = df[df["status"].str.startswith("❌")]
    elif show == "Models agree, differ from human":
        df = df[df["status"].str.startswith("🔶")]

    # Agreement summary
    total = len(rows)
    agree = sum(1 for r in rows if r["status"].startswith("✅"))
    st.caption(f"Total: {total}  |  ✅ Full agreement: {agree}  |  Not yet run: {sum(1 for r in rows if '⬜' in r['status'])}")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(400, len(df) * 35 + 40),
    )

    selected = st.selectbox(
        "Select story to review",
        ["—"] + list(df["story_id"]),
        key="eval_select",
    )
    if selected and selected != "—":
        story = next((s for s in ed_stories if s["story_id"] == selected), None)
        result = cached.get(selected, {})
        if story:
            _story_detail(story, result, mode="evaluate")


# ── Mode B: Annotate ──────────────────────────────────────────────────────────

def _mode_annotate(stories):
    all_editions = sorted({s["edition"] for s in stories})
    annotated = {s["edition"] for s in stories if s["category"] != "no-women"}
    unannotated = sorted(all_editions - annotated)

    st.subheader("Mode B — Annotate unannotated editions")
    st.caption(
        "Run Claude + Gemini. Where both agree → auto-accepted. "
        "Where they disagree → brief human review."
    )

    edition = st.selectbox("Edition", unannotated, key="ann_edition")
    ed_stories = _stories_by_edition(stories, edition)

    criteria = load_criteria()
    chash = criteria_hash(criteria)

    col_run, col_models = st.columns([1, 1])
    with col_run:
        if st.button("▶ Run both models on this edition", use_container_width=True):
            progress = st.progress(0)
            def _cb(i, total):
                progress.progress(i / total)
            with st.spinner(f"Annotating {len(ed_stories)} stories…"):
                results = annotate_batch(ed_stories, criteria=criteria,
                                         progress_callback=_cb)
            # Auto-write agreed results to XML
            for s, r in zip(ed_stories, results):
                if r.get("agreement") == "agree":
                    cat = r["claude_category"]
                    update_women_tag(s["xml_path"], s["story_id"], cat)
                    update_human_category(s["story_id"], cat)
            progress.empty()
            _get_stories.clear()
            st.rerun()

    cached = {r["story_id"]: r for r in get_cached_results(edition)}

    # Progress stats
    auto = sum(1 for r in cached.values() if r.get("agreement") == "agree")
    needs_review = sum(1 for r in cached.values() if r.get("agreement") == "disagree")
    done = sum(1 for r in cached.values() if r.get("human_category"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Auto-accepted", auto)
    c2.metric("Need review", needs_review)
    c3.metric("Total done", done)

    # Build table
    rows = []
    for s in ed_stories:
        r = cached.get(s["story_id"], {})
        has_keyword = any(kw in s.get("text", "") for kw in HEBREW_KEYWORDS)
        rows.append({
            "story_id": s["story_id"],
            "claude": r.get("claude_category", ""),
            "gemini": r.get("gemini_category", ""),
            "status": _agreement_badge(r),
            "keyword_hit": "🔍" if has_keyword else "",
        })

    df = pd.DataFrame(rows)
    show = st.radio("Show", ["All", "Needs review", "Keyword matches"],
                    horizontal=True, key="ann_filter")
    if show == "Needs review":
        df = df[df["status"].str.startswith("❌")]
    elif show == "Keyword matches":
        df = df[df["keyword_hit"] == "🔍"]

    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=min(400, len(df) * 35 + 40))

    selected = st.selectbox(
        "Select story to review",
        ["—"] + list(df["story_id"]),
        key="ann_select",
    )
    if selected and selected != "—":
        story = next((s for s in ed_stories if s["story_id"] == selected), None)
        result = cached.get(selected, {})
        if story:
            _story_detail(story, result, mode="annotate")


# ── Main page ─────────────────────────────────────────────────────────────────

st.title("Women Annotator")

stories = _get_stories()

_criteria_sidebar()
_keyword_section(stories)

st.markdown("---")
mode = st.radio(
    "Mode",
    ["A — Evaluate (9 annotated editions)", "B — Annotate (unannotated editions)"],
    horizontal=True,
)

if mode.startswith("A"):
    _mode_evaluate(stories)
else:
    _mode_annotate(stories)
