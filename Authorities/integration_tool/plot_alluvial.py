"""Alluvial / Sankey diagram of old human binary tags → new Claude 5-tier tags."""
import csv, os
from collections import Counter
import plotly.graph_objects as go

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC  = os.path.join(PROJ, "editions", "women-5tier-9editions-full.tsv")
PNG  = os.path.join(PROJ, "editions", "women-alluvial-old-to-new.png")
HTML = os.path.join(PROJ, "editions", "women-alluvial-old-to-new.html")

OLD_ORDER = ["no-women", "minor", "major", "major+minor"]
NEW_ORDER = ["no-women", "mention-only", "minor-character", "catalyst-character", "major-character"]
OLD_COLORS = {"no-women":"#5B9BD5","minor":"#FDBF6F","major":"#A9D18E","major+minor":"#C4A484"}
NEW_COLORS = {"no-women":"#5B9BD5","mention-only":"#A6CEE3","minor-character":"#FDBF6F",
              "catalyst-character":"#FFD966","major-character":"#A9D18E"}

# Load flow counts
rows = []
with open(SRC, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        rows.append(r)

flows = Counter((r["human_old_binary"], r["claude_new_5tier"]) for r in rows)
total = len(rows)

# Node lists: left side = old, right side = new
left_labels  = [f"{c} ({sum(n for (h,_),n in flows.items() if h==c)})" for c in OLD_ORDER]
right_labels = [f"{c} ({sum(n for (_,k),n in flows.items() if k==c)})" for c in NEW_ORDER]
labels = left_labels + right_labels
node_colors = [OLD_COLORS[c] for c in OLD_ORDER] + [NEW_COLORS[c] for c in NEW_ORDER]

# Build sources / targets
src_idx, tgt_idx, values, link_colors = [], [], [], []
def hex_to_rgba(hex_color, alpha=0.5):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"

for i, old in enumerate(OLD_ORDER):
    for j, new in enumerate(NEW_ORDER):
        v = flows.get((old, new), 0)
        if v == 0:
            continue
        src_idx.append(i)
        tgt_idx.append(len(OLD_ORDER) + j)
        values.append(v)
        link_colors.append(hex_to_rgba(NEW_COLORS[new], 0.55))

fig = go.Figure(go.Sankey(
    arrangement="snap",
    node=dict(
        pad=24, thickness=22, line=dict(color="white", width=1.2),
        label=labels, color=node_colors,
        x=[0.01]*len(OLD_ORDER) + [0.99]*len(NEW_ORDER),
        y=[(i+0.5)/len(OLD_ORDER) for i in range(len(OLD_ORDER))]
          + [(j+0.5)/len(NEW_ORDER) for j in range(len(NEW_ORDER))],
    ),
    link=dict(source=src_idx, target=tgt_idx, value=values, color=link_colors),
))

fig.update_layout(
    title=dict(
        text=f"Women annotation — old binary (human, n={total}) → new 5-tier (Claude)<br>"
             f"<sub>9 previously-tagged editions; arrows colored by destination tier</sub>",
        x=0.5, xanchor="center", font=dict(size=15),
    ),
    font=dict(size=12, family="Arial"),
    margin=dict(l=20, r=20, t=70, b=20),
    height=600, width=1100,
    paper_bgcolor="white",
)

fig.write_html(HTML)
fig.write_image(PNG, scale=2)
print(f"Saved: {PNG}")
print(f"Saved: {HTML}")
print()
print("Flows (old → new, counts):")
for (o, n), v in sorted(flows.items(), key=lambda x: -x[1]):
    print(f"  {o:<15} → {n:<22} {v:>4}")
