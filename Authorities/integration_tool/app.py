"""
Hasidigital Authority Integration Tool
Main entry point — provides two workflows:
  1. Edition Linker: match unlinked place names in edition XMLs
  2. CSV Integrator: merge CSV/Excel data into the TEI authority XML
"""
import json
import os

import streamlit as st

st.set_page_config(
    page_title="Hasidigital Integration Tool",
    page_icon="\U0001f4dc",
    layout="wide",
)

from config import MATCHING_DB_PATH

# ── Navigation ───────────────────────────────────────────────────────────────

edition_linker = st.Page(
    "pages/edition_linker.py",
    title="Edition Linker",
    icon="\U0001f4d6",
)

csv_integrator = st.Page(
    "pages/csv_integrator.py",
    title="CSV Integrator",
    icon="\U0001f4ca",
)

kima_review = st.Page(
    "pages/kima_review.py",
    title="Kima Review",
    icon="\U0001f5fa\ufe0f",
)

dedup_review = st.Page(
    "pages/dedup_review.py",
    title="Dedup Review",
    icon="\U0001f9f9",
)

ner_annotator = st.Page(
    "pages/ner_annotator.py",
    title="NER Annotator",
    icon="\U0001f3f7\ufe0f",
)

pg = st.navigation(
    {
        "Workflows": [edition_linker, csv_integrator],
        "Review": [kima_review],
        "Annotation": [ner_annotator],
        "Maintenance": [dedup_review],
    }
)


# ── Statistics helper ────────────────────────────────────────────────────────

@st.dialog("Authority Database Statistics", width="large")
def _show_stats():
    """Show a summary report of the matching database."""
    if not os.path.exists(MATCHING_DB_PATH):
        st.error("Matching database not found.")
        return

    with open(MATCHING_DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    places = db.get("places", [])
    persons = db.get("persons", [])

    # ── Entity counts ────────────────────────────────────────────────────
    st.subheader("Entities")
    c1, c2 = st.columns(2)
    c1.metric("Places", len(places))
    c2.metric("Persons", len(persons))

    # ── Variant counts ───────────────────────────────────────────────────
    st.subheader("Name variants")

    place_he = sum(len(p.get("names_he", [])) for p in places)
    place_en = sum(len(p.get("names_en", [])) for p in places)
    person_he = sum(len(p.get("names_he", [])) for p in persons)
    person_en = sum(len(p.get("names_en", [])) for p in persons)

    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Place (he)", place_he)
    v2.metric("Place (en)", place_en)
    v3.metric("Person (he)", person_he)
    v4.metric("Person (en)", person_en)

    # ── External identifiers ─────────────────────────────────────────────
    st.subheader("External identifiers")

    # Normalize keys to title-case for grouping
    def _count_ids(entities):
        counts = {}
        for ent in entities:
            for key in ent.get("identifiers", {}):
                norm = key.strip().title()
                counts[norm] = counts.get(norm, 0) + 1
        return counts

    st.markdown("**Places**")
    place_id_counts = _count_ids(places)
    if place_id_counts:
        for source in sorted(place_id_counts):
            n = place_id_counts[source]
            pct = n / len(places) * 100 if places else 0
            st.markdown(f"- **{source}**: {n}/{len(places)} ({pct:.0f}%)")
    else:
        st.markdown("_No external identifiers_")

    st.markdown("**Persons**")
    person_id_counts = _count_ids(persons)
    if person_id_counts:
        for source in sorted(person_id_counts):
            n = person_id_counts[source]
            pct = n / len(persons) * 100 if persons else 0
            st.markdown(f"- **{source}**: {n}/{len(persons)} ({pct:.0f}%)")
    else:
        st.markdown("_No external identifiers_")

    # ── Duplicate URI check ───────────────────────────────────────────────
    st.subheader("Duplicate URI check")

    def _find_duplicate_uris(entities, entity_label):
        """Find URIs shared by more than one entity. Returns list of warning dicts."""
        # source_key (normalized) -> uri -> [entity ids]
        uri_map = {}
        for ent in entities:
            ent_id = ent.get("id", "?")
            for key, val in ent.get("identifiers", {}).items():
                if not val:
                    continue
                norm_key = key.strip().title()
                uri = str(val).strip()
                uri_map.setdefault(norm_key, {}).setdefault(uri, []).append(ent_id)

        dupes = []
        for source, uri_ids in sorted(uri_map.items()):
            for uri, ids in sorted(uri_ids.items()):
                if len(ids) > 1:
                    dupes.append({
                        "source": source,
                        "uri": uri,
                        "entity_type": entity_label,
                        "ids": ids,
                    })
        return dupes

    place_dupes = _find_duplicate_uris(places, "Place")
    person_dupes = _find_duplicate_uris(persons, "Person")
    all_dupes = place_dupes + person_dupes

    if all_dupes:
        st.warning(f"Found **{len(all_dupes)}** duplicate URI(s)")
        for d in all_dupes:
            ids_str = ", ".join(f"`{i}`" for i in d["ids"])
            st.markdown(
                f"- **{d['source']}** `{d['uri']}`  \n"
                f"  Shared by {d['entity_type'].lower()}s: {ids_str}  \n"
                f"  *Fix: open `Authorities2026-01-14.xml` and remove "
                f"the duplicate `<idno>` from one of these entries, "
                f"or merge the entries if they refer to the same {d['entity_type'].lower()}.*"
            )
    else:
        st.success("No duplicate URIs found.")


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("\U0001f4dc Integration Tool")
    if st.button("\U0001f4ca Statistics", use_container_width=True):
        _show_stats()

pg.run()
