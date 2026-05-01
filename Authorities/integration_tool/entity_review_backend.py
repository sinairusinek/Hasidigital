"""
Backend for the Entity Review page.

Loads two data sources:
  - editions/incoming/ready/gemini-correction-log.tsv  (Gemini diff, 5180 rows)
  - editions/online/annotation-quality-report.tsv      (quality scanner, ~1130 rows)

Groups occurrences by (normalised_text, tag), assigns a confidence tier to each group,
and handles saving decisions to local TSV + GitHub.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

TOOL_DIR = Path(__file__).parent
PROJECT_DIR = TOOL_DIR.parent.parent
READY_DIR = PROJECT_DIR / "editions" / "incoming" / "ready"

DIFF_TSV = READY_DIR / "gemini-correction-log.tsv"
QUALITY_TSV = PROJECT_DIR / "editions" / "online" / "annotation-quality-report.tsv"
DECISIONS_TSV = READY_DIR / "entity-review-decisions.tsv"
MATCHING_DB_PATH = TOOL_DIR.parent / "authorities-matching-db.json"

DECISIONS_GH_PATH = "editions/incoming/ready/entity-review-decisions.tsv"
DECISIONS_FIELDNAMES = [
    "text", "tag", "tier", "group_decision", "per_occurrence_json",
    "reviewer_name", "reviewer_email", "timestamp", "note",
]

CONTEXT_WINDOW = 200  # chars either side of entity in context snippet

# NER label codes → display tag names
_LABEL_TO_TAG = {
    "PER": "persName", "GPE": "placeName", "LOC": "placeName",
    "ORG": "orgName", "TIMEX": "date",
    "WOA": "name[work]", "MISC": "name[misc]", "EVENT": "name[event]",
}

_DIACRITICS_RE = re.compile(r"[׳״\"']")
_WHITESPACE_RE = re.compile(r"\s")


# ── Text helpers ──────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalise for grouping: strip geresh/gershayim and surrounding whitespace."""
    return _DIACRITICS_RE.sub("", text).strip()


def _label_to_tag(label: str) -> str:
    return _LABEL_TO_TAG.get(label, label)


def _find_context(plain: str, entity_text: str, start: int, end: int) -> tuple[str, str, str]:
    """Return (before, entity, after) strings for display."""
    n = len(plain)
    window = plain[max(0, start - 400): min(n, end + 400)]
    pos = window.find(entity_text)
    if pos == -1:
        pos_g = plain.find(entity_text)
        actual_start = pos_g if pos_g != -1 else start
    else:
        actual_start = max(0, start - 400) + pos
    actual_end = actual_start + len(entity_text)

    ctx_s = max(0, actual_start - CONTEXT_WINDOW)
    ctx_e = min(n, actual_end + CONTEXT_WINDOW)
    before = plain[ctx_s:actual_start]
    after = plain[actual_end:ctx_e]

    # Trim to nearest word boundary so we don't split mid-word
    if ctx_s > 0 and before and before[0] not in " \n":
        sp = before.find(" ")
        before = before[sp + 1:] if sp != -1 else before
    if ctx_e < n and after and after[-1] not in " \n":
        sp = after.rfind(" ")
        after = after[:sp] if sp != -1 else after

    return before.strip(), entity_text, after.strip()


def _containing_word(plain: str, start: int, end: int) -> str:
    """Return the full whitespace-delimited word that contains the entity span.
    Returns empty string if the entity IS the full word."""
    w_start = start
    while w_start > 0 and not _WHITESPACE_RE.match(plain[w_start - 1]):
        w_start -= 1
    w_end = end
    while w_end < len(plain) and not _WHITESPACE_RE.match(plain[w_end]):
        w_end += 1
    word = plain[w_start:w_end]
    return word if word != plain[start:end] else ""


# ── Data loading ──────────────────────────────────────────────────────────────

def _create_standoff_view(tree):
    """Inline of ner_pipeline.text_extraction.create_standoff_view (avoids package import)."""
    from standoffconverter import Standoff, View
    TEI_NS = "http://www.tei-c.org/ns/1.0"
    NAMESPACES = {"tei": TEI_NS}
    root = tree.getroot()
    for facsimile in root.findall(f".//{{{TEI_NS}}}facsimile"):
        parent = facsimile.getparent()
        if parent is not None:
            parent.remove(facsimile)
    so = Standoff(tree, NAMESPACES)
    view = View(so)
    return so, view, view.get_plain()


def load_plain_texts() -> dict[str, str]:
    """Extract plain text from each XML in editions/incoming/ready/ via standoffconverter."""
    from lxml import etree

    plain_texts: dict[str, str] = {}
    for xml_path in sorted(READY_DIR.glob("*.xml")):
        try:
            tree = etree.parse(str(xml_path))
            _, _, plain = _create_standoff_view(tree)
            plain_texts[xml_path.name] = plain
        except Exception:
            plain_texts[xml_path.name] = ""
    return plain_texts


def load_authority_refs() -> set[str]:
    """Return normalised name strings that exist in the authority matching DB."""
    if not MATCHING_DB_PATH.exists():
        return set()
    with open(MATCHING_DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    refs: set[str] = set()
    for entity in db.get("places", []) + db.get("persons", []):
        for name in entity.get("names_he", []) + entity.get("names_en", []):
            refs.add(_norm(name))
    return refs


# ── Tier assignment ────────────────────────────────────────────────────────────

def _assign_tier(occurrences: list[dict], auth_refs: set[str], norm_text: str) -> tuple[str, str]:
    """Return (tier, reason) for a group of occurrences."""
    any_gemini_removed = any(
        o["source"] == "gemini_diff" and o["action"] == "removed"
        for o in occurrences
    )
    all_removed_or_flagged = all(
        o["action"] in ("removed", "short_fragment", "punct_only", "xmlid_leak")
        for o in occurrences
    )
    quality_issues = {o.get("issue_type") for o in occurrences if o["source"] == "quality_flag"}
    text_len = len(norm_text.replace(" ", ""))

    # auto_reject: Gemini removed something that is in the authority file
    if norm_text in auth_refs and any_gemini_removed:
        return "auto_reject", f"מופיע ב-Authority File · הוסר ע״י Gemini"

    # auto_accept: short/punctuation fragment removed everywhere
    if all_removed_or_flagged and (
        text_len <= 2
        or quality_issues <= {"short_fragment", "punct_only", "xmlid_leak"}
    ):
        parts = []
        if text_len <= 2:
            parts.append(f"פרגמנט קצר ({text_len} תווים)")
        if quality_issues:
            parts.append(", ".join(quality_issues))
        parts.append(f"הוסר בכל {len(occurrences)} ההופעות")
        return "auto_accept", " · ".join(parts)

    return "review", "הקשר דורש בדיקה"


# ── Group builder ─────────────────────────────────────────────────────────────

def build_groups(plain_texts: dict[str, str], auth_refs: set[str]) -> list[dict]:
    """
    Load both TSVs and assemble occurrence groups.

    Returns a list of group dicts, sorted: review → auto_reject → auto_accept,
    alphabetically within each tier.
    """
    raw: dict[tuple, list] = defaultdict(list)

    # ── Gemini diff ───────────────────────────────────────────────────────────
    if DIFF_TSV.exists():
        with open(DIFF_TSV, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                text = row["text"].strip()
                if not text:
                    continue
                orig = row["original_label"]
                corr = row["corrected_label"]
                tag = _label_to_tag(orig or corr)
                key = (_norm(text), tag)

                fname = row["source_file"]
                plain = plain_texts.get(fname, "")
                start, end = int(row["start"]), int(row["end"])

                if plain:
                    before, ent, after = _find_context(plain, text, start, end)
                    containing = _containing_word(plain, start, end)
                else:
                    before, ent, after, containing = "", text, "", ""

                raw[key].append({
                    "source": "gemini_diff",
                    "action": row["action"],
                    "orig_label": orig,
                    "new_label": corr,
                    "file": fname,
                    "story_id": "",
                    "before": before,
                    "entity": ent,
                    "after": after,
                    "containing_word": containing,
                    "issue_type": "",
                })

    # ── Quality report ────────────────────────────────────────────────────────
    if QUALITY_TSV.exists():
        with open(QUALITY_TSV, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                text = row["text"].strip()
                if not text:
                    continue
                tag = row["tag"]
                key = (_norm(text), tag)
                ctx = row.get("context", "")
                idx = ctx.find(text)
                before = ctx[:idx] if idx >= 0 else ""
                after = ctx[idx + len(text):] if idx >= 0 else ctx

                raw[key].append({
                    "source": "quality_flag",
                    "action": row.get("issue_type", "flag"),
                    "orig_label": tag,
                    "new_label": "",
                    "file": row["file"],
                    "story_id": row.get("story_id", ""),
                    "before": before,
                    "entity": text,
                    "after": after,
                    "containing_word": "",
                    "issue_type": row.get("issue_type", ""),
                })

    # ── Assemble & sort ───────────────────────────────────────────────────────
    groups: list[dict] = []
    for (norm_text, tag), occs in raw.items():
        tier, reason = _assign_tier(occs, auth_refs, norm_text)
        display_text = max(occs, key=lambda o: len(o["entity"]))["entity"]
        groups.append({
            "key": f"{norm_text}|{tag}",
            "text": display_text,
            "norm_text": norm_text,
            "tag": tag,
            "tier": tier,
            "tier_reason": reason,
            "occurrences": occs,
        })

    _tier_order = {"review": 0, "auto_reject": 1, "auto_accept": 2}
    groups.sort(key=lambda g: (_tier_order[g["tier"]], -len(g["occurrences"]), g["norm_text"]))
    return groups


# ── Persistence ───────────────────────────────────────────────────────────────

def load_existing_decisions() -> dict[str, dict]:
    """Load previously saved decisions keyed by group key (text|tag)."""
    if not DECISIONS_TSV.exists():
        return {}
    decisions: dict[str, dict] = {}
    with open(DECISIONS_TSV, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            k = f"{_norm(row.get('text',''))}|{row.get('tag','')}"
            decisions[k] = {
                "group_decision": row.get("group_decision", ""),
                "per_occurrence": json.loads(row.get("per_occurrence_json") or "{}"),
                "note": row.get("note", ""),
            }
    return decisions


def save_decisions(
    decisions: dict[str, dict],
    groups: list[dict],
    reviewer_name: str,
    reviewer_email: str,
) -> tuple[bool, str]:
    """
    Write decisions to local TSV and push to GitHub.

    Returns (success, message). Never raises — all errors surface as (False, message).
    The local write always happens first; GitHub push is attempted if credentials exist.
    """
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for g in groups:
        d = decisions.get(g["key"])
        if not d or not d.get("group_decision"):
            continue
        rows.append({
            "text": g["text"],
            "tag": g["tag"],
            "tier": g["tier"],
            "group_decision": d["group_decision"],
            "per_occurrence_json": json.dumps(d.get("per_occurrence", {}), ensure_ascii=False),
            "reviewer_name": reviewer_name,
            "reviewer_email": reviewer_email,
            "timestamp": ts,
            "note": d.get("note", ""),
        })

    if not rows:
        return False, "אין החלטות לשמור."

    # Local write (always)
    try:
        _write_tsv_local(DECISIONS_TSV, rows, DECISIONS_FIELDNAMES)
    except Exception as exc:
        return False, f"שגיאה בכתיבה מקומית: {exc}"

    # GitHub push (only when secrets are configured)
    gh_secrets = _get_gh_secrets()
    if gh_secrets:
        gh_secrets = dict(gh_secrets)
        gh_secrets["tsv_path"] = DECISIONS_GH_PATH
        commit_msg = (
            f"Entity review: {len(rows)} decisions by {reviewer_name} [{ts}]"
        )
        ok, gh_msg = _push_tsv_to_github(rows, DECISIONS_FIELDNAMES, gh_secrets, commit_msg)
        if not ok:
            return False, f"נשמר מקומית אך GitHub נכשל: {gh_msg}"
        return True, f"✓ נשמרו {len(rows)} החלטות · {gh_msg}"

    return True, f"✓ נשמרו {len(rows)} החלטות מקומית (GitHub לא מוגדר)"


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _get_gh_secrets() -> dict | None:
    try:
        import streamlit as st
        gh = st.secrets.get("github", {})
        if gh.get("token") and gh.get("repo"):
            return dict(gh)
    except Exception:
        pass
    return None


def _push_tsv_to_github(
    rows: list[dict],
    fieldnames: list[str],
    gh_secrets: dict,
    commit_message: str,
) -> tuple[bool, str]:
    try:
        from github import Github, GithubException
    except ImportError:
        return False, "PyGithub לא מותקן"

    content = _tsv_to_string(rows, fieldnames)
    try:
        g = Github(gh_secrets["token"])
        repo = g.get_repo(gh_secrets["repo"])
        branch = gh_secrets.get("branch", "main")
        path = gh_secrets["tsv_path"]
        try:
            existing = repo.get_contents(path, ref=branch)
            result = repo.update_file(path, commit_message, content, existing.sha, branch=branch)
        except Exception:
            result = repo.create_file(path, commit_message, content, branch=branch)
        sha = result["commit"].sha[:8]
        return True, f"commit {sha}"
    except Exception as exc:
        if hasattr(exc, "status") and exc.status == 409:
            return False, "conflict — מישהו אחר שמר בו-זמנית. טען מחדש ונסה שוב."
        return False, str(exc)


def _tsv_to_string(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL).writeheader()
    buf.seek(0)
    buf.truncate()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _write_tsv_local(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
