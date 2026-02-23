"""
Data models for the Hasidigital authority integration tool.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlaceRecord:
    """Represents a place entity from either XML or CSV."""
    xml_id: Optional[str] = None          # e.g. H-LOC_42
    names: list[str] = field(default_factory=list)  # all placeName values
    lat: Optional[float] = None
    lon: Optional[float] = None
    wikidata: Optional[str] = None        # full URL
    kima: Optional[str] = None            # full URL (may be pipe-separated in CSV)
    tsadikim: Optional[str] = None        # full URL
    jewishgen: Optional[str] = None
    # CSV-only extras preserved for output
    extra: dict = field(default_factory=dict)

    @property
    def primary_name(self) -> str:
        return self.names[0] if self.names else ""


@dataclass
class PersonRecord:
    """Represents a person entity from either XML or CSV."""
    xml_id: Optional[str] = None          # e.g. tempH-42, Tsadik_001.001
    names_he: list[str] = field(default_factory=list)
    names_en: list[str] = field(default_factory=list)
    birth: Optional[str] = None
    death: Optional[str] = None
    wikidata: Optional[str] = None
    tsadikim: Optional[str] = None
    dijestdb: Optional[str] = None
    kima: Optional[str] = None
    jewishgen: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @property
    def primary_name(self) -> str:
        if self.names_he:
            return self.names_he[0]
        if self.names_en:
            return self.names_en[0]
        return ""


@dataclass
class BiblRecord:
    """Represents a bibliographic entity."""
    xml_id: Optional[str] = None          # e.g. H-BIBL_1
    title: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    """The outcome of matching a CSV row to XML records."""
    MATCHED = "matched"
    CONFLICT = "conflict"
    NEW = "new"

    csv_record: object = None             # PlaceRecord / PersonRecord / BiblRecord
    xml_record: object = None             # matched XML record (or None)
    status: str = NEW                     # "matched", "conflict", "new"
    match_method: str = ""                # "identifier", "name+geo", "name"
    confidence: float = 0.0              # 0.0–1.0
    conflict_details: str = ""            # human-readable description
    distance_km: Optional[float] = None  # geographic distance (places only)
    # User resolution (set in Step 3)
    resolution: str = ""                  # "accept", "skip", "new_entity"
    assigned_id: Optional[str] = None    # ID assigned if new_entity
