"""Compare two snapshot folders and report how much of each page changed.

    python e2e/visual_diff.py before after [--save-diffs diffs]
"""

import os
import sys

from PIL import Image, ImageChops

a, b = sys.argv[1], sys.argv[2]
save = sys.argv[sys.argv.index("--save-diffs") + 1] if "--save-diffs" in sys.argv else None
if save:
    os.makedirs(save, exist_ok=True)

worst = 0.0
for name in sorted(os.listdir(a)):
    if not name.endswith(".png") or not os.path.exists(f"{b}/{name}"):
        print(f"{name}: missing in {b}")
        continue
    x, y = Image.open(f"{a}/{name}").convert("RGB"), Image.open(f"{b}/{name}").convert("RGB")
    if x.size != y.size:
        print(f"{name}: size changed {x.size} -> {y.size}")
        worst = max(worst, 100.0)
        continue
    diff = ImageChops.difference(x, y)
    box = diff.getbbox()
    changed = sum(1 for px in diff.convert("L").getdata() if px > 8)
    pct = 100.0 * changed / (x.width * x.height)
    worst = max(worst, pct)
    flag = "" if pct < 0.01 else "  <-- changed"
    print(f"{name}: {pct:.3f}% pixels differ{flag}")
    if save and box:
        diff.point(lambda v: min(255, v * 6)).save(f"{save}/{name}")
print(f"worst page: {worst:.3f}%")
