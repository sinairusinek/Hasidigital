#!/usr/bin/env python3
"""Direct Opus precision audit of the OLD weak-definition LLM inserts.

The patched Sonnet sweep cannot speak to the already-inserted tags (they sit
in `pos` and are excluded from the candidate funnel). So to test whether the
1,971 weak-definition inserts hold up under the patched definitions, we judge
each (story, tag) DIRECTLY with Opus — no funnel involved.

Source: editions/tag-audit/llm-confirmed-verdicts.tsv (the committed old
inserts), restricted to the 9 thematic categories that ran with weak
definitions (practice/kabbalah had real definitions and are skipped).

Verdicts append to the LLM cache as model=opus-cli at the CURRENT patched
prompt_hash — so an Opus-False here is genuine removal evidence. Resume-safe:
a pair already carrying an opus-cli row at the current hash is skipped.

Usage:
  python3 precision_audit_old_inserts.py [--model claude-opus-4-7] [--limit N] [--dry-run]
"""
import argparse, csv, hashlib, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))
import tag_data, tag_lexicons, tag_audit
from tag_audit import _presence_prompt, _call_claude_cli, _append_llm_cache

AUDIT = REPO / "editions" / "tag-audit"
CACHE = AUDIT / ".cache" / "llm-presence.tsv"
OLD = AUDIT / "llm-confirmed-verdicts.tsv"
WEAK = {"social", "ethics-and-emotions", "supernatural", "characters-and-roles",
        "experience", "folkloristics", "times", "spaces", "knowledge"}


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()
    ).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-7")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    os.environ["CLAUDE_CLI_MODEL"] = args.model
    tag_audit.CLAUDE_CLI_MODEL = args.model

    old = list(csv.DictReader(open(OLD), delimiter="\t"))
    targets = [(r["story_id"], r["tag"], r["source"]) for r in old
               if r["tag"].split(":")[0] in WEAK
               and r["tag"] not in tag_lexicons.DEFINITIONS]
    H = {t: phash(t) for _, t, _ in targets}

    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    opus_at_hash = {(r["story_id"], r["tag"]) for r in rows
                    if r["model"] == "opus-cli" and r.get("prompt_hash") == H.get(r["tag"])}
    need = [(s, t, src) for (s, t, src) in targets if (s, t) not in opus_at_hash]
    if args.limit:
        need = need[: args.limit]
    print(f"weak-def old inserts: {len(targets)} | already opus@hash: "
          f"{len(targets) - len([1 for s,t,_ in targets if (s,t) not in opus_at_hash])} "
          f"| to judge now: {len(need)} | model={args.model}")
    if args.dry_run or not need:
        return

    by_id = {s["story_id"]: s for s in tag_data.load_stories("core")}
    confirm = reject = errors = 0
    consec_err = 0          # circuit breaker: stop on a throttle wall
    MAX_CONSEC_ERR = 12
    out_rows = []
    start = time.time()
    for i, (sid, tag, src) in enumerate(need, 1):
        story = by_id.get(sid)
        if story is None:
            errors += 1
            print(f"[{i}/{len(need)}] SKIP story not in core: {sid}")
            continue
        definition = tag_lexicons.definition(tag)
        prompt = _presence_prompt(tag, definition)
        h = hashlib.md5(prompt.encode()).hexdigest()[:8]
        try:
            applies, conf, reason = _call_claude_cli(prompt, story["text"][:12000])
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_llm_cache({
                "story_id": sid, "tag": tag, "prompt_hash": h, "model": "opus-cli",
                "applies": str(applies), "confidence": conf, "reasoning": reason, "ts": ts,
            })
            verdict = "CONFIRM" if applies else "REJECT"
            confirm += applies
            reject += (not applies)
            consec_err = 0
        except Exception as e:
            errors += 1
            consec_err += 1
            applies, conf, reason = None, "", str(e)[:120]
            verdict = f"ERROR:{type(e).__name__}"
        if consec_err >= MAX_CONSEC_ERR:
            print(f"\n!! {consec_err} consecutive errors — throttle wall hit. "
                  f"Stopping at {i}/{len(need)}. Cache is saved; rerun to resume.")
            break
        out_rows.append({"story_id": sid, "tag": tag, "old_source": src,
                         "opus_applies": str(applies), "opus_confidence": conf,
                         "verdict": verdict, "opus_reasoning": reason})
        el = time.time() - start
        rate = i / el if el else 0
        eta = (len(need) - i) / rate / 60 if rate else 0
        print(f"[{i}/{len(need)}] {verdict:8s} {tag[:32]:32s} {sid[:22]:22s} "
              f"| {rate:.2f}/s eta={eta:.0f}m")

    out = AUDIT / "old-inserts-precision-audit.tsv"
    # append-or-create: merge with any prior partial results
    prior = []
    if out.exists():
        prior = [r for r in csv.DictReader(open(out), delimiter="\t")
                 if (r["story_id"], r["tag"]) not in {(o["story_id"], o["tag"]) for o in out_rows}]
    allrows = prior + out_rows
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["story_id", "tag", "old_source",
                           "opus_applies", "opus_confidence", "verdict", "opus_reasoning"],
                           delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(allrows)
    n = confirm + reject
    print(f"\n=== old-insert precision audit (this batch) ===")
    print(f"CONFIRM {confirm}/{n} = {confirm/n*100:.1f}%" if n else "no verdicts")
    print(f"REJECT {reject} (removal evidence) | errors {errors}")
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
