"""
Local multilingual story embeddings for the tag-audit semantic screen.

Long stories are CHUNKED into overlapping ~512-token windows (e5's context limit)
and each chunk is embedded, so tag-relevant content in the middle/end of a long
story is not lost (57% of stories exceed 512 tokens). Similarity of a story to a
tag is the MAX over its chunks, so any single relevant passage flags it.

Model: intfloat/multilingual-e5-base (local, free, good Hebrew). e5 wants a
"passage: " prefix; we treat each chunk as a passage.

Exposes a StoryEmb holding:
  ids         - story ids (order)
  story_mean  - [n, dim] per-story mean-of-chunks (normalized); used for centroids
                and for t-SNE / landscape (one vector per story)
  chunks      - [total_chunks, dim] all chunk vectors (normalized)
  owner       - [total_chunks] index into ids for each chunk
  offsets     - [total_chunks] char offset of each chunk in its story text
"""
import os
import hashlib
import numpy as np

from config import PROJECT_DIR

MODEL_NAME = "intfloat/multilingual-e5-base"
CACHE_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit", ".cache")
CACHE_PATH = os.path.join(CACHE_DIR, "story-chunks-e5base.npz")

CHUNK_CHARS = 1000     # ~ 450-500 Hebrew tokens
CHUNK_OVERLAP = 200

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _chunk(text):
    """Split text into overlapping char windows; returns list of (offset, substr)."""
    text = text or ""
    if len(text) <= CHUNK_CHARS:
        return [(0, text)]
    out, i, step = [], 0, CHUNK_CHARS - CHUNK_OVERLAP
    while i < len(text):
        out.append((i, text[i:i + CHUNK_CHARS]))
        i += step
    return out


class StoryEmb:
    def __init__(self, ids, story_mean, chunks, owner, offsets):
        self.ids = ids
        self.story_mean = story_mean
        self.chunks = chunks
        self.owner = np.asarray(owner)
        self.offsets = np.asarray(offsets)
        # precompute chunk-index groups per story for fast max-pool
        self._groups = [np.where(self.owner == i)[0] for i in range(len(ids))]

    def max_similarities(self, vec):
        """Per-story max cosine of its chunks to vec -> [n]."""
        cs = self.chunks @ vec
        return np.array([cs[g].max() if len(g) else -1.0 for g in self._groups])

    def best_chunk_offset(self, story_index, vec):
        """Char offset of the story's chunk most similar to vec (for excerpts)."""
        g = self._groups[story_index]
        if not len(g):
            return 0
        cs = self.chunks[g] @ vec
        return int(self.offsets[g[int(cs.argmax())]])


def _key(story_ids):
    return hashlib.sha1(("\n".join(story_ids)).encode("utf-8")).hexdigest()


def embed_stories(stories, batch_size=32):
    """Return (ids, StoryEmb). Cached to disk keyed by the story-id set."""
    ids = [s["story_id"] for s in stories]
    key = _key(ids)
    if os.path.exists(CACHE_PATH):
        d = np.load(CACHE_PATH, allow_pickle=True)
        if str(d.get("key")) == key:
            return list(d["ids"]), StoryEmb(list(d["ids"]), d["story_mean"],
                                            d["chunks"], d["owner"], d["offsets"])
    model = _get_model()
    passages, owner, offsets = [], [], []
    for i, s in enumerate(stories):
        for off, sub in _chunk(s["text"]):
            passages.append(f"passage: {sub}")
            owner.append(i)
            offsets.append(off)
    chunks = model.encode(passages, batch_size=batch_size, normalize_embeddings=True,
                          show_progress_bar=True, convert_to_numpy=True).astype("float32")
    owner = np.array(owner)
    dim = chunks.shape[1]
    story_mean = np.zeros((len(ids), dim), dtype="float32")
    for i in range(len(ids)):
        g = np.where(owner == i)[0]
        v = chunks[g].mean(axis=0)
        n = np.linalg.norm(v)
        story_mean[i] = v / n if n else v
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez(CACHE_PATH, key=key, ids=np.array(ids), story_mean=story_mean,
             chunks=chunks, owner=owner, offsets=np.array(offsets))
    return ids, StoryEmb(ids, story_mean, chunks, owner, np.array(offsets))


def centroid(emb_or_mat, idx):
    """L2-normalized centroid of per-story mean vectors at the given indices.
    Accepts a StoryEmb or a plain [n,dim] matrix (back-compat)."""
    mat = emb_or_mat.story_mean if isinstance(emb_or_mat, StoryEmb) else emb_or_mat
    if not len(idx):
        return None
    c = mat[idx].mean(axis=0)
    n = np.linalg.norm(c)
    return c / n if n else c


def similarities(emb_or_mat, vec):
    """Story-to-vec similarity. For StoryEmb this is the MAX over chunks; for a
    plain matrix it's the per-row cosine (back-compat)."""
    if isinstance(emb_or_mat, StoryEmb):
        return emb_or_mat.max_similarities(vec)
    return emb_or_mat @ vec


def smoke_test():
    model = _get_model()
    texts = ["passage: נתן פדיון נפש לצדיק", "passage: the merchant sold his goods"]
    v = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    print("dim", v.shape[1], "sim", round(float(v[0] @ v[1]), 3))


if __name__ == "__main__":
    smoke_test()
