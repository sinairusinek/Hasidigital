"""Rank likely story-boundary errors in an incoming TEI edition (story divisions not yet reviewed).

Signals per story division:
  dup_id        the same xml:id is used by more than one division (usually one story cut at a page change)
  short         under 250 characters of text
  open_end      the previous division does not end on a sentence end (':' '.' or '*)') -> boundary cuts a sentence
  cont_start    the division opens with a continuation word (ו..., אך, אבל, כי, גם, עוד...) or mid-sentence
  catchword     the previous division's last word equals this division's first word (printer's catchword)
  no_head_cue   the division neither starts a new page-paragraph nor opens like a tale ('מעשה', 'פעם', 'שמעתי', 'סיפר', numbers)
Output: <edition>-boundaries.tsv next to this script, sorted by score, with Transkribus links."""
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

T = "{http://www.tei-c.org/ns/1.0}"
XID = "{http://www.w3.org/XML/1998/namespace}id"
DOCS = {"Eser-Orot": 9194696, "Eser-Kedushot": 9194695}
CONT = ("ו", "אך", "אבל", "כי", "גם", "עוד", "אמנם", "רק", "אז", "ואז", "לכן", "על כן", "ע״כ", "ועכ״ז")
OPEN = ("מעשה", "פעם", "פ״א", "פעם אחת", "שמעתי", "סיפר", "ספר", "סח", "הנה", "אמר", "מסופר", "ראיתי", "שאלה", "תשובת")


def text(el):
    return " ".join("".join(el.itertext()).split())


def page_of(div):
    for el in div.iter():
        f = el.get("facs", "")
        m = re.match(r"#facs_(\d+)", f)
        if m:
            return int(m.group(1))
    return None


def run(path):
    ed = path.stem
    root = ET.parse(path).getroot()
    body = root.find(f".//{T}body")
    divs = [d for d in body.iter(f"{T}div") if d.get("type") in ("story", "non-story")]
    ids = Counter(d.get(XID) for d in divs if d.get("type") == "story")
    rows, prev = [], None
    for i, d in enumerate(divs):
        if d.get("type") != "story":
            prev = d if text(d) else prev
            continue
        t = re.sub(r"^" + re.escape(d.get(XID) or "") + r"\s*", "", text(d))
        sig = []
        if ids[d.get(XID)] > 1:
            sig.append("dup_id")
        if len(t) < 250:
            sig.append("short")
        body_t = re.sub(r"^[\(\[][א-ת״׳\"']{1,4}[\)\]]\s*", "", t)   # drop section number (ח)
        first = body_t.split()[0] if body_t else ""
        numbered = body_t != t
        if prev is not None:
            pt = text(prev)
            last = pt.split()[-1].strip(".:,") if pt else ""
            if last and first and last == first.strip(".:,"):
                sig.append("catchword")          # catchword left at the end of the previous division
            elif pt and not re.search(r"(:|\.|\*\))\s*$", pt):
                sig.append("open_end")
        if t.startswith(CONT) and not t.startswith(OPEN) or (first and first.startswith("ו") and len(first) > 2):
            sig.append("cont_start")
        if not numbered and not t.startswith(OPEN):
            sig.append("no_head_cue")
        w = {"dup_id": 4, "open_end": 3, "catchword": 0, "cont_start": 2, "short": 2, "no_head_cue": 1}
        pg = page_of(d)
        rows.append({"score": sum(w[s] for s in sig), "signals": ",".join(sig), "story_id": d.get(XID),
                     "div_index": i, "numbered": int(numbered), "page": pg, "chars": len(t),
                     "prev_end": text(prev)[-60:] if prev is not None else "",
                     "start": t[:80],
                     "transkribus": f"https://app.transkribus.org/collection/49371/doc/{DOCS[ed]}/edit?pageNr={pg}" if pg else ""})
        prev = d
    rows.sort(key=lambda r: (-r["score"], r["div_index"]))
    out = path.with_name(f"{ed}-boundaries.tsv")
    with open(out, "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w_.writeheader()
        w_.writerows(rows)
    c = Counter(s for r in rows for s in r["signals"].split(",") if s)
    print(f"{ed}: {len(rows)} story divisions, {len(ids)} distinct ids, {sum(1 for v in ids.values() if v > 1)} ids used more than once")
    print("   signals:", dict(c.most_common()), "| score>=5:", sum(r["score"] >= 5 for r in rows))
    return out


if __name__ == "__main__":
    for p in sys.argv[1:] or ["Eser-Orot.xml", "Eser-Kedushot.xml"]:
        run(Path(p))
