#!/usr/bin/env python3
"""Generate the two vocabularies for the women dashboard's keyword exhibit.

  women-keywords-empirical.json — {word: {women, no_women, ratio}}, the terms
    that actually distinguish women-tagged stories (pure corpus computation,
    prevalence ratio; no LLM).
  women-keywords-apriori.json   — {category: [words]}, the "obvious" women-words
    an LLM proposes BEFORE reading any text (one `claude -p` call, Sonnet).

The gap between them is the exhibit's point: keyword search is unreliable for
finding women in historical Hebrew/Yiddish narrative.

Usage:  python3 editions/gen_women_keywords.py [--no-llm]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
ONLINE = os.path.join(REPO, "editions", "online")
TIER_TSV = os.path.join(REPO, "editions", "women-5tier-9editions-summary.tsv")
EMP_OUT = os.path.join(REPO, "editions", "women-keywords-empirical.json")
APR_OUT = os.path.join(REPO, "editions", "women-keywords-apriori.json")

TEI = "http://www.tei-c.org/ns/1.0"
XID = "{http://www.w3.org/XML/1998/namespace}id"

# strip Hebrew points/cantillation + punctuation; keep Hebrew-letter tokens
_NIQQUD = re.compile(r"[֑-ׇ]")
_NONHEB = re.compile(r"[^א-ת\s]")
# common function words that carry no gender signal
STOP = set("""של את על אל כי אשר הוא היא היה הם הזה זה זאת אני אתה אנחנו לא כן גם
או אם כמו עד אחר אחרי לפני תחת בין רק עוד כל כך אך אבל הנה אז שם פה ויהי ויאמר
אמר אומר להם לו לה אותו אותה כאשר מן עם בו בה בא באו הלך אמרו""".split())


def women_map():
    """story_id -> True/False from the 5-tier TSV (no-women -> False)."""
    out = {}
    with open(TIER_TSV, encoding="utf-8") as f:
        import csv
        for r in csv.DictReader(f, delimiter="\t"):
            out[r["story_id"]] = r["new_claude_5tier"] != "no-women"
    return out


def story_texts(ids):
    """story_id -> set of normalized Hebrew word types (presence per story)."""
    texts = {}
    for fn in sorted(os.listdir(ONLINE)):
        if not fn.endswith(".xml"):
            continue
        try:
            root = ET.parse(os.path.join(ONLINE, fn)).getroot()
        except ET.ParseError:
            continue
        for div in root.iter(f"{{{TEI}}}div"):
            if div.get("type") != "story":
                continue
            sid = div.get(XID, "")
            if sid not in ids:
                continue
            raw = "".join(div.itertext())
            raw = _NIQQUD.sub("", raw)
            raw = _NONHEB.sub(" ", raw)
            toks = {w for w in raw.split() if len(w) >= 2 and w not in STOP}
            texts[sid] = toks
    return texts


def build_empirical(min_women=5, top=80):
    wm = women_map()
    n_women = sum(wm.values())
    n_no = len(wm) - n_women
    texts = story_texts(set(wm))
    w_cnt, n_cnt = defaultdict(int), defaultdict(int)
    for sid, toks in texts.items():
        tgt = w_cnt if wm[sid] else n_cnt
        for t in toks:
            tgt[t] += 1
    rows = {}
    for w in set(w_cnt) | set(n_cnt):
        wc, nc = w_cnt[w], n_cnt[w]
        if wc < min_women:
            continue
        ratio = (wc / n_women) / ((nc + 0.5) / n_no)  # prevalence ratio, smoothed
        rows[w] = {"women": wc, "no_women": nc, "ratio": ratio}
    ordered = dict(sorted(rows.items(), key=lambda kv: -kv[1]["ratio"])[:top])
    json.dump(ordered, open(EMP_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"empirical: {len(ordered)} terms (corpus: {n_women} women / {n_no} no-women) -> {EMP_OUT}")
    print("  top 10:", " · ".join(list(ordered)[:10]))


APRIORI_PROMPT = """You are helping build a methodology exhibit about finding women \
in 19th-century Hasidic Hebrew/Yiddish stories.

WITHOUT reading any actual stories, list the Hebrew (and Hebrew-script Yiddish) \
words you would EXPECT to signal that a woman is present or active in such a story. \
Give your a-priori intuition only.

Group them into these categories and return STRICT JSON, an object mapping each \
category name to an array of Hebrew-script words (no transliteration, no glosses):
- "kinship"        (e.g. mother, daughter, wife, widow…)
- "roles_titles"   (social/religious roles a woman might hold)
- "life_events"    (events that typically involve women)
- "pronouns_grammar" (feminine pronouns/forms)
- "other_signals"  (anything else you'd expect)

Return ONLY the JSON object, 8-15 words per category."""


def build_apriori():
    out = subprocess.run(
        ["claude", "-p", "--model", "claude-sonnet-4-6", "--output-format", "text",
         APRIORI_PROMPT],
        capture_output=True, text=True, timeout=180,
    )
    txt = out.stdout.strip()
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        sys.exit(f"Could not parse JSON from claude output:\n{txt[:500]}")
    data = json.loads(m.group(0))
    # keep lists of strings; strip niqqud so they match the unvocalized corpus
    # (otherwise the "gap" set-comparison never intersects the empirical terms)
    clean = {k: [_NIQQUD.sub("", w) for w in v if isinstance(w, str)]
             for k, v in data.items() if isinstance(v, list)}
    json.dump(clean, open(APR_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    n = sum(len(v) for v in clean.values())
    print(f"apriori: {n} words in {len(clean)} categories -> {APR_OUT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip the a-priori LLM call")
    args = ap.parse_args()
    build_empirical()
    if not args.no_llm:
        build_apriori()


if __name__ == "__main__":
    main()
