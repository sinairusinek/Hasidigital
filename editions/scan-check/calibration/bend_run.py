import sys
sys.path.insert(0, ".")
from curl_test import prep, line_bend
import cv2, numpy as np
for path in sys.argv[1:]:
    g, bgq, flat, bw = prep(path)
    # line pitch from the row profile
    sm = cv2.resize(bw, (1000, int(bw.shape[0] * 1000 / bw.shape[1])))
    prof = sm.sum(1).astype(float); prof -= prof.mean()
    ac = np.correlate(prof, prof, "full")[len(prof) - 1:]
    pk = [i for i in range(6, 200) if ac[i] > ac[i-1] and ac[i] >= ac[i+1] and ac[i] > .15 * ac[0]]
    pitch = pk[0] * bw.shape[1] / 1000 if pk else 60
    b, n = line_bend(bw, pitch)
    print(path.split("img/")[-1], "bend %.2f lines (%d lines)" % (b, n))
