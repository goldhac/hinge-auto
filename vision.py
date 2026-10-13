"""Image-based detection for UI elements whose position varies per profile.

The compose box (Send Like button + comment input) anchors to whichever
element's heart was tapped, so its absolute y coordinate shifts based on
photo height and scroll state. Static COORDS in config don't survive
across profiles — we have to find these elements at tap-time.
"""

import io

import numpy as np
from PIL import Image
from scipy.ndimage import label, find_objects


def _png_to_array(png: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png)).convert("RGB"))


def find_send_like(png: bytes) -> tuple[int, int] | None:
    """Locate the peach 'Send Like' button. Returns (x, y) center or None.

    The button is a wide peach pill (~595x109) sitting on the right side
    of the compose card. Some peach-toned prompt bubbles look similar in
    color and size, so we filter on:
      - width 500-700, height 80-130, area > 30000 (size of the pill)
      - x_center > 500 (Send Like is right-aligned; prompt pills are
        often left-aligned)
    When multiple candidates pass, pick the topmost — the compose card
    sits above any prompt elements visible below it.
    """
    arr = _png_to_array(png)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    peach = (
        (r > 220) & (g > 190) & (g < 235) & (b > 170) & (b < 220)
        & (r > g) & (g > b)
    )
    labeled, _ = label(peach)
    candidates = []
    for i, sl in enumerate(find_objects(labeled), 1):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        h, w = y1 - y0, x1 - x0
        area = (labeled[sl] == i).sum()
        if not (500 < w < 700 and 80 < h < 130 and area > 30000):
            continue
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if cx <= 500:
            continue
        candidates.append((cy, cx))
    if not candidates:
        return None
    candidates.sort()
    cy, cx = candidates[0]
    return (cx, cy)


def find_first_heart(png: bytes) -> tuple[int, int] | None:
    """Locate the heart icon on photo 1 (topmost heart in current view).

    Hinge's heart-on-photo widget is a white circle (~126x126, area ~10900)
    overlaid at the photo's bottom-right corner. Profile layouts vary —
    some have prompt headers above photo 1 ('Me in the wild'), others
    don't — so photo 1's heart y position drifts profile-to-profile.

    Strategy: find white near-circular blobs of the right size, return
    the topmost one (lowest y) since that's photo 1 when scrolled to top.

    Filters tuned to reject clothing false-positives (white dresses, shirts
    can blob-match by raw size). Real Hinge hearts are always:
      - right-aligned (x_center > 800) — the icon sits at the photo's
        bottom-right corner
      - near-circular (|w-h| < 15) — clothing blobs are elongated
      - area >= 8500 — clothing fragments tend to be smaller circular
        regions; the heart's white circle is ~10800-11000 px
    """
    arr = _png_to_array(png)
    mask = (arr[..., 0] > 235) & (arr[..., 1] > 235) & (arr[..., 2] > 235)
    labeled, _ = label(mask)
    hearts = []
    for i, sl in enumerate(find_objects(labeled), 1):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        h, w = y1 - y0, x1 - x0
        area = (labeled[sl] == i).sum()
        if not (100 < h < 140 and 100 < w < 140):
            continue
        if abs(w - h) >= 15:
            continue
        if area < 8500 or area > 12000:
            continue
        cx = (x0 + x1) // 2
        if cx <= 800:
            continue
        cy = (y0 + y1) // 2
        hearts.append((cy, cx))
    if not hearts:
        return _find_dark_heart(arr)
    hearts.sort()
    cy, cx = hearts[0]
    return (cx, cy)


def _find_dark_heart(arr: np.ndarray) -> tuple[int, int] | None:
    """Newer Hinge builds draw the heart as a BLACK ~126px circle with a
    white heart glyph. Over dark hair/clothing the circle merges into the
    photo, so blob sizing fails -- match the shape instead: a fully dark
    ring (r 48-58) around a center with some pure-white glyph pixels.
    Returns the topmost match (photo 1 when scrolled to top).
    """
    gray = arr.max(axis=2)
    dark, white = gray < 60, arr.min(axis=2) > 235
    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    ring = [(np.round(r * np.sin(ang)).astype(int), np.round(r * np.cos(ang)).astype(int))
            for r in (48, 53, 58)]
    gy, gx = np.mgrid[-30:31:3, -30:31:3]
    H, W = gray.shape
    for cy in range(300, H - 60, 3):
        for cx in range(870, min(1000, W - 60), 3):
            if not white[cy - 30:cy + 31, cx - 30:cx + 31].any():
                continue
            if all(dark[cy + dy, cx + dx].mean() > 0.97 for dy, dx in ring):
                frac = white[cy + gy, cx + gx].mean()
                if 0.05 < frac < 0.6:
                    return (cx, cy)
    return None


def comment_field_text_pixels(png: bytes, send_like_xy: tuple[int, int]) -> int:
    """Count dark (text) pixels in the comment input area above Send Like.

    Empty field shows only faint grey placeholder ('Add a comment') — very
    few dark pixels. A filled field has many dark pixels from typed text.
    Used to verify that `adb shell input text` actually landed before
    Send Like fires (events can drop under host CPU contention).
    """
    arr = _png_to_array(png)
    _, sy = send_like_xy
    y0 = max(0, sy - 230)
    y1 = max(0, sy - 60)
    # Span the whole compose card: typed text is left-aligned (x~137),
    # while Send Like can sit right of center, so anchoring on its x
    # missed short messages entirely.
    region = arr[y0:y1, 100:min(arr.shape[1], 980)]
    if region.size == 0:
        return 0
    # < 80 counts typed text but not the grey 'Add a comment' placeholder.
    dark = (region.max(axis=-1) < 80).sum()
    return int(dark)


def find_comment_input(send_like_xy: tuple[int, int]) -> tuple[int, int]:
    """Comment input sits at a fixed offset above the Send Like button.

    Measured offset across two profiles: ~171px above, x ~540 (centered
    in the compose card, not aligned with Send Like). Stable because the
    compose card's internal layout is fixed; only the whole card shifts.
    """
    _, send_y = send_like_xy
    return (540, send_y - 171)


def like_blocked(png: bytes) -> bool:
    """True when Hinge's purple 'Too many people are waiting for your reply'
    sheet is up (8+ matches awaiting a reply blocks all new likes). The sheet
    fills the lower screen in Hinge purple (~103,41,95); normal screens have
    none of that color in this band (the purple nav bar sits below it)."""
    band = _png_to_array(png)[1500:2150].astype(int)
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    purple = (abs(r - 102) < 25) & (abs(g - 40) < 25) & (abs(b - 97) < 30)
    return purple.mean() > 0.5
