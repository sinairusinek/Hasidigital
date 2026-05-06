"""Three visualization options for the Human/Claude/Gemini agreement on women annotation."""
import csv, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle, FancyArrow
from matplotlib_venn import venn3, venn3_circles

PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                    "editions", "women-annotation-comparison.tsv")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "editions")

def near_eq(a, b):
    if a == b: return True
    if a == "major+minor" and b in ("major", "minor"): return True
    if b == "major+minor" and a in ("major", "minor"): return True
    return False

# Load data
rows = []
with open(PATH, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["claude"] in ("error", "") or r["gemini"] in ("error", ""):
            continue
        rows.append(r)
total = len(rows)

# Counts
all_agree = sum(1 for r in rows if near_eq(r["human"], r["claude"]) and near_eq(r["human"], r["gemini"]) and near_eq(r["claude"], r["gemini"]))
hc_only   = sum(1 for r in rows if near_eq(r["human"], r["claude"]) and not near_eq(r["human"], r["gemini"]))
hg_only   = sum(1 for r in rows if near_eq(r["human"], r["gemini"]) and not near_eq(r["claude"], r["gemini"]))
cg_only   = sum(1 for r in rows if near_eq(r["claude"], r["gemini"]) and not near_eq(r["human"], r["claude"]))
all_diff  = total - (all_agree + hc_only + hg_only + cg_only)

# ─────────────────────────────────────────────────────────────────────────────
# OPTION 1: Pairwise-agreement Venn (relabeled to be more explicit)
# ─────────────────────────────────────────────────────────────────────────────
def plot_option_1():
    subsets = (hc_only, hg_only, 0, cg_only, 0, 0, all_agree)
    fig, ax = plt.subplots(figsize=(10, 8.5))
    v = venn3(
        subsets=subsets,
        set_labels=("Human = Claude", "Human = Gemini", "Claude = Gemini"),
        set_colors=("#4C72B0", "#DD8452", "#55A467"),
        alpha=0.55,
        ax=ax,
    )
    venn3_circles(subsets=subsets, linestyle="-", linewidth=1.0, color="white", ax=ax)

    def relabel(rid, text, fs=11, bold=False):
        lbl = v.get_label_by_id(rid)
        if lbl:
            lbl.set_text(text)
            lbl.set_fontsize(fs)
            if bold: lbl.set_fontweight("bold")

    relabel("111", f"All three agree\n{all_agree}\n({all_agree/total*100:.0f}%)", fs=14, bold=True)
    relabel("100", f"H = C\n(Gemini differs)\n{hc_only} ({hc_only/total*100:.0f}%)")
    relabel("010", f"H = G\n(Claude differs)\n{hg_only} ({hg_only/total*100:.0f}%)")
    relabel("001", f"C = G\n(Human differs)\n{cg_only} ({cg_only/total*100:.0f}%)")
    for rid in ("110", "101", "011"):
        lbl = v.get_label_by_id(rid)
        if lbl: lbl.set_text("")

    ax.set_title(
        f"Women annotation agreement — pairwise structure\n"
        f"({total} stories, 9 annotated editions)",
        fontsize=13, pad=20,
    )
    ax.annotate(
        f"All three differ: {all_diff} ({all_diff/total*100:.1f}%)",
        xy=(0.98, 0.02), xycoords="axes fraction",
        ha="right", va="bottom", fontsize=10, style="italic",
        bbox=dict(boxstyle="round,pad=0.4", fc="#f5f5f5", ec="#888"),
    )
    ax.text(0.5, -0.04,
        "Each circle = stories where one pair of annotators gave the same category.\n"
        "Center = all three agree.  Petals = exactly one pair agrees.  Outside = all three differ.",
        ha="center", va="top", transform=ax.transAxes, fontsize=9, color="#555", style="italic",
    )
    out = os.path.join(OUT_DIR, "women-venn-option1-pairwise.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 2: Classical Venn — each circle = "sees women" verdict by that annotator
# ─────────────────────────────────────────────────────────────────────────────
def plot_option_2():
    def sees_women(cat): return cat in ("minor", "major", "major+minor")

    H_set = {i for i, r in enumerate(rows) if sees_women(r["human"])}
    C_set = {i for i, r in enumerate(rows) if sees_women(r["claude"])}
    G_set = {i for i, r in enumerate(rows) if sees_women(r["gemini"])}

    only_H = len(H_set - C_set - G_set)
    only_C = len(C_set - H_set - G_set)
    only_G = len(G_set - H_set - C_set)
    H_C    = len((H_set & C_set) - G_set)
    H_G    = len((H_set & G_set) - C_set)
    C_G    = len((C_set & G_set) - H_set)
    all3   = len(H_set & C_set & G_set)
    none   = total - (only_H + only_C + only_G + H_C + H_G + C_G + all3)

    subsets = (only_H, only_C, H_C, only_G, H_G, C_G, all3)

    fig, ax = plt.subplots(figsize=(10, 8.5))
    v = venn3(
        subsets=subsets,
        set_labels=("Human sees women", "Claude sees women", "Gemini sees women"),
        set_colors=("#4C72B0", "#DD8452", "#55A467"),
        alpha=0.55,
        ax=ax,
    )
    venn3_circles(subsets=subsets, linestyle="-", linewidth=1.0, color="white", ax=ax)

    for rid, n in [("100", only_H), ("010", only_C), ("001", only_G),
                   ("110", H_C), ("101", H_G), ("011", C_G), ("111", all3)]:
        lbl = v.get_label_by_id(rid)
        if lbl:
            pct = f"{n/total*100:.0f}%" if n > 0 else ""
            lbl.set_text(f"{n}\n({pct})" if n else "0")
            lbl.set_fontsize(11)
            if rid == "111":
                lbl.set_fontweight("bold")
                lbl.set_fontsize(13)

    ax.set_title(
        f"Where do the three annotators see women?\n"
        f"(binary view: any category ≠ \"no-women\";  {total} stories)",
        fontsize=13, pad=20,
    )
    ax.annotate(
        f"None of the three see women: {none} ({none/total*100:.1f}%)",
        xy=(0.5, -0.03), xycoords="axes fraction",
        ha="center", va="top", fontsize=10, style="italic",
        bbox=dict(boxstyle="round,pad=0.4", fc="#f5f5f5", ec="#888"),
    )
    out = os.path.join(OUT_DIR, "women-venn-option2-binary.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 3: Concentric bullseye — all-agree at center, disagreement rings outward
# ─────────────────────────────────────────────────────────────────────────────
def plot_option_3():
    # Each ring's area is proportional to its count.
    # Ring i covers radii [r_{i-1}, r_i], area = pi*(r_i^2 - r_{i-1}^2) ∝ count_i.
    rings = [
        ("All three agree",            all_agree, "#4C9A2A"),
        ("Two agree (H=C; G differs)", hc_only,   "#4C72B0"),
        ("Two agree (C=G; H differs)", cg_only,   "#55A467"),
        ("Two agree (H=G; C differs)", hg_only,   "#DD8452"),
        ("All three differ",           all_diff,  "#C44E52"),
    ]
    counts = np.array([r[1] for r in rings], dtype=float)
    cum = np.cumsum(counts)
    total_area = cum[-1]
    radii = np.sqrt(cum / total_area)  # outer radius for each ring (normalized 0..1)

    fig, ax = plt.subplots(figsize=(11, 9))
    inner = 0.0
    for (label, n, color), r_outer in zip(rings, radii):
        wedge = Wedge((0, 0), r_outer, 0, 360, width=r_outer - inner,
                      facecolor=color, edgecolor="white", linewidth=2.5, alpha=0.85)
        ax.add_patch(wedge)
        inner = r_outer

    # Center label
    ax.text(0, 0,
            f"All three\nagree\n{all_agree}\n({all_agree/total*100:.0f}%)",
            ha="center", va="center", fontsize=14, fontweight="bold", color="white")

    # Ring labels (place each at the angular middle of its ring annulus, off to the right)
    inner = 0.0
    angles = [40, 130, 220, 310]  # degrees, where to place the labels for outer rings
    for i, ((label, n, color), r_outer) in enumerate(zip(rings, radii)):
        if i == 0:
            inner = r_outer
            continue
        angle = np.radians(angles[i-1])
        r_mid = (inner + r_outer) / 2
        x = r_mid * np.cos(angle)
        y = r_mid * np.sin(angle)
        # leader line out
        x_label = 1.45 * np.cos(angle)
        y_label = 1.45 * np.sin(angle)
        ax.annotate(
            f"{label}\n{n}  ({n/total*100:.1f}%)",
            xy=(x, y), xytext=(x_label, y_label),
            ha="center", va="center", fontsize=10,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, lw=1.3),
        )
        inner = r_outer

    ax.set_xlim(-1.8, 1.8)
    ax.set_ylim(-1.8, 1.8)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(
        f"Women annotation — concentric agreement rings\n"
        f"(ring area ∝ story count;  {total} total stories)",
        fontsize=13, pad=20,
    )

    out = os.path.join(OUT_DIR, "women-venn-option3-bullseye.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    plot_option_1()
    plot_option_2()
    plot_option_3()
