"""Three-way agreement Venn diagram (Human / Claude / Gemini) on women annotation."""
import csv
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib_venn import venn3, venn3_circles

PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                    "editions", "women-annotation-comparison.tsv")
OUT  = os.path.join(os.path.dirname(__file__), "..", "..",
                    "editions", "women-agreement-venn.png")

def near_eq(a, b):
    if a == b: return True
    if a == "major+minor" and b in ("major", "minor"): return True
    if b == "major+minor" and a in ("major", "minor"): return True
    return False

rows = []
with open(PATH, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["claude"] in ("error", "") or r["gemini"] in ("error", ""):
            continue
        rows.append(r)

all_agree = 0
hc_only   = 0   # H==C != G
hg_only   = 0   # H==G != C
cg_only   = 0   # C==G != H
all_diff  = 0
for r in rows:
    h, c, g = r["human"], r["claude"], r["gemini"]
    eq_hc, eq_hg, eq_cg = near_eq(h, c), near_eq(h, g), near_eq(c, g)
    if eq_hc and eq_hg and eq_cg:
        all_agree += 1
    elif eq_hc and not eq_cg:
        hc_only += 1
    elif eq_hg and not eq_cg:
        hg_only += 1
    elif eq_cg and not eq_hc:
        cg_only += 1
    else:
        all_diff += 1

total = len(rows)
print(f"Total: {total}")
print(f"All three agree:                {all_agree}  ({all_agree/total*100:.1f}%)")
print(f"Human=Claude (Gemini differs):  {hc_only}  ({hc_only/total*100:.1f}%)")
print(f"Human=Gemini (Claude differs):  {hg_only}  ({hg_only/total*100:.1f}%)")
print(f"Claude=Gemini (Human differs):  {cg_only}  ({cg_only/total*100:.1f}%)")
print(f"All three differ:               {all_diff}  ({all_diff/total*100:.1f}%)")

# venn3 subset order: (Abc, aBc, ABc, abC, AbC, aBC, ABC)
# A = Human-Claude agreement set
# B = Human-Gemini agreement set
# C = Claude-Gemini agreement set
subsets = (
    hc_only,    # A only           (H=C, ≠G)
    hg_only,    # B only           (H=G, ≠C)
    0,          # A∩B only         impossible
    cg_only,    # C only           (C=G, ≠H)
    0,          # A∩C only         impossible
    0,          # B∩C only         impossible
    all_agree,  # A∩B∩C            all agree
)

fig, ax = plt.subplots(figsize=(10, 8))

v = venn3(
    subsets=subsets,
    set_labels=("Human ∩ Claude", "Human ∩ Gemini", "Claude ∩ Gemini"),
    set_colors=("#4C72B0", "#DD8452", "#55A467"),
    alpha=0.55,
    ax=ax,
)
venn3_circles(subsets=subsets, linestyle="-", linewidth=1.0, color="white", ax=ax)

# Customize labels — bigger center, descriptive captions on petals
def relabel(region_id, text):
    lbl = v.get_label_by_id(region_id)
    if lbl:
        lbl.set_text(text)
        lbl.set_fontsize(11)

# center = "111"
relabel("111", f"All three agree\n{all_agree}\n({all_agree/total*100:.0f}%)")
# A only = "100" (H=C only)
relabel("100", f"H=C\nGemini differs\n{hc_only} ({hc_only/total*100:.0f}%)")
# B only = "010" (H=G only)
relabel("010", f"H=G\nClaude differs\n{hg_only} ({hg_only/total*100:.0f}%)")
# C only = "001" (C=G only)
relabel("001", f"C=G\nHuman differs\n{cg_only} ({cg_only/total*100:.0f}%)")
# Hide impossible pairwise-only regions
for rid in ("110", "101", "011"):
    lbl = v.get_label_by_id(rid)
    if lbl:
        lbl.set_text("")

# Center label larger
center = v.get_label_by_id("111")
if center:
    center.set_fontsize(14)
    center.set_fontweight("bold")

# Title + outside annotation
ax.set_title(
    f"Women annotation agreement — Human vs Claude vs Gemini\n"
    f"({total} stories across 9 annotated editions)",
    fontsize=13, pad=20,
)

# "All three differ" annotation (outside the Venn)
ax.annotate(
    f"All three differ: {all_diff} ({all_diff/total*100:.1f}%)",
    xy=(0.98, 0.02), xycoords="axes fraction",
    ha="right", va="bottom",
    fontsize=10, style="italic",
    bbox=dict(boxstyle="round,pad=0.4", fc="#f5f5f5", ec="#888"),
)

# Pairwise totals as a footer
hc_total = sum(1 for r in rows if near_eq(r["human"], r["claude"]))
hg_total = sum(1 for r in rows if near_eq(r["human"], r["gemini"]))
cg_total = sum(1 for r in rows if near_eq(r["claude"], r["gemini"]))
ax.annotate(
    f"Pairwise agreement —  Human↔Claude: {hc_total/total*100:.0f}%   "
    f"Human↔Gemini: {hg_total/total*100:.0f}%   "
    f"Claude↔Gemini: {cg_total/total*100:.0f}%",
    xy=(0.5, -0.05), xycoords="axes fraction",
    ha="center", va="top", fontsize=10, color="#444",
)

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"\nSaved: {OUT}")
