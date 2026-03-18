"""Hasidigital-specific adapter for person name review (Shidduch results).

Implements ``ReviewBackend`` by wiring Hasidigital's data files
(Shidduch CSV results, unmatched-persons TSV, authorities-matching-db.json)
into the generic review UI.

Works both locally (file-based writes) and on Streamlit Cloud
(GitHub API write-back via st.secrets).

Usage in a Streamlit page::

    from shidduch_adapter import HasidigitalPersonBackend
    from kimatch.review import render_review_page, ReviewConfig

    backend = HasidigitalPersonBackend()
    render_review_page(backend, config)

Streamlit secrets required for cloud deployment::

    [github]
    token = "ghp_..."
    repo  = "sinairusinek/Hasidigital"
    branch = "main"
    tsv_path = "editions/unmatched-persons-report.tsv"
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess

import streamlit as st

try:
    from kimatch.review.backend import ReviewBackend
    from kimatch.review.models import ReviewItem, Candidate, ActionOption
except ImportError:
    from kimatch_review.backend import ReviewBackend  # type: ignore[no-redef]
    from kimatch_review.models import ReviewItem, Candidate, ActionOption  # type: ignore[no-redef]

from config import (
    MATCHING_DB_PATH,
    UNMATCHED_PERSONS_CSV,
    UNMATCHED_PERSONS_TSV,
)


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
        return False, "PyGithub not installed -- cannot push to GitHub"

    token = gh_secrets["token"]
    repo_name = gh_secrets["repo"]
    branch = gh_secrets.get("branch", "main")
    tsv_path = gh_secrets.get(
        "persons_tsv_path", "editions/unmatched-persons-report.tsv"
    )

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
        return True, "Saved to GitHub"
    except GithubException as e:
        if e.status == 409:
            return (
                False,
                "Conflict -- someone else saved at the same time. "
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


# ── Backend ───────────────────────────────────────────────────────────────────

class HasidigitalPersonBackend(ReviewBackend):
    """ReviewBackend for Hasidigital person name review.

    Reads Shidduch CSV results, unmatched-persons TSV,
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
        self._persons_db: dict[str, dict] = {}  # person_id -> person dict
        self._gh = _github_secrets()

    # ── data loading ──────────────────────────────────────────────────────

    def load(self) -> None:
        # 1. Shidduch results CSV
        if not os.path.exists(UNMATCHED_PERSONS_CSV):
            st.error(f"Shidduch results not found: {UNMATCHED_PERSONS_CSV}")
            st.stop()
        with open(UNMATCHED_PERSONS_CSV, encoding="utf-8") as f:
            self._results = list(csv.DictReader(f))

        # 2. TSV (live decisions)
        if not os.path.exists(UNMATCHED_PERSONS_TSV):
            st.error(f"Unmatched persons TSV not found: {UNMATCHED_PERSONS_TSV}")
            st.stop()
        self._tsv_rows = _read_tsv(UNMATCHED_PERSONS_TSV)
        self._tsv_fieldnames = (
            list(self._tsv_rows[0].keys()) if self._tsv_rows else []
        )
        self._tsv_by_name = {r["name"]: r for r in self._tsv_rows}

        # 3. Person authority DB (for candidate display)
        self._persons_db = {}
        if os.path.exists(MATCHING_DB_PATH):
            with open(MATCHING_DB_PATH, encoding="utf-8") as f:
                db = json.load(f)
            for p in db.get("persons", []):
                pid = p["id"]
                self._persons_db[pid] = p

    # ── items ─────────────────────────────────────────────────────────────

    def get_items(self) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        for row in self._results:
            status = row.get("_match_status", "")
            # Include all rows (matched and unmatched) for review
            context_raw = row.get("context", "")
            contexts = [context_raw] if context_raw.strip() else []
            items.append(
                ReviewItem(
                    name=row.get("name", ""),
                    match_status=status,
                    confidence=row.get("_confidence", ""),
                    contexts=contexts,
                    metadata={
                        "occurrences": row.get("occurrences", "?"),
                        "editions": row.get("editions", ""),
                        "place_ref": row.get("place_ref", ""),
                        "person_id": row.get("_person_id", ""),
                        "person_name_he": row.get("_person_name_he", ""),
                        "person_name_en": row.get("_person_name_en", ""),
                    },
                    raw=row,
                )
            )
        return items

    def get_candidates(self, item: ReviewItem) -> list[Candidate]:
        candidates: list[Candidate] = []

        # Parse _candidates field: "tempH-1(0.85)|tempH-2(0.72)"
        cand_str = item.raw.get("_candidates", "")
        if cand_str:
            for part in cand_str.split("|"):
                part = part.strip()
                if not part:
                    continue
                # Parse "tempH-1(0.85)"
                paren = part.rfind("(")
                if paren >= 0:
                    pid = part[:paren]
                    conf = part[paren + 1 :].rstrip(")")
                else:
                    pid = part
                    conf = ""

                p = self._persons_db.get(pid, {})
                names_he = p.get("names_he", [])
                names_en = p.get("names_en", [])
                dijest = p.get("identifiers", {}).get("DiJeStDB", "")

                candidates.append(
                    Candidate(
                        authority_id=pid,
                        names={
                            "heb": " / ".join(names_he) if names_he else "",
                            "eng": " / ".join(names_en) if names_en else "",
                        },
                        local_id=pid,
                        local_name=(
                            f"{' / '.join(names_he)}"
                            + (f" ({dijest})" if dijest else "")
                        ),
                    )
                )

        # Also include the top match if not already in candidates
        top_pid = item.raw.get("_person_id", "")
        if top_pid and not any(c.authority_id == top_pid for c in candidates):
            p = self._persons_db.get(top_pid, {})
            names_he = p.get("names_he", [])
            names_en = p.get("names_en", [])
            dijest = p.get("identifiers", {}).get("DiJeStDB", "")
            candidates.insert(
                0,
                Candidate(
                    authority_id=top_pid,
                    names={
                        "heb": " / ".join(names_he) if names_he else "",
                        "eng": " / ".join(names_en) if names_en else "",
                    },
                    local_id=top_pid,
                    local_name=(
                        f"{' / '.join(names_he)}"
                        + (f" ({dijest})" if dijest else "")
                    ),
                ),
            )

        # Also check TSV for a previously suggested ID
        tsv_row = self._tsv_by_name.get(item.name)
        if tsv_row:
            suggested = tsv_row.get("suggested_id", "").strip()
            if suggested and not any(c.authority_id == suggested for c in candidates):
                p = self._persons_db.get(suggested, {})
                names_he = p.get("names_he", [])
                names_en = p.get("names_en", [])
                candidates.append(
                    Candidate(
                        authority_id=suggested,
                        names={
                            "heb": " / ".join(names_he) if names_he else "",
                            "eng": " / ".join(names_en) if names_en else "",
                        },
                        local_id=suggested,
                        local_name=" / ".join(names_he) if names_he else suggested,
                    )
                )

        return candidates

    def get_action_options(
        self, item: ReviewItem, candidates: list[Candidate]
    ) -> list[ActionOption]:
        options: list[ActionOption] = []
        for c in candidates:
            heb = c.names.get("heb", c.authority_id)
            eng = c.names.get("eng", "")
            display = heb
            if eng:
                display += f" / {eng}"
            label = f"Link to {c.authority_id}  ({display})"
            options.append(
                ActionOption(
                    label=label,
                    action=f"map_to:{c.authority_id}",
                    suggested_id=c.authority_id,
                )
            )
        # Always add "new person" and "skip" options
        options.append(
            ActionOption(
                label="New person entry",
                action="new",
                suggested_id="",
            )
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
            ok, msg = _push_tsv_to_github(
                self._tsv_rows,
                self._tsv_fieldnames,
                self._gh,
                commit_message=(
                    f"Person Review: decision for '{name}' -> {action or 'cleared'}\n\n"
                    f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
                ),
            )
            if not ok:
                st.warning(f"Save failed: {msg}")
        else:
            _write_tsv_local(
                UNMATCHED_PERSONS_TSV, self._tsv_rows, self._tsv_fieldnames
            )

    # ── filtering ─────────────────────────────────────────────────────────

    def classify_item(self, item: ReviewItem) -> str:
        action = self._tsv_by_name.get(item.name, {}).get("action", "")
        status = item.match_status

        if action == "ambiguous":
            return "ambiguous"
        if action == "":
            # Auto-classify based on match status
            if status in ("name_exact", "phonetic"):
                return "has_candidates"
            return "unset"
        return "auto"

    # ── optional overrides ────────────────────────────────────────────────

    def commit(self) -> tuple[bool, str]:
        if self._gh:
            changed = sum(1 for r in self._tsv_rows if r.get("action", ""))
            return True, f"{changed} decisions are already saved to GitHub automatically."

        changed = sum(1 for r in self._tsv_rows if r.get("action", ""))
        subprocess.run(
            ["git", "add", UNMATCHED_PERSONS_TSV, UNMATCHED_PERSONS_CSV],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(UNMATCHED_PERSONS_TSV),
        )
        result = subprocess.run(
            [
                "git", "commit", "-m",
                f"Person Review: {changed} decisions recorded in "
                f"unmatched-persons-report.tsv\n\n"
                f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(UNMATCHED_PERSONS_TSV),
        )
        if result.returncode == 0:
            return True, f"Committed {changed} decisions"
        return False, result.stderr or result.stdout
