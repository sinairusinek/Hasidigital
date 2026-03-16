"""Hasidigital-specific adapter for the Kimatch generic review module.

Implements ``ReviewBackend`` by wiring Hasidigital's data files
(Kimatch CSV results, unmatched-places TSV, authorities-matching-db.json,
Kima places CSV) into the generic review UI.

Works both locally (file-based writes) and on Streamlit Cloud
(GitHub API write-back via st.secrets).

Usage in a Streamlit page::

    from kimatch_adapter import HasidigitalPlaceBackend
    from kimatch.review import render_review_page, ReviewConfig

    backend = HasidigitalPlaceBackend()
    render_review_page(backend, config)

Streamlit secrets required for cloud deployment::

    [github]
    token = "ghp_..."
    repo  = "sinairusinek/Hasidigital"
    branch = "main"
    tsv_path = "editions/unmatched-places-report.tsv"
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess

import pandas as pd
import streamlit as st

try:
    from kimatch.review.backend import ReviewBackend
    from kimatch.review.models import ReviewItem, Candidate, ActionOption
except ImportError:
    from kimatch_review.backend import ReviewBackend  # type: ignore[no-redef]
    from kimatch_review.models import ReviewItem, Candidate, ActionOption  # type: ignore[no-redef]

from config import (
    MATCHING_DB_PATH,
    UNMATCHED_CSV,
    UNMATCHED_TSV,
    KIMA_PLACES_CSV,
)

KIMA_URL_BASE = "https://data.geo-kima.org/Places/Details/"


# ── GitHub write-back helpers ─────────────────────────────────────────────────

def _github_secrets() -> dict | None:
    """Return GitHub secrets dict if running on Streamlit Cloud, else None."""
    try:
        gh = st.secrets.get("github", {})
        if gh.get("token") and gh.get("repo"):
            return dict(gh)
    except Exception:
        pass
    return None


def _tsv_to_string(rows: list[dict], fieldnames: list[str]) -> str:
    """Serialise TSV rows to a string (for GitHub API upload)."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _push_tsv_to_github(
    rows: list[dict],
    fieldnames: list[str],
    gh_secrets: dict,
    commit_message: str,
) -> tuple[bool, str]:
    """Update the TSV file in GitHub via the Contents API. Returns (ok, message)."""
    try:
        from github import Github, GithubException
    except ImportError:
        return False, "PyGithub not installed — cannot push to GitHub"

    token = gh_secrets["token"]
    repo_name = gh_secrets["repo"]
    branch = gh_secrets.get("branch", "main")
    tsv_path = gh_secrets.get("tsv_path", "editions/unmatched-places-report.tsv")

    content = _tsv_to_string(rows, fieldnames)

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        existing = repo.get_contents(tsv_path, ref=branch)
        repo.update_file(
            path=tsv_path,
            message=commit_message,
            content=content,
            sha=existing.sha,
            branch=branch,
        )
        return True, "Saved to GitHub ✓"
    except GithubException as e:
        if e.status == 409:
            return (
                False,
                "⚠️ Conflict — someone else saved at the same time. "
                "Please reload the page and try again.",
            )
        return False, f"GitHub error {e.status}: {e.data.get('message', str(e))}"
    except Exception as e:
        return False, f"Error pushing to GitHub: {e}"


# ── TSV helpers ───────────────────────────────────────────────────────────────

def _read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return list(csv.DictReader(io.StringIO(content), delimiter="\t"))


def _write_tsv_local(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)


# ── Kima ID helpers ───────────────────────────────────────────────────────────

def _kima_url_to_id(url: str) -> int | None:
    m = re.search(r"/(\d+)$", url or "")
    return int(m.group(1)) if m else None


def _candidate_ids(result_row: dict, tsv_row: dict | None = None) -> list[int]:
    """Collect all Kima candidate IDs from Kimatch output and TSV suggested_id."""
    ids: list[int] = []
    for raw in [
        result_row.get("_kima_id", ""),
        *(result_row.get("_candidates", "").split("|")),
    ]:
        raw = (raw or "").strip()
        if raw:
            try:
                ids.append(int(raw))
            except ValueError:
                pass
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


# ── Backend ───────────────────────────────────────────────────────────────────

class HasidigitalPlaceBackend(ReviewBackend):
    """ReviewBackend for Hasidigital Kima place review.

    Reads Kimatch CSV results, unmatched-places TSV, Kima CSV,
    and authorities-matching-db.json to drive the review UI.

    On Streamlit Cloud (st.secrets["github"] present): saves decisions via
    the GitHub Contents API so every save is a real commit in the repo.
    Locally: writes the TSV file directly; ``commit()`` runs git commit.
    """

    def __init__(self) -> None:
        self._results: list[dict] = []
        self._tsv_rows: list[dict] = []
        self._tsv_fieldnames: list[str] = []
        self._tsv_by_name: dict[str, dict] = {}
        self._kima_names: dict[int, dict] = {}
        self._kima_to_hloc: dict[int, str] = {}
        self._hloc_names: dict[str, str] = {}
        self._gh = _github_secrets()  # None when running locally

    # ── data loading ──────────────────────────────────────────────────────

    def load(self) -> None:
        # 1. Kimatch results CSV
        if not os.path.exists(UNMATCHED_CSV):
            st.error(f"Kimatch results not found: {UNMATCHED_CSV}")
            st.stop()
        with open(UNMATCHED_CSV, encoding="utf-8") as f:
            self._results = list(csv.DictReader(f))

        # 2. TSV (live decisions) — always available (in repo checkout on Cloud too)
        if not os.path.exists(UNMATCHED_TSV):
            st.error(f"Unmatched TSV not found: {UNMATCHED_TSV}")
            st.stop()
        self._tsv_rows = _read_tsv(UNMATCHED_TSV)
        self._tsv_fieldnames = (
            list(self._tsv_rows[0].keys()) if self._tsv_rows else []
        )
        self._tsv_by_name = {r["name"]: r for r in self._tsv_rows}

        # 3. Collect all Kima IDs
        all_kima_ids: set[int] = set()
        for row in self._results:
            for kid in _candidate_ids(row):
                all_kima_ids.add(kid)

        # 4. Load Kima place names (full CSV locally, trimmed CSV on Cloud)
        self._kima_names = {}
        if os.path.exists(KIMA_PLACES_CSV) and all_kima_ids:
            try:
                with st.spinner("Loading Kima place names…"):
                    df = pd.read_csv(KIMA_PLACES_CSV, dtype=str, low_memory=False)
                    df["id"] = pd.to_numeric(df["id"], errors="coerce")
                    subset = df[df["id"].isin(all_kima_ids)]
                    for _, r in subset.iterrows():
                        kid = int(r["id"])
                        self._kima_names[kid] = {
                            "heb": str(r.get("primary_heb_full", "") or ""),
                            "rom": str(r.get("primary_rom_full", "") or ""),
                        }
            except Exception as e:
                st.warning(f"Could not load Kima CSV: {e}")
        elif not os.path.exists(KIMA_PLACES_CSV):
            st.warning(
                f"Kima CSV not found at {KIMA_PLACES_CSV}. "
                "Candidate names will be limited."
            )

        # 5. Build kima_id → H-LOC and H-LOC → name from authority DB
        self._kima_to_hloc = {}
        self._hloc_names = {}
        if os.path.exists(MATCHING_DB_PATH):
            with open(MATCHING_DB_PATH, encoding="utf-8") as f:
                db = json.load(f)
            for p in db.get("places", []):
                hloc = p["id"]
                self._hloc_names[hloc] = (
                    p.get("primary_name_he", "") or p.get("primary_name_en", "")
                )
                kid = _kima_url_to_id(
                    p.get("identifiers", {}).get("Kima", "")
                )
                if kid is not None:
                    self._kima_to_hloc[kid] = hloc

    # ── items ─────────────────────────────────────────────────────────────

    def get_items(self) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        for row in self._results:
            status = row.get("_match_status", "")
            if status == "no_match":
                continue
            contexts_raw = row.get("contexts", "")
            contexts = [c.strip() for c in contexts_raw.split(" | ") if c.strip()]
            items.append(
                ReviewItem(
                    name=row["name"],
                    match_status=status,
                    confidence=row.get("_confidence", ""),
                    contexts=contexts,
                    metadata={
                        "occurrences": row.get("occurrences", "?"),
                        "editions": row.get("editions", ""),
                    },
                    raw=row,
                )
            )
        return items

    def get_candidates(self, item: ReviewItem) -> list[Candidate]:
        tsv_row = self._tsv_by_name.get(item.name)
        cand_ids = _candidate_ids(item.raw, tsv_row)
        candidates: list[Candidate] = []
        for kid in cand_ids:
            info = self._kima_names.get(kid, {})
            hloc = self._kima_to_hloc.get(kid, "")
            candidates.append(
                Candidate(
                    authority_id=f"kima:{kid}",
                    names={
                        "heb": info.get("heb", ""),
                        "lat": info.get("rom", ""),
                    },
                    local_id=hloc or None,
                    local_name=self._hloc_names.get(hloc, "") if hloc else "",
                    url=f"{KIMA_URL_BASE}{kid}",
                )
            )
        return candidates

    def get_action_options(
        self, item: ReviewItem, candidates: list[Candidate]
    ) -> list[ActionOption]:
        options: list[ActionOption] = []
        for c in candidates:
            kid = c.authority_id  # "kima:123"
            heb = c.names.get("heb", kid)
            if c.local_id:
                label = f"🔗 Map to {c.local_id}  ({c.local_name} / {heb})"
                options.append(
                    ActionOption(
                        label=label,
                        action=f"map_to:{c.local_id}",
                        suggested_id=kid,
                    )
                )
            else:
                label = f"🆕 New entry — {kid}  ({heb})"
                options.append(
                    ActionOption(label=label, action="new", suggested_id=kid)
                )
        return options

    # ── decisions ─────────────────────────────────────────────────────────

    def get_decision(self, name: str) -> tuple[str, str]:
        tsv_row = self._tsv_by_name.get(name, {})
        return tsv_row.get("action", ""), tsv_row.get("suggested_id", "")

    def save_decision(self, name: str, action: str, suggested_id: str) -> None:
        tsv_row = self._tsv_by_name.get(name)
        if tsv_row is None:
            return
        tsv_row["action"] = action
        tsv_row["suggested_id"] = suggested_id

        if self._gh:
            # Cloud: push to GitHub immediately (each save = one commit)
            ok, msg = _push_tsv_to_github(
                self._tsv_rows,
                self._tsv_fieldnames,
                self._gh,
                commit_message=(
                    f"Kima Review: decision for '{name}' → {action or 'cleared'}\n\n"
                    f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
                ),
            )
            if not ok:
                st.warning(f"Save failed: {msg}")
        else:
            # Local: write file directly
            _write_tsv_local(UNMATCHED_TSV, self._tsv_rows, self._tsv_fieldnames)

    # ── filtering ─────────────────────────────────────────────────────────

    def classify_item(self, item: ReviewItem) -> str:
        action = self._tsv_by_name.get(item.name, {}).get("action", "")
        if action == "ambiguous":
            return "ambiguous"
        if action == "":
            return "unset"
        return "auto"

    # ── optional overrides ────────────────────────────────────────────────

    def commit(self) -> tuple[bool, str]:
        if self._gh:
            # On Cloud, every save is already a GitHub commit
            changed = sum(1 for r in self._tsv_rows if r.get("action", ""))
            return True, f"{changed} decisions are already saved to GitHub automatically."

        # Local: git commit
        changed = sum(1 for r in self._tsv_rows if r.get("action", ""))
        subprocess.run(
            ["git", "add", UNMATCHED_TSV, UNMATCHED_CSV],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(UNMATCHED_TSV),
        )
        result = subprocess.run(
            [
                "git", "commit", "-m",
                f"Kima Review: {changed} decisions recorded in "
                f"unmatched-places-report.tsv\n\n"
                f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(UNMATCHED_TSV),
        )
        if result.returncode == 0:
            return True, f"Committed {changed} decisions"
        return False, result.stderr or result.stdout
