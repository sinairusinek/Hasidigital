"""Tag Audit dashboard — live view of the multi-layer thematic-tag annotation.

Read-only. Computes everything from the authoritative LLM cache
(.cache/llm-presence.tsv), the committed verdict files, and the edition XMLs
at render time, so it always reflects the current state — including new Opus
verdicts as the paced precision audit lands them and removals once applied.

Layers shown:
  • RA-original tags vs. additive LLM inserts already in the XML
  • Patched-definition sweep: Sonnet candidates → Opus confirm/reject, agreement
  • Old-insert precision audit: progress + reject rates (over-tagging cleanup)
"""
import csv
import hashlib
import os
import re
from collections import defaultdict, Counter

import pandas as pd
import streamlit as st

import config
import tag_lexicons
from tag_audit import _presence_prompt

AUDIT = os.path.join(config.PROJECT_DIR, "editions", "tag-audit")
LIVE_CACHE = os.path.join(AUDIT, ".cache", "llm-presence.tsv")
# Committed fallback for Streamlit Cloud (the live cache is git-ignored).
# Refresh with: python3 editions/tag-audit/scripts/export_audit_snapshot.py
SNAPSHOT = os.path.join(AUDIT, "audit-cache-snapshot.tsv")
CACHE = LIVE_CACHE if os.path.exists(LIVE_CACHE) else SNAPSHOT
ONLINE = os.path.join(config.PROJECT_DIR, "editions", "online")
OLD_VERDICTS = os.path.join(AUDIT, "llm-confirmed-verdicts.tsv")
PATCHED_ADDS = os.path.join(AUDIT, "llm-confirmed-verdicts-patched.tsv")

WEAK_CATS = {"social", "ethics-and-emotions", "supernatural", "characters-and-roles",
             "experience", "folkloristics", "times", "spaces", "knowledge"}


# ── data loading (cached on file mtime so it refreshes when the audit writes) ──

def _mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


@st.cache_data(show_spinner=False)
def patched_hash(tag, _defs_mtime):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]


@st.cache_data(show_spinner="Reading LLM cache…")
def load_cache(_cache_mtime):
    rows = []
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
    return rows


@st.cache_data(show_spinner="Scanning edition XMLs…")
def load_xml_pairs(_xml_mtime):
    """(story_id, tag) pairs currently in the story-level תיוגים spans."""
    pairs = set()
    div_re = re.compile(r'<div\b(?=[^>]*\btype="story")(?=[^>]*\bxml:id="([^"]+)")[^>]*>')
    span_re = re.compile(r'<span\s+[^>]*ana="([^"]+)"[^>]*>תיוגים\*?</span>')
    if os.path.isdir(ONLINE):
        for fn in sorted(os.listdir(ONLINE)):
            if not fn.endswith(".xml"):
                continue
            txt = open(os.path.join(ONLINE, fn), encoding="utf-8").read()
            ms = list(div_re.finditer(txt))
            for i, m in enumerate(ms):
                sid = m.group(1)
                end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
                sm = span_re.search(txt[m.end():end])
                if sm:
                    for t in (x.strip() for x in sm.group(1).split(";")):
                        if t:
                            pairs.add((sid, t))
    return pairs


@st.cache_data(show_spinner=False)
def load_verdict_pairs(path, _mt):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [(r["story_id"], r["tag"]) for r in csv.DictReader(f, delimiter="\t")]


def compute():
    defs_mt = _mtime(os.path.join(AUDIT, "tag-definitions-merged.tsv"))
    rows = load_cache(_mtime(CACHE))
    xml_pairs = load_xml_pairs(max(_mtime(os.path.join(ONLINE, fn))
                               for fn in os.listdir(ONLINE) if fn.endswith(".xml")))
    tags = sorted({r["tag"] for r in rows if r["model"] == "claude-cli"})
    H = {t: patched_hash(t, defs_mt) for t in tags}

    sonnet_true, sonnet_cand = set(), set()
    opus_true, opus_false = set(), set()
    for r in rows:
        tag = r["tag"]
        if r["model"] == "claude-cli" and r.get("prompt_hash") == H.get(tag):
            sonnet_cand.add((r["story_id"], tag))
            if r["applies"] == "True":
                sonnet_true.add((r["story_id"], tag))
        elif r["model"] == "opus-cli" and r.get("prompt_hash") == H.get(tag):
            (opus_true if r["applies"] == "True" else opus_false).add((r["story_id"], tag))

    old = set(load_verdict_pairs(OLD_VERDICTS, _mtime(OLD_VERDICTS)))
    adds = set(load_verdict_pairs(PATCHED_ADDS, _mtime(PATCHED_ADDS))) & xml_pairs
    # RA-original = in XML but neither an old insert nor a patched-sweep add
    ra_pairs = xml_pairs - old - adds
    return dict(rows=rows, H=H, xml_pairs=xml_pairs, ra_pairs=ra_pairs, old=old,
                adds=adds, sonnet_true=sonnet_true, sonnet_cand=sonnet_cand,
                opus_true=opus_true, opus_false=opus_false)


# ── page ──────────────────────────────────────────────────────────────────────

st.title("🏷️ Tag Audit")
st.caption("Live multi-layer view of thematic-tag annotation across the 9 core editions. "
           "Read-only; recomputes from the LLM cache + XML on each load.")

if not os.path.exists(CACHE):
    st.error(f"LLM cache not found at {CACHE}")
    st.stop()

D = compute()
ts = pd.to_datetime(_mtime(CACHE), unit="s")
src = "live cache" if CACHE == LIVE_CACHE else "committed snapshot"
st.caption(f"Source: {src} · last updated {ts:%Y-%m-%d %H:%M} · "
           f"{len(D['rows']):,} verdicts")

# ── corpus overview ──
st.header("Corpus")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("RA-original tags", f"{len(D['ra_pairs']):,}")
c2.metric("Old LLM inserts", f"{len(D['old']):,}")
c3.metric("Patched adds", f"{len(D['adds']):,}")
c4.metric("Total in XML", f"{len(D['xml_pairs']):,}")
c5.metric("Tags audited", f"{len({t for _, t in D['sonnet_cand']}):,}")

# ── patched sweep + Opus refinement ──
st.header("Patched-definition sweep → Opus refinement")
st_true, ot, of = D["sonnet_true"], D["opus_true"], D["opus_false"]
confirmed = st_true & ot
rejected = st_true & of
judged = len(confirmed) + len(rejected)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Sonnet candidates", f"{len(D['sonnet_cand']):,}")
m2.metric("Sonnet-True", f"{len(st_true):,}")
m3.metric("Opus-confirmed", f"{len(confirmed):,}")
m4.metric("Opus agreement", f"{len(confirmed)/judged*100:.0f}%" if judged else "—")

# per-category confirm/reject (patched sweep)
cat = defaultdict(lambda: [0, 0])
for k in confirmed:
    cat[k[1].split(":")[0]][0] += 1
for k in rejected:
    cat[k[1].split(":")[0]][1] += 1
if cat:
    df = pd.DataFrame(
        [{"category": c, "confirmed": v[0], "rejected": v[1]} for c, v in cat.items()]
    ).set_index("category").sort_values("confirmed", ascending=False)
    st.subheader("New missed-positives by category (Sonnet-True × Opus)")
    st.bar_chart(df, color=["#4c9f70", "#c45b5b"])

# ── old-insert precision audit ──
st.header("Old-insert precision audit (over-tagging cleanup)")
st.caption("Direct Opus re-judgment of the old weak-definition inserts under the "
           "patched definitions. Opus-False ⇒ removal candidate.")
old_weak = {(s, t) for (s, t) in D["old"]
            if t.split(":")[0] in WEAK_CATS and t not in tag_lexicons.DEFINITIONS}
audited = {k for k in old_weak if k in ot or k in of}
conf_old = {k for k in old_weak if k in ot}
rej_old = {k for k in old_weak if k in of}
p1, p2, p3, p4 = st.columns(4)
p1.metric("Weak-def inserts", f"{len(old_weak):,}")
p2.metric("Audited", f"{len(audited):,}", f"{len(audited)/len(old_weak)*100:.0f}%" if old_weak else "")
p3.metric("Confirmed", f"{len(conf_old):,}")
p4.metric("Removal candidates", f"{len(rej_old):,}",
          f"{len(rej_old)/len(audited)*100:.0f}% reject" if audited else "")
st.progress(len(audited) / len(old_weak) if old_weak else 0.0)

# per-category reject rate
catr = defaultdict(lambda: [0, 0])
for k in conf_old:
    catr[k[1].split(":")[0]][0] += 1
for k in rej_old:
    catr[k[1].split(":")[0]][1] += 1
if catr:
    rows_r = []
    for c, (cf, rj) in catr.items():
        n = cf + rj
        rows_r.append({"category": c, "confirmed": cf, "rejected": rj,
                       "reject %": round(rj / n * 100) if n else 0})
    dfr = pd.DataFrame(rows_r).set_index("category").sort_values("reject %", ascending=False)
    cc1, cc2 = st.columns([3, 2])
    cc1.subheader("Confirm / reject by category")
    cc1.bar_chart(dfr[["confirmed", "rejected"]], color=["#4c9f70", "#c45b5b"])
    cc2.subheader("Reject rate")
    cc2.dataframe(dfr[["reject %"]], width="stretch")

    # worst-offender subtags
    tagr = defaultdict(lambda: [0, 0])
    for k in conf_old:
        tagr[k[1]][0] += 1
    for k in rej_old:
        tagr[k[1]][1] += 1
    worst = sorted(
        ({"tag": t, "confirmed": v[0], "rejected": v[1],
          "reject %": round(v[1] / (v[0] + v[1]) * 100)} for t, v in tagr.items()
         if v[1] >= 3),
        key=lambda x: (-x["reject %"], -x["rejected"]))[:20]
    if worst:
        st.subheader("Most over-tagged subtags (≥3 rejects)")
        st.dataframe(pd.DataFrame(worst).set_index("tag"), width="stretch")

# ── removal candidate detail (for review before any XML write) ──
with st.expander("Removal candidates — story-level detail"):
    if rej_old:
        verd = {}
        for r in D["rows"]:
            if r["model"] == "opus-cli" and r.get("prompt_hash") == D["H"].get(r["tag"]) \
                    and r["applies"] == "False":
                verd[(r["story_id"], r["tag"])] = r.get("reasoning", "")
        det = [{"story_id": s, "tag": t, "opus_reasoning": verd.get((s, t), "")}
               for (s, t) in sorted(rej_old)]
        cats = sorted({t.split(":")[0] for _, t in rej_old})
        pick = st.multiselect("Filter categories", cats, default=cats)
        det = [d for d in det if d["tag"].split(":")[0] in pick]
        st.caption(f"{len(det)} removal candidates shown — none applied to XML yet.")
        st.dataframe(pd.DataFrame(det), width="stretch", height=400)
    else:
        st.info("No removal candidates yet — run the precision audit batches.")
