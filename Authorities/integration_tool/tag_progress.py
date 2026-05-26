"""
Show progress + ETA of a running (or finished) category audit.

The audit writes a heartbeat to editions/tag-audit/<category>/.progress.json after
each tag. This reads it and prints a one-glance status.

    python3 tag_progress.py practice          # one snapshot
    python3 tag_progress.py practice --watch   # refresh every 15s until done
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

from config import PROJECT_DIR

AUDIT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit")


def _fmt(sec):
    if sec is None:
        return "—"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return (f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s")


def show(category):
    p = os.path.join(AUDIT_DIR, category, ".progress.json")
    if not os.path.exists(p):
        print(f"No progress file for '{category}' yet (run not started, or finished before this feature).")
        return None
    d = json.load(open(p, encoding="utf-8"))
    ct, cd = d["calls_total"], d["calls_done"]
    pct = (cd / ct * 100) if ct else 100.0
    bar_n = int(pct / 5)
    bar = "█" * bar_n + "·" * (20 - bar_n)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["updated"])).total_seconds()
    status = "DONE" if d.get("done") else ("STALLED?" if age > 300 else "running")
    print(f"  {category}  [{status}]  model={d.get('model')}")
    print(f"  tags : {d['tags_done']}/{d['tags_total']}   current: {d.get('current_tag') or '—'}")
    print(f"  calls: {cd}/{ct}  [{bar}] {pct:4.1f}%")
    print(f"  eta  : {_fmt(d.get('eta_seconds'))}   (last update {int(age)}s ago)")
    return d


def main():
    args = sys.argv[1:]
    watch = "--watch" in args
    cats = [a for a in args if not a.startswith("--")] or ["practice"]
    cat = cats[0]
    if not watch:
        show(cat); return
    while True:
        os.system("clear")
        d = show(cat)
        if not d or d.get("done"):
            break
        time.sleep(15)


if __name__ == "__main__":
    main()
