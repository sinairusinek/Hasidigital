"""
NER pipeline configuration: model names, entity-tag mappings, and constants.
"""

# DictaBERT NER model for Hebrew NER.
# "joint" variant uses a custom .predict() API (trust_remote_code=True).
# "pipeline" variant (e.g. dictabert-large-ner) uses HF pipeline("ner").
MODEL_NAME = "dicta-il/dictabert-joint"
MODEL_TYPE = "joint"   # "joint" | "pipeline"
MAX_TOKENS_PER_CHUNK = 512

# Gemini model for post-correction
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_CHUNK_SIZE = 2000  # characters per Gemini chunk
GEMINI_OVERLAP = 200  # character overlap between chunks
GEMINI_DELAY = 0.5  # seconds between API calls

# XML namespaces
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NAMESPACES = {"tei": TEI_NS}
TEI_XMLID = f"{{{XML_NS}}}id"

# NER entity types recognised by DictaBERT
NER_TYPES = ["PER", "TTL", "TIMEX", "GPE", "ORG", "FAC", "MISC", "LOC"]

# Mapping from NER label to TEI inline tag + attributes
TAGS_DICT = {
    "LOC": {"tag": "placeName", "attr": {}},
    "GPE": {"tag": "placeName", "attr": {}},
    "PER": {"tag": "persName", "attr": {}},
    "ORG": {"tag": "orgName", "attr": {}},
    "TIMEX": {"tag": "date", "attr": {}},
    "WOA": {"tag": "name", "attr": {"type": "work"}},
    "MISC": {"tag": "name", "attr": {"type": "misc"}},
    "EVENT": {"tag": "name", "attr": {"type": "event"}},
}

# Labels to skip (TTL = title, not a standalone entity)
SKIP_LABELS = {"TTL", "FAC"}
