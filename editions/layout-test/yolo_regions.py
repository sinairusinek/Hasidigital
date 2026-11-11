"""A small YOLO region detector trained on our tags, scored on books it never saw.

The test books are split into two folds; each fold's model is trained on the tagged FINAL pages of every
other book (test-set pages excluded), then predicts its own fold's test pages → xml/<doc>/<page>.yolo.xml.

    python yolo_regions.py data  FOLD    build the dataset (images resized to 1280 px)
    python yolo_regions.py train FOLD    train (Apple GPU)
    python yolo_regions.py predict FOLD  write .yolo.xml for that fold's test pages
Data lives in ~/Documents/Hasidigital-data/ (layout-train/final, layout-train/img, yolo/).
"""
import csv, re, sys, random, shutil
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).parent
DATA = Path.home() / "Documents/Hasidigital-data"
TRAIN = DATA / "layout-train"
CLASSES = ["main-text", "heading", "running-head", "page-number", "catch-word", "footnote"]
MAP = {"footnote-continued": "footnote", "none": "main-text", "paragraph": "main-text", "text": "main-text"}
FOLDS = {1: ["9568035", "9194535", "9194696", "9194695", "6577969", "9194635", "5758447"],
         2: ["9194455", "7125297", "9194435", "9568095", "6705107", "9561376", "15471223", "7627111"]}
SIDE = 1280


def regions(f):
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    pg = root.find(q("Page")); W, H = int(pg.get("imageWidth")), int(pg.get("imageHeight")); out = []
    for r in root.iter(q("TextRegion")):
        m = re.search(r"type:([\w-]+)", r.get("custom", "")); lab = MAP.get(m.group(1) if m else "none", m.group(1) if m else "none")
        c = r.find(q("Coords"))
        if lab not in CLASSES or c is None or not c.get("points"): continue
        pts = [tuple(map(int, xy.split(","))) for xy in c.get("points").split()]
        out.append((lab, min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
    return out, W, H


def build(fold):
    import cv2
    test = {(r["docId"], int(r["pageNr"])) for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t")}
    out = DATA / "yolo" / f"fold{fold}"; shutil.rmtree(out, ignore_errors=True)
    pages = sorted(f for f in (TRAIN / "img").glob("*/*.jpg")
                   if f.parent.name not in FOLDS.get(fold, []) and (f.parent.name, int(f.stem)) not in test)
    random.Random(fold).shuffle(pages); nval = max(20, len(pages) // 10)
    for i, img in enumerate(pages):
        regs, W, H = regions(TRAIN / "final" / img.parent.name / f"{img.stem}.final.xml")
        if not regs: continue
        split = "val" if i < nval else "train"
        (out / "images" / split).mkdir(parents=True, exist_ok=True); (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        im = cv2.imread(str(img)); s = SIDE / max(im.shape[:2])
        cv2.imwrite(str(out / "images" / split / f"{img.parent.name}_{img.stem}.jpg"), cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
        with open(out / "labels" / split / f"{img.parent.name}_{img.stem}.txt", "w") as fh:
            for lab, x0, y0, x1, y1 in regs:
                fh.write(f"{CLASSES.index(lab)} {(x0+x1)/2/W:.5f} {(y0+y1)/2/H:.5f} {(x1-x0)/W:.5f} {(y1-y0)/H:.5f}\n")
    (out / "data.yaml").write_text(f"path: {out}\ntrain: images/train\nval: images/val\nnames: {CLASSES}\n")
    print(fold, len(list((out / 'images/train').glob('*.jpg'))), "train,", len(list((out / 'images/val').glob('*.jpg'))), "val")


def train(fold):
    from ultralytics import YOLO
    YOLO("yolo11n.pt").train(data=str(DATA / "yolo" / f"fold{fold}" / "data.yaml"), imgsz=1024, epochs=50, patience=12,
                             batch=8, device="mps", project=str(DATA / "yolo" / "runs"), name=f"fold{fold}", exist_ok=True,
                             fliplr=0.0, mosaic=0.0, degrees=1.0, scale=0.2, translate=0.05, verbose=False)


PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"><Page imageFilename="{img}" imageWidth="{W}" imageHeight="{H}">
{regions}</Page></PcGts>
"""


def predict(fold, conf=0.25):
    from ultralytics import YOLO
    import cv2
    model = YOLO(str(DATA / "yolo" / "runs" / f"fold{fold}" / "weights" / "best.pt"))
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        if r["docId"] not in FOLDS[fold]: continue
        img = DATA / "layout-test" / r["docId"] / f"{int(r['pageNr']):04d}.jpg"
        im = cv2.imread(str(img)); H, W = im.shape[:2]
        res = model.predict(im, imgsz=1024, conf=conf, device="mps", verbose=False)[0]
        regs = []
        for i, (b, c, s) in enumerate(zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist())):
            x0, y0, x1, y1 = map(int, b)
            regs.append(f'<TextRegion id="y{i}" custom="structure {{type:{CLASSES[int(c)]};score:{s:.2f};}}"><Coords points="{x0},{y0} {x1},{y0} {x1},{y1} {x0},{y1}"/></TextRegion>\n')
        (HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.yolo.xml").write_text(PAGE.format(img=img.name, W=W, H=H, regions="".join(regs)))
    print("predicted fold", fold)


if __name__ == "__main__":
    {"data": build, "train": train, "predict": predict}[sys.argv[1]](int(sys.argv[2]))
