"""Hide 'Your turn' matches so Hinge stops blocking likes (8+ waiting = blocked).

Run with the Matches tab open:  python hide_matches.py [keep]
Hides from the top of 'Your turn' down, leaving the `keep` most recent rows
(default 2). Hide is reversible (Hidden section). It never taps Unmatch: the
tap lands at x=640, inside Hide and clear of Unmatch (x 323-575), and each
hide is verified by checking the name left the list.

Note: once you're near the limit Hinge may undo hides -- then you have to
reply to (or end) some chats instead.
"""

import re
import sys
import time

import adb


def your_turn_count() -> int | None:
    """Read N from the 'Your turn (N)' header via the UI dump."""
    adb._run(["shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture=True)
    xml = adb._run(["shell", "cat", "/sdcard/ui.xml"], capture=True).decode("utf-8", "ignore")
    m = re.search(r"Your turn \((\d+)\)", xml)
    return int(m.group(1)) if m else (0 if "Their turn" in xml else None)


def _your_turn_rows() -> list[tuple[str, int]]:
    """(name, y) for each visible 'Your turn' row, read from the UI dump.

    Row positions depend on which limit banner Hinge shows (purple 'over',
    grey 'approaching', or none), so locate rows by their name labels
    (left edge x=269) between the 'Your turn' and 'Their turn' headers."""
    adb._run(["shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture=True)
    xml = adb._run(["shell", "cat", "/sdcard/ui.xml"], capture=True).decode("utf-8", "ignore")
    nodes = [(m.group(1), int(m.group(2)), (int(m.group(3)) + int(m.group(5))) // 2)
             for m in re.finditer(r'text="([^"]+)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)]
    top = next((y for t, _, y in nodes if t.startswith("Your turn (")), None)
    end = next((y for t, _, y in nodes if t.startswith(("Their turn (", "Hidden ("))), 2200)
    if top is None:
        return []
    rows, last = [], -999
    for t, x0, y in sorted((n for n in nodes if n[1] == 269), key=lambda n: n[2]):
        if top < y < min(end, 2150) and y - last > 150:   # first label in a row = name
            rows.append((t, y)); last = y
    return rows


def main(keep: int = 2) -> None:
    n = your_turn_count()
    if n is None:
        sys.exit("Open the Matches tab first.")
    print(f"Your turn: {n}, keeping {keep}")
    while n is not None and n > keep:
        rows = _your_turn_rows()
        if len(rows) <= keep:
            print("next row not on screen -- stopping")
            break
        name, y = rows[keep]
        adb.swipe(900, y, 200, y, 300)
        time.sleep(0.8)
        # The swipe menu auto-closes within ~2s, so tap Hide right away.
        # x=640 is inside Hide (x 575-826) and clear of Unmatch (x 323-575).
        adb.tap(640, y)
        time.sleep(2)
        if "Send a message" in adb._run(["shell", "uiautomator", "dump", "/dev/tty"], capture=True).decode("utf-8", "ignore"):
            adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])   # opened a chat instead
            print("tap opened a chat -- stopping for safety")
            break
        # Verify by name, not count: new matches can land mid-run and bump N.
        if name in [t for t, _ in _your_turn_rows()]:
            print(f"hide of {name} didn't take -- stopping for safety")
            break
        n = your_turn_count()
    print(f"Your turn now: {your_turn_count()}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
