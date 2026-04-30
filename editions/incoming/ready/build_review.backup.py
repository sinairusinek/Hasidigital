#!/usr/bin/env python3
"""
Build a self-contained HTML entity review page from gemini-correction-log.tsv.

Usage (from repo root):
    python editions/incoming/ready/build_review.py

Output: editions/incoming/ready/entity-review.html
"""

import csv
import json
import sys
from pathlib import Path

READY_DIR = Path(__file__).parent
LOG_FILE = READY_DIR / "gemini-correction-log.tsv"
OUTPUT = READY_DIR / "entity-review.html"
CONTEXT_WINDOW = 160  # chars either side of entity


def get_plain_text(xml_path: Path) -> str:
    """Extract plain text using the same standoffconverter path as the pipeline."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from lxml import etree
    from ner_pipeline.text_extraction import create_standoff_view

    tree = etree.parse(str(xml_path))
    _, _, plain_text = create_standoff_view(tree)
    return plain_text


def find_context(plain_text: str, entity_text: str, start: int, end: int):
    """
    Find entity_text near (start, end) in plain_text and return
    (before, entity, after) triple for display.  Falls back to
    a raw slice if the string cannot be located.
    """
    n = len(plain_text)
    # Search within a generous window around the logged offset
    search_start = max(0, start - 400)
    search_end = min(n, end + 400)
    window = plain_text[search_start:search_end]

    pos = window.find(entity_text)
    if pos == -1:
        # Try the whole document
        pos_global = plain_text.find(entity_text)
        if pos_global != -1:
            actual_start = pos_global
        else:
            # Give up — show raw slice
            ctx_s = max(0, start - CONTEXT_WINDOW)
            ctx_e = min(n, end + CONTEXT_WINDOW)
            return plain_text[ctx_s:start], entity_text, plain_text[end:ctx_e]
        actual_start = pos_global
    else:
        actual_start = search_start + pos

    actual_end = actual_start + len(entity_text)
    ctx_s = max(0, actual_start - CONTEXT_WINDOW)
    ctx_e = min(n, actual_end + CONTEXT_WINDOW)
    before = plain_text[ctx_s:actual_start]
    after = plain_text[actual_end:ctx_e]
    # Trim to nearest space boundary so we don't split mid-word
    if ctx_s > 0 and before and before[0] not in " \n":
        sp = before.find(" ")
        before = before[sp + 1:] if sp != -1 else before
    if ctx_e < n and after and after[-1] not in " \n":
        sp = after.rfind(" ")
        after = after[:sp] if sp != -1 else after
    return before.strip(), entity_text, after.strip()


def build_entries(log_path: Path, ready_dir: Path):
    plain_texts: dict[str, str] = {}
    rows = []
    with open(log_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    print(f"Loading plain texts for {len({r['source_file'] for r in rows})} editions…")
    for fname in sorted({r["source_file"] for r in rows}):
        xml_path = ready_dir / fname
        if xml_path.exists():
            try:
                plain_texts[fname] = get_plain_text(xml_path)
                print(f"  {fname}: {len(plain_texts[fname])} chars")
            except Exception as e:
                print(f"  WARNING: could not load {fname}: {e}")
                plain_texts[fname] = ""
        else:
            plain_texts[fname] = ""

    entries = []
    for i, row in enumerate(rows):
        fname = row["source_file"]
        text = row["text"]
        start = int(row["start"])
        end = int(row["end"])
        plain = plain_texts.get(fname, "")

        if plain and text:
            before, ent, after = find_context(plain, text, start, end)
        else:
            before, ent, after = "", text, ""

        entries.append({
            "id": i,
            "action": row["action"],
            "text": text,
            "orig_label": row["original_label"],
            "new_label": row["corrected_label"],
            "file": fname,
            "before": before,
            "entity": ent,
            "after": after,
        })

    return entries


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>Entity Review — Gemini Correction Log</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f4f4f8;
    margin: 0; padding: 0;
    direction: rtl;
  }
  #header {
    background: #2d3a4a;
    color: #fff;
    padding: 14px 20px;
    position: sticky; top: 0; z-index: 100;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  #header h1 { margin: 0; font-size: 1.1rem; white-space: nowrap; }
  #counter { font-size: 0.85rem; color: #aad4ff; white-space: nowrap; }
  #filters { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn {
    padding: 4px 10px; border: 1px solid #ccc; border-radius: 4px;
    background: #fff; cursor: pointer; font-size: 0.8rem;
  }
  .btn.active { background: #2d3a4a; color: #fff; border-color: #2d3a4a; }
  select.btn { padding: 4px 6px; }
  #export-btn {
    margin-right: auto; background: #1a7a4a; color: #fff;
    border-color: #1a7a4a; font-weight: bold;
  }
  #main { max-width: 960px; margin: 0 auto; padding: 16px; }
  .card {
    background: #fff;
    border: 1px solid #dde;
    border-radius: 6px;
    margin-bottom: 10px;
    padding: 12px 14px;
    transition: opacity 0.15s;
  }
  .card.decided { opacity: 0.45; }
  .card.decided:hover { opacity: 1; }
  .card-top {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 8px; flex-wrap: wrap;
  }
  .badge {
    font-size: 0.72rem; font-weight: bold; padding: 2px 7px;
    border-radius: 10px; white-space: nowrap;
  }
  .badge-added    { background: #d4edda; color: #1a6030; }
  .badge-removed  { background: #f8d7da; color: #721c24; }
  .badge-reclassified { background: #fff3cd; color: #856404; }
  .badge-label { background: #e8eaf6; color: #283593; }
  .badge-file { background: #f0f0f0; color: #555; font-weight: normal; font-size: 0.68rem; }
  .entity-text {
    font-weight: bold; font-size: 0.95rem;
    border-radius: 3px; padding: 1px 4px;
  }
  .action-added    .entity-text { background: #c3e6cb; color: #155724; }
  .action-removed  .entity-text { background: #f5c6cb; color: #721c24; }
  .action-reclassified .entity-text { background: #ffeeba; color: #856404; }
  .context {
    font-size: 0.9rem; color: #333; line-height: 1.6;
    direction: rtl; text-align: right;
    border-right: 3px solid #dde;
    padding-right: 10px; margin-bottom: 10px;
  }
  .actions { display: flex; gap: 8px; }
  .act-btn {
    padding: 4px 14px; border-radius: 4px; border: 1px solid #ccc;
    cursor: pointer; font-size: 0.82rem; font-weight: bold;
  }
  .approve-btn { background: #d4edda; color: #155724; border-color: #b8dfc4; }
  .approve-btn:hover { background: #b8dfc4; }
  .reject-btn  { background: #f8d7da; color: #721c24; border-color: #f5b8be; }
  .reject-btn:hover  { background: #f5b8be; }
  .skip-btn    { background: #f0f0f0; color: #555; }
  .skip-btn:hover    { background: #e0e0e0; }
  .decided-badge {
    font-size: 0.75rem; padding: 2px 8px; border-radius: 10px;
    font-weight: bold; display: none;
  }
  .card[data-decision="approve"] .decided-badge {
    display: inline-block; background: #d4edda; color: #155724;
  }
  .card[data-decision="approve"] .decided-badge::after { content: "✓ approved"; }
  .card[data-decision="reject"] .decided-badge {
    display: inline-block; background: #f8d7da; color: #721c24;
  }
  .card[data-decision="reject"] .decided-badge::after { content: "✗ rejected"; }
  .card[data-decision="skip"] .decided-badge {
    display: inline-block; background: #f0f0f0; color: #888;
  }
  .card[data-decision="skip"] .decided-badge::after { content: "— skipped"; }
  #no-results { text-align: center; color: #888; padding: 40px; display: none; }
</style>
</head>
<body>

<div id="header">
  <h1>Entity Review</h1>
  <div id="counter">–</div>
  <div id="filters">
    <span style="font-size:0.8rem;color:#aaa">Action:</span>
    <button class="btn active" data-filter-action="all">All</button>
    <button class="btn" data-filter-action="added">Added</button>
    <button class="btn" data-filter-action="removed">Removed</button>
    <button class="btn" data-filter-action="reclassified">Reclassified</button>
    <span style="font-size:0.8rem;color:#aaa">Decided:</span>
    <button class="btn active" data-filter-decided="all">All</button>
    <button class="btn" data-filter-decided="undecided">Undecided</button>
    <button class="btn" data-filter-decided="decided">Decided</button>
    <span style="font-size:0.8rem;color:#aaa">Edition:</span>
    <select class="btn" id="edition-filter"><option value="all">All editions</option></select>
    <span style="font-size:0.8rem;color:#aaa">Label:</span>
    <select class="btn" id="label-filter"><option value="all">All labels</option></select>
  </div>
  <button class="btn" id="export-btn">Export decisions ↓</button>
</div>

<div id="main">
  <div id="no-results">No entries match current filters.</div>
</div>

<script>
const DATA = __DATA_JSON__;

const decisions = {};  // id -> "approve" | "reject" | "skip"

function labelFor(entry) {
  return entry.action === "removed" ? entry.orig_label
       : entry.action === "added"   ? entry.new_label
       : (entry.orig_label + "→" + entry.new_label);
}

function renderCard(entry) {
  const card = document.createElement("div");
  card.className = `card action-${entry.action}`;
  card.dataset.id = entry.id;
  card.dataset.action = entry.action;
  card.dataset.file = entry.file;
  card.dataset.label = labelFor(entry);
  card.dataset.decision = decisions[entry.id] || "";

  const label = labelFor(entry);
  card.innerHTML = `
    <div class="card-top">
      <span class="badge badge-${entry.action}">${entry.action}</span>
      <span class="badge badge-label">${label}</span>
      <span class="entity-text">${esc(entry.entity || entry.text)}</span>
      <span class="badge badge-file">${entry.file}</span>
      <span class="decided-badge"></span>
    </div>
    <div class="context" dir="rtl">
      ${esc(entry.before)}<strong style="background:rgba(255,220,0,0.35);padding:0 2px">${esc(entry.entity || entry.text)}</strong>${esc(entry.after)}
    </div>
    <div class="actions">
      <button class="act-btn approve-btn" data-id="${entry.id}">✓ Approve</button>
      <button class="act-btn reject-btn"  data-id="${entry.id}">✗ Reject</button>
      <button class="act-btn skip-btn"    data-id="${entry.id}">— Skip</button>
    </div>`;

  card.querySelectorAll(".approve-btn").forEach(b =>
    b.onclick = () => decide(entry.id, "approve"));
  card.querySelectorAll(".reject-btn").forEach(b =>
    b.onclick = () => decide(entry.id, "reject"));
  card.querySelectorAll(".skip-btn").forEach(b =>
    b.onclick = () => decide(entry.id, "skip"));

  return card;
}

function esc(s) {
  return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function decide(id, verdict) {
  decisions[id] = verdict;
  const card = document.querySelector(`.card[data-id="${id}"]`);
  if (card) {
    card.dataset.decision = verdict;
    card.classList.toggle("decided", verdict !== "");
  }
  updateCounter();
}

let activeFilters = { action: "all", decided: "all", file: "all", label: "all" };

function matchesFilters(card) {
  if (activeFilters.action !== "all" && card.dataset.action !== activeFilters.action) return false;
  if (activeFilters.file   !== "all" && card.dataset.file   !== activeFilters.file)   return false;
  if (activeFilters.label  !== "all" && card.dataset.label  !== activeFilters.label)  return false;
  if (activeFilters.decided === "undecided" && card.dataset.decision !== "") return false;
  if (activeFilters.decided === "decided"   && card.dataset.decision === "") return false;
  return true;
}

function applyFilters() {
  let visible = 0;
  document.querySelectorAll(".card").forEach(card => {
    const show = matchesFilters(card);
    card.style.display = show ? "" : "none";
    if (show) visible++;
  });
  document.getElementById("no-results").style.display = visible ? "none" : "block";
  updateCounter();
}

function updateCounter() {
  const total   = DATA.length;
  const decided = Object.keys(decisions).length;
  const approved = Object.values(decisions).filter(d => d === "approve").length;
  const rejected = Object.values(decisions).filter(d => d === "reject").length;
  document.getElementById("counter").textContent =
    `${decided}/${total} decided  ·  ✓ ${approved}  ✗ ${rejected}`;
}

function init() {
  const main = document.getElementById("main");

  // Populate edition & label dropdowns
  const files  = [...new Set(DATA.map(e => e.file))].sort();
  const labels = [...new Set(DATA.map(labelFor))].sort();
  const edSel  = document.getElementById("edition-filter");
  const lbSel  = document.getElementById("label-filter");
  files.forEach(f  => { const o = document.createElement("option"); o.value = f; o.text = f; edSel.add(o); });
  labels.forEach(l => { const o = document.createElement("option"); o.value = l; o.text = l; lbSel.add(o); });

  // Render cards
  DATA.forEach(entry => main.appendChild(renderCard(entry)));

  // Action filter buttons
  document.querySelectorAll("[data-filter-action]").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll("[data-filter-action]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilters.action = btn.dataset.filterAction;
      applyFilters();
    };
  });
  document.querySelectorAll("[data-filter-decided]").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll("[data-filter-decided]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilters.decided = btn.dataset.filterDecided;
      applyFilters();
    };
  });
  edSel.onchange = () => { activeFilters.file  = edSel.value;  applyFilters(); };
  lbSel.onchange = () => { activeFilters.label = lbSel.value; applyFilters(); };

  // Export
  document.getElementById("export-btn").onclick = () => {
    const rows = ["id\taction\ttext\torig_label\tnew_label\tfile\tdecision"];
    DATA.forEach(e => {
      const d = decisions[e.id] || "";
      if (d) rows.push([e.id, e.action, e.text, e.orig_label, e.new_label, e.file, d].join("\t"));
    });
    const blob = new Blob([rows.join("\n")], {type:"text/tab-separated-values"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "entity-review-decisions.tsv";
    a.click();
  };

  updateCounter();
}

document.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
"""


def main():
    print(f"Reading {LOG_FILE}…")
    entries = build_entries(LOG_FILE, READY_DIR)
    print(f"Built {len(entries)} entries. Generating HTML…")

    data_json = json.dumps(entries, ensure_ascii=False, indent=None)
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}  ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
