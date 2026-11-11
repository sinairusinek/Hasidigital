import cv2, numpy as np, sys
def prep(path):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE); h, w = g.shape
    q = cv2.resize(g, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    bgq = cv2.medianBlur(cv2.morphologyEx(q, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)), 21)
    bg = cv2.resize(bgq, (w, h))
    flat = np.clip(g.astype(np.float32) / np.maximum(bg, 1) * 255, 0, 255).astype(np.uint8)
    _, bw = cv2.threshold(cv2.GaussianBlur(flat, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return g, bgq, flat, bw

def curl(bw, nstrips=6):
    """Bending of text lines: vertical offset of the row profile between neighbouring vertical strips,
    measured separately in the top, middle and bottom of the page; a straight page (even if skewed) gives
    offsets that change linearly across the page, a curled one does not. Returns the worst deviation from
    linear, in line pitches."""
    h, w = bw.shape
    x0, x1 = int(w * .06), int(w * .94)
    sw = (x1 - x0) // nstrips
    worst = 0.0
    profs_all = []
    for band in range(3):
        y0, y1 = int(h * (.08 + band * .28)), int(h * (.08 + (band + 1) * .28))
        profs = [bw[y0:y1, x0 + i * sw: x0 + (i + 1) * sw].sum(1).astype(float) for i in range(nstrips)]
        ink = [p.sum() for p in profs]
        if min(ink) < 0.02 * 255 * sw * (y1 - y0):   # a strip without text (margin, column gap)
            continue
        # line pitch from the whole band, so the search stays within half a line (evenly spaced lines
        # otherwise match their neighbours and look like a jump of one line)
        full = sum(profs); full = full - full.mean()
        ac = np.correlate(full, full, "full")[len(full) - 1:]
        pk = [i for i in range(8, min(400, len(ac) - 1)) if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > .1 * ac[0]]
        if not pk:
            continue
        lim = max(3, int(pk[0] * .4))
        offs = []
        for a, b in zip(profs, profs[1:]):
            a = a - a.mean(); b = b - b.mean()
            c = np.correlate(a, b, "full"); mid = len(a) - 1
            k = np.argmax(c[mid - lim: mid + lim + 1]) - lim
            offs.append(k)
        offs = np.array(offs, float)
        # cumulative position of a line across strips; remove the straight-line fit (= skew)
        pos = np.concatenate([[0], np.cumsum(offs)])
        x = np.arange(len(pos)); fit = np.polyval(np.polyfit(x, pos, 1), x)
        worst = max(worst, np.abs(pos - fit).max() / pk[0])
    return worst

def background(g, bgq, flat):
    """Unevenness of the paper (spread of the background estimate) and show-through
    (share of mid-grey pixels in the flattened page: faint text from the other side)."""
    inner = bgq[bgq.shape[0]//10: -bgq.shape[0]//10, bgq.shape[1]//10: -bgq.shape[1]//10].astype(float)
    uneven = (np.percentile(inner, 95) - np.percentile(inner, 5)) / max(np.median(inner), 1)
    f = flat[flat.shape[0]//10: -flat.shape[0]//10, flat.shape[1]//10: -flat.shape[1]//10]
    show = ((f > 150) & (f < 225)).mean()
    return uneven, show

if __name__ == "__main__" and False:
  for path in sys.argv[1:]:
    g, bgq, flat, bw = prep(path)
    u, s = background(g, bgq, flat)
    print(path.split("img/")[-1], "curl %.2f lines" % curl(bw), "uneven %.2f" % u, "show %.3f" % s)

def line_bend(bw, pitch_px):
    """Trace each text line (words merged by horizontal smearing), follow the vertical centre of its ink
    along the line, fit a straight line, and measure how far the line's ends leave it, in line pitches.
    Returns the 80th percentile over lines of at least a third of the page width."""
    h, w = bw.shape
    f = 1200 / w
    small = cv2.resize(bw, (1200, int(h * f)), interpolation=cv2.INTER_AREA)
    small = (small > 60).astype(np.uint8)
    pitch = max(6, pitch_px * f)
    smear = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (int(pitch * 1.5), 1)))
    smear = cv2.morphologyEx(smear, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(pitch), 1)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(smear, 8)
    bends = []
    for i in range(1, n):
        x, y, ww, hh, area = st[i]
        if ww < 400 or hh > 2.5 * pitch:
            continue
        m = (lab[y:y + hh, x:x + ww] == i) & (small[y:y + hh, x:x + ww] > 0)
        xs, ys = [], []
        step = 20
        for c0 in range(0, ww - step, step):
            col = m[:, c0:c0 + step]
            if col.sum() < 10:
                continue
            yy = np.nonzero(col)[0]
            xs.append(c0 + step / 2); ys.append(np.median(yy))
        if len(xs) < 8:
            continue
        xs, ys = np.array(xs), np.array(ys)
        mid = (xs > xs.min() + .2 * ww) & (xs < xs.max() - .2 * ww)
        if mid.sum() < 4:
            continue
        fit = np.polyfit(xs[mid], ys[mid], 1)          # straight line through the middle of the line
        res = ys - np.polyval(fit, xs)
        ends = ~mid
        bends.append(np.abs(res[ends]).max() / pitch)
    return (float(np.percentile(bends, 80)), len(bends)) if len(bends) >= 5 else (float("nan"), len(bends))

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "bend":
    pass
