#!/usr/bin/env python3
"""Build the Zenodo deposit for the Mandel-Edrei / Rusinek / Sagiv women article.

Assembles:
  topics/women_and_topics/zenodo_deposit/
    data/
      topics_9editions.tsv            -- topics with binary women_in_story from 5-tier (presence-strict)
      women_binary_source.tsv         -- per-story 5-tier -> binary provenance
      editions/<edition>.xml          -- the 9 edition XMLs (post pidyon + 5-tier retag)
    README.md
    CHANGES.md
    zenodo.json

Binary cutoff (presence-strict):
    Yes        = {minor-character, catalyst-character, major-character}
    No Women   = {no-women, mention-only}
    blank/unscored = pass-through original value

Idempotent: regenerate any time after re-running the retag scripts.
"""
from __future__ import annotations
import csv
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPOSIT = REPO / "topics/women_and_topics/zenodo_deposit"
DATA = DEPOSIT / "data"
EDITIONS_OUT = DATA / "editions"

EDITION_XML = {
    "Adat-Zadikim": REPO / "editions/online/Adat-Zadikim.xml",
    "Khal-Hasidim": REPO / "editions/online/Khal-Hasidim.xml",
    "Khal-Kdoshim": REPO / "editions/online/Khal-Kdoshim.xml",
    "Maase-Zadikim": REPO / "editions/online/maase-zadikim.xml",
    "Mifalot-HaZadikim": REPO / "editions/online/Mifalot-HaZadikim.xml",
    "Peer-MiKdoshim": REPO / "editions/online/PeerMikdoshim.xml",
    "Shivhei-Habesht": REPO / "editions/online/Shivhei-Habesht.xml",
    "Shivhei-Harav": REPO / "editions/online/Shivhei-Harav.xml",
    "Sipurei-Zadikim": REPO / "editions/online/Sipurei-Zadikim.xml",
}

# 5-tier file uses different casing/naming for "Maase-Zadikim" and "PeerMikdoshim"
EDITION_5TIER_KEY = {
    "Adat-Zadikim": "Adat-Zadikim",
    "Khal-Hasidim": "Khal-Hasidim",
    "Khal-Kdoshim": "Khal-Kdoshim",
    "maase-zadikim": "Maase-Zadikim",
    "Mifalot-HaZadikim": "Mifalot-HaZadikim",
    "PeerMikdoshim": "Peer-MiKdoshim",
    "Shivhei-Habesht": "Shivhei-Habesht",
    "Shivhei-Harav": "Shivhei-Harav",
    "Sipurei-Zadikim": "Sipurei-Zadikim",
}

YES_TIERS = {"minor-character", "catalyst-character", "major-character"}
NO_TIERS = {"no-women", "mention-only"}


def binary_from_tier(tier: str) -> str | None:
    if tier in YES_TIERS:
        return "Yes"
    if tier in NO_TIERS:
        return "No Women"
    return None


def main():
    EDITIONS_OUT.mkdir(parents=True, exist_ok=True)

    # 1. Load 5-tier source: story_id -> claude_new_5tier
    tier_tsv = REPO / "editions/women-5tier-9editions-full.tsv"
    tier_by_story: dict[str, str] = {}
    binary_by_story: dict[str, str] = {}
    with tier_tsv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sid = row["story_id"].strip()
            tier = (row.get("claude_new_5tier") or "").strip()
            tier_by_story[sid] = tier
            b = binary_from_tier(tier)
            if b:
                binary_by_story[sid] = b

    print(f"Loaded {len(tier_by_story)} 5-tier rows; {len(binary_by_story)} have a binary mapping.")

    # 2. Write provenance TSV
    prov_path = DATA / "women_binary_source.tsv"
    with prov_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["story_id", "claude_new_5tier", "women_in_story_binary"])
        for sid, tier in sorted(tier_by_story.items()):
            w.writerow([sid, tier, binary_from_tier(tier) or ""])
    print(f"Wrote {prov_path.relative_to(REPO)}")

    # 3. Build topics_9editions.tsv: rewrite the women-in-story column from the binary map
    topics_in = REPO / "topics/data/10HasidicEditionsTopics.tsv"
    topics_out = DATA / "topics_9editions.tsv"
    n_rows = 0
    n_rewritten = 0
    n_passthrough = 0
    unmapped_stories: set[str] = set()
    with topics_in.open(encoding="utf-8") as fin, topics_out.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.reader(fin, delimiter="\t")
        writer = csv.writer(fout, delimiter="\t", lineterminator="\n")
        header = next(reader)
        writer.writerow(header)
        # column index for story (3) and women-in-story (7)
        idx_story, idx_women = 3, 7
        for row in reader:
            if len(row) > idx_story:
                sid = row[idx_story]
                if sid in binary_by_story:
                    new_val = binary_by_story[sid]
                    if len(row) > idx_women and row[idx_women] != new_val:
                        row[idx_women] = new_val
                        n_rewritten += 1
                    else:
                        n_passthrough += 1
                else:
                    if sid:
                        unmapped_stories.add(sid)
                    n_passthrough += 1
            writer.writerow(row)
            n_rows += 1
    print(f"Wrote {topics_out.relative_to(REPO)}: {n_rows} rows; rewritten women col on {n_rewritten}; pass-through {n_passthrough}")
    if unmapped_stories:
        print(f"  Stories without 5-tier mapping (left as-is): {len(unmapped_stories)}")

    # 4. Copy edition XMLs into deposit
    for edition_name, src in EDITION_XML.items():
        dst = EDITIONS_OUT / f"{edition_name}.xml"
        shutil.copy2(src, dst)
    print(f"Copied {len(EDITION_XML)} edition XMLs to {EDITIONS_OUT.relative_to(REPO)}")

    # 5. zenodo.json metadata
    metadata = {
        "title": "Women in Hasidic Literature: Between Close and Distant Reading — Dataset",
        "upload_type": "dataset",
        "creators": [
            {"name": "Mandel-Edrei, [given name]", "affiliation": ""},
            {"name": "Rusinek, Sinai", "affiliation": ""},
            {"name": "Sagiv, [given name]", "affiliation": ""},
        ],
        "description": (
            "Annotated TEI XML editions and topic-tag dataset for nine 19th-century Hasidic "
            "hagiographic collections, accompanying the article 'Women in Hasidic Literature: "
            "Between Close and Distant Reading.' Topics are manually curated; the 'women in story' "
            "column is a binary (presence-strict) projection of a five-tier annotation produced "
            "with LLM assistance and human curation. The dataset includes the underlying 5-tier "
            "labels for transparency."
        ),
        "keywords": [
            "Hasidism", "Hasidic stories", "TEI", "digital humanities",
            "gender in literature", "Hebrew", "Yiddish", "topic annotation"
        ],
        "license": "CC-BY-4.0",
        "language": "heb",
        "related_identifiers": [
            {"relation": "isSupplementTo", "identifier": "TBD-article-DOI", "resource_type": "publication-article"}
        ],
        "notes": (
            "Women tags reflect the five-tier scheme; the binary women_in_story column in the TSV "
            "is a presence-strict projection of those labels. See CHANGES.md for details."
        ),
    }
    (DEPOSIT / "zenodo.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {(DEPOSIT/'zenodo.json').relative_to(REPO)}")


if __name__ == "__main__":
    main()
