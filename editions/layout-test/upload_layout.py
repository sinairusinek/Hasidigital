"""Upload run_layout.py's PAGE XML to Transkribus as new IN_PROGRESS versions (no credits; images untouched).

    python upload_layout.py DOCID "NOTE" [--dry]

A page is uploaded only when its latest version is our own (toolName TOOL) or the empty version Transkribus made on
upload (status NEW, no regions): if anyone has saved the page since, in the app or otherwise, it is left alone and
listed. A page whose latest version already has NOTE is skipped, so a
run that was cut short can be started again. Each version's note is NOTE plus that page's flags (flags.tsv).
"""
import csv, sys
from run_layout import session, TRP, DATA

TOOL = "Hasidigital local layout"


def main():
    doc, note = sys.argv[1], sys.argv[2]; dry = "--dry" in sys.argv
    base = DATA / "books" / doc
    flags = {int(r["pageNr"]): r["flags"] for r in csv.DictReader(open(base / "flags.tsv"), delimiter="\t")}
    s = session()
    full = s.get(f"{TRP}/collections/49371/{doc}/fulldoc", params={"nrOfTranscripts": 1}, headers={"Accept": "application/json"}, timeout=180).json()
    done, kept = [], []
    for p in full["pageList"]["pages"]:
        n = p["pageNr"]; f = base / "layout" / f"{n:04d}.xml"
        if not f.exists(): continue
        last = p["tsList"]["transcripts"][0]
        fresh = last.get("status") == "NEW" and not last.get("nrOfRegions") and not last.get("toolName")
        if last.get("toolName") != TOOL and not fresh:
            kept.append((n, last.get("toolName"), last.get("userName"))); continue
        if (last.get("note") or "").startswith(note): continue  # already there (a run cut short and started again)
        if dry: done.append(n); continue
        r = s.post(f"{TRP}/collections/49371/{doc}/{n}/text", data=f.read_bytes(), headers={"Content-Type": "application/xml"},
                   params={"status": "IN_PROGRESS", "toolName": TOOL, "parent": last["tsId"],
                           "note": note + (f"; flags: {flags[n]}" if flags.get(n) else "")}, timeout=300)
        r.raise_for_status(); done.append(n)
    print(f"{'would upload' if dry else 'uploaded'} {len(done)} pages; left alone (saved by someone since): {kept}")


if __name__ == "__main__":
    main()
