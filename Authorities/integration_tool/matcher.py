"""
Two-pass matching algorithm:
  Pass 1 – identifier matching (Wikidata, Kima, Tsadikim, DiJeStDB)
  Pass 2 – name similarity + optional coordinate proximity
"""
from data_models import PlaceRecord, PersonRecord, BiblRecord, MatchResult
from utils import (
    extract_kima_id, extract_wikidata_qid,
    name_similarity, haversine_km,
)

# Thresholds
NAME_THRESHOLD = 0.55       # Jaccard trigram similarity min for name-only
NAME_THRESHOLD_GEO = 0.35   # Lower name bar when geo is very close
GEO_EXACT_KM = 5.0          # Essentially the same location
GEO_CLOSE_KM = 30.0         # Close enough to boost a name match
GEO_FAR_KM = 100.0          # Beyond this, geo is a negative signal
HIGH_CONF = 0.80             # Above this → auto-accept


def _compute_distance(csv_rec: PlaceRecord, xml_rec: PlaceRecord):
    """Return distance in km or None if either side lacks coordinates."""
    if (csv_rec.lat is not None and csv_rec.lon is not None
            and xml_rec.lat is not None and xml_rec.lon is not None):
        return haversine_km(csv_rec.lat, csv_rec.lon, xml_rec.lat, xml_rec.lon)
    return None


def _distance_label(dist_km) -> str:
    """Human-readable distance string."""
    if dist_km is None:
        return "no coordinates"
    if dist_km < 0.1:
        return "0 km (exact)"
    if dist_km < 1:
        return f"{dist_km * 1000:.0f} m"
    return f"{dist_km:.1f} km"


# ── Places ───────────────────────────────────────────────────────────────────

def match_places(
    csv_records: list[PlaceRecord],
    xml_records: list[PlaceRecord],
) -> list[MatchResult]:
    results = []
    for csv_rec in csv_records:
        result = _match_single_place(csv_rec, xml_records)
        results.append(result)
    return results


def _match_single_place(
    csv_rec: PlaceRecord,
    xml_records: list[PlaceRecord],
) -> MatchResult:
    # ── Pass 1: identifier match ──────────────────────────────────────────
    id_matches = []
    csv_wd = extract_wikidata_qid(csv_rec.wikidata or "")
    csv_kima = extract_kima_id(csv_rec.kima or "")
    csv_tsad = (csv_rec.tsadikim or "").rstrip("/")

    for xml_rec in xml_records:
        xml_wd = extract_wikidata_qid(xml_rec.wikidata or "")
        xml_kima = extract_kima_id(xml_rec.kima or "")
        xml_tsad = (xml_rec.tsadikim or "").rstrip("/")

        matched_by = []
        if csv_wd and xml_wd and csv_wd == xml_wd:
            matched_by.append("Wikidata")
        if csv_kima and xml_kima and csv_kima == xml_kima:
            matched_by.append("Kima")
        if csv_tsad and xml_tsad and csv_tsad == xml_tsad:
            matched_by.append("Tsadikim")

        if matched_by:
            id_matches.append((xml_rec, matched_by))

    if len(id_matches) == 1:
        xml_rec, by = id_matches[0]
        dist = _compute_distance(csv_rec, xml_rec)
        return MatchResult(
            csv_record=csv_rec,
            xml_record=xml_rec,
            status=MatchResult.MATCHED,
            match_method=f"identifier ({', '.join(by)})",
            confidence=1.0,
            distance_km=dist,
        )
    if len(id_matches) > 1:
        ids = [r.xml_id for r, _ in id_matches]
        dist = _compute_distance(csv_rec, id_matches[0][0])
        return MatchResult(
            csv_record=csv_rec,
            xml_record=id_matches[0][0],
            status=MatchResult.CONFLICT,
            match_method="identifier (multiple)",
            confidence=0.9,
            conflict_details=f"Matches multiple XML records: {', '.join(ids)}",
            distance_km=dist,
        )

    # ── Pass 2: name + coordinates ────────────────────────────────────────
    csv_name = csv_rec.primary_name
    csv_has_geo = csv_rec.lat is not None and csv_rec.lon is not None

    # Score each candidate: (combined_score, name_sim, distance_km, xml_rec)
    candidates = []

    for xml_rec in xml_records:
        # Name similarity — check all XML names against CSV name
        name_sim = max(
            (name_similarity(csv_name, xn) for xn in xml_rec.names),
            default=0.0,
        )

        dist = _compute_distance(csv_rec, xml_rec)
        both_have_geo = dist is not None

        # Determine combined score based on name + geo
        if both_have_geo:
            if dist <= GEO_EXACT_KM:
                # Very close: accept even with moderate name similarity
                if name_sim >= NAME_THRESHOLD_GEO:
                    score = min(1.0, name_sim + 0.30)
                else:
                    continue
            elif dist <= GEO_CLOSE_KM:
                if name_sim >= NAME_THRESHOLD:
                    score = min(1.0, name_sim + 0.15)
                else:
                    continue
            elif dist <= GEO_FAR_KM:
                # Moderate distance: name must be good on its own
                if name_sim >= NAME_THRESHOLD:
                    score = name_sim
                else:
                    continue
            else:
                # Far apart: penalise, only keep if name is very strong
                if name_sim >= NAME_THRESHOLD:
                    score = max(0.0, name_sim - 0.15)
                else:
                    continue
        else:
            # No geo available: rely on name alone
            if name_sim >= NAME_THRESHOLD:
                score = name_sim
            else:
                continue

        candidates.append((score, name_sim, dist, xml_rec))

    if not candidates:
        return MatchResult(csv_record=csv_rec, status=MatchResult.NEW, match_method="no match")

    # Pick the best candidate
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_name_sim, best_dist, best_rec = candidates[0]

    # Build details string
    details_parts = [f"name similarity {best_name_sim:.0%}"]
    details_parts.append(f"distance: {_distance_label(best_dist)}")

    if best_score >= HIGH_CONF:
        method = "name+geo" if best_dist is not None else "name"
        return MatchResult(
            csv_record=csv_rec,
            xml_record=best_rec,
            status=MatchResult.MATCHED,
            match_method=method,
            confidence=best_score,
            distance_km=best_dist,
        )

    # Low-confidence → flag as conflict for user review
    method = "name+geo (review)" if best_dist is not None else "name (review)"
    return MatchResult(
        csv_record=csv_rec,
        xml_record=best_rec,
        status=MatchResult.CONFLICT,
        match_method=method,
        confidence=best_score,
        conflict_details=f"{'; '.join(details_parts)} — please verify",
        distance_km=best_dist,
    )


# ── Persons ──────────────────────────────────────────────────────────────────

def match_persons(
    csv_records: list[PersonRecord],
    xml_records: list[PersonRecord],
) -> list[MatchResult]:
    results = []
    for csv_rec in csv_records:
        results.append(_match_single_person(csv_rec, xml_records))
    return results


def _match_single_person(
    csv_rec: PersonRecord,
    xml_records: list[PersonRecord],
) -> MatchResult:
    csv_wd = extract_wikidata_qid(csv_rec.wikidata or "")
    csv_tsad = (csv_rec.tsadikim or "").rstrip("/")
    csv_dij = (csv_rec.dijestdb or "").strip()
    csv_kima = extract_kima_id(csv_rec.kima or "")

    id_matches = []
    for xml_rec in xml_records:
        xml_wd = extract_wikidata_qid(xml_rec.wikidata or "")
        xml_tsad = (xml_rec.tsadikim or "").rstrip("/")
        xml_dij = (xml_rec.dijestdb or "").strip()
        xml_kima = extract_kima_id(xml_rec.kima or "")

        matched_by = []
        if csv_wd and xml_wd and csv_wd == xml_wd:
            matched_by.append("Wikidata")
        if csv_tsad and xml_tsad and csv_tsad == xml_tsad:
            matched_by.append("Tsadikim")
        if csv_dij and xml_dij and csv_dij == xml_dij:
            matched_by.append("DiJeStDB")
        if csv_kima and xml_kima and csv_kima == xml_kima:
            matched_by.append("Kima")

        if matched_by:
            id_matches.append((xml_rec, matched_by))

    if len(id_matches) == 1:
        xml_rec, by = id_matches[0]
        return MatchResult(
            csv_record=csv_rec,
            xml_record=xml_rec,
            status=MatchResult.MATCHED,
            match_method=f"identifier ({', '.join(by)})",
            confidence=1.0,
        )
    if len(id_matches) > 1:
        ids = [r.xml_id for r, _ in id_matches]
        return MatchResult(
            csv_record=csv_rec,
            xml_record=id_matches[0][0],
            status=MatchResult.CONFLICT,
            match_method="identifier (multiple)",
            confidence=0.9,
            conflict_details=f"Matches multiple XML records: {', '.join(ids)}",
        )

    # Pass 2: name similarity
    all_csv_names = csv_rec.names_he + csv_rec.names_en
    best_score = 0.0
    best_rec = None

    for xml_rec in xml_records:
        all_xml_names = xml_rec.names_he + xml_rec.names_en
        sim = max(
            (name_similarity(cn, xn) for cn in all_csv_names for xn in all_xml_names),
            default=0.0,
        )
        if sim > best_score:
            best_score = sim
            best_rec = xml_rec

    if best_rec is None or best_score < NAME_THRESHOLD:
        return MatchResult(csv_record=csv_rec, status=MatchResult.NEW, match_method="no match")

    if best_score >= HIGH_CONF_NAME:
        return MatchResult(
            csv_record=csv_rec,
            xml_record=best_rec,
            status=MatchResult.MATCHED,
            match_method="name",
            confidence=best_score,
        )
    return MatchResult(
        csv_record=csv_rec,
        xml_record=best_rec,
        status=MatchResult.CONFLICT,
        match_method="name (low confidence)",
        confidence=best_score,
        conflict_details=f"Name similarity {best_score:.0%} — please verify",
    )


# ── Bibls ─────────────────────────────────────────────────────────────────────

def match_bibls(
    csv_records: list[BiblRecord],
    xml_records: list[BiblRecord],
) -> list[MatchResult]:
    results = []
    for csv_rec in csv_records:
        results.append(_match_single_bibl(csv_rec, xml_records))
    return results


def _match_single_bibl(
    csv_rec: BiblRecord,
    xml_records: list[BiblRecord],
) -> MatchResult:
    # Match by xml_id if provided
    if csv_rec.xml_id:
        for xml_rec in xml_records:
            if xml_rec.xml_id == csv_rec.xml_id:
                return MatchResult(
                    csv_record=csv_rec,
                    xml_record=xml_rec,
                    status=MatchResult.MATCHED,
                    match_method="xml_id",
                    confidence=1.0,
                )

    # Match by title similarity
    best_score = 0.0
    best_rec = None
    for xml_rec in xml_records:
        sim = name_similarity(csv_rec.title or "", xml_rec.title or "")
        if sim > best_score:
            best_score = sim
            best_rec = xml_rec

    if best_rec and best_score >= 0.85:
        return MatchResult(
            csv_record=csv_rec,
            xml_record=best_rec,
            status=MatchResult.MATCHED,
            match_method="title",
            confidence=best_score,
        )
    return MatchResult(csv_record=csv_rec, status=MatchResult.NEW, match_method="no match")
