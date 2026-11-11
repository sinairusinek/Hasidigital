#!/usr/bin/env python3
"""Build editions/edition-status.html: one row per catalogued work, one coloured cell per pipeline stage.

Reads editions/edition-registry.tsv (rebuild it first with build_edition_registry.py) plus the TEI files in
editions/online and editions/incoming/ready, so the page is always current with the registry.

    python3 editions/build_status_page.py
"""
import csv
import html
import re
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "editions" / "edition-registry.tsv"
OUT = REPO / "editions" / "edition-status.html"
SCAN_BOOKS = REPO / "editions" / "scan-check" / "scan-books.tsv"      # series check results, one row per doc
SCAN_ISSUES = REPO / "editions" / "scan-check" / "scan-issues.tsv"    # problems Sinai checks before layout
# per-work state of the local layout experiment and of the layout run itself:
# work_nu, layout_test (done/part/todo/na), layout (done/part/todo), note
LAYOUT_STATUS = REPO / "editions" / "layout-status.tsv"

# Zenodo v1 (DOI 10.5281/zenodo.20524710, published 2026-10-07)
ZENODO_V1 = {"Shivhei-Habesht", "Shivhei-Harav", "Sipurei-Zadikim", "Khal-Hasidim", "Khal-Kdoshim",
             "Adat-Zadikim", "maase-zadikim", "Mifalot-HaZadikim", "PeerMikdoshim"}

STAGES = ["Decision", "Scan", "Transkribus", "Scan QA", "Layout test", "Layout", "Transcribed", "TEI", "Stories", "Online", "Women", "Zenodo"]
LABELS = {"done": "Done", "part": "In progress / partial", "todo": "Not started",
          "block": "Blocked (needs a scan or Gadi)", "na": "N/A"}


def xml_files():
    """stem -> (path, location) for every TEI edition file."""
    out = {}
    for loc, d in (("online", REPO / "editions" / "online"), ("incoming", REPO / "editions" / "incoming" / "ready")):
        for p in d.rglob("*.xml"):
            out[p.stem] = (p, "check" if p.parent.name == "check" else loc)
    return out


def resolve(name, files):
    stem = Path(name).stem
    if stem in files:
        return stem
    base = re.split(r"_(?:Hebrewbooks|NLI|archive|HathiTrust|Hebraica)", stem)[0]
    return base if base in files else None


def stories_and_women(path):
    t = path.read_text(encoding="utf-8")
    return len(re.findall(r'<div\b[^>]*type="story"', t)), bool(re.search(r"women:", t))


def tsv(path):
    return list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t")) if path.exists() else []


SCANNED = {b["docId"]: b for b in tsv(SCAN_BOOKS)}
OPEN_ISSUES: dict[str, list[str]] = {}      # block layout
AFTER_OCR: dict[str, list[str]] = {}        # duplicate pages kept through OCR, deleted before annotation
for i in tsv(SCAN_ISSUES):
    {"open": OPEN_ISSUES, "after-ocr": AFTER_OCR}.get(i["status"], {}).setdefault(i["work_nu"], []).append(i["id"])
LAYOUT = {l["work_nu"]: l for l in tsv(LAYOUT_STATUS)}


def layout_cells(r, c, has_xml):
    """Scan QA → Layout test → Layout. Works the RA already transcribed went through a manual check and
    Transkribus layout, so they count as past these stages."""
    final = int(r["trp_pages_final"] or 0)
    if has_xml or final or "finish transcription" in r["next_step"] or "re-export" in r["next_step"]:
        c["Scan QA"] = ("done", "checked by hand by the RA")
        c["Layout test"] = ("na", "transcribed before the layout experiment")
        c["Layout"] = ("done", "Transkribus models, corrected by the RA")
        return
    checked = [SCANNED[d] for d in r["trp_main_docs"].split() if d in SCANNED]
    if OPEN_ISSUES.get(r["nu"]):
        c["Scan QA"] = ("part", "open scan issue " + " ".join(OPEN_ISSUES[r["nu"]]) + ": check before layout")
    elif checked:
        later = [f"repeated pages kept until after OCR ({' '.join(AFTER_OCR[r['nu']])})"] if AFTER_OCR.get(r["nu"]) else []
        c["Scan QA"] = ("done", " | ".join(later + [b["verdict"] for b in checked if b["verdict"]]) or "no findings")
    else:
        c["Scan QA"] = ("todo", "")
    l = LAYOUT.get(r["nu"], {})
    c["Layout test"] = (l.get("layout_test") or "todo", l.get("note", "") or ("waiting for the layout experiment" if checked else ""))
    c["Layout"] = (l.get("layout") or "todo", l.get("note", ""))


def cells(r, files):
    c = {}
    dec, step = r["decision"], r["next_step"]
    c["Decision"] = ({"included": "done", "no": "na"}.get(dec, "part"), dec)

    src = r["scan_source"]
    if "later edition" in step:
        c["Scan"] = ("block", "later edition only")
    elif "find a scan" in step:  # the catalogue's download is the wrong book or another volume
        c["Scan"] = ("block", "no usable scan")
    elif src in ("HebrewBooks", "NLI downloaded") or r["trp_main_docs"] or r["xml"]:
        c["Scan"] = ("done", src if src in ("HebrewBooks", "NLI downloaded") else "")
    elif src == "library request":
        c["Scan"] = ("block", src)
    elif src == "no scan found" or "find a scan" in step:
        c["Scan"] = ("block", "no scan found")
    else:
        c["Scan"] = ("todo", src)

    key = resolve(r["xml"], files) if r["xml"] else None
    has_xml = key is not None
    if r["trp_main_docs"]:
        c["Transkribus"] = ("done", r["trp_main_docs"].replace(" ", ", "))
    elif "Drive scan" in step:
        c["Transkribus"] = ("todo", "Drive scan not uploaded")
    elif r["trp_other_docs"]:
        c["Transkribus"] = ("part", "other scans only: " + r["trp_other_docs"])
    else:
        c["Transkribus"] = ("todo", "")

    layout_cells(r, c, has_xml)

    pages, final = int(r["trp_pages"] or 0), int(r["trp_pages_final"] or 0)
    if has_xml:
        c["Transcribed"] = ("done", f"{final}/{pages} pp final" if pages else "")
    elif pages:
        frac = final / pages
        c["Transcribed"] = ("done" if frac >= .9 else "part" if final else "todo", f"{final}/{pages} pp")
    else:
        c["Transcribed"] = ("todo", "")

    if has_xml:
        path, loc = files[key]
        n, women = stories_and_women(path)
        c["TEI"] = ("done", f"{path.name} ({loc})")
        c["Stories"] = ("part" if loc == "check" else "done", f"{n} stories" + (", structure check" if loc == "check" else ""))
        c["Online"] = ("done", "") if loc == "online" else ("todo", "ready" if loc == "incoming" else "")
        c["Women"] = ("done", "") if women else ("todo", "")
        c["Zenodo"] = ("done", "v1") if key in ZENODO_V1 else ("todo", "")
    else:
        c["TEI"] = ("part", "needs re-export") if r["xml_location"] == "registered, no XML" else ("todo", "")
        for s in ("Stories", "Online", "Women", "Zenodo"):
            c[s] = ("todo", "")
    if dec == "no":
        c = {s: ("na", v[1]) if s != "Decision" else v for s, v in c.items()}
    return c


def main():
    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8"), delimiter="\t"))
    files = xml_files()
    data = []
    for r in rows:
        c = cells(r, files)
        reached = sum(1 for s in STAGES if c[s][0] == "done" or (s == "Layout test" and c[s][0] == "na"))
        data.append((r, c, reached))
    data.sort(key=lambda x: (x[0]["decision"] == "no", -x[2], int(x[0]["nu"] or 0)))

    active = [d for d in data if d[0]["decision"] != "no"]
    n = len(active)
    funnel = "".join(
        f'<div class="frow"><span class="flabel">{s}</span><div class="fbar"><div style="width:{100*k/n:.1f}%"></div></div>'
        f'<span class="fnum">{k} / {n}</span></div>'
        for s in STAGES[1:] for k in [sum(1 for _, c, _ in active if c[s][0] == "done" or (s == "Layout test" and c[s][0] == "na"))])

    steps = Counter(re.sub(r" \(.*", "", r["next_step"]) or "decided no" for r, _, _ in data)
    chips = '<button class="chip on" data-step="">All works <b>%d</b></button>' % len(data) + "".join(
        f'<button class="chip" data-step="{html.escape(k)}">{html.escape(k)} <b>{v}</b></button>'
        for k, v in steps.most_common())

    body = []
    for r, c, _ in data:
        step = re.sub(r" \(.*", "", r["next_step"]) or "decided no"
        tds = "".join(f'<td class="{c[s][0]}" title="{html.escape(c[s][1])}">{html.escape(c[s][1]) if s in ("Decision", "Stories") else ""}</td>'
                      for s in STAGES)
        body.append(f'<tr data-step="{html.escape(step)}" class="{"no" if r["decision"] == "no" else ""}">'
                    f'<td class="num">{r["nu"] or "—"}</td><td class="work" dir="rtl">{html.escape(r["work"])}</td>'
                    f'<td class="num">{r["edition_year"]}</td>{tds}<td class="step">{html.escape(r["next_step"])}</td></tr>')

    legend = "".join(f'<span><i class="{k}"></i>{v}</span>' for k, v in LABELS.items())
    head = "".join(f"<th>{s}</th>" for s in STAGES)
    OUT.write_text(TEMPLATE.format(date=date.today().isoformat(), total=len(data), active=n, funnel=funnel,
                                   chips=chips, legend=legend, head=head, body="\n".join(body)), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {len(data)} works")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Edition Status</title>
<style>
:root {{ --bg:#f7f7f5; --panel:#fff; --ink:#1f2328; --muted:#6a6f76; --line:#e3e3df;
  --done:#2f8f5b; --part:#e0a526; --todo:#e9e9e4; --block:#c8553d; --na:#f1f1ee; --accent:#2f5d8a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#16181b; --panel:#1e2125; --ink:#e6e6e3;
  --muted:#9aa0a6; --line:#2e3237; --done:#3fa66d; --part:#d29b27; --todo:#2b2f34; --block:#d0644c; --na:#1b1d20; --accent:#7fa8d1; }} }}
:root[data-theme="dark"] {{ --bg:#16181b; --panel:#1e2125; --ink:#e6e6e3; --muted:#9aa0a6; --line:#2e3237;
  --done:#3fa66d; --part:#d29b27; --todo:#2b2f34; --block:#d0644c; --na:#1b1d20; --accent:#7fa8d1; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
h1 {{ margin:0 0 2px; font-size:22px; }} .sub {{ color:var(--muted); margin-bottom:20px; }}
.funnel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; max-width:640px; margin-bottom:18px; }}
.funnel h2 {{ font-size:13px; margin:0 0 10px; color:var(--muted); font-weight:600; }}
.frow {{ display:flex; align-items:center; gap:10px; margin:5px 0; }}
.flabel {{ width:92px; font-size:13px; }} .fnum {{ width:70px; font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }}
.fbar {{ flex:1; height:12px; background:var(--todo); border-radius:3px; overflow:hidden; }} .fbar div {{ height:100%; background:var(--done); }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }}
.chip {{ border:1px solid var(--line); background:var(--panel); color:var(--ink); border-radius:14px; padding:4px 10px; font-size:12px; cursor:pointer; }}
.chip.on {{ border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent); }} .chip b {{ color:var(--muted); font-weight:600; }}
.legend {{ display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); margin-bottom:10px; }}
.legend i {{ display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:5px; vertical-align:-2px; border:1px solid var(--line); }}
.wrap {{ overflow-x:auto; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
table {{ border-collapse:separate; border-spacing:2px; font-size:12px; width:100%; }}
th {{ position:sticky; top:0; background:var(--panel); text-align:left; font-weight:600; padding:6px 4px; color:var(--muted); white-space:nowrap; }}
td {{ padding:4px 6px; white-space:nowrap; }} td.num {{ color:var(--muted); font-variant-numeric:tabular-nums; text-align:right; }}
td.work {{ font-size:14px; text-align:right; }} td.step {{ color:var(--muted); }}
td.done, i.done {{ background:var(--done); color:#fff; }} td.part, i.part {{ background:var(--part); color:#1f2328; }}
td.todo, i.todo {{ background:var(--todo); }} td.block, i.block {{ background:var(--block); color:#fff; }}
td.na, i.na {{ background:var(--na); color:var(--muted); }}
td.done, td.part, td.todo, td.block, td.na {{ min-width:58px; border-radius:2px; font-size:11px; }}
tr.no td.work {{ color:var(--muted); }} tr.hide {{ display:none; }}
</style></head><body>
<h1>Edition Status</h1>
<div class="sub">Hasidic editions up to 1914 · {total} catalogued works · generated {date} from <code>edition-registry.tsv</code></div>
<div class="funnel"><h2>Works reaching each stage (excluding the works decided “no”)</h2>{funnel}</div>
<div class="chips">{chips}</div>
<div class="legend">{legend}<span>Hover a cell for details</span></div>
<div class="wrap"><table><thead><tr><th>#</th><th>Work</th><th>Year</th>{head}<th>Next step</th></tr></thead>
<tbody>
{body}
</tbody></table></div>
<script>
document.querySelectorAll('.chip').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('tbody tr').forEach(tr => tr.classList.toggle('hide', !!b.dataset.step && tr.dataset.step !== b.dataset.step));
}});
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
