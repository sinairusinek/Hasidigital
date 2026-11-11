import csv, sys
import numpy as np
from multiprocessing import Pool
from scipy.stats import spearmanr
sys.path.insert(0, ".")
from curl_test import prep, background
def one(r):
    g, bgq, flat, bw = prep(f"calib/{r['docId']}/{int(r['page']):04d}.jpg")
    return background(g, bgq, flat)
R = list(csv.DictReader(open("calib.tsv"), delimiter="\t"))
if __name__ == "__main__":
    with Pool(10) as p: res = p.map(one, R, chunksize=8)
    u = np.array([x[0] for x in res]); s = np.array([x[1] for x in res]); cer = np.array([float(r["cer"]) for r in R])
    lc = np.array([float(r["line_change"]) for r in R])
    print("show: rho CER %+.2f, rho line_change %+.2f; p50 %.3f p90 %.3f p97 %.3f max %.3f" % (spearmanr(s, cer)[0], spearmanr(s, lc)[0], *np.percentile(s, [50, 90, 97]), s.max()))
    print("uneven: rho CER %+.2f; p50 %.3f p90 %.3f p97 %.3f" % (spearmanr(u, cer)[0], *np.percentile(u, [50, 90, 97])))
    for t in (0.08, 0.12, 0.15, 0.2):
        m = s > t
        print(f"show>{t}: {m.sum()} pages, median CER {np.median(cer[m]) if m.any() else float('nan'):.3f} vs {np.median(cer[~m]):.3f}; share>5% {np.mean(cer[m]>.05) if m.any() else float('nan'):.2f} vs {np.mean(cer[~m]>.05):.2f}")
    import collections
    by = collections.defaultdict(list)
    for r, x in zip(R, s): by[r["docId"]].append(x)
    print(sorted(((round(float(np.median(v)), 3), d) for d, v in by.items()), reverse=True)[:8])
