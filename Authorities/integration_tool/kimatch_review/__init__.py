"""Generic authority review module for Kimatch.

Provides a reusable Streamlit review page that can be configured
for any entity type (places, persons, etc.) by supplying a ReviewBackend.
"""
from kimatch_review.models import ReviewItem, Candidate, ActionOption, ReviewConfig
from kimatch_review.backend import ReviewBackend
from kimatch_review.page import render_review_page

__all__ = [
    "ReviewItem",
    "Candidate",
    "ActionOption",
    "ReviewConfig",
    "ReviewBackend",
    "render_review_page",
]
