"""Data models for the generic authority review system."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewItem:
    """One item to review (e.g. an unmatched place name or person name)."""
    name: str
    match_status: str = ""        # e.g. "name_exact", "fuzzy", "no_match"
    confidence: str = ""          # e.g. "high", "0.85"
    contexts: list[str] = field(default_factory=list)   # source-text excerpts
    metadata: dict = field(default_factory=dict)        # arbitrary (editions, occurrences, ...)
    raw: dict = field(default_factory=dict)             # original row data


@dataclass
class Candidate:
    """One authority candidate for a review item."""
    authority_id: str             # external ID (e.g. "kima:223", "tsadik:012.077")
    names: dict[str, str] = field(default_factory=dict)  # e.g. {"heb": "...", "lat": "..."}
    local_id: str | None = None   # project-local ID if already mapped (e.g. "H-LOC_123")
    local_name: str = ""          # display name for the local entry
    url: str | None = None        # link to authority source


@dataclass
class ActionOption:
    """One possible action in the decision radio list."""
    label: str          # display text (e.g. "🔗 Map to H-LOC_123 (Jerusalem)")
    action: str         # stored action value (e.g. "map_to:H-LOC_123")
    suggested_id: str   # stored ID value (e.g. "kima:223")


@dataclass
class ReviewConfig:
    """Static configuration for the review page."""
    entity_label: str = "Place"        # "Place", "Person", etc.
    sidebar_title: str = "Review"
    page_title: str = "Authority Review"
    session_prefix: str = "rv_"        # session state key prefix
    context_window: int = 200          # chars around name in context excerpts
    # Filter categories: key → (emoji_label_template, filter_function_name)
    filters: dict[str, str] = field(default_factory=lambda: {
        "ambiguous":  "Ambiguous",
        "unset":      "Unset",
        "auto":       "Auto-decided",
        "all":        "All",
    })
