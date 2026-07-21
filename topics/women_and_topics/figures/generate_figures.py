"""
Generate publication-quality figures for the women × topics article
(Mandel-Edrei, Rusinek, Sagiv) — POST-AUDIT VERSION (2026-07).

Data source: editions/online/*.xml directly (NOT the stale topics TSV).
The XML is the post-audit corpus: RA tags + LLM-audited net additions
(general audit 2026-06, precision audit removals applied 2026-06-30,
commits d5c1891 / 815d694 / f81b07b), with the 5-tier women scheme
(women:{major,catalyst,minor,mention_only}_character spans).

Every figure is generated in TWO variants per the team's decision:
  *_any.{pdf,png}  — "women present" = ANY women tier incl. mention-only
  *_char.{pdf,png} — "women present" = women as CHARACTERS
                     (major + catalyst + minor; mention-only excluded)

Figures (numbered as referenced in the article draft):
  figure_1_per_edition_{any,char}   — % stories with women per edition, Wilson CIs
  figure_2_practice_{any,char}      — women rate across Practice sub-tags
  figure_3_extremes_{any,char}      — ALL tags, the extremes: women-over
                                      (domestic/sexuality) vs women-under
                                      (spiritual elite), economy highlighted

Design (consistent with the previous session's system):
  * Okabe-Ito palette (colorblind-safe, greyscale-legible).
    Role-based, not categorical-identity:
      - bluish green #009E73 = women OVER-represented (above baseline)
      - vermillion   #D55E00 = women UNDER-represented (below baseline)
      - orange       #E69F00 = Shivhei ha-Besht highlight
      - grey         #777777 = neutral/context (achromatic by design)
      - black dashed line     = corpus baseline
    CVD separation of the co-occurring hues validated (worst adjacent
    ΔE 11.0 deutan); every bar carries a direct label, so no encoding is
    color-alone. Economic-cluster bars additionally carry a hatch texture.

Also writes:
  story_tags_post_audit.tsv — the per-story extraction backing the figures
  numbers-for-article.md    — key statistics + text corrections + caveats
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

# white halo so value labels stay legible where they cross the baseline rule
HALO = [pe.withStroke(linewidth=2.5, foreground="white")]

ROOT = Path(__file__).resolve().parents[3]
EDITIONS_DIR = ROOT / "editions" / "online"
OUT = Path(__file__).resolve().parent

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# ---------------------------------------------------------------- palette
C_OVER = "#009E73"      # women over-represented
C_UNDER = "#D55E00"     # women under-represented
C_HILITE = "#E69F00"    # Shivhei ha-Besht
C_NEUTRAL = "#777777"
C_BASELINE = "#000000"

CREDIT = "Hasidigital · hasidic-stories.org"   # set to "" to drop the credit line
SHOW_CREDIT = True

# ---------------------------------------------------------------- style
mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#DDDDDD",
    "grid.linestyle": ":",
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "hatch.linewidth": 0.6,
})

# ---------------------------------------------------------------- corpus
# filename stem -> print name (as in the article's edition list)
CORE_EDITIONS = {
    "Shivhei-Habesht":   ("Shivhei ha-Besht", "Kopys", 1814),
    "Sipurei-Zadikim":   ("Sipurei Tsadikim", "Lemberg", 1864),
    "Shivhei-Harav":     ("Shivhei ha-Rav", "Lemberg", 1864),
    "Adat-Zadikim":      ("Adat Tsadikim", "Lemberg", 1864),
    "maase-zadikim":     ("Ma'ase Tsadikim", "Lemberg", 1864),
    "PeerMikdoshim":     ("Pe'er mi-Kdoshim", "Lemberg", 1865),
    "Khal-Kdoshim":      ("Kehal Kdoshim", "Lemberg", 1865),
    "Mifalot-HaZadikim": ("Mif'alot ha-Tsadikim", "Lemberg", 1866),
    "Khal-Hasidim":      ("Kehal Hasidim", "Warsaw", 1866),
}

TIER_ORDER = [  # highest first
    "women:major_character",
    "women:catalyst_character",
    "women:minor_character",
    "women:mention_only",
]
# canonical top-level categories (filters out the ~50 anomalous singleton tokens
# still awaiting consolidation in the tag-definitions review)
CANON_TOPS = {
    "practice", "social", "characters-and-roles", "ethics-and-emotions",
    "folkloristics", "supernatural", "experience", "times", "spaces",
    "knowledge", "kabbalah", "ritual",
}

ECONOMY_TAGS = {
    "practice:pidyon_nefesh",
    "practice:pidyon_shvuyim",
    "practice:business_advice",
    "social:poverty",
    "ethics-and-emotions:charity",
}

TAG_RENAME = {
    "practice:pidyon_nefesh": "pidyon nefesh",
    "practice:pidyon_shvuyim": "pidyon shvuyim (captives)",
    "practice:pidyon_haben": "pidyon ha-ben",
    "practice:business_advice": "business advice",
    "practice:releasing_agunot": "releasing agunot",
    "practice:coping_with_alien_thoughts": "coping with alien thoughts",
    "practice:recitation_of_psalms": "recitation of psalms",
    "practice:pilgrimage_to_the_graves_of_tsaddikim": "pilgrimage to tsaddikim's graves",
    "practice:use_of_holy_names": "use of holy names",
    "practice:travel_to_the_tsaddik": "travel to the tsaddik",
    "practice:the_travels_of_the_tsaddik": "travels of the tsaddik",
    "practice:travel_to_other_tsaddik": "travel to another tsaddik",
    "practice:reception_of_hasidim": "reception of hasidim",
    "practice:torat_ha_tsaddik": "torat ha-tsaddik",
    "practice:healing_of_the_soul": "healing of the soul",
    "practice:ritual_slaughtering": "ritual slaughtering",
    "practice:sexual_abstinence": "sexual abstinence",
    "practice:writing_amulets": "writing amulets",
    "practice:drinking_alcohol": "drinking alcohol",
    "social:poverty": "poverty",
    "social:marital_relationship": "marital relationship",
    "social:inter_hasidic_master_disciple_relationship": "master–disciple relationship",
    "social:converts_and_conversion": "converts and conversion",
    "social:relations_with_sinners": "relations with sinners",
    "characters-and-roles:agunah": "agunah",
    "characters-and-roles:the_family_of_the_tsaddik": "family of the tsaddik",
    "characters-and-roles:tavern_keeper": "tavern keeper",
    "characters-and-roles:angel_of_death": "angel of death",
    "ethics-and-emotions:resisting_temptation": "resisting temptation",
    "folkloristics:story_type_birth_of_the_tsaddik": "story type: birth of the tsaddik",
    "folkloristics:story_type_death_of_the_tsaddik": "story type: death of the tsaddik",
    "folkloristics:story_type_inauguration": "story type: inauguration",
    "supernatural:contraction_of_the_road": "contraction of the road",
    "supernatural:light_or_fire_as_a_sign_of_righteousness": "light/fire as sign of righteousness",
    "spaces:rabbinical_court": "rabbinical court",
    "spaces:institutions_hassidic_court": "hasidic court",
    "experience:journey_to_heaven": "journey to heaven",
    "times:eschatology": "eschatology",
    "kabbalah": "kabbalah (general)",
}


def pretty(tag: str) -> str:
    if tag in TAG_RENAME:
        return TAG_RENAME[tag]
    sub = tag.split(":", 1)[-1]
    return sub.replace("_", " ")


# ---------------------------------------------------------------- extraction
def extract() -> list[dict]:
    """One record per story: id, edition, tier (0..4), tags(set)."""
    records = []
    for stem in CORE_EDITIONS:
        path = EDITIONS_DIR / f"{stem}.xml"
        root = ET.parse(path).getroot()
        idx = 0
        for div in root.iter(TEI + "div"):
            if div.get("type") != "story":
                continue
            idx += 1
            sid = div.get(XML_ID) or f"{stem}_{idx:04d}"
            tags = set()
            for sp in div.iter(TEI + "span"):
                ana = sp.get("ana") or ""
                tags.update(t.strip() for t in ana.split(";") if t.strip())
            tier = 0
            for rank, t in enumerate(TIER_ORDER):
                if t in tags:
                    tier = len(TIER_ORDER) - rank  # major=4 … mention=1
                    break
            records.append({
                "id": sid, "edition": stem, "tier": tier,
                "tags": {t for t in tags if t.split(":")[0] in CANON_TOPS},
            })
    return records


def women_flag(rec: dict, definition: str) -> int:
    """definition: 'any' (incl. mention-only) or 'char' (excl. mention-only)."""
    return int(rec["tier"] >= (1 if definition == "any" else 2))


DEF_LABEL = {
    "any": "women present = any reference (incl. mention-only)",
    "char": "women present = women as characters (excl. mention-only)",
}


# ---------------------------------------------------------------- helpers
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def tag_table(records: list[dict], definition: str, min_n: int = 5):
    """[(tag, n, k, p)] for tags with >= min_n stories."""
    tag_stories = defaultdict(list)
    for r in records:
        for t in r["tags"]:
            tag_stories[t].append(r)
    rows = []
    for t, rs in tag_stories.items():
        n = len(rs)
        if n < min_n:
            continue
        k = sum(women_flag(r, definition) for r in rs)
        rows.append((t, n, k, k / n))
    return rows


def add_credit(fig: plt.Figure) -> None:
    if SHOW_CREDIT and CREDIT:
        fig.text(0.99, 0.005, CREDIT, ha="right", va="bottom",
                 fontsize=7, color="#999999")


def save(fig: plt.Figure, slug: str) -> None:
    add_credit(fig)
    fig.savefig(OUT / f"{slug}.pdf")
    fig.savefig(OUT / f"{slug}.png", dpi=300)
    plt.close(fig)
    print(f"  wrote {slug}.pdf/.png")


# ================================================================ FIG 1
def fig1_per_edition(records: list[dict], definition: str) -> None:
    rows = []
    for stem, (name, place, year) in CORE_EDITIONS.items():
        rs = [r for r in records if r["edition"] == stem]
        n = len(rs)
        k = sum(women_flag(r, definition) for r in rs)
        lo, hi = wilson_ci(k, n)
        rows.append((stem, name, place, year, n, k, k / n, lo, hi))
    rows.sort(key=lambda r: r[6])
    baseline = sum(women_flag(r, definition) for r in records) / len(records)

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ypos = range(len(rows))
    colors = [C_HILITE if r[0] == "Shivhei-Habesht" else C_NEUTRAL for r in rows]
    ps = [r[6] * 100 for r in rows]
    ax.barh(list(ypos), ps, color=colors, edgecolor="white", height=0.7)
    err_lo = [(r[6] - r[7]) * 100 for r in rows]
    err_hi = [(r[8] - r[6]) * 100 for r in rows]
    ax.errorbar(ps, list(ypos), xerr=[err_lo, err_hi],
                fmt="none", ecolor="#444444", elinewidth=0.8, capsize=2)
    ax.set_yticks(list(ypos))
    ax.set_yticklabels([f"{name}  ({place} {year}, n={n})"
                        for _, name, place, year, n, *_ in rows])
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1,
               label=f"Corpus baseline ({baseline*100:.0f}%)")
    for i, r in enumerate(rows):
        ax.text(r[8] * 100 + 1, i, f"{r[6]*100:.0f}%", va="center", fontsize=9,
                path_effects=HALO)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of stories with women  (Wilson 95% CI)")
    ax.set_title("Stories with women, by edition\n" + DEF_LABEL[definition],
                 fontsize=10.5)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    save(fig, f"figure_1_per_edition_{definition}")


# ================================================================ FIG 2
def fig2_practice(records: list[dict], definition: str, min_n: int = 8) -> None:
    baseline = sum(women_flag(r, definition) for r in records) / len(records)
    rows = [r for r in tag_table(records, definition, min_n)
            if r[0].startswith("practice:")]
    rows.sort(key=lambda r: r[3])

    fig, ax = plt.subplots(figsize=(8.5, 0.32 * len(rows) + 1.8))
    y = range(len(rows))
    for i, (t, n, k, p) in enumerate(rows):
        over = p >= baseline
        ax.barh(i, p * 100,
                color=C_OVER if over else C_UNDER,
                edgecolor="black" if t in ECONOMY_TAGS else "white",
                linewidth=0.9 if t in ECONOMY_TAGS else 0.5,
                hatch="///" if t in ECONOMY_TAGS else "",
                height=0.72)
        ax.text(p * 100 + 1, i, f"{p*100:.0f}%  ({k}/{n})",
                va="center", fontsize=8.5, path_effects=HALO)
    ax.set_yticks(list(y))
    ax.set_yticklabels([pretty(t) for t, *_ in rows], fontsize=9)
    for lbl, (t, *_ ) in zip(ax.get_yticklabels(), rows):
        if t in ECONOMY_TAGS:
            lbl.set_fontweight("bold")
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1)
    ax.set_xlim(0, 112)
    ax.set_xlabel("% of stories on this practice that include women")
    ax.set_title("Women across the practices of Hasidic life\n"
                 + DEF_LABEL[definition], fontsize=10.5)
    handles = [
        mpl.patches.Patch(facecolor=C_OVER, label="above corpus baseline"),
        mpl.patches.Patch(facecolor=C_UNDER, label="below corpus baseline"),
        mpl.patches.Patch(facecolor="#FFFFFF", edgecolor="black",
                          hatch="///", label="economic practice"),
        mpl.lines.Line2D([], [], color=C_BASELINE, ls="--", lw=1,
                         label=f"corpus baseline ({baseline*100:.0f}%)"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.5)
    save(fig, f"figure_2_practice_{definition}")


# ================================================================ FIG 3
def fig3_extremes(records: list[dict], definition: str,
                  min_n: int = 6, k_each: int = 14) -> None:
    """All tags, but the EXTREMES: the most women-loaded vs the least.
    Shows the normative poles (women ↔ domestic/sexuality vs men ↔
    spiritual life) with the economic cluster highlighted between them."""
    baseline = sum(women_flag(r, definition) for r in records) / len(records)
    rows = tag_table(records, definition, min_n)
    rows.sort(key=lambda r: (-r[3], -r[1]))
    top = rows[:k_each]
    bottom = rows[-k_each:]
    in_extremes = {r[0] for r in top} | {r[0] for r in bottom}
    # the economic cluster must stay visible between the poles even when a
    # tag's rate is mid-range (Chen: "בתוך אלו גם רואים את הכלכלה")
    econ_mid = sorted((r for r in rows
                       if r[0] in ECONOMY_TAGS and r[0] not in in_extremes),
                      key=lambda r: -r[3])
    n_omitted = len(rows) - len(top) - len(bottom) - len(econ_mid)

    DIV_ECON = "— the economic cluster, mid-range —"
    shown = top + ([DIV_ECON] + econ_mid if econ_mid else []) \
        + [f"···  {n_omitted} other mid-range topics omitted  ···"] + bottom
    fig, ax = plt.subplots(figsize=(9.0, 0.30 * len(shown) + 2.0))
    ys, labels = [], []
    for i, row in enumerate(shown):
        y = len(shown) - 1 - i
        ys.append(y)
        if isinstance(row, str):      # divider row
            labels.append(row)
            continue
        t, n, k, p = row
        over = p >= baseline
        ax.barh(y, p * 100,
                color=C_OVER if over else C_UNDER,
                edgecolor="black" if t in ECONOMY_TAGS else "white",
                linewidth=0.9 if t in ECONOMY_TAGS else 0.5,
                hatch="///" if t in ECONOMY_TAGS else "",
                height=0.72)
        ax.text(p * 100 + 1, y, f"{p*100:.0f}%  ({k}/{n})",
                va="center", fontsize=8.5, path_effects=HALO)
        labels.append(pretty(t))
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9)
    for lbl, row in zip(ax.get_yticklabels(), shown):
        if isinstance(row, str):
            lbl.set_color("#999999")
            lbl.set_fontstyle("italic")
        elif row[0] in ECONOMY_TAGS:
            lbl.set_fontweight("bold")
    ax.axvline(baseline * 100, color=C_BASELINE, ls="--", lw=1)
    ax.set_xlim(0, 112)
    ax.set_xlabel("% of stories on this topic that include women")
    ax.set_title("The extremes of the topic field: where women are — and are not\n"
                 + DEF_LABEL[definition] + f"  ·  topics with ≥{min_n} stories",
                 fontsize=10.5)
    handles = [
        mpl.patches.Patch(facecolor=C_OVER, label="women over-represented"),
        mpl.patches.Patch(facecolor=C_UNDER, label="women under-represented"),
        mpl.patches.Patch(facecolor="#FFFFFF", edgecolor="black",
                          hatch="///", label="economic cluster"),
        mpl.lines.Line2D([], [], color=C_BASELINE, ls="--", lw=1,
                         label=f"corpus baseline ({baseline*100:.0f}%)"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.5)
    save(fig, f"figure_3_extremes_{definition}")


# ================================================================ data dump
def write_story_tsv(records: list[dict]) -> None:
    path = OUT / "story_tags_post_audit.tsv"
    with path.open("w", encoding="utf-8") as f:
        f.write("story_id\tedition\twomen_tier\ttags\n")
        tier_name = {0: "none", 1: "mention_only", 2: "minor",
                     3: "catalyst", 4: "major"}
        for r in records:
            f.write(f"{r['id']}\t{r['edition']}\t{tier_name[r['tier']]}\t"
                    + "|".join(sorted(r["tags"])) + "\n")
    print(f"  wrote {path.name} ({len(records)} stories)")


# ================================================================ main
def main() -> None:
    print("Extracting from editions/online/*.xml (post-audit corpus) …")
    records = extract()
    n = len(records)
    for d in ("any", "char"):
        k = sum(women_flag(r, d) for r in records)
        print(f"  {n} stories; {d}: {k} with women ({k/n*100:.1f}%)")
    write_story_tsv(records)

    for d in ("any", "char"):
        print(f"— variant {d!r} —")
        fig1_per_edition(records, d)
        fig2_practice(records, d)
        fig3_extremes(records, d)
    print("Done. Outputs in", OUT.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
