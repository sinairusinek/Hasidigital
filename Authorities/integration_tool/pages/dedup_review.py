"""
Dedup Review — scan for and merge duplicate place entries.

Finds place entries in the authority XML that share external identifiers
(Kima, Wikidata, Tsadikim, etc.), lets you review each group, and merges
confirmed groups by keeping the lowest H-LOC ID as the canonical entry.
"""
import sys
import os
import subprocess

import streamlit as st
import pandas as pd

# Allow imports from parent directories
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from config import (
    AUTHORITY_XML_PATH, DISPLAY_XML_PATH, EDITIONS_INCOMING,
    GEN_SCRIPT, MATCHING_DB_PATH, PROJECT_DIR,
)
from dedup_places import find_duplicate_groups, merge_groups

# ── Session state ────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "dd_groups": None,
        "dd_fixes": None,
        "dd_scanned": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# ── Main UI ──────────────────────────────────────────────────────────────────

st.header("Deduplicate Places")
st.markdown(
    "Scan the authority XML for place entries sharing external identifiers "
    "(Kima, Wikidata, Tsadikim). Review each group and merge confirmed duplicates."
)

# ── Step 1: Scan ─────────────────────────────────────────────────────────────

if not ss.dd_scanned:
    if st.button("Scan for duplicates", type="primary"):
        with st.spinner("Scanning authority XML..."):
            groups, fixes = find_duplicate_groups(str(AUTHORITY_XML_PATH))
            ss.dd_groups = groups
            ss.dd_fixes = fixes
            ss.dd_scanned = True
            st.rerun()
    st.stop()

# ── Show scan results ────────────────────────────────────────────────────────

groups = ss.dd_groups
fixes = ss.dd_fixes

if fixes:
    st.info("Auto-fixes applied before scanning: " + "; ".join(fixes))

if not groups:
    st.success("No duplicate groups found!")
    if st.button("Re-scan"):
        ss.dd_scanned = False
        st.rerun()
    st.stop()

mergeable = [g for g in groups if not g.get("flag")]
flagged = [g for g in groups if g.get("flag")]

m1, m2, m3 = st.columns(3)
m1.metric("Duplicate groups", len(groups))
m2.metric("Mergeable", len(mergeable))
m3.metric("Flagged", len(flagged))

st.markdown("---")

# ── Per-group review ─────────────────────────────────────────────────────────

st.subheader("Review groups")

for i, g in enumerate(groups):
    canonical = g["canonical_id"]
    merge_ids = g["merge_ids"]
    flag = g.get("flag")

    label = f"**{canonical}** \u2190 {', '.join(merge_ids)}"
    if flag:
        label += f"  \u26a0 {flag}"

    with st.expander(label, expanded=False):
        # Names
        st.markdown("**Names:** " + " \u00b7 ".join(g["all_names"]))

        # Shared identifiers
        shared_parts = []
        for src, uri in g["shared_identifiers"].items():
            shared_parts.append(f"**{src}**: `{uri}`")
        if shared_parts:
            st.markdown("**Shared identifiers:** " + " | ".join(shared_parts))

        # All IDs table
        rows = []
        for pid in g["all_ids"]:
            is_canonical = pid == canonical
            rows.append({
                "ID": pid,
                "Role": "canonical (keep)" if is_canonical else "merge \u2192 " + canonical,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if flag:
            st.warning(f"Flagged: {flag} \u2014 this group will be **skipped**.")

        # Per-group skip toggle
        action = st.radio(
            "Action",
            options=["merge", "skip"],
            format_func=lambda x: {
                "merge": "\u2705 Merge into canonical",
                "skip": "\u23ed Skip (don't merge)",
            }[x],
            key=f"dd_action_{i}",
            index=1 if flag else 0,
            horizontal=True,
        )
        # Store decision back on the group dict
        if action == "skip":
            g["flag"] = g.get("flag") or "user_skipped"
        elif not g.get("flag") or g["flag"] == "user_skipped":
            g["flag"] = None

# ── Step 2: Apply merges ────────────────────────────────────────────────────

st.markdown("---")

to_merge = [g for g in groups if not g.get("flag")]
st.markdown(f"**{len(to_merge)}** group(s) will be merged, "
            f"**{len(groups) - len(to_merge)}** skipped.")

if not to_merge:
    st.warning("Nothing to merge \u2014 all groups are skipped or flagged.")
else:
    commit_msg = st.text_input(
        "Commit message",
        value=f"Deduplicate places: merge {len(to_merge)} groups",
        key="dd_commit_msg",
    )

    col_dry, col_apply = st.columns(2)

    with col_dry:
        if st.button("Preview (dry run)"):
            with st.spinner("Running dry-run merge..."):
                report = merge_groups(
                    str(AUTHORITY_XML_PATH),
                    str(EDITIONS_INCOMING),
                    groups,
                    dry_run=True,
                )
            st.markdown(
                f"**Dry run result:** {report['groups_merged']} groups merged, "
                f"{report['places_removed']} places removed, "
                f"{report['total_refs_rewritten']} edition refs rewritten"
            )
            if report["refs_rewritten"]:
                with st.expander("Edition ref changes"):
                    for fname, cnt in sorted(report["refs_rewritten"].items()):
                        st.markdown(f"- `{fname}`: {cnt} ref(s)")

    with col_apply:
        if st.button("\U0001f4be Apply merges and commit", type="primary"):
            # Step 1: Merge duplicates (writes authority XML + edition XMLs)
            with st.spinner("Merging duplicates..."):
                report = merge_groups(
                    str(AUTHORITY_XML_PATH),
                    str(EDITIONS_INCOMING),
                    groups,
                    dry_run=False,
                )

            # Step 2: Regenerate matching DB + display XML from updated authority XML
            with st.spinner("Regenerating matching DB and display XML..."):
                gen_result = subprocess.run(
                    ["python3", str(GEN_SCRIPT)],
                    capture_output=True, text=True, cwd=str(PROJECT_DIR),
                )
                gen_ok = gen_result.returncode == 0

            if not gen_ok:
                st.error(
                    f"generate_matching_db.py failed — XML has been updated on disk "
                    f"but the JSON DB may be stale. Commit manually.\n\n"
                    f"```\n{gen_result.stderr}\n```"
                )
                ss.dd_scanned = False
                st.stop()

            # Step 3: Stage all changed files and commit
            files_to_stage = [
                str(AUTHORITY_XML_PATH),  # merged authority
                str(MATCHING_DB_PATH),    # regenerated matching DB
                str(DISPLAY_XML_PATH),    # regenerated display XML
            ]
            for fname in report["refs_rewritten"]:
                files_to_stage.append(
                    os.path.join(str(EDITIONS_INCOMING), fname)
                )

            try:
                subprocess.run(
                    ["git", "add"] + files_to_stage,
                    cwd=str(PROJECT_DIR), check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=str(PROJECT_DIR), check=True, capture_output=True,
                )
                commit_ok = True
                commit_err = ""
            except subprocess.CalledProcessError as e:
                commit_ok = False
                commit_err = e.stderr.decode() if e.stderr else str(e)

            if commit_ok:
                fixes = report.get("false_dupe_fixes_applied", [])
                fix_note = ""
                if fixes:
                    fix_note = f" · {len(fixes)} false-dupe fix(es) persisted"
                st.success(
                    f"\u2705 Merged {report['groups_merged']} groups, "
                    f"removed {report['places_removed']} duplicate places, "
                    f"rewrote {report['total_refs_rewritten']} edition refs{fix_note}. "
                    f"Matching DB and display XML regenerated. All files committed."
                )
            else:
                st.error(f"Git commit failed:\n```\n{commit_err}\n```")
                st.info(
                    "All XML and JSON files have been updated on disk "
                    "\u2014 you can commit manually."
                )

            # Reset scan state
            ss.dd_scanned = False

# ── Re-scan ──────────────────────────────────────────────────────────────────

st.markdown("---")
if st.button("\U0001f504 Re-scan"):
    ss.dd_scanned = False
    ss.dd_groups = None
    ss.dd_fixes = None
    st.rerun()
