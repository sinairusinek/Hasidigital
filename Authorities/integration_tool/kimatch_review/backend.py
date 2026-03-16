"""Abstract backend for the review page.

Subclass ReviewBackend and implement all methods to adapt the generic
review UI to a specific project's data and authority system.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from kimatch_review.models import ReviewItem, Candidate, ActionOption


class ReviewBackend(ABC):
    """Base class for project-specific review backends.

    Implement all abstract methods to wire the generic review page
    to your project's data files, authority DB, and persistence layer.
    """

    # ── data loading ──────────────────────────────────────────────────────

    @abstractmethod
    def load(self) -> None:
        """Load all data needed for the review session.

        Called once when the page first loads (or on explicit reload).
        """

    # ── items ─────────────────────────────────────────────────────────────

    @abstractmethod
    def get_items(self) -> list[ReviewItem]:
        """Return all reviewable items (pre-filtered to exclude no-match, etc.)."""

    @abstractmethod
    def get_candidates(self, item: ReviewItem) -> list[Candidate]:
        """Return authority candidates for a given item."""

    @abstractmethod
    def get_action_options(self, item: ReviewItem, candidates: list[Candidate]) -> list[ActionOption]:
        """Build the radio-button action options for this item.

        Should include candidate-specific options (map/new) plus
        generic ones (skip, ambiguous, custom).
        """

    # ── decisions ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_decision(self, name: str) -> tuple[str, str]:
        """Return (action, suggested_id) for the named item, or ("", "")."""

    @abstractmethod
    def save_decision(self, name: str, action: str, suggested_id: str) -> None:
        """Persist a decision for the named item."""

    # ── filtering ─────────────────────────────────────────────────────────

    @abstractmethod
    def classify_item(self, item: ReviewItem) -> str:
        """Return the filter category for an item: "ambiguous", "unset", "auto", etc.

        Used by the generic page to build filter counts and queue.
        """

    # ── optional ──────────────────────────────────────────────────────────

    def commit(self) -> tuple[bool, str]:
        """Commit current decisions (e.g. git commit). Return (success, message).

        Override if your backend supports committing. Default: no-op.
        """
        return True, "No commit configured"

    def render_context(self, context: str, name: str, window: int = 200) -> str:
        """Return an HTML snippet for a context excerpt, with the name highlighted.

        Default implementation does basic Hebrew-aware highlighting.
        Override for project-specific rendering.
        """
        return _default_render_context(context, name, window)


# ── default context renderer ──────────────────────────────────────────────

def _default_render_context(ctx: str, name: str, window: int = 200) -> str:
    """Basic Hebrew-aware context rendering with highlighting."""
    import html as html_lib
    import re

    # Find the name in context
    idx = ctx.find(name)
    if idx == -1:
        # Try with common Hebrew prefix letter (מ/ב/ל/ו/ה/כ/ש)
        m = re.search(r"[במולהוכש]" + re.escape(name), ctx)
        idx = m.start() + 1 if m else -1

    if idx != -1:
        start = max(0, idx - window)
        end = min(len(ctx), idx + len(name) + window)
        prefix = "\u2026" if start > 0 else ""
        suffix = "\u2026" if end < len(ctx) else ""
        excerpt = prefix + ctx[start:end] + suffix
    else:
        excerpt = ctx[:400] + ("\u2026" if len(ctx) > 400 else "")

    # Escape HTML, then highlight the name
    escaped = html_lib.escape(excerpt)
    esc_name = html_lib.escape(name)
    mark = "<mark style='background:#ffe066;padding:0 2px;border-radius:2px'>"

    # Bare match
    highlighted = escaped.replace(esc_name, f"{mark}{esc_name}</mark>")

    # Prefix match (Hebrew prefix letters glued to the name)
    for pfx in "\u05d1\u05de\u05d5\u05dc\u05d4\u05d5\u05db\u05e9":  # במולהוכש
        glued = html_lib.escape(pfx) + esc_name
        highlighted = highlighted.replace(
            glued,
            f"{html_lib.escape(pfx)}{mark}{esc_name}</mark>",
        )

    return (
        f"<div style='direction:rtl;text-align:right;font-size:0.9em;"
        f"padding:6px;background:#f8f9fa;border-radius:4px;margin-bottom:4px'>"
        f"{highlighted}</div>"
    )
