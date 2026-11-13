"""Run every new book through run_layout.py and upload_layout.py, smallest first (no credits, no HTR).

    python run_books.py NOTE [--max-pages N] [DOCID ...]

Books: the docs uploaded in 2026-11 (transkribus-collection-map.tsv), less the holds and any book already uploaded
with NOTE (books/<doc>/uploaded.txt). A book whose Claude tag calls failed (e.g. the Max usage limit) is not uploaded;
it waits 30 minutes and runs again (answers already given are cached), up to 8 times. Log: books/batch.log.
--max-pages: no book is started that would take this run past N pages, so that one run stays inside a share of the
Max plan's 5-hour usage window (about 0.12% of a window per page with Opus, measured 2026-11-12).
"""
import csv, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from run_layout import HOLD, DATA

HERE = Path(__file__).parent
PY = sys.executable
LOG = DATA / "books" / "batch.log"


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"; print(line, flush=True)
    with open(LOG, "a") as f: f.write(line + "\n")


def books(only):
    rows = [r for r in csv.DictReader(open(HERE.parent / "transkribus-collection-map.tsv"), delimiter="\t")
            if r["uploaded"] >= "2026-11" and r["role"] == "main" and r["work_nu"].split(".")[0] not in HOLD]
    if only: rows = [r for r in rows if r["docId"] in only]
    return sorted(rows, key=lambda r: int(r["pages"]))


def main():
    args = sys.argv[2:]; cap = 10 ** 9
    if "--max-pages" in args: k = args.index("--max-pages"); cap = int(args[k + 1]); del args[k:k + 2]
    note, only, used = sys.argv[1], args, 0
    for r in books(only):
        doc = r["docId"]; done = DATA / "books" / doc / "uploaded.txt"
        if done.exists() and done.read_text().startswith(note): continue
        # a book bigger than the cap still runs, alone, as a run's first book
        if used and used + int(r["pages"]) > cap: log(f"page cap {cap} reached ({used} pages run); stopping before {doc} ({r['pages']} pp.)"); break
        used += int(r["pages"])
        for attempt in range(8):
            t0 = time.time()
            p = subprocess.run([PY, str(HERE / "run_layout.py"), doc], capture_output=True, text=True, cwd=HERE)
            failed = p.stdout.count("relabel failed")
            log(f"{doc} work {r['work_nu']} {r['work']} ({r['pages']} pp.): layout exit {p.returncode}, {failed} Claude failures, "
                f"{(time.time() - t0) / 60:.0f} min; " + (p.stdout.strip().splitlines() or [""])[-1][:200])
            if p.returncode == 0 and not failed: break
            log("  " + (p.stderr.strip().splitlines() or [""])[-1][:300] + "; waiting 30 min"); time.sleep(1800)
        else:
            log(f"{doc}: gave up, not uploaded"); continue
        u = subprocess.run([PY, str(HERE / "upload_layout.py"), doc, note], capture_output=True, text=True, cwd=HERE)
        if u.returncode:  # upload cut short (timeout): once more, it resumes
            u = subprocess.run([PY, str(HERE / "upload_layout.py"), doc, note], capture_output=True, text=True, cwd=HERE)
        log(f"  upload exit {u.returncode}: " + ((u.stdout or u.stderr).strip().splitlines() or [""])[-1][:300])
        if u.returncode == 0: done.write_text(note + "\n")


if __name__ == "__main__":
    main()
