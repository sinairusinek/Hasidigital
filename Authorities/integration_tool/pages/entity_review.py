"""
Entity Review — unified NER annotation review page.

Merges two data sources:
  • Gemini correction diff  (editions/incoming/ready/gemini-correction-log.tsv)
  • Online-edition quality flags  (editions/online/annotation-quality-report.tsv)

Groups occurrences by (text, tag), assigns a confidence tier, and lets the
reviewer make a single keep/remove decision per group (or per occurrence for
ambiguous cases).  Decisions are saved to GitHub via the same write-back
pattern as Kima Review and Person Review.

Session state prefix: er_
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from entity_review_backend import (
    build_groups,
    load_authority_refs,
    load_existing_decisions,
    load_plain_texts,
    save_decisions,
)

# ── Constants ─────────────────────────────────────────────────────────────────

TIER_LABELS = {
    "review":      ("⚑", "לבדיקה",           "#7a5a00", "#fff3cd"),
    "auto_reject": ("✗", "דחייה אוטומטית",    "#8b1a24", "#f8d7da"),
    "auto_accept": ("✓", "קבלה אוטומטית",     "#1e6e3e", "#d4edda"),
}

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

    # Collapse whitespace runs (tabs, newlines from XML indentation) to single spaces
    # so Markdown doesn't treat tab-indented lines as code blocks.
    import re as _re
    before  = _re.sub(r"\s+", " ", before).strip()
    after   = _re.sub(r"\s+", " ", after).strip()
    containing = _re.sub(r"\s+", " ", containing).strip() if containing else ""

    b, e, a = esc(before), esc(entity), esc(after)

    # Blue-tint the containing word by replacing entity within it
    if containing and containing != entity:
        ct = esc(containing)
        highlighted_entity = f'<mark style="background:rgba(255,200,0,0.4);padding:0 1px;border-radius:2px;font-weight:700">{e}</mark>'
        word_tinted = ct.replace(e, highlighted_entity, 1)
        last_b = b.rfind(esc(containing[: containing.find(entity)]))
        # Simpler: just highlight the entity and show containing word hint separately
        entity_html = (
            f'<span style="background:rgba(100,160,255,0.15);padding:0 2px;border-radius:2px">'
            f'{word_tinted}</span>'
        )
        # Replace trailing part of before + entity + leading part of after with entity_html
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


def _reviewer_sidebar() -> tuple[str, str]:
    """Render reviewer identity inputs in sidebar. Return (name, email)."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("זהות הסוקר")
    name = st.sidebar.text_input(
        "שם", key="er_reviewer_name",
        placeholder="שם מלא",
    )
    email = st.sidebar.text_input(
        "דוא״ל", key="er_reviewer_email",
        placeholder="name@example.com",
    )
    if not name or not email:
        st.sidebar.warning("נא למלא שם ודוא״ל לפני השמירה.")
    return name.strip(), email.strip()


# ── Data loading (cached) ─────────────────────────────────────────────────────

@st.cache_data(show_spinner="טוען Authority File…")
def _load_auth_refs() -> set:
    return load_authority_refs()


@st.cache_data(show_spinner="בונה קבוצות…")
def _build_groups() -> list:
    # Context is pre-baked into gemini-correction-log.tsv — no XML parsing needed.
    auth_refs = load_authority_refs()
    return build_groups({}, auth_refs)


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _count_tiers(groups: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"review": 0, "auto_reject": 0, "auto_accept": 0}
    for g in groups:
        counts[g["tier"]] = counts.get(g["tier"], 0) + 1
    return counts


def _count_decided(groups: list[dict], decisions: dict) -> int:
    return sum(1 for g in groups if decisions.get(g["key"], {}).get("group_decision"))


# ── Group card renderer ───────────────────────────────────────────────────────

def _render_group(g: dict, decisions: dict, idx: int) -> None:
    key = g["key"]
    tier = g["tier"]
    tier_icon, tier_lbl, tier_fg, tier_bg = TIER_LABELS[tier]
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

    with st.expander(
        f"{tier_icon} **{g['text']}** · {g['tag']} · {n_occs} הופעות"
        + (f"  —  _{decided_label}_" if decided_label else ""),
        expanded=False,
    ):
        # ── Tier + reason ─────────────────────────────────────────────────
        cols = st.columns([3, 7])
        with cols[0]:
            st.markdown(
                _badge(f"{tier_icon} {tier_lbl}", tier_fg, tier_bg)
                + "&nbsp;"
                + _badge(g["tag"], tag_fg, tag_bg),
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.caption(g["tier_reason"])

        # ── Group-level decision buttons ──────────────────────────────────
        st.markdown("**החלטה לכל הקבוצה:**")
        b1, b2, b3, _ = st.columns([2, 2, 2, 4])
        if b1.button("שמור הכל", key=f"er_keep_{idx}", type="primary" if group_decision == "keep" else "secondary"):
            decisions.setdefault(key, {})["group_decision"] = "keep"
            st.rerun()
        if b2.button("הסר הכל", key=f"er_remove_{idx}"):
            decisions.setdefault(key, {})["group_decision"] = "remove"
            st.rerun()
        if b3.button("החלט לפי הופעה", key=f"er_each_{idx}"):
            decisions.setdefault(key, {})["group_decision"] = "per_occurrence"
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
                    st.rerun()
                if c2.button(
                    "✗ הסר" + (" ◀" if occ_decision == "remove" else ""),
                    key=f"er_occ_remove_{idx}_{oi}",
                ):
                    decisions.setdefault(key, {}).setdefault("per_occurrence", {})[occ_key] = "remove"
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
    st.title("🏷️ Entity Review")
    st.caption("בדיקת איכות הערות NER — Gemini diff + quality flags")

    # ── Reviewer identity ─────────────────────────────────────────────────────
    reviewer_name, reviewer_email = _reviewer_sidebar()

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("טוען נתונים…"):
        groups = _build_groups()

    if not groups:
        st.warning("לא נמצאו נתונים. ודא שקובצי ה-TSV קיימים.")
        return

    # ── Decisions (session state) ──────────────────────────────────────────────
    if "er_decisions" not in st.session_state:
        st.session_state.er_decisions = load_existing_decisions()
    decisions: dict = st.session_state.er_decisions

    # ── Summary bar ───────────────────────────────────────────────────────────
    tier_counts = _count_tiers(groups)
    n_decided = _count_decided(groups, decisions)
    n_total = len(groups)

    c_all, c_rev, c_rej, c_acc, c_done = st.columns(5)
    c_all.metric("סה״כ קבוצות", n_total)
    c_rev.metric("⚑ לבדיקה",          tier_counts["review"])
    c_rej.metric("✗ דחייה אוטומטית",   tier_counts["auto_reject"])
    c_acc.metric("✓ קבלה אוטומטית",    tier_counts["auto_accept"])
    c_done.metric("הוחלט", f"{n_decided}/{n_total}")

    st.progress(n_decided / n_total if n_total else 0)

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("סינון", expanded=False):
        fcols = st.columns(3)
        filter_tier = fcols[0].selectbox(
            "שכבה",
            ["הכל", "⚑ לבדיקה", "✗ דחייה אוטומטית", "✓ קבלה אוטומטית"],
            key="er_filter_tier",
        )
        filter_decided = fcols[1].selectbox(
            "סטטוס",
            ["הכל", "לא הוחלט", "הוחלט"],
            key="er_filter_decided",
        )
        all_tags = sorted({g["tag"] for g in groups})
        filter_tag = fcols[2].selectbox("תג", ["הכל"] + all_tags, key="er_filter_tag")

    tier_map = {
        "⚑ לבדיקה": "review",
        "✗ דחייה אוטומטית": "auto_reject",
        "✓ קבלה אוטומטית": "auto_accept",
    }

    def _visible(g: dict) -> bool:
        if filter_tier != "הכל" and g["tier"] != tier_map.get(filter_tier):
            return False
        if filter_tag != "הכל" and g["tag"] != filter_tag:
            return False
        has_decision = bool(decisions.get(g["key"], {}).get("group_decision"))
        if filter_decided == "לא הוחלט" and has_decision:
            return False
        if filter_decided == "הוחלט" and not has_decision:
            return False
        return True

    visible_groups = [g for g in groups if _visible(g)]

    # ── Save button ───────────────────────────────────────────────────────────
    save_col, reload_col, _ = st.columns([2, 2, 6])
    save_disabled = not (reviewer_name and reviewer_email)
    if save_col.button(
        "💾 שמור החלטות ל-GitHub",
        disabled=save_disabled,
        type="primary",
        key="er_save",
    ):
        with st.spinner("שומר…"):
            ok, msg = save_decisions(decisions, groups, reviewer_name, reviewer_email)
        if ok:
            st.success(msg)
        else:
            st.error(f"שגיאה בשמירה: {msg}")

    if save_disabled:
        st.caption("⚠️ נא למלא שם ודוא״ל בסרגל הצד לפני השמירה.")

    if reload_col.button("↺ טען מחדש", key="er_reload"):
        _build_groups.clear()
        st.cache_data.clear()
        st.session_state.er_decisions = load_existing_decisions()
        st.rerun()

    st.markdown("---")

    # ── Render tier sections ──────────────────────────────────────────────────
    for tier_key, (tier_icon, tier_lbl, tier_fg, tier_bg) in TIER_LABELS.items():
        tier_groups = [g for g in visible_groups if g["tier"] == tier_key]
        if not tier_groups:
            continue

        n_tier_decided = sum(
            1 for g in tier_groups if decisions.get(g["key"], {}).get("group_decision")
        )

        # review open by default, auto tiers collapsed
        default_open = tier_key == "review"
        with st.expander(
            f"{tier_icon} {tier_lbl} — {len(tier_groups)} קבוצות  "
            f"({n_tier_decided}/{len(tier_groups)} הוחלט)",
            expanded=default_open,
        ):
            for idx, g in enumerate(tier_groups):
                global_idx = groups.index(g)
                _render_group(g, decisions, global_idx)

    if not visible_groups:
        st.info("אין קבוצות התואמות את הסינון הנוכחי.")


st.markdown(
    """
    <style>
    section[data-testid="stMain"] > div.block-container,
    .main > div.block-container {
        max-width: 860px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
main()
