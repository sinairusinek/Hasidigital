import csv, sys
from PIL import Image, ImageDraw
rows = list(csv.DictReader(open("/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/scan-check/scan-pages.tsv"), delimiter="\t"))
def sheet(name, picks):
    ims = []
    for doc, pg, label in picks:
        im = Image.open(f"img/{doc}/{int(pg):04d}.jpg").convert("RGB"); im.thumbnail((420, 600))
        c = Image.new("RGB", (430, 630), "white"); c.paste(im, (5, 25)); ImageDraw.Draw(c).text((5, 5), f"{doc} p{pg} {label}"[:70], fill="red"); ims.append(c)
    W = Image.new("RGB", (430 * min(4, len(ims)), 630 * ((len(ims) + 3) // 4)), "white")
    for i, c in enumerate(ims): W.paste(c, ((i % 4) * 430, (i // 4) * 630))
    W.save(f"look/{name}.jpg", quality=80)
def pick(flag, doc=None, n=4):
    return [(r["docId"], r["page"], r["flags"]) for r in rows if flag in r["flags"] and (doc is None or r["docId"] == doc)][:: max(1, len([1 for r in rows if flag in r["flags"] and (doc is None or r["docId"] == doc)]) // n)][:n]
for name, flag, doc in [("cut_w3", "text_cut", "20169720"), ("warp_w6", "warped", "20164512"), ("lsd_w11", "line_spacing", "20153220"),
                        ("dup_150460", "duplicate", "20150460"), ("notext_150584", "no_text", "20150584"), ("blur_150542", "blurred", "20150542"),
                        ("skew_152203", "skewed", "20152203"), ("lowcon", "low_contrast", None)]:
    sheet(name, pick(flag, doc))
