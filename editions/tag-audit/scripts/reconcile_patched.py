#!/usr/bin/env python3
"""Reconcile the patched-definition audit against the already-inserted
old-definition tags. DRY by default — writes report TSVs, never touches XML.

Builds:
  * NEW confirmed set  = Opus True at the CURRENT (patched) prompt_hash,
    propagated to near-duplicates (skipping RA-original / already-present).
  * ADDS               = new confirmed pairs not already in the XML.
  * REMOVAL candidates = OLD LLM inserts (from committed
    llm-confirmed-verdicts.tsv) that the patched audit now contradicts:
      - direct old insert whose (story,tag) is now Opus-REJECTED, or now
        Sonnet-False (dropped out of the candidate set) under patched defs;
      - propagated old insert whose source story is itself a removal.
    Conservative guards: practice/kabbalah PILOT inserts are never removed
    (they came from a separate, already-validated pilot, not the Sonnet
    sweep); a pair the patched sweep never evaluated is never removed.

Outputs (in editions/tag-audit/):
  llm-confirmed-verdicts-patched.tsv  — the new add-list (direct+propagated)
  reconcile-removals.tsv              — removal candidates w/ reason
  reconcile-summary.txt               — counts
"""
import csv, hashlib, re, sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))
import tag_lexicons
from tag_audit import _presence_prompt

AUDIT = REPO / "editions" / "tag-audit"
ONLINE = REPO / "editions" / "online"
CACHE = AUDIT / ".cache" / "llm-presence.tsv"

# categories that went through the patched Sonnet sweep (eligible for removal)
RERUN_CATS = {
    "social", "ethics-and-emotions", "supernatural", "characters-and-roles",
    "experience", "folkloristics", "times", "spaces", "knowledge", "kabbalah",
}


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()
    ).hexdigest()[:8]


def main():
    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    tags = sorted({r["tag"] for r in rows if r["model"] == "claude-cli"})
    H = {t: phash(t) for t in tags}

    # --- patched-definition verdicts (hash-aware) ---
    sonnet_cand = {(r["story_id"], r["tag"]) for r in rows
                   if r["model"] == "claude-cli" and r["prompt_hash"] == H.get(r["tag"])}
    opus_true, opus_false = {}, set()
    for r in rows:
        if r["model"] == "opus-cli" and r.get("prompt_hash") == H.get(r["tag"]):
            if r["applies"] == "True":
                opus_true[(r["story_id"], r["tag"])] = (r["confidence"], r["reasoning"])
            else:
                opus_false.add((r["story_id"], r["tag"]))

    # --- duplicate adjacency ---
    adj = defaultdict(set)
    with open(AUDIT / "story-duplicates.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            adj[r["story_a"]].add(r["story_b"])
            adj[r["story_b"]].add(r["story_a"])

    # --- current (story,tag) pairs in the XML תיוגים spans ---
    xml_pairs = set()
    div_re = re.compile(r'<div\b(?=[^>]*\btype="story")(?=[^>]*\bxml:id="([^"]+)")[^>]*>')
    span_re = re.compile(r'<span\s+[^>]*ana="([^"]+)"[^>]*>תיוגים\*?</span>')
    for xml in sorted(ONLINE.glob("*.xml")):
        txt = xml.read_text()
        ms = list(div_re.finditer(txt))
        for i, m in enumerate(ms):
            sid = m.group(1)
            end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
            sm = span_re.search(txt[m.end():end])
            if not sm:
                continue
            for t in (t.strip() for t in sm.group(1).split(";")):
                if t:
                    xml_pairs.add((sid, t))

    # --- old LLM inserts (committed) ---
    import subprocess
    old_txt = subprocess.check_output(
        ["git", "show", "HEAD:editions/tag-audit/llm-confirmed-verdicts.tsv"],
        cwd=REPO, text=True)
    old = list(csv.DictReader(old_txt.splitlines(), delimiter="\t"))
    old_pairs = {(r["story_id"], r["tag"]): r for r in old}

    # RA-original = in XML but NOT an old LLM insert
    ra_pairs = xml_pairs - set(old_pairs)

    # --- ADDS: new confirmed, propagated, minus what's already in XML ---
    add = {}
    for (sid, tag), (conf, reason) in opus_true.items():
        if (sid, tag) not in xml_pairs:
            add[(sid, tag)] = ("direct", sid, conf, reason)
        for dup in adj.get(sid, ()):
            if (dup, tag) not in xml_pairs and (dup, tag) not in opus_true:
                add.setdefault((dup, tag), ("propagated", sid, conf, reason))

    # --- REMOVAL candidates ---
    removals = []
    for (sid, tag), r in old_pairs.items():
        cat = tag.split(":")[0]
        if cat not in RERUN_CATS:
            continue  # pilot / non-re-run category: preserve
        if (sid, tag) in opus_true:
            continue  # still confirmed
        reason = None
        if r["source"] == "direct":
            if (sid, tag) in opus_false:
                reason = "direct: Opus rejected under patched def"
            elif (sid, tag) not in sonnet_cand:
                reason = "direct: dropped from Sonnet candidate set (patched def)"
        else:  # propagated
            src = r.get("source_story", "")
            if (src, tag) in opus_false:
                reason = f"propagated: source {src} now Opus-rejected"
            elif (src, tag) not in opus_true and (src, tag) not in sonnet_cand:
                reason = f"propagated: source {src} no longer confirmed"
        if reason:
            removals.append({"story_id": sid, "tag": tag, "source": r["source"],
                             "source_story": r.get("source_story", ""), "reason": reason})

    # --- write reports ---
    addf = AUDIT / "llm-confirmed-verdicts-patched.tsv"
    with open(addf, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["story_id", "tag", "source", "source_story",
                    "opus_confidence", "opus_reasoning"])
        for (sid, tag), (src, ss, conf, reason) in sorted(add.items()):
            w.writerow([sid, tag, src, ss, conf, reason])
    remf = AUDIT / "reconcile-removals.tsv"
    with open(remf, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["story_id", "tag", "source",
                           "source_story", "reason"], delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(sorted(removals, key=lambda x: (x["tag"], x["story_id"])))

    kept = sum(1 for k in old_pairs if k in opus_true or k in xml_pairs) - len(removals)
    lines = [
        f"RA-original pairs in XML:           {len(ra_pairs)}",
        f"Old LLM inserts (committed):        {len(old_pairs)}",
        f"Patched Opus-confirmed (direct):    {len(opus_true)}",
        f"",
        f"ADDS (new, not yet in XML):         {len(add)}",
        f"  direct:    {sum(1 for v in add.values() if v[0]=='direct')}",
        f"  propagated:{sum(1 for v in add.values() if v[0]=='propagated')}",
        f"REMOVAL candidates:                 {len(removals)}",
        f"  direct:    {sum(1 for r in removals if r['source']=='direct')}",
        f"  propagated:{sum(1 for r in removals if r['source']=='propagated')}",
    ]
    from collections import Counter
    lines.append("\nRemovals by category:")
    for c, n in sorted(Counter(r["tag"].split(":")[0] for r in removals).items(), key=lambda x: -x[1]):
        lines.append(f"  {c:24s} {n}")
    lines.append("\nAdds by category:")
    for c, n in sorted(Counter(t.split(":")[0] for (_, t) in add).items(), key=lambda x: -x[1]):
        lines.append(f"  {c:24s} {n}")
    summary = "\n".join(lines)
    (AUDIT / "reconcile-summary.txt").write_text(summary + "\n")
    print(summary)
    print(f"\nWrote: {addf.name}, {remf.name}, reconcile-summary.txt")


if __name__ == "__main__":
    main()
