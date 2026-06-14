"""Diagnostic: dump every white blob find_first_heart considers, with the
reason it was accepted/rejected. Tells us whether a heart is truly absent
or being filtered out by a too-strict threshold.

Usage: python heart_diag.py
"""
import numpy as np
from PIL import Image
from scipy.ndimage import label, find_objects

import adb

png = adb.screenshot()
with open("heart_diag.png", "wb") as f:
    f.write(png)

arr = np.array(Image.open(__import__("io").BytesIO(png)).convert("RGB"))
H, W = arr.shape[:2]
print(f"screen {W}x{H}")

mask = (arr[..., 0] > 235) & (arr[..., 1] > 235) & (arr[..., 2] > 235)
labeled, n = label(mask)
print(f"white blobs total: {n}\n")

rows = []
for i, sl in enumerate(find_objects(labeled), 1):
    if sl is None:
        continue
    y0, y1 = sl[0].start, sl[0].stop
    x0, x1 = sl[1].start, sl[1].stop
    h, w = y1 - y0, x1 - x0
    area = int((labeled[sl] == i).sum())
    if area < 4000:           # ignore tiny specks
        continue
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    reasons = []
    if not (100 < h < 140 and 100 < w < 140):
        reasons.append(f"size h={h} w={w} (need 100-140)")
    if abs(w - h) >= 15:
        reasons.append(f"not square |w-h|={abs(w-h)} (need <15)")
    if area < 8500 or area > 12000:
        reasons.append(f"area={area} (need 8500-12000)")
    if cx <= 800:
        reasons.append(f"x={cx} not right-aligned (need >800)")
    verdict = "HEART" if not reasons else "reject: " + "; ".join(reasons)
    rows.append((cy, cx, w, h, area, verdict))

rows.sort()
for cy, cx, w, h, area, verdict in rows:
    print(f"  blob @ ({cx},{cy})  w={w} h={h} area={area}  -> {verdict}")
if not rows:
    print("  (no white blobs over 4000px at all -> screen is blank/loading)")
