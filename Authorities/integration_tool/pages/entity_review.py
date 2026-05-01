"""
Entity Review — unified NER annotation review page.

Merges two data sources:
  • Gemini correction diff  (editions/incoming/ready/gemini-correction-log.tsv)
  • Online-edition quality flags  (editions/online/annotation-quality-report.tsv)

Groups occurrences by (text, tag) and lets the reviewer make a keep/remove
decision per group (or per occurrence).  Decisions are saved to GitHub via the
same write-back pattern as Kima Review and Person Review.

Session state prefix: er_
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from entity_review_backend import (
    build_groups,
    load_existing_decisions,
    save_decisions,
)

# ── Constants ─────────────────────────────────────────────────────────────────

PAGE_SIZE = 50

TAG_COLORS = {
    "persName":   ("#1a3a99", "#e3eaff"),
    "placeName":  ("#1a5c2a", "#e8f5e9"),
    "orgName":    ("#8a4000", "#fff3e0"),
    "date":       ("#8a003a", "#fce4ec"),
}

SOURCE_LABELS = {
    "gemini_diff":  ("Gemini diff",   "#0d47a1", "#e3f2fd"),
    "quality_flag": ("quality flag",  "#6a1b9a", "#f3e5f5"),
}

ACTION_LABELS = {
    "added":           ("נוסף",       "#1a6030", "#d4edda"),
    "removed":         ("הוסר",       "#721c24", "#f8d7da"),
    "reclassified":    ("סווג מחדש",  "#856404", "#fff3cd"),
    "short_fragment":  ("פרגמנט",     "#555",    "#f0f0f0"),
    "punct_only":      ("פיסוק",      "#555",    "#f0f0f0"),
    "xmlid_leak":      ("xml:id",     "#555",    "#f0f0f0"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(text: str, fg: str, bg: str, extra: str = "") -> str:
    style = (
        f"display:inline-block;padding:2px 8px;border-radius:10px;"
        f"font-size:0.72rem;font-weight:700;color:{fg};background:{bg};"
        f"white-space:nowrap;{extra}"
    )
    return f'<span style="{style}">{text}</span>'


def _ctx_html(before: str, entity: str, after: str, containing: str) -> str:
    """Render a context snippet with entity highlighted (and containing word tinted)."""
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    import re as _re
    before  = _re.sub(r"\s+", " ", before).strip()
    after   = _re.sub(r"\s+", " ", after).strip()
    containing = _re.sub(r"\s+", " ", containing).strip() if containing else ""

    b, e, a = esc(before), esc(entity), esc(after)

    if containing and containing != entity:
        ct = esc(containing)
        highlighted_entity = f'<mark style="background:rgba(255,200,0,0.4);padding:0 1px;border-radius:2px;font-weight:700">{e}</mark>'
        word_tinted = ct.replace(e, highlighted_entity, 1)
        entity_html = (
            f'<span style="background:rgba(100,160,255,0.15);padding:0 2px;border-radius:2px">'
            f'{word_tinted}</span>'
        )
        prefix_in_containing = esc(containing[: containing.find(entity)])
        suffix_in_containing = esc(containing[containing.find(entity) + len(entity):])
        if b.endswith(prefix_in_containing) and a.startswith(suffix_in_containing):
            b = b[: len(b) - len(prefix_in_containing)]
            a = a[len(suffix_in_containing):]
            mid = entity_html
        else:
            mid = f'<mark style="background:rgba(255,200,0,0.4);padding:0 1px;border-radius:2px;font-weight:700">{e}</mark>'
    else:
        mid = f'<mark style="background:rgba(255,200,0,0.4);padding:0 1px;border-radius:2px;font-weight:700">{e}</mark>'

    return (
        f'<div dir="rtl" style="font-size:0.9rem;line-height:1.8;color:#222;'
        f'border-right:3px solid #dde;padding-right:10px;'
        f'font-family:\'Segoe UI\',Arial,sans-serif">'
        f'…{b}{mid}{a}…</div>'
    )


def _reviewer_gate() -> str:
    """Show an email prompt and block the page until the user enters their email."""
    if st.session_state.get("er_reviewer_name"):
        return st.session_state.er_reviewer_name

    st.title("🏷️ NER Review")
    st.markdown("### ברוך הבא! נא להזין את כתובת המייל לפני הצפייה בנתונים.")
    col, _ = st.columns([2, 3])
    email = col.text_input("דוא״ל", key="_er_name_input", placeholder="name@example.com")
    if col.button("המשך", type="primary", disabled=not email.strip()):
        st.session_state.er_reviewer_name = email.strip()
        st.rerun()
    st.stop()


# ── Data loading (cached) ─────────────────────────────────────────────────────

@st.cache_data(show_spinner="בונה קבוצות…")
def _build_groups() -> list:
    # Context is pre-baked into gemini-correction-log.tsv — no XML parsing needed.
    return build_groups({})


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _count_decided(groups: list[dict], decisions: dict) -> int:
    return sum(1 for g in groups if decisions.get(g["key"], {}).get("group_decision"))


# ── Group card renderer ───────────────────────────────────────────────────────

def _render_group(g: dict, decisions: dict, idx: int) -> None:
    key = g["key"]
    tag_fg, tag_bg = TAG_COLORS.get(g["tag"], ("#333", "#eee"))

    current = decisions.get(key, {})
    group_decision = current.get("group_decision", "")
    per_occ = current.get("per_occurrence", {})

    decided_label = ""
    if group_decision == "keep":
        decided_label = "✓ שמור הכל"
    elif group_decision == "remove":
        decided_label = "✗ הסר הכל"
    elif group_decision == "per_occurrence":
        done = sum(1 for v in per_occ.values() if v)
        decided_label = f"לפי הופעה ({done}/{len(g['occurrences'])} הוחלט)"

    n_occs = len(g["occurrences"])

    is_expanded = idx in st.session_state.er_expanded

    with st.expander(
        f"**{g['text']}** · {g['tag']} · {n_occs} הופעות"
        + (f"  —  _{decided_label}_" if decided_label else ""),
        expanded=is_expanded,
    ):
        # ── Tag badge ─────────────────────────────────────────────────────
        st.markdown(_badge(g["tag"], tag_fg, tag_bg), unsafe_allow_html=True)

        # ── Group-level decision buttons ──────────────────────────────────
        st.markdown("**החלטה לכל הקבוצה:**")
        b1, b2, b3, _ = st.columns([2, 2, 2, 4])
        if b1.button("שמור הכל", key=f"er_keep_{idx}", type="primary" if group_decision == "keep" else "secondary"):
            decisions.setdefault(key, {})["group_decision"] = "keep"
            st.session_state.er_expanded.add(idx)
            st.rerun()
        if b2.button("הסר הכל", key=f"er_remove_{idx}"):
            decisions.setdefault(key, {})["group_decision"] = "remove"
            st.session_state.er_expanded.add(idx)
            st.rerun()
        if b3.button("החלט לפי הופעה", key=f"er_each_{idx}"):
            decisions.setdefault(key, {})["group_decision"] = "per_occurrence"
            st.session_state.er_expanded.add(idx)
            st.rerun()

        if group_decision:
            st.markdown("---")

        # ── Occurrences ───────────────────────────────────────────────────
        show_occ_buttons = (group_decision == "per_occurrence")

        for oi, occ in enumerate(g["occurrences"]):
            src_lbl, src_fg, src_bg = SOURCE_LABELS.get(
                occ["source"], (occ["source"], "#333", "#eee")
            )
            act_lbl, act_fg, act_bg = ACTION_LABELS.get(
                occ["action"], (occ["action"], "#333", "#eee")
            )

            badges = (
                _badge(src_lbl, src_fg, src_bg)
                + "&nbsp;"
                + _badge(act_lbl, act_fg, act_bg)
                + "&nbsp;"
                + _badge(occ["file"], "#555", "#f0f0f0")
            )
            if occ.get("story_id"):
                badges += "&nbsp;" + _badge(occ["story_id"], "#667", "#f8f8f8")

            st.markdown(badges, unsafe_allow_html=True)
            st.markdown(
                _ctx_html(occ["before"], occ["entity"], occ["after"], occ.get("containing_word", "")),
                unsafe_allow_html=True,
            )

            if show_occ_buttons:
                occ_key = f"{idx}_{oi}"
                occ_decision = per_occ.get(occ_key, "")
                c1, c2, _ = st.columns([2, 2, 6])
                if c1.button(
                    "✓ שמור" + (" ◀" if occ_decision == "keep" else ""),
                    key=f"er_occ_keep_{idx}_{oi}",
                    type="primary" if occ_decision == "keep" else "secondary",
                ):
                    decisions.setdefault(key, {}).setdefault("per_occurrence", {})[occ_key] = "keep"
                    st.session_state.er_expanded.add(idx)
                    st.rerun()
                if c2.button(
                    "✗ הסר" + (" ◀" if occ_decision == "remove" else ""),
                    key=f"er_occ_remove_{idx}_{oi}",
                ):
                    decisions.setdefault(key, {}).setdefault("per_occurrence", {})[occ_key] = "remove"
                    st.session_state.er_expanded.add(idx)
                    st.rerun()

            if oi < len(g["occurrences"]) - 1:
                st.markdown('<hr style="margin:6px 0;border-color:#eef">', unsafe_allow_html=True)

        # ── Note field ────────────────────────────────────────────────────
        note_val = current.get("note", "")
        new_note = st.text_input(
            "הערה (אופציונלי)", value=note_val, key=f"er_note_{idx}",
            placeholder="הסבר, שאלה, הפניה…",
        )
        if new_note != note_val:
            decisions.setdefault(key, {})["note"] = new_note


# ── Main page ─────────────────────────────────────────────────────────────────

def main() -> None:
    reviewer_name = _reviewer_gate()

    st.title("🏷️ NER Review")
    st.caption(f"בדיקת איכות הערות NER — Gemini diff + quality flags · {reviewer_name}")

    with st.spinner("טוען נתונים…"):
        groups = _build_groups()

    if not groups:
        st.warning("לא נמצאו נתונים. ודא שקובצי ה-TSV קיימים.")
        return

    if "er_decisions" not in st.session_state:
        st.session_state.er_decisions = load_existing_decisions()
    decisions: dict = st.session_state.er_decisions

    if "er_expanded" not in st.session_state:
        st.session_state.er_expanded = set()

    # ── Summary bar ───────────────────────────────────────────────────────────
    n_decided = _count_decided(groups, decisions)
    n_total = len(groups)

    c_all, c_done = st.columns(2)
    c_all.metric("סה״כ קבוצות", n_total)
    c_done.metric("הוחלט", f"{n_decided}/{n_total}")
    st.progress(n_decided / n_total if n_total else 0)

    # ── Filters ───────────────────────────────────────────────────────────────
    # Map user-facing action labels to the raw action values in the data
    _ACTION_FILTER_MAP = {
        "הוספות":        {"added"},
        "הסרות":         {"removed"},
        "קטגוריזציות":   {"reclassified"},
        "בעיות איכות":   {"short_fragment", "punct_only", "xmlid_leak", "flag"},
    }

    with st.expander("סינון", expanded=False):
        fcols = st.columns(3)
        prev_decided = st.session_state.get("er_filter_decided", "הכל")
        prev_tag     = st.session_state.get("er_filter_tag",     "הכל")
        prev_action  = st.session_state.get("er_filter_action",  "הכל")

        filter_decided = fcols[0].selectbox(
            "סטטוס", ["הכל", "לא הוחלט", "הוחלט"], key="er_filter_decided"
        )
        all_tags = sorted({g["tag"] for g in groups})
        filter_tag = fcols[1].selectbox("תג", ["הכל"] + all_tags, key="er_filter_tag")
        filter_action = fcols[2].selectbox(
            "סוג שינוי", ["הכל"] + list(_ACTION_FILTER_MAP.keys()), key="er_filter_action"
        )

    # Reset to page 0 when any filter changes
    if filter_decided != prev_decided or filter_tag != prev_tag or filter_action != prev_action:
        st.session_state.er_page = 0

    _allowed_actions = _ACTION_FILTER_MAP.get(filter_action, set())

    def _visible(g: dict) -> bool:
        if filter_tag != "הכל" and g["tag"] != filter_tag:
            return False
        if filter_action != "הכל" and not any(
            o.get("action") in _allowed_actions for o in g["occurrences"]
        ):
            return False
        has_decision = bool(decisions.get(g["key"], {}).get("group_decision"))
        if filter_decided == "לא הוחלט" and has_decision:
            return False
        if filter_decided == "הוחלט" and not has_decision:
            return False
        return True

    visible_groups = [g for g in groups if _visible(g)]

    # ── Save / Reload ─────────────────────────────────────────────────────────
    save_col, reload_col, _ = st.columns([2, 2, 6])
    if save_col.button("💾 שמור החלטות ל-GitHub", type="primary", key="er_save"):
        with st.spinner("שומר…"):
            ok, msg = save_decisions(decisions, groups, reviewer_name, "")
        if ok:
            st.success(msg)
        else:
            st.error(f"שגיאה בשמירה: {msg}")

    if reload_col.button("↺ טען מחדש", key="er_reload"):
        _build_groups.clear()
        st.cache_data.clear()
        st.session_state.er_decisions = load_existing_decisions()
        st.rerun()

    st.markdown("---")

    # ── Pagination ────────────────────────────────────────────────────────────
    n_visible = len(visible_groups)
    n_pages = max(1, (n_visible + PAGE_SIZE - 1) // PAGE_SIZE)

    if "er_page" not in st.session_state:
        st.session_state.er_page = 0
    page = min(st.session_state.er_page, n_pages - 1)

    page_groups = visible_groups[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    # Page nav (top)
    if n_pages > 1:
        pc1, pc2, pc3 = st.columns([1, 3, 1])
        if pc1.button("◀ הקודם", key="er_prev", disabled=page == 0):
            st.session_state.er_page = page - 1
            st.rerun()
        pc2.markdown(
            f'<div style="text-align:center;padding-top:6px">עמוד {page + 1} מתוך {n_pages} ({n_visible} קבוצות)</div>',
            unsafe_allow_html=True,
        )
        if pc3.button("הבא ▶", key="er_next", disabled=page >= n_pages - 1):
            st.session_state.er_page = page + 1
            st.rerun()

    # ── Render groups ─────────────────────────────────────────────────────────
    for local_idx, g in enumerate(page_groups):
        global_idx = groups.index(g)
        _render_group(g, decisions, global_idx)

    # Page nav (bottom)
    if n_pages > 1:
        bc1, bc2, bc3 = st.columns([1, 3, 1])
        if bc1.button("◀ הקודם", key="er_prev_b", disabled=page == 0):
            st.session_state.er_page = page - 1
            st.rerun()
        bc2.markdown(
            f'<div style="text-align:center;padding-top:6px">עמוד {page + 1} מתוך {n_pages}</div>',
            unsafe_allow_html=True,
        )
        if bc3.button("הבא ▶", key="er_next_b", disabled=page >= n_pages - 1):
            st.session_state.er_page = page + 1
            st.rerun()

    if not visible_groups:
        st.info("אין קבוצות התואמות את הסינון הנוכחי.")


st.markdown(
    """
    <style>
    /* RTL for all text elements in the main content area */
    section[data-testid="stMain"] .block-container,
    section[data-testid="stMain"] p,
    section[data-testid="stMain"] h1,
    section[data-testid="stMain"] h2,
    section[data-testid="stMain"] h3,
    section[data-testid="stMain"] label,
    section[data-testid="stMain"] .stMarkdown,
    section[data-testid="stMain"] .stText,
    section[data-testid="stMain"] .stCaption,
    section[data-testid="stMain"] details summary,
    section[data-testid="stMain"] [data-testid="stExpander"] summary p,
    section[data-testid="stMain"] [data-testid="stMetricLabel"],
    section[data-testid="stMain"] [data-testid="stMetricValue"] {
        direction: rtl;
        text-align: right;
    }
    section[data-testid="stMain"] .stTextInput input {
        direction: rtl;
        text-align: right;
    }
    section[data-testid="stMain"] .stSelectbox label,
    section[data-testid="stMain"] .stSelectbox div[data-baseweb="select"] {
        direction: rtl;
        text-align: right;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
main()
