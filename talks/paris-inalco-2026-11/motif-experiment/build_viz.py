"""Collect steps 1-4 (+ recall check if present) into one JSON and inject it into the
viz page template. Output goes to private/ because it quotes motif titles."""
import csv
import json
from collections import Counter

from common import HERE, OUT, SAMPLE_TSV, STEP1_DIR, STEP3_DIR, event_level, is_heading

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
for r in csv.DictReader(open(SAMPLE_TSV), delimiter="\t"):
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

ev = [e for s in stories for e in s["events"]]
cov = Counter(e["coverage"] for e in ev)
covw = Counter(e["coverage_wider"] or "none" for e in ev)
rel = Counter(t["relation"] for s in stories for t in s["tags"])
levels = Counter(e["level"] for e in ev)
data = {"stories": stories, "flow": flow, "chapters": CH,
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
