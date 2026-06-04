"""
Binary women-in-story annotation on the 9 previously-tagged editions.

Uses the revised PI-aligned criteria at editions/women-criteria-binary.md
(direct mention of real woman in story-world; per-mention exclusions for
marriage-category, biblical quotes, halakhic abstractions, adultery-
without-woman, formulaic idioms).

Self-contained: does NOT touch the 5-tier pipeline (women_llm.py,
women-criteria.md, women-llm-results-v2.tsv). Its own cache lives at
editions/women-binary-results.tsv.

Output:
  - editions/women-binary-results.tsv         (cache: per-(story, hash))
  - editions/women-binary-9editions.tsv       (run summary + comparison)
"""
import csv, hashlib, json, os, sys, time
from collections import Counter
from datetime import datetime
from typing import Dict, Tuple

sys.path.insert(0, os.path.dirname(__file__))

from women_data import load_stories
from config import PROJECT_DIR

CRITERIA_PATH = os.path.join(PROJECT_DIR, "editions", "women-criteria-binary.md")
CACHE_PATH    = os.path.join(PROJECT_DIR, "editions", "women-binary-results.tsv")
OUT_PATH      = os.path.join(PROJECT_DIR, "editions", "women-binary-9editions.tsv")

CACHE_COLUMNS = [
    "story_id", "edition",
    "women_in_story", "confidence", "reasoning",
    "old_human_binary", "old_claude_5tier",
    "run_timestamp", "criteria_hash",
]

VALID_CONF = {"high", "medium", "low"}


# ── criteria / hashing ────────────────────────────────────────────────────────

def load_criteria() -> str:
    with open(CRITERIA_PATH, encoding="utf-8") as f:
        return f.read().strip()

def criteria_hash(criteria: str) -> str:
    return hashlib.md5(criteria.encode()).hexdigest()[:8]


# ── cache ─────────────────────────────────────────────────────────────────────

def _load_cache() -> Dict[Tuple[str, str], dict]:
    cache = {}
    if not os.path.exists(CACHE_PATH):
        return cache
    with open(CACHE_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            cache[(row["story_id"], row.get("criteria_hash", ""))] = row
    return cache

def _save_cache(cache: Dict[Tuple[str, str], dict]):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CACHE_COLUMNS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(cache.values())


# ── LLM call ──────────────────────────────────────────────────────────────────

def _parse(raw: str) -> Tuple[str, str, str]:
    """Returns (women_in_story 'true'|'false', confidence, reasoning)."""
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        val = data.get("women_in_story")
        if isinstance(val, bool):
            wis = "true" if val else "false"
        else:
            wis = str(val).strip().lower()
            if wis not in ("true", "false"):
                wis = "false"
        conf = str(data.get("confidence", "")).strip().lower()
        if conf not in VALID_CONF:
            conf = "medium"
        return wis, conf, data.get("reasoning", "")
    except Exception:
        return "false", "medium", f"[parse error] {raw[:200]}"

def _call_claude(story_text: str, criteria: str) -> Tuple[str, str, str]:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=criteria,
        messages=[{"role": "user", "content": story_text}],
    )
    return _parse(msg.content[0].text)


# ── 5-tier comparison loader (read-only reference) ────────────────────────────

def load_5tier_by_id() -> Dict[str, str]:
    """Pull existing Claude 5-tier categories from the v2 cache, if present."""
    out = {}
    p = os.path.join(PROJECT_DIR, "editions", "women-llm-results-v2.tsv")
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[r["story_id"]] = r.get("claude_category", "")
    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main(force: bool = False):
    if not os.path.exists(CRITERIA_PATH):
        sys.exit(f"Missing criteria file: {CRITERIA_PATH}")

    criteria = load_criteria()
    chash = criteria_hash(criteria)
    print(f"Criteria hash: {chash}")

    all_stories = load_stories()
    annotated_eds = sorted({s["edition"] for s in all_stories if s["category"] != "no-women"})
    target = [s for s in all_stories if s["edition"] in annotated_eds]
    print(f"Target editions ({len(annotated_eds)}): {', '.join(annotated_eds)}")
    print(f"Total stories: {len(target)}\n")

    five_tier = load_5tier_by_id()
    cache = _load_cache()

    for i, s in enumerate(target, 1):
        key = (s["story_id"], chash)
        if not force and key in cache and cache[key].get("women_in_story") in ("true", "false"):
            continue
        text = s.get("text", "")[:12000]
        try:
            wis, conf, reason = _call_claude(text, criteria)
        except Exception as e:
            wis, conf, reason = "error", "", str(e)
        cache[key] = {
            "story_id": s["story_id"],
            "edition":  s["edition"],
            "women_in_story": wis,
            "confidence": conf,
            "reasoning":  reason,
            "old_human_binary": "women" if s["category"] != "no-women" else "no-women",
            "old_claude_5tier": five_tier.get(s["story_id"], ""),
            "run_timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "criteria_hash": chash,
        }
        if i % 25 == 0:
            _save_cache(cache)
        print(f"  {i}/{len(target)}", end="\r", flush=True)
        time.sleep(0.05)

    _save_cache(cache)
    print(f"\nCache: {CACHE_PATH}")

    # ── output summary TSV ────────────────────────────────────────────────────
    rows = [cache[(s["story_id"], chash)] for s in target if (s["story_id"], chash) in cache]
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CACHE_COLUMNS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Summary: {OUT_PATH}\n")

    # ── headline stats ────────────────────────────────────────────────────────
    non_error = [r for r in rows if r["women_in_story"] in ("true", "false")]
    total = len(non_error)
    n_true = sum(1 for r in non_error if r["women_in_story"] == "true")
    print("=" * 60)
    print(f"BINARY DISTRIBUTION ({total} non-error)")
    print("=" * 60)
    print(f"  women_in_story=true  : {n_true:>4}  ({n_true/total*100:.1f}%)")
    print(f"  women_in_story=false : {total-n_true:>4}  ({(total-n_true)/total*100:.1f}%)\n")

    confs = Counter(r["confidence"] for r in non_error)
    print("CONFIDENCE")
    for c in ("high", "medium", "low"):
        n = confs.get(c, 0)
        print(f"  {c:<7} {n:>4}  ({n/total*100:.1f}%)")
    print()

    # comparison: old human binary vs new binary
    print("OLD HUMAN (binary) → NEW BINARY")
    combos = Counter((r["old_human_binary"], r["women_in_story"]) for r in non_error)
    for (h, b), n in sorted(combos.items(), key=lambda x: -x[1]):
        print(f"  {h:<10} → {b:<6} {n:>4}")
    print()

    # comparison: 5-tier vs new binary (the headline question PI raised)
    print("5-TIER → NEW BINARY  (does PI rule shrink mention-only?)")
    combos5 = Counter((r["old_claude_5tier"], r["women_in_story"]) for r in non_error)
    for (t, b), n in sorted(combos5.items(), key=lambda x: (x[0][0], -x[1])):
        print(f"  {t:<22} → {b:<6} {n:>4}")
    print()

    print("PER-EDITION")
    print(f"  {'edition':<24}{'total':>7}{'true':>7}{'%':>7}")
    for ed in annotated_eds:
        ed_rows = [r for r in non_error if r["edition"] == ed]
        if not ed_rows: continue
        nt = sum(1 for r in ed_rows if r["women_in_story"] == "true")
        print(f"  {ed:<24}{len(ed_rows):>7}{nt:>7}{nt/len(ed_rows)*100:>6.1f}%")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
