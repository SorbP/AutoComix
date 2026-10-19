"""Creates a small synthetic comic (3 pages, 3 framed panels per page) for the self-test in CI."""
import sys
import zipfile

import cv2
import numpy as np

with zipfile.ZipFile(sys.argv[1], "w") as z:
    for i in range(3):
        img = np.full((1200, 850, 3), 255, np.uint8)
        for x, y, w, h in [(40, 40, 370, 500), (440, 40, 370, 500), (40, 600, 770, 560)]:
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 6)
            cv2.circle(img, (x + w // 2, y + h // 2), min(w, h) // 4, (90, 90, 90), -1)
        z.writestr(f"{i + 1:03d}.png", cv2.imencode(".png", img)[1].tobytes())
