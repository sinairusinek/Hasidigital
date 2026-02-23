"""
Read CSV or Excel files and convert rows to data model objects,
using a user-supplied column mapping.
"""
import io
from typing import Optional
import pandas as pd
from data_models import PlaceRecord, PersonRecord, BiblRecord
from utils import (
    normalize_wikidata_url, normalize_kima_url,
    normalize_id_type
)


# ── Column mapping schema ────────────────────────────────────────────────────

PLACE_FIELDS = {
    "name":       "Primary name",
    "lat":        "Latitude",
    "lon":        "Longitude",
    "wikidata":   "Wikidata ID / URL",
    "kima":       "Kima ID / URL",
    "tsadikim":   "Tsadikim URL",
    "jewishgen":  "JewishGen URL",
}

PERSON_FIELDS = {
    "name_he":    "Hebrew name",
    "name_en":    "English name",
    "birth":      "Birth year",
    "death":      "Death year",
    "wikidata":   "Wikidata ID / URL",
    "tsadikim":   "Tsadikim URL",
    "dijestdb":   "DiJeStDB ID",
    "kima":       "Kima ID / URL",
    "jewishgen":  "JewishGen URL",
}

BIBL_FIELDS = {
    "title": "Title",
    "xml_id": "ID (H-BIBL_N)",
}

ENTITY_FIELDS = {
    "place": PLACE_FIELDS,
    "person": PERSON_FIELDS,
    "bibl": BIBL_FIELDS,
}


def load_file(uploaded_file) -> pd.DataFrame:
    """
    Accept a Streamlit UploadedFile (CSV, TSV, or Excel) and return a DataFrame.
    Excel is read with openpyxl directly to avoid pandas version requirements.
    """
    name = uploaded_file.name.lower()

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return _load_excel(uploaded_file)

    # Detect TSV vs CSV from extension or sniff delimiter
    raw = uploaded_file.read()
    sep = "\t" if name.endswith(".tsv") or name.endswith(".tab") else None  # None = sniff
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            if sep is not None:
                return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, sep=sep)
            # Sniff: if more tabs than commas in first line, treat as TSV
            first_line = raw.split(b"\n")[0]
            detected_sep = "\t" if first_line.count(b"\t") > first_line.count(b",") else ","
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, sep=detected_sep)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode file — please save as UTF-8.")


def _load_excel(uploaded_file) -> pd.DataFrame:
    """Read Excel using openpyxl directly, returning a DataFrame of strings."""
    import openpyxl
    raw = uploaded_file.read()
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return pd.DataFrame()
    headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    data = [
        [str(cell) if cell is not None else "" for cell in row]
        for row in rows[1:]
    ]
    return pd.DataFrame(data, columns=headers)


def df_to_places(df: pd.DataFrame, mapping: dict[str, str]) -> list[PlaceRecord]:
    """
    Convert a DataFrame to PlaceRecord objects using the column mapping.
    mapping: { field_key -> column_name_in_df }  (missing keys -> skipped)
    """
    records = []
    for _, row in df.iterrows():
        rec = PlaceRecord()

        name_col = mapping.get("name")
        if name_col and name_col in row and pd.notna(row[name_col]):
            rec.names.append(str(row[name_col]).strip())

        lat_col = mapping.get("lat")
        if lat_col and lat_col in row and pd.notna(row[lat_col]):
            try:
                rec.lat = float(row[lat_col])
            except ValueError:
                pass

        lon_col = mapping.get("lon")
        if lon_col and lon_col in row and pd.notna(row[lon_col]):
            try:
                rec.lon = float(row[lon_col])
            except ValueError:
                pass

        wd_col = mapping.get("wikidata")
        if wd_col and wd_col in row and pd.notna(row[wd_col]):
            rec.wikidata = normalize_wikidata_url(str(row[wd_col]))

        kima_col = mapping.get("kima")
        if kima_col and kima_col in row and pd.notna(row[kima_col]):
            # Pipe-separated: use first valid entry
            raw = str(row[kima_col]).strip()
            parts = [p.strip() for p in raw.split("|") if p.strip()]
            if parts:
                rec.kima = normalize_kima_url(parts[0])

        tsad_col = mapping.get("tsadikim")
        if tsad_col and tsad_col in row and pd.notna(row[tsad_col]):
            rec.tsadikim = str(row[tsad_col]).strip()

        jg_col = mapping.get("jewishgen")
        if jg_col and jg_col in row and pd.notna(row[jg_col]):
            rec.jewishgen = str(row[jg_col]).strip()

        # Preserve unmapped columns in extra
        mapped_cols = set(mapping.values())
        for col in df.columns:
            if col not in mapped_cols and pd.notna(row.get(col)):
                rec.extra[col] = str(row[col])

        records.append(rec)
    return records


def df_to_persons(df: pd.DataFrame, mapping: dict[str, str]) -> list[PersonRecord]:
    records = []
    for _, row in df.iterrows():
        rec = PersonRecord()

        def _get(field):
            col = mapping.get(field)
            if col and col in row and pd.notna(row[col]):
                return str(row[col]).strip()
            return None

        he = _get("name_he")
        if he:
            rec.names_he.append(he)
        en = _get("name_en")
        if en:
            rec.names_en.append(en)

        rec.birth = _get("birth")
        rec.death = _get("death")
        rec.wikidata = normalize_wikidata_url(_get("wikidata") or "")
        rec.tsadikim = _get("tsadikim")
        rec.dijestdb = _get("dijestdb")
        kima_raw = _get("kima")
        rec.kima = normalize_kima_url(kima_raw) if kima_raw else None
        rec.jewishgen = _get("jewishgen")

        mapped_cols = set(mapping.values())
        for col in df.columns:
            if col not in mapped_cols and pd.notna(row.get(col)):
                rec.extra[col] = str(row[col])

        records.append(rec)
    return records


def df_to_bibls(df: pd.DataFrame, mapping: dict[str, str]) -> list[BiblRecord]:
    records = []
    for _, row in df.iterrows():
        rec = BiblRecord()

        title_col = mapping.get("title")
        if title_col and title_col in row and pd.notna(row[title_col]):
            rec.title = str(row[title_col]).strip()

        id_col = mapping.get("xml_id")
        if id_col and id_col in row and pd.notna(row[id_col]):
            rec.xml_id = str(row[id_col]).strip()

        records.append(rec)
    return records


def guess_mapping(df_columns: list[str], entity_type: str) -> dict[str, str]:
    """
    Heuristically guess column→field mapping for user convenience.
    Returns {field_key: column_name}.
    """
    fields = ENTITY_FIELDS.get(entity_type, {})
    result = {}
    cols_lower = {c.lower(): c for c in df_columns}

    hints = {
        "name":      ["name", "place", "placename", "toponym"],
        "name_he":   ["name_he", "hebrew", "שם"],
        "name_en":   ["name_en", "english", "name"],
        "lat":       ["lat", "latitude", "y"],
        "lon":       ["lon", "lng", "longitude", "x"],
        "wikidata":  ["wikidata", "wiki", "qid", "q_id"],
        "kima":      ["kima", "kima_id", "kima id"],
        "tsadikim":  ["tsadikim", "tsadik"],
        "jewishgen": ["jewishgen", "jewish gen", "jg"],
        "dijestdb":  ["dijestdb", "dijest", "disjest"],
        "birth":     ["birth", "born", "yob"],
        "death":     ["death", "died", "yod"],
        "title":     ["title", "שם", "כותרת"],
        "xml_id":    ["id", "xml_id", "identifier"],
    }

    for field_key in fields:
        for hint in hints.get(field_key, [field_key]):
            if hint in cols_lower:
                result[field_key] = cols_lower[hint]
                break

    return result
