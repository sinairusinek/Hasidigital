"""Generic Streamlit review page for authority matching decisions.

Call ``render_review_page(backend, config)`` from your Streamlit app
to display the full review UI.  The backend supplies all project-specific
data; this module handles the UI structure (sidebar, filters, navigation,
candidate table, decision radios, save/next).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from kimatch_review.backend import ReviewBackend
from kimatch_review.models import ActionOption, ReviewConfig


# ── internal helpers ──────────────────────────────────────────────────────────

def _ss_key(cfg: ReviewConfig, key: str) -> str:
    """Namespaced session-state key."""
    return f"{cfg.session_prefix}{key}"


def _ensure_loaded(backend: ReviewBackend, cfg: ReviewConfig) -> None:
    """Load data once per session (or on explicit reload)."""
    ss = st.session_state
    k = _ss_key(cfg, "loaded")
    if not ss.get(k):
        backend.load()
        items = backend.get_items()
        ss[_ss_key(cfg, "items")] = items
        ss[k] = True
        ss[_ss_key(cfg, "filter")] = ss.get(_ss_key(cfg, "filter"), "ambiguous")
        ss[_ss_key(cfg, "pos")] = 0
        _rebuild_queue(backend, cfg)


def _rebuild_queue(backend: ReviewBackend, cfg: ReviewConfig) -> None:
    """Build the queue of item indices matching the current filter."""
    ss = st.session_state
    filt = ss.get(_ss_key(cfg, "filter"), "ambiguous")
    items = ss.get(_ss_key(cfg, "items"), [])

    queue = []
    for i, item in enumerate(items):
        cat = backend.classify_item(item)
        if filt == "all" or cat == filt:
            queue.append(i)

    ss[_ss_key(cfg, "queue")] = queue
    ss[_ss_key(cfg, "pos")] = min(
        ss.get(_ss_key(cfg, "pos"), 0),
        max(len(queue) - 1, 0),
    )


def _filter_counts(backend: ReviewBackend, cfg: ReviewConfig) -> dict[str, int]:
    """Count items per filter category."""
    ss = st.session_state
    items = ss.get(_ss_key(cfg, "items"), [])
    counts: dict[str, int] = {k: 0 for k in cfg.filters}
    counts["all"] = 0

    for item in items:
        cat = backend.classify_item(item)
        counts["all"] += 1
        if cat in counts:
            counts[cat] += 1

    return counts


# ── render one item ───────────────────────────────────────────────────────────

def _render_item(backend: ReviewBackend, cfg: ReviewConfig, item) -> None:
    """Render the full review card for a single item."""
    name = item.name
    action, suggested_id = backend.get_decision(name)

    # ── header ────────────────────────────────────────────────────────────
    st.markdown(f"<h2 style='margin-bottom:0'>{name}</h2>", unsafe_allow_html=True)

    # Metadata caption
    meta_parts = []
    if "occurrences" in item.metadata:
        meta_parts.append(f"{item.metadata['occurrences']} occurrence(s)")
    if "editions" in item.metadata:
        eds = [e.strip() for e in item.metadata["editions"].split(",") if e.strip()]
        meta_parts.append(
            f"{len(eds)} edition(s): "
            + ", ".join(eds[:5])
            + ("\u2026" if len(eds) > 5 else "")
        )
    if meta_parts:
        st.caption(" \u00b7 ".join(meta_parts))

    # Status badges
    if item.match_status or item.confidence:
        col_s, col_c = st.columns([1, 1])
        if item.match_status:
            icon = {"name_exact": "\U0001f3af", "fuzzy": "\u3030\ufe0f"}.get(
                item.match_status, "\u2753"
            )
            col_s.info(f"{icon} Match: **{item.match_status}**")
        if item.confidence:
            col_c.info(f"Confidence: **{item.confidence}**")

    # ── contexts ──────────────────────────────────────────────────────────
    if item.contexts:
        with st.expander("\U0001f4c4 Contexts", expanded=True):
            for ctx in item.contexts[:3]:
                html_snippet = backend.render_context(ctx, name, cfg.context_window)
                st.markdown(html_snippet, unsafe_allow_html=True)

    # ── candidates table ──────────────────────────────────────────────────
    candidates = backend.get_candidates(item)
    if candidates:
        st.markdown(f"**{cfg.entity_label} candidates**")
        table_rows = []
        for c in candidates:
            row = {"ID": f"[{c.authority_id}]({c.url})" if c.url else c.authority_id}
            for lang, val in c.names.items():
                row[lang.capitalize()] = val
            local_label = (
                f"{c.local_id} ({c.local_name})" if c.local_id else "\u2014"
            )
            row["In authority"] = local_label
            table_rows.append(row)
        st.markdown(
            pd.DataFrame(table_rows).to_markdown(index=False),
            unsafe_allow_html=True,
        )

    # ── decision radios ───────────────────────────────────────────────────
    st.divider()
    st.markdown("**Decision**")

    action_options = backend.get_action_options(item, candidates)

    # Always add the standard tail options
    action_options += [
        ActionOption(
            label="\u23ed\ufe0f Skip \u2014 not a valid entity",
            action="skip",
            suggested_id="",
        ),
        ActionOption(
            label="\U0001f500 Ambiguous \u2014 decide later",
            action="ambiguous",
            suggested_id=(
                suggested_id
                or "|".join(c.authority_id for c in candidates)
            ),
        ),
        ActionOption(
            label="\u270f\ufe0f Custom action\u2026",
            action="__custom__",
            suggested_id="",
        ),
    ]

    radio_labels = [opt.label for opt in action_options]

    # Pre-select current decision
    default_idx = 0
    if action == "skip":
        default_idx = next(
            (i for i, o in enumerate(action_options) if o.action == "skip"), 0
        )
    elif action == "ambiguous":
        default_idx = next(
            (i for i, o in enumerate(action_options) if o.action == "ambiguous"), 0
        )
    elif action:
        for i, opt in enumerate(action_options):
            if opt.action == action:
                default_idx = i
                break
            if action.startswith("map_to:") and opt.action.startswith("map_to:"):
                target = action[len("map_to:"):]
                if target in opt.label:
                    default_idx = i
                    break
            if action == "new" and opt.action == "new" and suggested_id in opt.label:
                default_idx = i
                break
        else:
            default_idx = next(
                (i for i, o in enumerate(action_options) if o.action == "__custom__"),
                0,
            )

    choice_label = st.radio(
        "Choose action:",
        radio_labels,
        index=default_idx,
        key=f"{cfg.session_prefix}radio_{name}",
        label_visibility="collapsed",
    )

    chosen = action_options[radio_labels.index(choice_label)]

    custom_action = ""
    custom_id = ""
    if chosen.action == "__custom__":
        col_a, col_b = st.columns(2)
        custom_action = col_a.text_input(
            "Action (e.g. map_to:ID / new / skip)",
            value=action,
            key=f"{cfg.session_prefix}custom_action_{name}",
        )
        custom_id = col_b.text_input(
            "Suggested ID",
            value=suggested_id,
            key=f"{cfg.session_prefix}custom_id_{name}",
        )

    # ── save & navigate ───────────────────────────────────────────────────
    st.write("")
    ss = st.session_state
    pos = ss.get(_ss_key(cfg, "pos"), 0)
    queue = ss.get(_ss_key(cfg, "queue"), [])

    # Callbacks execute BEFORE the rerun — the correct Streamlit pattern for
    # buttons that update session state. Using st.rerun() inside a button
    # handler can misbehave in certain Streamlit Cloud environments.
    def _go_prev():
        ss[_ss_key(cfg, "pos")] = ss.get(_ss_key(cfg, "pos"), 0) - 1

    def _go_next():
        ss[_ss_key(cfg, "pos")] = ss.get(_ss_key(cfg, "pos"), 0) + 1

    def _do_save():
        if chosen.action == "__custom__":
            act = ss.get(f"{cfg.session_prefix}custom_action_{name}", "").strip()
            sid = ss.get(f"{cfg.session_prefix}custom_id_{name}", "").strip()
        else:
            act = chosen.action
            sid = chosen.suggested_id
        backend.save_decision(name, act, sid)
        cur_pos = ss.get(_ss_key(cfg, "pos"), 0)
        cur_queue = ss.get(_ss_key(cfg, "queue"), [])
        if cur_pos < len(cur_queue) - 1:
            ss[_ss_key(cfg, "pos")] = cur_pos + 1
        _rebuild_queue(backend, cfg)

    col_prev, col_save, col_next = st.columns([1, 2, 1])

    col_prev.button(
        "\u2190 Prev",
        use_container_width=True,
        disabled=pos == 0,
        on_click=_go_prev,
    )

    save_label = (
        "\U0001f4be Save & Next \u2192" if pos < len(queue) - 1 else "\U0001f4be Save"
    )
    col_save.button(
        save_label,
        type="primary",
        use_container_width=True,
        on_click=_do_save,
    )

    col_next.button(
        "Next \u2192",
        use_container_width=True,
        disabled=pos >= len(queue) - 1,
        on_click=_go_next,
    )


# ── public entry point ────────────────────────────────────────────────────────

def render_review_page(backend: ReviewBackend, config: ReviewConfig | None = None) -> None:
    """Render the full review page (sidebar + main content).

    Call this from your Streamlit page script.

    Parameters
    ----------
    backend : ReviewBackend
        Project-specific data provider.
    config : ReviewConfig, optional
        UI configuration.  Defaults to sensible place-review settings.
    """
    cfg = config or ReviewConfig()
    ss = st.session_state

    _ensure_loaded(backend, cfg)

    # ── sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"### {cfg.sidebar_title}")

        counts = _filter_counts(backend, cfg)
        filter_options = {
            k: f"{label} ({counts.get(k, 0)})"
            for k, label in cfg.filters.items()
        }
        if "all" not in filter_options:
            filter_options["all"] = f"All ({counts.get('all', 0)})"

        current_filter = ss.get(_ss_key(cfg, "filter"), "ambiguous")
        chosen_label = st.radio(
            "Filter",
            list(filter_options.values()),
            index=list(filter_options.keys()).index(current_filter)
            if current_filter in filter_options
            else 0,
            key=f"{cfg.session_prefix}filter_radio",
        )
        new_filter = [k for k, v in filter_options.items() if v == chosen_label][0]
        if new_filter != current_filter:
            ss[_ss_key(cfg, "filter")] = new_filter
            ss[_ss_key(cfg, "pos")] = 0
            _rebuild_queue(backend, cfg)
            st.rerun()

        st.divider()

        queue = ss.get(_ss_key(cfg, "queue"), [])
        items = ss.get(_ss_key(cfg, "items"), [])
        if queue:
            reviewed = sum(
                1
                for i in queue
                if backend.classify_item(items[i]) == "auto"
            )
            st.metric("Reviewed", f"{reviewed}/{len(queue)}")
            st.progress(reviewed / len(queue) if queue else 0)

        st.divider()

        def _reload():
            for k in list(ss.keys()):
                if k.startswith(cfg.session_prefix):
                    del ss[k]
            # Also clear the cached backend so it reloads fresh data
            if "kr_backend" in ss:
                del ss["kr_backend"]

        st.button(
            "\U0001f504 Reload data",
            use_container_width=True,
            on_click=_reload,
        )

        st.divider()
        if st.button("\U0001f4be Commit decisions", use_container_width=True):
            ok, msg = backend.commit()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    # ── main content ──────────────────────────────────────────────────────
    st.title(cfg.page_title)

    queue = ss.get(_ss_key(cfg, "queue"), [])
    pos = ss.get(_ss_key(cfg, "pos"), 0)

    if not queue:
        st.info("No rows match the current filter. Try switching in the sidebar.")
        return

    # Position indicator + jump
    st.caption(f"Row {pos + 1} of {len(queue)}")
    jump = st.number_input(
        "Jump to row #",
        min_value=1,
        max_value=len(queue),
        value=pos + 1,
        step=1,
        key=f"{cfg.session_prefix}jump",
        label_visibility="collapsed",
    )
    if jump - 1 != pos:
        ss[_ss_key(cfg, "pos")] = jump - 1
        st.rerun()

    items = ss.get(_ss_key(cfg, "items"), [])
    item = items[queue[pos]]
    _render_item(backend, cfg, item)
