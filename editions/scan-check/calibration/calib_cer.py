"""Page CER of PyLaia 52805 against the RA's final text, plus scan measurements for the same page."""
import csv, re, sys, unicodedata
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
from rapidfuzz.distance import Levenshtein
sys.path.insert(0, "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/scan-check")
import scan_checks as sc

def lines(path):
    root = ET.parse(path).getroot()
    ns = root.tag.split("}")[0] + "}"
    out = {}
    for tl in root.iter(ns + "TextLine"):
        u = tl.find(f"{ns}TextEquiv/{ns}Unicode")
        out[tl.get("id")] = re.sub(r"\s+", " ", unicodedata.normalize("NFC", (u.text or "") if u is not None else "")).strip()
    return out

def one(img):
    n = img.stem; d = img.parent
    try:
        h, f = lines(d / f"{n}.htr.xml"), lines(d / f"{n}.final.xml")
    except Exception as e:
        return None
    # line by line on matching ids, so a changed reading order does not count as errors
    common = [i for i in f if i in h]
    ref_len = sum(len(f[i]) for i in common)
    if ref_len < 200: return None
    dist = sum(Levenshtein.distance(h[i], f[i]) for i in common)
    line_change = (len(set(h) ^ set(f))) / max(len(f), 1)   # lines the RA deleted or drew anew
    same_ids = len(set(h) & set(f)) / max(len(f), 1)
    r = sc.analyse((d.name, int(n), img))
    r.pop("dhash", None)
    r.update(cer=dist / ref_len, ref_chars=ref_len, lines_final=len(f), lines_htr=len(h), same_line_ids=round(same_ids, 2), line_change=round(line_change, 3))
    r["flags"] = " ".join(sc.flags(r))
    return r

if __name__ == "__main__":
    imgs = sorted(Path("calib").glob("*/*.jpg"))
    with Pool(10) as p: rows = [r for r in p.map(one, imgs, chunksize=4) if r]
    with open("calib.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t"); w.writeheader(); w.writerows(rows)
    print(len(rows), "pages")
