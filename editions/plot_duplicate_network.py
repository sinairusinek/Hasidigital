"""
Network graph of inter-edition story duplication.

Reads editions/story-duplicates.tsv (pairs at sim >= 0.99). Each node is an
edition, sized by total #stories in that edition; each edge connects two
editions, weighted by the number of duplicate story pairs between them.

Outputs editions/edition-duplication-network.png.
"""
import os
import sys
import csv
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Authorities", "integration_tool"))
from tag_data import load_stories  # noqa: E402

PAIRS_TSV = os.path.join(HERE, "story-duplicates.tsv")
OUT_PNG = os.path.join(HERE, "edition-duplication-network.png")

# Article-9 editions, in chronological order.
NINE = ["Shivhei-Habesht", "Mifalot-HaZadikim", "Adat-Zadikim", "Shivhei-Harav",
        "Sipurei-Zadikim", "maase-zadikim", "Khal-Kdoshim", "PeerMikdoshim",
        "Khal-Hasidim"]
NINE_SET = set(NINE)

# Edge counts.
edges = Counter()
with open(PAIRS_TSV) as f:
    r = csv.DictReader(f, delimiter="\t")
    for row in r:
        a, b = row["edition_a"], row["edition_b"]
        if a == b:
            continue
        key = tuple(sorted([a, b]))
        edges[key] += 1

# Story counts per edition.
sizes = Counter(s["edition"] for s in load_stories("online"))

# Restrict to editions that participate in any duplicate edge (keeps the graph readable).
participating = set()
for (a, b) in edges:
    participating.add(a); participating.add(b)

G = nx.Graph()
for ed in participating:
    G.add_node(ed, n=sizes.get(ed, 0))
for (a, b), w in edges.items():
    G.add_edge(a, b, weight=w)

# Layout: Khal-Hasidim at center (it's the hub — connects to almost every duplicate),
# other editions arranged on a ring around it, ordered by edge weight so the
# heaviest partners sit closest.
import math
HUB = "Khal-Hasidim"
others = [n for n in G.nodes() if n != HUB]
# Sort by edge weight to HUB (descending), missing edges = 0.
others.sort(key=lambda n: -(G[HUB][n]["weight"] if G.has_edge(HUB, n) else 0))
pos = {HUB: (0.0, 0.0)}
m = len(others)
for i, n in enumerate(others):
    theta = 2 * math.pi * i / m + math.pi / 2  # start at top
    r = 1.0
    pos[n] = (r * math.cos(theta), r * math.sin(theta))

# Drawing.
fig, ax = plt.subplots(figsize=(15, 9))

# Edges scaled by weight.
ews = [G[u][v]["weight"] for u, v in G.edges()]
max_w = max(ews) if ews else 1
edge_widths = [0.4 + 4.0 * (w / max_w) for w in ews]
edge_colors = [plt.cm.viridis(0.15 + 0.7 * (w / max_w)) for w in ews]

nx.draw_networkx_edges(G, pos, width=edge_widths, edge_color=edge_colors,
                       alpha=0.75, ax=ax)

# Edge labels (only on edges with weight >= 2 to reduce clutter).
elabels = {(u, v): G[u][v]["weight"] for u, v in G.edges() if G[u][v]["weight"] >= 2}
nx.draw_networkx_edge_labels(G, pos, edge_labels=elabels, font_size=9,
                             bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                       ec="none", alpha=0.85), ax=ax)

# Nodes sized by #stories; the 9 article editions colored gold, others gray.
node_sizes = [80 + (G.nodes[n]["n"] or 1) * 6 for n in G.nodes()]
node_colors = ["#e6b800" if n in NINE_SET else "#9aa0a6" for n in G.nodes()]
nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=node_colors,
                       edgecolors="black", linewidths=1.0, ax=ax)

# Labels with story counts — placed below each node, except hub which goes above.
for n in G.nodes():
    x, y = pos[n]
    if n == HUB:
        ax.text(x, y + 0.10, f"{n}\n({G.nodes[n]['n']} stories)",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    else:
        # Offset outward radially.
        nx_, ny = x * 0.18 + (0.18 if x >= 0 else -0.18), y * 0.18
        ax.text(x + nx_, y + ny - 0.05, f"{n}\n({G.nodes[n]['n']})",
                ha="center", va="top", fontsize=9)

ax.set_title("Inter-edition story duplication (e5-base cos ≥ 0.99)\n"
             "node size = #stories in edition · edge width/label = #duplicate story pairs",
             fontsize=12)
ax.set_axis_off()
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=160, bbox_inches="tight")
print(f"wrote {OUT_PNG}")

# Also print top edges for the chat.
print("\nTop inter-edition duplication edges:")
for (a, b), w in sorted(edges.items(), key=lambda kv: -kv[1])[:15]:
    print(f"  {w:3d}  {a}  <->  {b}")
