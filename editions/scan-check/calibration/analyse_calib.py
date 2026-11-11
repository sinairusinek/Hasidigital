import csv, numpy as np, collections
from scipy.stats import spearmanr
R = list(csv.DictReader(open("calib.tsv"), delimiter="\t"))
f = lambda k: np.array([float(r[k]) if r[k] not in ("", "nan") else np.nan for r in R])
cer = f("cer"); same = f("same_line_ids"); ok = np.ones(len(R), bool)
print("pages", len(R), "stable-line pages", ok.sum(), "CER median %.4f mean %.4f p90 %.3f p97 %.3f" % (np.median(cer[ok]), cer[ok].mean(), np.percentile(cer[ok], 90), np.percentile(cer[ok], 97)))
print("share CER==0:", (cer[ok] == 0).mean().round(3), " share >5%:", (cer[ok] > .05).mean().round(3))
for k in ["line_px", "letter_h", "contrast", "sharp", "skew", "warp", "ink", "cut_letters", "stamp", "w"]:
    x = f(k); m = ok & ~np.isnan(x)
    print(f"{k:12s} rho={spearmanr(x[m], cer[m])[0]:+.2f}  p5={np.nanpercentile(x[m],5):.3f} p50={np.nanmedian(x[m]):.3f} p95={np.nanpercentile(x[m],95):.3f}")
fl = collections.defaultdict(list)
for r, c, o in zip(R, cer, ok):
    if o:
        for x in (r["flags"].split() or ["none"]): fl[x].append(c)
for k, v in sorted(fl.items(), key=lambda x: -len(x[1])): print(f"  {k:18s} {len(v):4d} median CER {np.median(v):.3f}  share>5% {np.mean(np.array(v)>.05):.2f}")
