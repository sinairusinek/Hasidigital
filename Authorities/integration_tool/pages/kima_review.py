"""
Kima Review — step-through GUI for reviewing Kimatch candidate matches.

Shows each unmatched place name with its full Kima candidate names (Hebrew + Latin)
and the corresponding H-LOC authority entry (if one exists), so the user can make
an informed decision: map to existing authority, create new entry, or skip.

Session state prefix: kr_
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MATCHING_DB_PATH,
    UNMATCHED_CSV,
    UNMATCHED_TSV,
    KIMA_PLACES_CSV,
)

KIMA_URL_BASE = "https://data.geo-kima.org/Places/Details/"


# ── helpers ───────────────────────────────────────────────────────────────────

def _kima_url_to_id(url: str) -> int | None:
    m = re.search(r"/(\d+)$", url or "")
    return int(m.group(1)) if m else None


def _candidate_ids(result_row: dict, tsv_row: dict | None = None) -> list[int]:
    """Collect all Kima candidate IDs from both Kimatch output and TSV suggested_id."""
    ids: list[int] = []
    # From Kimatch output columns
    for raw in [result_row.get("_kima_id", ""), *(result_row.get("_candidates", "").split("|"))]:
        raw = (raw or "").strip()
        if raw:
            try:
                ids.append(int(raw))
            except ValueError:
                pass
    # From TSV suggested_id (e.g. "kima:223|kima:19737" — set by apply_kima_results.py)
    if tsv_row:
        for part in (tsv_row.get("suggested_id", "") or "").split("|"):
            part = part.strip().removeprefix("kima:")
            if part:
                try:
                    ids.append(int(part))
                except ValueError:
                    pass
    seen: set[int] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]


def _read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return list(csv.DictReader(io.StringIO(content), delimiter="\t"))


def _write_tsv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


# ── data loading ──────────────────────────────────────────────────────────────

def _load_all() -> None:
    ss = st.session_state

    # 1. Read Kimatch results CSV
    if not os.path.exists(UNMATCHED_CSV):
        st.error(f"Kimatch results not found: {UNMATCHED_CSV}")
        st.stop()
    with open(UNMATCHED_CSV, encoding="utf-8") as f:
        results = list(csv.DictReader(f))
    ss.kr_results = results

    # 2. Read TSV (live decisions)
    if not os.path.exists(UNMATCHED_TSV):
        st.error(f"Unmatched TSV not found: {UNMATCHED_TSV}")
        st.stop()
    tsv_rows = _read_tsv(UNMATCHED_TSV)
    ss.kr_tsv_rows = tsv_rows
    ss.kr_tsv_fieldnames = list(tsv_rows[0].keys()) if tsv_rows else []
    ss.kr_tsv_by_name = {r["name"]: r for r in tsv_rows}

    # 3. Collect unique Kima IDs across all rows
    all_kima_ids: set[int] = set()
    for row in results:
        for kid in _candidate_ids(row):
            all_kima_ids.add(kid)

    # 4. Load Kima place names (lightweight: only needed rows)
    kima_names: dict[int, dict] = {}
    if os.path.exists(KIMA_PLACES_CSV) and all_kima_ids:
        try:
            with st.spinner("Loading Kima place names…"):
                df = pd.read_csv(KIMA_PLACES_CSV, dtype=str, low_memory=False)
                df["id"] = pd.to_numeric(df["id"], errors="coerce")
                subset = df[df["id"].isin(all_kima_ids)]
                for _, r in subset.iterrows():
                    kid = int(r["id"])
                    kima_names[kid] = {
                        "heb": str(r.get("primary_heb_full", "") or ""),
                        "rom": str(r.get("primary_rom_full", "") or ""),
                    }
        except Exception as e:
            st.warning(f"Could not load Kima CSV: {e}")
    else:
        if not os.path.exists(KIMA_PLACES_CSV):
            st.warning(f"Kima CSV not found at {KIMA_PLACES_CSV}. Candidate names will be limited.")
    ss.kr_kima_names = kima_names

    # 5. Build kima_id → H-LOC and H-LOC → name from authority DB
    kima_to_hloc: dict[int, str] = {}
    hloc_names: dict[str, str] = {}
    if os.path.exists(MATCHING_DB_PATH):
        with open(MATCHING_DB_PATH, encoding="utf-8") as f:
            db = json.load(f)
        for p in db.get("places", []):
            hloc = p["id"]
            hloc_names[hloc] = p.get("primary_name_he", "") or p.get("primary_name_en", "")
            kid = _kima_url_to_id(p.get("identifiers", {}).get("Kima", ""))
            if kid is not None:
                kima_to_hloc[kid] = hloc
    ss.kr_kima_to_hloc = kima_to_hloc
    ss.kr_hloc_names = hloc_names

    ss.kr_loaded = True
    ss.kr_filter = ss.get("kr_filter", "ambiguous")
    ss.kr_pos = 0
    _rebuild_queue()


def _rebuild_queue() -> None:
    ss = st.session_state
    filt = ss.kr_filter
    results = ss.kr_results
    tsv = ss.kr_tsv_by_name

    queue = []
    for i, row in enumerate(results):
        status = row.get("_match_status", "")
        if status == "no_match":
            continue  # exclude no-match rows (no Kima data)
        action = tsv.get(row["name"], {}).get("action", "")
        if filt == "ambiguous" and action == "ambiguous":
            queue.append(i)
        elif filt == "unset" and action == "":
            queue.append(i)
        elif filt == "auto" and action and action not in ("ambiguous", ""):
            queue.append(i)
        elif filt == "all" and status != "no_match":
            queue.append(i)

    ss.kr_queue = queue
    ss.kr_pos = min(ss.get("kr_pos", 0), max(len(queue) - 1, 0))


# ── decision saving ────────────────────────────────────────────────────────────

def _save_decision(name: str, action: str, suggested_id: str) -> None:
    ss = st.session_state
    tsv_row = ss.kr_tsv_by_name.get(name)
    if tsv_row is None:
        return
    tsv_row["action"] = action
    tsv_row["suggested_id"] = suggested_id
    _write_tsv(UNMATCHED_TSV, ss.kr_tsv_rows, ss.kr_tsv_fieldnames)


# ── main page ─────────────────────────────────────────────────────────────────

def _init() -> None:
    if not st.session_state.get("kr_loaded"):
        _load_all()


def _filter_counts() -> dict[str, int]:
    ss = st.session_state
    results = ss.kr_results
    tsv = ss.kr_tsv_by_name
    counts = {"ambiguous": 0, "unset": 0, "auto": 0, "all": 0}
    for row in results:
        if row.get("_match_status") == "no_match":
            continue
        action = tsv.get(row["name"], {}).get("action", "")
        counts["all"] += 1
        if action == "ambiguous":
            counts["ambiguous"] += 1
        elif action == "":
            counts["unset"] += 1
        elif action not in ("ambiguous", ""):
            counts["auto"] += 1
    return counts


def _render_row(result_row: dict) -> None:
    ss = st.session_state
    name = result_row["name"]
    tsv_row = ss.kr_tsv_by_name.get(name, {})

    current_action = tsv_row.get("action", "")
    current_id = tsv_row.get("suggested_id", "")
    status = result_row.get("_match_status", "")
    confidence = result_row.get("_confidence", "")
    editions_str = result_row.get("editions", "")
    occurrences = result_row.get("occurrences", "?")
    contexts_raw = result_row.get("contexts", "")

    # ── header ──────────────────────────────────────────────────────────────
    st.markdown(
        f"<h2 style='margin-bottom:0'>{name}</h2>", unsafe_allow_html=True
    )
    editions_list = [e.strip() for e in editions_str.split(",") if e.strip()]
    st.caption(
        f"{occurrences} occurrence(s) · {len(editions_list)} edition(s): "
        + ", ".join(editions_list[:5])
        + ("…" if len(editions_list) > 5 else "")
    )

    col_status, col_conf = st.columns([1, 1])
    status_icon = {"name_exact": "🎯", "fuzzy": "〰️"}.get(status, "❓")
    col_status.info(f"{status_icon} Kimatch: **{status}**")
    if confidence:
        col_conf.info(f"Confidence: **{confidence}**")

    # ── contexts ─────────────────────────────────────────────────────────────
    contexts = [c.strip() for c in contexts_raw.split(" | ") if c.strip()]
    if contexts:
        with st.expander("📄 Contexts", expanded=True):
            for ctx in contexts[:3]:
                # Truncate very long contexts to ~400 chars for readability
                display = ctx if len(ctx) <= 400 else ctx[:400] + "…"
                st.markdown(
                    f"<div style='direction:rtl;text-align:right;font-size:0.9em;"
                    f"padding:6px;background:#f8f9fa;border-radius:4px;margin-bottom:4px'>"
                    f"{display}</div>",
                    unsafe_allow_html=True,
                )

    # ── candidates table ─────────────────────────────────────────────────────
    cand_ids = _candidate_ids(result_row, tsv_row)
    kima_names: dict[int, dict] = ss.kr_kima_names
    kima_to_hloc: dict[int, str] = ss.kr_kima_to_hloc
    hloc_names: dict[str, str] = ss.kr_hloc_names

    if cand_ids:
        st.markdown("**Kima candidates**")
        table_rows = []
        for kid in cand_ids:
            info = kima_names.get(kid, {})
            hloc = kima_to_hloc.get(kid, "")
            hloc_label = f"{hloc} ({hloc_names.get(hloc, '')})" if hloc else "—"
            kima_url = f"[{kid}]({KIMA_URL_BASE}{kid})"
            table_rows.append({
                "Kima ID": kima_url,
                "Hebrew": info.get("heb", ""),
                "Latin": info.get("rom", ""),
                "In authority": hloc_label,
            })
        st.markdown(
            pd.DataFrame(table_rows).to_markdown(index=False),
            unsafe_allow_html=True,
        )

    # ── decision ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Decision**")

    # Build radio options from candidates
    radio_options: list[str] = []
    radio_actions: dict[str, tuple[str, str]] = {}  # label → (action, suggested_id)

    for kid in cand_ids:
        info = kima_names.get(kid, {})
        heb = info.get("heb", f"kima:{kid}")
        hloc = kima_to_hloc.get(kid)
        if hloc:
            label = f"🔗 Map to {hloc}  ({hloc_names.get(hloc, '')} / {heb})"
            radio_options.append(label)
            radio_actions[label] = (f"map_to:{hloc}", f"kima:{kid}")
        else:
            label = f"🆕 New entry — kima:{kid}  ({heb})"
            radio_options.append(label)
            radio_actions[label] = ("new", f"kima:{kid}")

    radio_options += [
        "⏭️ Skip — not a geographic place",
        "🔀 Ambiguous — decide later",
        "✏️ Custom action…",
    ]
    radio_actions["⏭️ Skip — not a geographic place"] = ("skip", "")
    radio_actions["🔀 Ambiguous — decide later"] = ("ambiguous", current_id or "|".join(f"kima:{k}" for k in cand_ids))

    # Pre-select current decision
    default_idx = 0
    if current_action == "skip":
        default_idx = radio_options.index("⏭️ Skip — not a geographic place")
    elif current_action == "ambiguous":
        default_idx = radio_options.index("🔀 Ambiguous — decide later")
    elif current_action.startswith("map_to:"):
        hloc_target = current_action[len("map_to:"):]
        for i, lbl in enumerate(radio_options):
            if hloc_target in lbl and lbl.startswith("🔗"):
                default_idx = i
                break
    elif current_action == "new":
        for i, lbl in enumerate(radio_options):
            if lbl.startswith("🆕") and current_id.replace("kima:", "") in lbl:
                default_idx = i
                break
    elif current_action:
        default_idx = radio_options.index("✏️ Custom action…")

    choice = st.radio(
        "Choose action:",
        radio_options,
        index=default_idx,
        key=f"kr_radio_{name}",
        label_visibility="collapsed",
    )

    custom_action = ""
    custom_id = ""
    if choice == "✏️ Custom action…":
        col_a, col_b = st.columns(2)
        custom_action = col_a.text_input(
            "Action (e.g. map_to:H-LOC_xxx / new / skip)",
            value=current_action,
            key=f"kr_custom_action_{name}",
        )
        custom_id = col_b.text_input(
            "Suggested ID (e.g. kima:1234)",
            value=current_id,
            key=f"kr_custom_id_{name}",
        )

    # ── save & navigate ───────────────────────────────────────────────────────
    st.write("")
    col_prev, col_save, col_next = st.columns([1, 2, 1])

    pos = ss.kr_pos
    queue = ss.kr_queue

    if col_prev.button("← Prev", use_container_width=True, disabled=pos == 0):
        ss.kr_pos = pos - 1
        st.rerun()

    save_label = "💾 Save & Next →" if pos < len(queue) - 1 else "💾 Save"
    if col_save.button(save_label, type="primary", use_container_width=True):
        if choice == "✏️ Custom action…":
            action_to_save = custom_action.strip()
            id_to_save = custom_id.strip()
        else:
            action_to_save, id_to_save = radio_actions.get(choice, ("", ""))

        _save_decision(name, action_to_save, id_to_save)

        if pos < len(queue) - 1:
            ss.kr_pos = pos + 1
        _rebuild_queue()
        st.rerun()

    if col_next.button("Next →", use_container_width=True, disabled=pos >= len(queue) - 1):
        ss.kr_pos = pos + 1
        st.rerun()


# ── page entry point ──────────────────────────────────────────────────────────

_init()
ss = st.session_state

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🗺️ Kima Review")

    counts = _filter_counts()

    filter_options = {
        "ambiguous":  f"🟠 Ambiguous ({counts['ambiguous']})",
        "unset":      f"❓ Unset — has Kima data ({counts['unset']})",
        "auto":       f"✅ Auto-decided ({counts['auto']})",
        "all":        f"📋 All with Kima data ({counts['all']})",
    }

    prev_filter = ss.kr_filter
    chosen_label = st.radio(
        "Filter",
        list(filter_options.values()),
        index=list(filter_options.keys()).index(ss.kr_filter),
        key="kr_filter_radio",
    )
    new_filter = [k for k, v in filter_options.items() if v == chosen_label][0]
    if new_filter != prev_filter:
        ss.kr_filter = new_filter
        ss.kr_pos = 0
        _rebuild_queue()
        st.rerun()

    st.divider()
    queue = ss.kr_queue
    pos = ss.kr_pos
    if queue:
        reviewed = sum(
            1 for i in queue
            if ss.kr_tsv_by_name.get(ss.kr_results[i]["name"], {}).get("action", "") not in ("", "ambiguous")
        )
        st.metric("Reviewed", f"{reviewed}/{len(queue)}")
        st.progress(reviewed / len(queue) if queue else 0)

    st.divider()
    if st.button("🔄 Reload data", use_container_width=True):
        for k in list(ss.keys()):
            if k.startswith("kr_"):
                del ss[k]
        st.rerun()

    st.divider()
    if st.button("💾 Commit decisions", use_container_width=True):
        changed = sum(1 for r in ss.kr_tsv_rows if r.get("action", ""))
        result = subprocess.run(
            ["git", "add", UNMATCHED_TSV, UNMATCHED_CSV],
            capture_output=True, text=True,
            cwd=os.path.dirname(UNMATCHED_TSV),
        )
        result2 = subprocess.run(
            ["git", "commit", "-m",
             f"Kima Review: {changed} decisions recorded in unmatched-places-report.tsv\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"],
            capture_output=True, text=True,
            cwd=os.path.dirname(UNMATCHED_TSV),
        )
        if result2.returncode == 0:
            st.success(f"Committed {changed} decisions")
        else:
            st.error(result2.stderr or result2.stdout)

# ── main content ──────────────────────────────────────────────────────────────

st.title("🗺️ Kima Place Review")

queue = ss.kr_queue
pos = ss.kr_pos

if not queue:
    st.info(
        f"No rows match the current filter. "
        f"Try switching to a different filter in the sidebar."
    )
else:
    # position indicator
    st.caption(f"Row {pos + 1} of {len(queue)}")
    jump = st.number_input(
        "Jump to row #", min_value=1, max_value=len(queue),
        value=pos + 1, step=1, key="kr_jump",
        label_visibility="collapsed",
    )
    if jump - 1 != pos:
        ss.kr_pos = jump - 1
        st.rerun()

    result_row = ss.kr_results[queue[pos]]
    _render_row(result_row)
