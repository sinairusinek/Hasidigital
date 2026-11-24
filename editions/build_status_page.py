#!/usr/bin/env python3
"""Build editions/edition-status.html: one row per catalogued work, one coloured cell per pipeline stage.

Reads editions/edition-registry.tsv (rebuild it first with build_edition_registry.py) plus the TEI files in
editions/online and editions/incoming/ready, so the page is always current with the registry.

    python3 editions/build_status_page.py
"""
import csv
import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "editions" / "edition-registry.tsv"
OUT = REPO / "editions" / "edition-status.html"
SCAN_BOOKS = REPO / "editions" / "scan-check" / "scan-books.tsv"      # series check results, one row per doc
SCAN_ISSUES = REPO / "editions" / "scan-check" / "scan-issues.tsv"    # problems Sinai checks before layout
# per-work state of the local layout experiment and of the layout run itself:
# work_nu, layout_test (done/part/todo/na), layout (done/part/todo), note
LAYOUT_STATUS = REPO / "editions" / "layout-status.tsv"
# the overnight layout batch (layout-test/run_books.py) leaves books/<docId>/uploaded.txt once a book's layout is in Transkribus
BOOKS = Path.home() / "Documents" / "Hasidigital-data" / "books"

# Zenodo v1 (DOI 10.5281/zenodo.20524710, published 2026-10-07)
ZENODO_V1 = {"Shivhei-Habesht", "Shivhei-Harav", "Sipurei-Zadikim", "Khal-Hasidim", "Khal-Kdoshim",
             "Adat-Zadikim", "maase-zadikim", "Mifalot-HaZadikim", "PeerMikdoshim"}

# cross-edition near-duplicates (find_duplicate_stories.py, e5 embeddings, cosine >= 0.99); that run covered
# editions/online only, on 2026-06-01. Update DUP_RUN when it is re-run, and the scope if it covers incoming too.
DUPLICATES = REPO / "editions" / "story-duplicates.tsv"
DUP_RUN = "2026-06-01"


def story_summary(files):
    """HTML for the totals line: stories per location over distinct TEI files, plus the duplicate count."""
    n = Counter()
    ed = Counter()
    for stem, (path, loc) in files.items():
        n[loc] += stories_and_women(path)[0]
        ed[loc] += 1
    pairs = [r for r in tsv(DUPLICATES) if float(r["sim"]) >= 0.99]
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in pairs:
        parent[find(r["story_a"])] = find(r["story_b"])
    involved = {x for x in parent}
    groups = {find(x) for x in involved}
    distinct = n["online"] - (len(involved) - len(groups))
    total = sum(n.values())
    parts = [f'{n["online"]:,} in {ed["online"]} editions online']
    if ed["incoming"]:
        parts.append(f'{n["incoming"]:,} in {ed["incoming"]} incoming editions')
    if ed["check"]:
        parts.append(f'{n["check"]:,} in {ed["check"]} editions under structure check')
    return (f'<div class="tot"><div><b>{total:,}</b> stories in {sum(ed.values())} TEI editions '
            f'({", ".join(parts)})</div>'
            f'<div><b>{len(pairs)}</b> cross-edition duplicate pairs ({len(involved)} stories) among the online editions, '
            f'so {distinct:,} distinct stories there. Near-identical texts only (embedding similarity ≥ 0.99, run {DUP_RUN}); '
            f'the incoming editions are not yet checked for duplicates, and looser retellings are not counted.</div></div>')


STAGES = ["Decision", "Scan", "Transkribus", "Scan QA", "Layout test", "Layout", "Transcribed", "TEI", "Stories", "Topics", "Online", "Women", "Zenodo"]
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


TRP_LINK = "https://app.transkribus.org/collection/49371/doc/{}/edit?pageNr=1"
SITE_STORY = "https://www.hasidic-stories.org/Story/{}/{}"
EXIST_DATA = "https://teipub9.dh-dev.com/exist/rest/db/apps/HasidicStoriesServer/data/"


def first_story_id(path):
    for tag in re.findall(r'<div\b[^>]*type="story"[^>]*>', path.read_text(encoding="utf-8")):
        m = re.search(r'xml:id="([^"]+)"', tag)
        if m:
            return m.group(1)
    return None


def links(r, files):
    """[(group, label, url)] for the hover popover on the work name."""
    out = []
    for u in (x.strip() for x in r["nli_link"].split("|")):
        if u and not any(u.split("/NLI")[0].replace("beta.", "www.") == o[2].split("/NLI")[0] for o in out):
            out.append(("NLI", "NLI catalogue", u))
    for u in (x.strip() for x in r["hebrewbooks_link"].split("|")):
        if u:
            out.append(("HebrewBooks", "HebrewBooks", u))
    for d in r["trp_main_docs"].split():
        out.append(("Transkribus", f"doc {d}", TRP_LINK.format(d)))
    for d, role in re.findall(r"(\d{5,})(?:\(([^)]*)\))?", r["trp_other_docs"]):
        out.append(("Transkribus", f"doc {d} ({role or 'other scan'})", TRP_LINK.format(d)))
    key = resolve(r["xml"], files) if r["xml"] else None
    if key and files[key][1] == "online":
        sid = first_story_id(files[key][0])
        if sid:
            out.append(("Online", "hasidic-stories.org (first story)", SITE_STORY.format(key, sid)))
    return out


def stories_and_women(path):
    t = path.read_text(encoding="utf-8")
    return len(re.findall(r'<div\b[^>]*type="story"', t)), bool(re.search(r"women:", t))


def tsv(path):
    return list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t")) if path.exists() else []


SCANNED = {b["docId"]: b for b in tsv(SCAN_BOOKS)}
OPEN_ISSUES: dict[str, list[str]] = {}      # Sinai checks before layout
FIND_SCAN: dict[str, list[str]] = {}        # the scan is not usable: find a better copy
AFTER_OCR: dict[str, list[str]] = {}        # duplicate pages kept through OCR, deleted before annotation
for i in tsv(SCAN_ISSUES):
    {"open": OPEN_ISSUES, "find-scan": FIND_SCAN, "after-ocr": AFTER_OCR}.get(i["status"], {}).setdefault(
        i["work_nu"], []).append(i["id"])
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
    if FIND_SCAN.get(r["nu"]):
        c["Scan QA"] = ("block", "scan too poor, find a better copy: " + " ".join(FIND_SCAN[r["nu"]]))
    elif OPEN_ISSUES.get(r["nu"]):
        c["Scan QA"] = ("part", "open scan issue " + " ".join(OPEN_ISSUES[r["nu"]]) + ": check before layout")
    elif checked:
        later = [f"repeated pages kept until after OCR ({' '.join(AFTER_OCR[r['nu']])})"] if AFTER_OCR.get(r["nu"]) else []
        c["Scan QA"] = ("done", " | ".join(later + [b["verdict"] for b in checked if b["verdict"]]) or "no findings")
    else:
        c["Scan QA"] = ("todo", "")
    l = LAYOUT.get(r["nu"], {})
    c["Layout test"] = (l.get("layout_test") or "todo", l.get("note", "") or ("waiting for the layout experiment" if checked else ""))
    c["Layout"] = (l.get("layout") or "todo", l.get("note", ""))
    docs = r["trp_main_docs"].split()
    up = [d for d in docs if (BOOKS / d / "uploaded.txt").exists()]
    if up:
        import datetime
        when = max(datetime.date.fromtimestamp((BOOKS / d / "uploaded.txt").stat().st_mtime) for d in up).isoformat()
        pp = sum(len(list((BOOKS / d / "layout").glob("*.xml"))) for d in up)
        c["Layout"] = ("done" if len(up) == len(docs) else "part",
                       f"local layout uploaded to Transkribus {when}, {pp} pp; next: review it in Transkribus, collecting layout issues for a fix pass on all books, then HTR")


_SERVER = None


def server_dates():
    """file name -> last-modified on the eXist server (public REST listing), {} when offline."""
    global _SERVER
    if _SERVER is None:
        try:
            import urllib.request
            x = urllib.request.urlopen(EXIST_DATA, timeout=30).read().decode("utf-8")
            _SERVER = dict(re.findall(r'name="([^"]+\.xml)"[^>]*last-modified="([^"]+)"', x))
        except Exception:
            _SERVER = {}
    return _SERVER


def topics_cell(path, n):
    """Topic coverage: how many of the edition's stories carry a real topic tag.

    Counted from the XML, not inferred from the gate's pass/fail, so an edition
    that is mostly untagged cannot show as done. TBD:Unknown is a placeholder
    left where tags would go, so it does not count as tagged.

    Malformed tags (e.g. a bare 'kabbalah') are a separate problem from
    coverage: they are mentioned in the tooltip but do not by themselves turn
    a fully tagged edition orange.
    """
    import xml.etree.ElementTree as ET
    from preupload_check import check
    T = "{http://www.tei-c.org/ns/1.0}"
    root = ET.parse(path).getroot()
    stories = [d for d in root.iter(T + "div") if d.get("type") == "story"]
    tagged = 0
    for d in stories:
        toks = [t for s in d.iter(T + "span")
                for t in re.split(r"[;\s]+", s.get("ana") or "") if t]
        if [t for t in toks if t != "TBD:Unknown"]:
            tagged += 1
    total = len(stories)
    untagged = total - tagged
    llm = 'resp="#llm-tagging"' in path.read_text(encoding="utf-8")
    errs, _ = check(str(path))
    other = [e for e in errs if "TOPIC TAGGING" not in e]
    note = "; gate: " + other[0][:60] if other else ""

    if total and untagged == 0:
        return ("done", f"{total} tagged, {'LLM-tagged' if llm else 'hand-tagged'}{note}")
    if tagged == 0:
        return ("todo", f"all {total} stories untagged{note}")
    return ("part", f"{untagged} of {total} untagged{note}")


def online_cell(path, loc):
    if loc != "online" and loc != "incoming":
        return ("todo", "")
    srv = server_dates().get(path.name)
    if not srv:
        return ("todo", "ready, not uploaded" if loc == "incoming" else "not on the server")
    import subprocess
    repo = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path)], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    from datetime import datetime
    if repo and datetime.fromisoformat(repo) > datetime.fromisoformat(re.sub(r"\.\d+", "", srv).replace("Z", "+00:00")):
        return ("part", f"online; repo newer ({repo[:10]}) than the site ({srv[:10]}): re-upload")
    return ("done", f"online, up to date ({srv[:10]})")


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
        c["Topics"] = topics_cell(path, n)
        c["Online"] = online_cell(path, loc)
        c["Women"] = ("done", "") if women else ("todo", "")
        c["Zenodo"] = ("done", "v1") if key in ZENODO_V1 else ("todo", "")
    else:
        c["TEI"] = ("part", "needs re-export") if r["xml_location"] == "registered, no XML" else ("todo", "")
        for s in ("Stories", "Topics", "Online", "Women", "Zenodo"):
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
                    f'<td class="num">{r["nu"] or "—"}</td><td class="work" dir="rtl" tabindex="0" data-links="{html.escape(json.dumps(links(r, files), ensure_ascii=False))}">{html.escape(r["work"])}</td>'
                    f'<td class="num">{r["edition_year"]}</td>{tds}<td class="step">{html.escape(r["next_step"])}</td></tr>')

    legend = "".join(f'<span><i class="{k}"></i>{v}</span>' for k, v in LABELS.items())
    done = lambda s: sum(1 for _, c, _ in active if c[s][0] == "done" or (s == "Layout test" and c[s][0] == "na"))
    head = "".join(f'<th>{s}<br><span class="cnt">{done(s)}/{n}</span></th>' for s in STAGES)
    OUT.write_text(TEMPLATE.format(date=date.today().isoformat(), total=len(data), active=n, funnel=funnel,
                                   chips=chips, legend=legend, summary=story_summary(files), head=head, body="\n".join(body)), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {len(data)} works")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hasidic Edition Status</title>
<style>
:root {{ --bg:#f7f7f5; --panel:#fff; --ink:#1f2328; --muted:#6a6f76; --line:#e3e3df;
  --done:#2f8f5b; --part:#e0a526; --todo:#e9e9e4; --block:#c8553d; --na:#f1f1ee; --accent:#2f5d8a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#16181b; --panel:#1e2125; --ink:#e6e6e3;
  --muted:#9aa0a6; --line:#2e3237; --done:#3fa66d; --part:#d29b27; --todo:#2b2f34; --block:#d0644c; --na:#1b1d20; --accent:#7fa8d1; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#16181b; --panel:#1e2125; --ink:#e6e6e3; --muted:#9aa0a6; --line:#2e3237;
  --done:#3fa66d; --part:#d29b27; --todo:#2b2f34; --block:#d0644c; --na:#1b1d20; --accent:#7fa8d1; color-scheme:dark; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
h1 {{ margin:0 0 2px; font-size:22px; }} .sub {{ color:var(--muted); margin-bottom:20px; }}
.tot {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px 16px; max-width:640px; margin-bottom:12px; display:grid; gap:6px; }}
.tot div:first-child {{ font-size:15px; }} .tot div + div {{ color:var(--muted); font-size:12.5px; }} .tot b {{ color:var(--ink); font-variant-numeric:tabular-nums; }}
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
th .cnt {{ font-weight:400; font-variant-numeric:tabular-nums; }}
td.work {{ cursor:pointer; text-decoration:underline dotted var(--muted); text-underline-offset:3px; }}
#pop {{ position:fixed; z-index:10; display:none; background:var(--panel); border:1px solid var(--line); border-radius:8px;
  box-shadow:0 6px 20px rgba(0,0,0,.18); padding:10px 12px; font-size:12px; min-width:220px; max-width:min(340px, calc(100vw - 32px)); }}
#pop .g {{ color:var(--muted); font-weight:600; margin:6px 0 2px; }} #pop .g:first-child {{ margin-top:0; }}
#pop a {{ color:var(--accent); display:block; padding:2px 0; text-decoration:none; overflow-wrap:anywhere; }} #pop a:hover {{ text-decoration:underline; }}
#pop .none {{ color:var(--muted); }}
tr.no td.work {{ color:var(--muted); }} tr.hide {{ display:none; }}
</style></head><body>
<h1>Edition Status</h1>
<div class="sub">Hasidic editions up to 1914 · {total} catalogued works · generated {date} from <code>edition-registry.tsv</code></div>
{summary}
<div class="funnel"><h2>Works reaching each stage (excluding the works decided “no”)</h2>{funnel}</div>
<div class="chips">{chips}</div>
<div class="legend">{legend}<span>Hover a cell for details · hover or tap a work name for its NLI, Transkribus and site links</span></div>
<div class="wrap"><table><thead><tr><th>#</th><th>Work</th><th>Year</th>{head}<th>Next step</th></tr></thead>
<tbody>
{body}
</tbody></table></div>
<div id="pop" role="dialog"></div>
<script>
const pop = document.getElementById('pop'); let hideT, cur;
function esc(t) {{ const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }}
function show(td) {{
  clearTimeout(hideT); cur = td;
  const L = JSON.parse(td.dataset.links || '[]'); let h = '', g = '';
  for (const [grp, label, url] of L) {{
    if (grp !== g) {{ h += `<div class="g">${{esc(grp)}}</div>`; g = grp; }}
    h += `<a href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(label)}} ↗</a>`;
  }}
  pop.innerHTML = h || '<span class="none">No links recorded</span>';
  pop.style.display = 'block';
  const r = td.getBoundingClientRect(), pw = pop.offsetWidth, ph = pop.offsetHeight;
  let x = Math.min(Math.max(8, r.left), innerWidth - pw - 8), y = r.bottom + 4;
  if (y + ph > innerHeight - 8) y = Math.max(8, r.top - ph - 4);
  pop.style.left = x + 'px'; pop.style.top = y + 'px';
}}
function hideSoon() {{ hideT = setTimeout(() => {{ pop.style.display = 'none'; cur = null; }}, 250); }}
document.querySelectorAll('td.work').forEach(td => {{
  td.addEventListener('mouseenter', () => show(td));
  td.addEventListener('mouseleave', hideSoon);
  td.addEventListener('focus', () => show(td));
  td.addEventListener('click', e => {{ e.stopPropagation(); cur === td && pop.style.display === 'block' ? hideSoon() : show(td); }});
}});
pop.addEventListener('mouseenter', () => clearTimeout(hideT));
pop.addEventListener('mouseleave', hideSoon);
document.addEventListener('click', e => {{ if (!pop.contains(e.target)) {{ pop.style.display = 'none'; cur = null; }} }});
addEventListener('scroll', () => {{ pop.style.display = 'none'; }}, true);
document.querySelectorAll('.chip').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('tbody tr').forEach(tr => tr.classList.toggle('hide', !!b.dataset.step && tr.dataset.step !== b.dataset.step));
}});
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
