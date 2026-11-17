"""Collect steps 1-4 (+ recall check if present) into one JSON and inject it into the
viz page template. Output goes to private/ because it quotes motif titles."""
import csv
import json
import re
from collections import Counter

from common import HERE, OUT, STEP1_DIR, STEP3_DIR, event_level, is_heading

META = {m["id"]: m for m in json.loads((OUT / "motif_meta.json").read_text())}
CH = {"A": "Mythological", "B": "Animals", "C": "Tabu", "D": "Magic", "E": "The dead",
      "F": "Marvels", "G": "Ogres", "H": "Tests", "J": "Wise and foolish", "K": "Deceptions",
      "L": "Reversal of fortune", "M": "Ordaining the future", "N": "Chance and fate",
      "P": "Society", "Q": "Rewards and punishments", "R": "Captives and fugitives",
      "S": "Unnatural cruelty", "T": "Sex", "U": "Nature of life", "V": "Religion",
      "W": "Traits of character", "X": "Humor", "Z": "Miscellaneous"}


def chapter(code):
    return code.replace("Noy ", "")[0]


def kind(m):
    if m["origin"] != "tmi":
        return "noy"
    return "jewish" if m["jewish"] else "intl"


stories = []
SAMPLES = [HERE / "sample.tsv"] + sorted(HERE.glob("sample-round*.tsv"))  # pilot + every round
rows, seen_ids = [], set()
for f in SAMPLES:
    for r in csv.DictReader(open(f), delimiter="\t"):
        if r["story_id"] not in seen_ids:
            seen_ids.add(r["story_id"]); rows.append(r)
for r in rows:
    sid = r["story_id"]
    f4 = OUT / "step4" / f"{sid}.json"
    if not f4.exists():
        continue
    d1 = json.loads((STEP1_DIR / f"{sid}.json").read_text())
    d3 = json.loads((STEP3_DIR / f"{sid}.json").read_text())
    d4 = json.loads(f4.read_text())
    fr = OUT / "recall" / f"{sid}.json"
    rec = {e["n"]: e for e in json.loads(fr.read_text())["events"]} if fr.exists() else {}
    p3 = {e["n"]: e for e in d3["events"]}
    events = []
    for e in d1["events"]:
        e3 = p3.get(e["n"], {})
        picks = [{"code": p["code"], "grade": p["grade"], "title": META[p["code"]]["title"],
                  "kind": kind(META[p["code"]]), "why": p.get("why", ""), "wider": False}
                 for p in e3.get("picks", [])]
        cov = e3.get("coverage", "none")
        re_ = rec.get(e["n"])
        if cov == "none" and re_ and re_.get("picks"):
            picks += [{"code": p["code"], "grade": p["grade"], "title": META[p["code"]]["title"],
                       "kind": kind(META[p["code"]]), "why": p.get("why", ""), "wider": True}
                      for p in re_["picks"]]
        for p in picks:
            p["heading"] = is_heading(p["code"])
        level, how = event_level(picks, e3.get("proposed_branch", ""))
        events.append({"n": e["n"], "level": level, "level_how": how, "event": e["event"], "detail": e.get("detail", ""),
                       "quote": e.get("quote", ""), "coverage": cov,
                       "coverage_wider": (re_ or {}).get("coverage") if cov == "none" else cov,
                       "picks": picks, "proposed": e3.get("proposed_motif", ""),
                       "proposed_branch": e3.get("proposed_branch", "")})
    seen, tags = set(), []
    for t in d4["tags"]:
        if t["tag"] in seen:
            continue
        seen.add(t["tag"])
        tags.append({k: t.get(k) for k in ("tag", "events", "motifs", "propp", "relation", "why")})
    stories.append({"id": sid, "edition": r["edition"], "url": f"https://www.hasidic-stories.org/Story/{r['edition']}/{sid}",
                    "summary": d1["summary_en"], "frame": d1.get("frame", ""), "genre": d1.get("genre_free", ""),
                    "propp": d1["propp"], "events": events, "tags": tags,
                    "motif_tags": {m["code"]: m["tags"] for m in d4["motifs"]}, "note": d4.get("note", "")})

# aggregate flow: our category -> Thompson chapter
links = Counter()
for s in stories:
    for t in s["tags"]:
        cat = t["tag"].split(":")[0]
        ms = [m for m in (t["motifs"] or []) if m in META]
        if t["relation"] == "no_counterpart" or not ms:
            links[(cat, "∅ no motif")] += 1
        for m in ms:
            links[(cat, chapter(m))] += 1
    for code, tg in s["motif_tags"].items():
        if not tg:
            links[("∅ no tag", chapter(code))] += 1
flow = [{"source": a, "target": b, "value": v} for (a, b), v in links.items()]

# gaps: how much of each system the other one fails to represent (bubble packs)
def tnum(code):
    m = re.match(r"([A-Z])(\d+)", re.sub(r"#\d+$", "", code.replace("Noy ", "")))
    return (m.group(1), int(m.group(2))) if m else (code[:1], 0)


def mtitle(code):
    return (META.get(code) or {}).get("title", "")


tag_use, tag_gap = Counter(), Counter()
mot_use, mot_gap = Counter(), Counter()
for s in stories:
    for t in s["tags"]:
        ms = [m for m in (t["motifs"] or []) if m in META]
        tag_use[t["tag"]] += 1
        if t["relation"] == "no_counterpart" or not ms:
            tag_gap[t["tag"]] += 1
    for code, tg in s["motif_tags"].items():
        if code not in META:
            continue
        mot_use[code] += 1
        if not tg:
            mot_gap[code] += 1
cats = {}
for tag in tag_use:
    cat, _, sub = tag.partition(":")
    cats.setdefault(cat, []).append({"name": sub or cat, "id": tag, "use": tag_use[tag], "gap": tag_gap[tag]})
tag_tree = {"name": "Our tags", "children": [{"name": c, "children": v} for c, v in sorted(cats.items())]}
tree = {}
for code in mot_use:
    L, n = tnum(code)
    blk, ten = f"{L}{n // 100 * 100}", f"{L}{n // 10 * 10}"
    leaf = {"name": code, "id": code, "title": mtitle(code), "kind": kind(META[code]),
            "use": mot_use[code], "gap": mot_gap[code]}
    tree.setdefault(L, {}).setdefault(blk, {}).setdefault(ten, []).append(leaf)
mot_tree = {"name": "Motifs", "children": [
    {"name": L, "title": CH.get(L, ""), "children": [
        {"name": b, "title": mtitle(b), "children": [
            {"name": t, "title": mtitle(t), "children": lv} for t, lv in sorted(tens.items())]}
        for b, tens in sorted(blks.items())]}
    for L, blks in sorted(tree.items())]}
gaps = {"tags": tag_tree, "motifs": mot_tree,
        "totals": {"tag_use": sum(tag_use.values()), "tag_gap": sum(tag_gap.values()),
                   "mot_use": sum(mot_use.values()), "mot_gap": sum(mot_gap.values()),
                   "tags": len(tag_use), "motifs": len(mot_use)}}

ev = [e for s in stories for e in s["events"]]
cov = Counter(e["coverage"] for e in ev)
covw = Counter(e["coverage_wider"] or "none" for e in ev)
rel = Counter(t["relation"] for s in stories for t in s["tags"])
levels = Counter(e["level"] for e in ev)
data = {"stories": stories, "flow": flow, "chapters": CH, "gaps": gaps,
        "stats": {"stories": len(stories), "events": len(ev), "coverage": cov, "coverage_wider": covw,
                  "recall_done": any((OUT / "recall").glob("*.json")) if (OUT / "recall").exists() else False,
                  "propp_mean": round(sum(s["propp"]["fit"] for s in stories) / len(stories), 1),
                  "propp_forced": round(100 * sum(f["strength"] == "forced" for s in stories for f in s["propp"]["functions"])
                                        / sum(len(s["propp"]["functions"]) for s in stories)),
                  "tag_rel": rel, "levels": levels}}
VIZ = OUT / "viz"
VIZ.mkdir(exist_ok=True)
html = (HERE / "viz_template.html").read_text().replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
(VIZ / "motif-score.html").write_text(html)
print("wrote", VIZ / "motif-score.html", len(html) // 1024, "KB;", len(stories), "stories;", len(flow), "flow links")
