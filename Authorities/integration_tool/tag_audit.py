"""
Multi-signal per-tag consistency audit.

For a story tag, combines three signals into a candidate funnel and adjudicates it
with Claude (generalizing the women/pidyon method):

  1. Lexical   — substring hits from tag_lexicons (lexical-strong tags only).
  2. Semantic  — cosine similarity to the centroid of human-tagged stories (embeddings).
  3. LLM       — Claude yes/no presence verdict on the funnel + a random control sample
                 of un-flagged stories (the recall check).

Outputs per tag (written under editions/tag-audit/<category>/):
  - <tag>-mentions.tsv : untagged candidates + Claude verdict + decision columns
  - returns a summary dict (counts, false-positive candidates, recall estimate)

Run:  python3 tag_audit.py practice:pidyon_nefesh      # one tag (validation)
      python3 tag_audit.py --category practice          # whole category
      python3 tag_audit.py --category practice --no-llm  # signals only, no API calls
"""
import os
import re
import sys
import csv
import json
import random
import hashlib
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np

import tag_data
import tag_embeddings
import tag_lexicons
from config import PROJECT_DIR

AUDIT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit")
LLM_CACHE = os.path.join(AUDIT_DIR, ".cache", "llm-presence.tsv")

# Funnel caps. Coverage chosen 2026-05-26: stricter 40th-pct threshold (more precise
# pool) + cap 60 (high-freq tags reach a solid majority of candidates).
MAX_MISSED_CANDIDATES = 60
CONTROL_SAMPLE_N = 10
MISSED_SIM_PERCENTILE = 40   # untagged stories above this pct of positive self-sim -> candidate
FP_SIM_PERCENTILE = 10       # tagged stories below this pct of positive self-sim -> outlier

random.seed(42)


# ── Lexical signal ─────────────────────────────────────────────────────────────

def lexical_hits(story_text: str, lex: dict):
    """Return (matched_terms, only_homograph). only_homograph=True if the only hits
    are homographs (false friends) -> likely NOT the phenomenon."""
    if not lex:
        return [], False
    terms = [t for t in lex.get("terms", []) if tag_lexicons.term_in_text(t, story_text)]
    homs = [h for h in lex.get("homographs", []) if h in story_text]
    only_homograph = bool(homs) and not terms
    return terms, only_homograph


# ── LLM presence check (cached) ────────────────────────────────────────────────

def _humanize(tag: str) -> str:
    return tag.split(":")[-1].replace("_", " ")


def _presence_prompt(tag: str, definition: str) -> str:
    top = tag.split(":")[0]
    return (
        f"You are auditing thematic tagging of Hasidic stories (18th-19th century "
        f"Hebrew/Yiddish). Decide whether the tag '{tag}' applies to the story below.\n\n"
        f"Tag meaning ({top}): {definition}\n\n"
        f"Apply the tag only if the story actually depicts/contains this — not a faint "
        f"or incidental association. Respond in JSON only: "
        f'{{"applies": true|false, "confidence": "high|medium|low", "reasoning": "<=1 sentence"}}'
    )


# Adjudicating model: "gemini" (default — Anthropic key currently has no credits)
# or "claude". The audit method is model-agnostic; cache rows record which model judged.
LLM_MODEL = os.environ.get("TAG_AUDIT_MODEL", "gemini")
_CACHE_COLS = ["story_id", "tag", "prompt_hash", "model",
               "applies", "confidence", "reasoning", "ts"]


def _load_llm_cache():
    cache = {}
    if os.path.exists(LLM_CACHE):
        with open(LLM_CACHE, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                cache[(row["story_id"], row["tag"], row["prompt_hash"], row.get("model", ""))] = row
    return cache


_CACHE_LOCK = threading.Lock()


def _append_llm_cache(row):
    os.makedirs(os.path.dirname(LLM_CACHE), exist_ok=True)
    with _CACHE_LOCK:
        new = not os.path.exists(LLM_CACHE)
        with open(LLM_CACHE, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CACHE_COLS, delimiter="\t", extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)


def _parse_json_verdict(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.startswith("json") else raw
    data = json.loads(raw)
    return (bool(data.get("applies", False)),
            str(data.get("confidence", "medium")).lower(),
            data.get("reasoning", ""))


_claude = None
_gemini = {}


CLAUDE_CLI_BIN = os.environ.get("CLAUDE_CLI_BIN", "claude")
CLAUDE_CLI_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "claude-opus-4-7")


def _call_claude_cli(prompt: str, story_text: str, _retries: int = 3) -> tuple:
    """Run `claude -p --bare --model …` as a subprocess for one verdict.
    Each call is a fresh process so context never overflows.

    The CLI prints assistant text to stdout. We expect a JSON object matching
    _parse_json_verdict's schema (applies, confidence, reasoning). Errors are
    retried with exponential backoff."""
    # NOTE: do NOT use --bare here. --bare forces ANTHROPIC_API_KEY auth and
    # ignores OAuth/keychain — i.e. it would bypass the Pro plan and try to bill
    # the API (which has no credit on this account). Plain `claude -p` reads the
    # OAuth/keychain creds and runs on the plan.
    cmd = [
        CLAUDE_CLI_BIN, "-p",
        "--model", CLAUDE_CLI_MODEL,
        "--system-prompt", prompt,
        "--output-format", "text",
        "--disallowedTools", "*",  # presence-judgment only; never read files / run code
    ]
    last_err = None
    for attempt in range(_retries):
        try:
            r = subprocess.run(cmd, input=story_text, capture_output=True,
                               text=True, timeout=180)
            if r.returncode != 0:
                last_err = f"rc={r.returncode}: {r.stderr.strip()[:200]}"
                continue
            return _parse_json_verdict(r.stdout)
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout: {e}"
        except Exception as e:
            last_err = str(e)
        # backoff
        import time as _t
        _t.sleep(2 ** attempt)
    raise RuntimeError(f"claude-cli failed after {_retries} retries: {last_err}")


def _call_model(prompt, story_text, model, _retries=4):
    if model == OPUS_MODEL_LABEL:
        # opus-cli verdicts come only from the ingested cache; never call an API here.
        raise RuntimeError(f"{OPUS_MODEL_LABEL}: story not yet adjudicated by the agent")
    if model == "claude-cli":
        return _call_claude_cli(prompt, story_text, _retries=min(_retries, 3))
    if model == "claude":
        global _claude
        if _claude is None:
            import anthropic
            _claude = anthropic.Anthropic()
        msg = _claude.messages.create(
            model="claude-sonnet-4-6", max_tokens=256, system=prompt,
            messages=[{"role": "user", "content": story_text}],
        )
        return _parse_json_verdict(msg.content[0].text)
    elif model in ("gemini-3", "gemini-2.5"):
        # New google-genai SDK (supports Gemini 3). Reads full story text.
        from google import genai as _g
        from google.genai import types as _t2
        model_id = {"gemini-3": "gemini-3-flash-preview",
                    "gemini-2.5": "gemini-2.5-flash"}[model]
        if "_client3" not in _gemini:
            _gemini["_client3"] = _g.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        client = _gemini["_client3"]
        cfg = _t2.GenerateContentConfig(
            system_instruction=prompt, response_mime_type="application/json",
            max_output_tokens=900,
        )
        import time as _tt
        for attempt in range(_retries):
            try:
                resp = client.models.generate_content(model=model_id, contents=story_text, config=cfg)
                _tt.sleep(1.0)
                return _parse_json_verdict(resp.text)
            except Exception as e:
                if any(k in str(e).lower() for k in ("429", "exhaust", "quota", "resource")):
                    _tt.sleep(15 * (attempt + 1)); continue
                raise
        raise RuntimeError("gemini-3 rate-limit retries exhausted")
    else:  # gemini (2.0 flash, legacy SDK)
        import google.generativeai as genai
        m = genai.GenerativeModel("gemini-2.0-flash", system_instruction=prompt)
        import time as _t
        for attempt in range(_retries):
            try:
                resp = m.generate_content(
                    story_text,
                    generation_config={"response_mime_type": "application/json",
                                       "max_output_tokens": 200},
                )
                _t.sleep(4.2)
                return _parse_json_verdict(resp.text)
            except Exception as e:
                if "429" in str(e) or "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    _t.sleep(20 * (attempt + 1)); continue
                raise
        raise RuntimeError("gemini rate-limit retries exhausted")


def _llm_presence(story, tag, definition, cache, model=None):
    model = model or LLM_MODEL
    prompt = _presence_prompt(tag, definition)
    phash = hashlib.md5(prompt.encode()).hexdigest()[:8]
    # Prefer a high-quality Opus-in-CLI verdict if one exists, regardless of the
    # current model — so a Gemini sweep never overrides hand-adjudicated tags.
    opus_key = (story["story_id"], tag, phash, OPUS_MODEL_LABEL)
    if opus_key in cache:
        c = cache[opus_key]
        return c["applies"] == "True", c["confidence"], c["reasoning"]
    key = (story["story_id"], tag, phash, model)
    if key in cache:
        c = cache[key]
        return c["applies"] == "True", c["confidence"], c["reasoning"]
    try:
        applies, conf, reason = _call_model(prompt, story["text"][:12000], model)
        cached_ok = True
    except Exception as e:
        applies, conf, reason, cached_ok = False, "", f"[error] {e}", False
    row = {
        "story_id": story["story_id"], "tag": tag, "prompt_hash": phash, "model": model,
        "applies": str(applies), "confidence": conf, "reasoning": reason,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if cached_ok:                       # never cache errors — let them retry
        _append_llm_cache(row)
        cache[key] = row
    return applies, conf, reason


# ── Per-tag audit ──────────────────────────────────────────────────────────────

def _relevant_excerpt(story, terms, emb, centroid_vec, id_to_idx, width=220):
    """Show the tag-relevant passage, not the story opening: a window around the
    first matched lexical term, else the story's chunk most similar to the centroid."""
    text = story["text"]
    if terms:
        i = text.find(terms[0])
        if i >= 0:
            s = max(0, i - 60)
            return text[s:s + width].replace("\n", " ")
    if centroid_vec is not None and story["story_id"] in id_to_idx:
        off = emb.best_chunk_offset(id_to_idx[story["story_id"]], centroid_vec)
        return text[off:off + width].replace("\n", " ")
    return text[:width].replace("\n", " ")


def _llm_presence_batch(items, tag, definition, llm_cache, workers=1):
    """Adjudicate multiple stories for one tag. Returns list parallel to `items`
    of (applies, conf, reason). When workers == 1, runs sequentially (preserves
    the legacy ordering for Gemini's rate-limiter)."""
    n = len(items)
    out = [None] * n
    if workers <= 1:
        for i, s in enumerate(items):
            out[i] = _llm_presence(s, tag, definition, llm_cache)
        return out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_to_i = {ex.submit(_llm_presence, s, tag, definition, llm_cache): i
                    for i, s in enumerate(items)}
        for fut in as_completed(fut_to_i):
            i = fut_to_i[fut]
            try:
                out[i] = fut.result()
            except Exception as e:
                out[i] = (False, "", f"[error] {e}")
    return out


def audit_tag(tag, stories, ids, mat, definition=None, run_llm=True, llm_cache=None,
              workers=1):
    definition = definition or tag_lexicons.definition(tag)
    if llm_cache is None:
        llm_cache = _load_llm_cache()
    id_to_idx = {sid: i for i, sid in enumerate(ids)}
    detect = tag_lexicons.detectability(tag)
    lex = tag_lexicons.lexicon(tag)

    pos = [s for s in stories if tag in s["tags"]]
    neg = [s for s in stories if tag not in s["tags"]]
    pos_idx = [id_to_idx[s["story_id"]] for s in pos if s["story_id"] in id_to_idx]

    # Semantic signal
    sim = None
    thr_missed = thr_fp = None
    if pos_idx:
        cen = tag_embeddings.centroid(mat, pos_idx)
        sim = tag_embeddings.similarities(mat, cen)
        pos_self = sim[pos_idx]
        thr_missed = float(np.percentile(pos_self, MISSED_SIM_PERCENTILE))
        thr_fp = float(np.percentile(pos_self, FP_SIM_PERCENTILE))

    # ── Funnel: candidate MISSED tags among untagged ──
    candidates = {}  # story_id -> {signals:set, sim, terms}
    for s in neg:
        sid = s["story_id"]
        entry = {"signals": set(), "sim": None, "terms": []}
        if lex:
            terms, only_hom = lexical_hits(s["text"], lex)
            if terms:
                entry["signals"].add("lexical")
                entry["terms"] = terms
        if sim is not None and sid in id_to_idx:
            sv = float(sim[id_to_idx[sid]])
            entry["sim"] = sv
            if thr_missed is not None and sv >= thr_missed:
                entry["signals"].add("embedding")
        if entry["signals"]:
            candidates[sid] = entry

    # rank: lexical+embedding first, then by sim desc; cap
    def rank_key(item):
        e = item[1]
        return (-len(e["signals"]), -(e["sim"] or 0))
    ranked = sorted(candidates.items(), key=rank_key)[:MAX_MISSED_CANDIDATES]

    # ── Control sample: un-flagged untagged stories (recall check) ──
    unflagged = [s for s in neg if s["story_id"] not in candidates]
    control = random.sample(unflagged, min(CONTROL_SAMPLE_N, len(unflagged)))

    # ── False-positive candidates among tagged ──
    fp_candidates = []
    if sim is not None and thr_fp is not None:
        for s in pos:
            sv = float(sim[id_to_idx[s["story_id"]]])
            low_sim = sv < thr_fp
            lex_ok = True
            if lex:
                terms, _ = lexical_hits(s["text"], lex)
                lex_ok = bool(terms)
            if low_sim and not lex_ok:
                fp_candidates.append((s["story_id"], sv))

    # ── LLM adjudication ──
    neg_by_id = {s["story_id"]: s for s in neg}
    mention_rows = []
    control_yes = 0
    if run_llm:
        cand_stories = [neg_by_id[sid] for sid, _ in ranked]
        cand_verdicts = _llm_presence_batch(cand_stories, tag, definition, llm_cache,
                                            workers=workers)
        for (sid, e), (applies, conf, reason) in zip(ranked, cand_verdicts):
            mention_rows.append({
                "story_id": sid, "edition": neg_by_id[sid]["edition"],
                "signals": "+".join(sorted(e["signals"])),
                "sim": round(e["sim"], 3) if e["sim"] is not None else "",
                "matched_terms": " ".join(e["terms"]),
                "claude_applies": applies, "claude_confidence": conf,
                "claude_reasoning": reason,
                "excerpt": _relevant_excerpt(neg_by_id[sid], e["terms"], mat, cen, id_to_idx),
                "should_tag": "", "notes": "",
            })
        ctrl_verdicts = _llm_presence_batch(control, tag, definition, llm_cache,
                                            workers=workers)
        control_yes = sum(1 for applies, _, _ in ctrl_verdicts if applies)

    confirmed = sum(1 for r in mention_rows if r["claude_applies"])
    return {
        "tag": tag, "detectability": detect,
        "n_tagged": len(pos), "n_editions_tagged": len({s["edition"] for s in pos}),
        "n_candidates": len(ranked), "n_confirmed_missed": confirmed,
        "n_fp_candidates": len(fp_candidates),
        "fp_candidates": fp_candidates,
        "control_n": len(control), "control_yes": control_yes,
        "recall_flag": (control_yes / len(control)) if control else 0.0,
        "mention_rows": mention_rows,
    }


# ── CLI (Opus-in-CLI) adjudication path: dump funnel, ingest verdicts ───────────
# Lets the running Claude Code agent (Opus) judge the funnel directly — no API
# calls. Verdicts land in the same llm-presence cache (model="opus-cli") so the
# normal run_category/tag_review pipeline consumes them identically.

OPUS_MODEL_LABEL = "opus-cli"


def _funnel_for_tag(tag, stories, ids, mat):
    """Return (candidate_rows, control_rows) without any LLM call."""
    id_to_idx = {sid: i for i, sid in enumerate(ids)}
    lex = tag_lexicons.lexicon(tag)
    pos = [s for s in stories if tag in s["tags"]]
    neg = [s for s in stories if tag not in s["tags"]]
    pos_idx = [id_to_idx[s["story_id"]] for s in pos if s["story_id"] in id_to_idx]
    sim = thr = None
    if pos_idx:
        cen = tag_embeddings.centroid(mat, pos_idx)
        sim = tag_embeddings.similarities(mat, cen)
        thr = float(np.percentile(sim[pos_idx], MISSED_SIM_PERCENTILE))
    cands = {}
    for s in neg:
        sid = s["story_id"]; sigs = set(); terms = []
        if lex:
            terms = [t for t in lex["terms"] if tag_lexicons.term_in_text(t, s["text"])]
            if terms:
                sigs.add("lexical")
        if sim is not None:
            sv = float(sim[id_to_idx[sid]])
            if thr is not None and sv >= thr:
                sigs.add("embedding")
        if sigs:
            cands[sid] = {"signals": sigs, "sim": float(sim[id_to_idx[sid]]) if sim is not None else None,
                          "terms": terms, "story": s}
    ranked = sorted(cands.items(),
                    key=lambda kv: (-len(kv[1]["signals"]), -(kv[1]["sim"] or 0)))[:MAX_MISSED_CANDIDATES]
    unflagged = [s for s in neg if s["story_id"] not in cands]
    control = random.sample(unflagged, min(CONTROL_SAMPLE_N, len(unflagged)))
    return ranked, control


def dump_funnel(category, max_text=2500):
    """Write <category>/adjudication-queue.tsv for the agent (Opus) to judge."""
    stories = tag_data.load_stories("core")
    ids, mat = tag_embeddings.embed_stories(stories)
    tags = sorted({t for s in stories for t in s["tags"] if t.split(":")[0] == category},
                  key=lambda t: -sum(1 for s in stories if t in s["tags"]))
    rows = []
    for tag in tags:
        definition = tag_lexicons.definition(tag)
        phash = hashlib.md5(_presence_prompt(tag, definition).encode()).hexdigest()[:8]
        ranked, control = _funnel_for_tag(tag, stories, ids, mat)
        for sid, e in ranked:
            rows.append({"tag": tag, "definition": definition, "prompt_hash": phash,
                         "kind": "candidate", "story_id": sid, "edition": e["story"]["edition"],
                         "signals": "+".join(sorted(e["signals"])),
                         "sim": round(e["sim"], 3) if e["sim"] is not None else "",
                         "terms": " ".join(e["terms"]),
                         "text": e["story"]["text"][:max_text]})
        for s in control:
            rows.append({"tag": tag, "definition": definition, "prompt_hash": phash,
                         "kind": "control", "story_id": s["story_id"], "edition": s["edition"],
                         "signals": "", "sim": "", "terms": "", "text": s["text"][:max_text]})
    d = os.path.join(AUDIT_DIR, category); os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "adjudication-queue.tsv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tag", "definition", "prompt_hash", "kind",
                           "story_id", "edition", "signals", "sim", "terms", "text"],
                           delimiter="\t")
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {path}: {len(rows)} items across {len(tags)} tags")
    return path


def ingest_verdicts(verdict_path, model=OPUS_MODEL_LABEL):
    """Read agent verdicts (TSV: story_id, tag, applies, confidence, reasoning) and
    append to the llm-presence cache with the matching prompt_hash + model label."""
    n = 0
    with open(verdict_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            tag = r["tag"]
            definition = tag_lexicons.definition(tag)
            phash = hashlib.md5(_presence_prompt(tag, definition).encode()).hexdigest()[:8]
            applies = str(r["applies"]).strip().lower() in ("true", "1", "yes")
            _append_llm_cache({
                "story_id": r["story_id"], "tag": tag, "prompt_hash": phash, "model": model,
                "applies": str(applies), "confidence": r.get("confidence", "").strip(),
                "reasoning": r.get("reasoning", "").strip(),
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            n += 1
    print(f"Ingested {n} verdicts (model={model}) from {verdict_path}")


def _story_url(story_id):
    ed = re.sub(r"_\d+[A-Za-z]?$", "", story_id)
    return f"https://www.hasidic-stories.org/Story/{ed}/{story_id}"


def _write_all_mentions(category, all_rows):
    """One combined mentions file for the whole category (story_url instead of id)."""
    if not all_rows:
        return
    d = os.path.join(AUDIT_DIR, category)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{category}-mentions.tsv")
    cols = ["tag", "story_url", "story_id", "edition", "signals", "sim", "matched_terms",
            "claude_applies", "claude_confidence", "claude_reasoning", "excerpt"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    return path


# ── Drivers ────────────────────────────────────────────────────────────────────

def _progress_path(category):
    return os.path.join(AUDIT_DIR, category, ".progress.json")


def _write_progress(category, d):
    import json as _json
    os.makedirs(os.path.join(AUDIT_DIR, category), exist_ok=True)
    with open(_progress_path(category), "w", encoding="utf-8") as f:
        _json.dump(d, f, ensure_ascii=False, indent=2)


def _calls_needed(tag, ranked, control, llm_cache):
    """How many of this tag's items still need an API call (not already cached)."""
    phash = hashlib.md5(_presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]
    n = 0
    items = [sid for sid, _ in ranked] + [s["story_id"] for s in control]
    for sid in items:
        if ((sid, tag, phash, OPUS_MODEL_LABEL) in llm_cache
                or (sid, tag, phash, LLM_MODEL) in llm_cache):
            continue
        n += 1
    return n


def run_category(category, run_llm=True, workers=1):
    import time as _t
    stories = tag_data.load_stories("core")
    ids, mat = tag_embeddings.embed_stories(stories)
    tags = sorted({t for s in stories for t in s["tags"] if t.split(":")[0] == category},
                  key=lambda t: -sum(1 for s in stories if t in s["tags"]))
    llm_cache = _load_llm_cache()

    # ── pre-pass: estimate total API calls remaining (for the progress monitor) ──
    per_tag_calls = {}
    for tag in tags:
        ranked, control = _funnel_for_tag(tag, stories, ids, mat)
        per_tag_calls[tag] = _calls_needed(tag, ranked, control, llm_cache) if run_llm else 0
    total_calls = sum(per_tag_calls.values())
    start = _t.time()
    calls_done = 0
    _write_progress(category, {
        "category": category, "model": LLM_MODEL,
        "tags_total": len(tags), "tags_done": 0,
        "calls_total": total_calls, "calls_done": 0,
        "current_tag": None, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eta_seconds": None, "done": False,
    })

    summaries = []
    all_mentions = []
    for i, tag in enumerate(tags, 1):
        res = audit_tag(tag, stories, ids, mat, run_llm=run_llm, llm_cache=llm_cache,
                        workers=workers)
        for r in res["mention_rows"]:
            all_mentions.append({"tag": tag, "story_url": _story_url(r["story_id"]), **r})
        summaries.append(res)
        calls_done += per_tag_calls[tag]
        elapsed = _t.time() - start
        rate = calls_done / elapsed if calls_done else 0
        eta = int((total_calls - calls_done) / rate) if rate > 0 else None
        _write_progress(category, {
            "category": category, "model": LLM_MODEL,
            "tags_total": len(tags), "tags_done": i,
            "calls_total": total_calls, "calls_done": calls_done,
            "current_tag": tag, "started": datetime.fromtimestamp(start, timezone.utc).isoformat(timespec="seconds"),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "eta_seconds": eta, "done": i == len(tags),
        })
        print(f"[{i}/{len(tags)}] {tag:46s} tagged={res['n_tagged']:3d} cand={res['n_candidates']:2d} "
              f"missed+={res['n_confirmed_missed']:2d} fp?={res['n_fp_candidates']:2d} "
              f"recall={res['recall_flag']:.0%}  | calls {calls_done}/{total_calls}"
              + (f" eta~{eta//60}m" if eta else ""))
    _write_all_mentions(category, all_mentions)
    _write_summary(category, summaries)
    return summaries


def _write_summary(category, summaries):
    d = os.path.join(AUDIT_DIR, category)
    os.makedirs(d, exist_ok=True)
    cols = ["tag", "detectability", "n_tagged", "n_editions_tagged", "n_candidates",
            "n_confirmed_missed", "n_fp_candidates", "control_n", "control_yes",
            "recall_flag", "your_decision", "notes"]
    path = os.path.join(d, f"{category}-audit.tsv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for s in summaries:
            row = {k: s.get(k, "") for k in cols}
            row["recall_flag"] = f"{s['recall_flag']:.2f}"
            row["your_decision"] = ""
            row["notes"] = ""
            w.writerow(row)
    print(f"\nWrote {path}")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--dump-funnel":
        dump_funnel(args[1])
        return
    if args and args[0] == "--ingest":
        ingest_verdicts(args[1])
        return
    run_llm = "--no-llm" not in args
    args = [a for a in args if a != "--no-llm"]
    workers = 1
    if "--workers" in args:
        i = args.index("--workers")
        workers = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if args and args[0] == "--category":
        run_category(args[1], run_llm=run_llm, workers=workers)
    elif args:
        tag = args[0]
        stories = tag_data.load_stories("core")
        ids, mat = tag_embeddings.embed_stories(stories)
        res = audit_tag(tag, stories, ids, mat, run_llm=run_llm, workers=workers)
        category = tag.split(":")[0]
        p = _write_mentions(category, tag, res["mention_rows"])
        print(json.dumps({k: v for k, v in res.items() if k != "mention_rows"},
                         ensure_ascii=False, indent=2, default=str))
        if p:
            print("mentions ->", p)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
