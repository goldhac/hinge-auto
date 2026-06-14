"""Fast blind-like mode -- NO Gemini, NO judging, NO 7-frame capture.

For each profile: like photo 1, drop one of the user's premade lines
(rotating), advance. Built to test like+message SUCCESS RATE at speed.

Usage:  python fast_like.py [N]      (default N = 10)
"""
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import adb
import config
import vision

# Just the user's own lines, rotated.
LINES = [p["message"] for p in config.PREMADES]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10

PKG = "co.hinge.app"


def hinge_foreground() -> bool:
    """True if Hinge is the currently resumed (foreground) app."""
    out = (adb._run(["shell", "dumpsys", "activity", "activities"],
                    capture=True) or b"").decode("utf-8", "ignore")
    for line in out.splitlines():
        if "ResumedActivity" in line:
            return PKG in line
    return PKG in out  # fallback: package appears anywhere in the dump


def handle_anr() -> bool:
    """If a system 'X isn't responding' (ANR) dialog is covering the screen,
    tap 'Wait' to keep the app alive and give it time to catch up.

    The ANR dialog window is named 'Application Not Responding: <pkg>', so we
    detect it straight from the window dump. We tap the LOWER button ('Wait',
    ~y1380); biasing low means a misfire misses into dead space rather than
    hitting 'Close app' just above it. Returns True if it acted."""
    out = (adb._run(["shell", "dumpsys", "window", "windows"],
                    capture=True) or b"").decode("utf-8", "ignore")
    if "not responding" in out.lower():
        print("  ! ANR dialog -> tapping Wait, pausing for app to recover")
        adb._run(["shell", "input", "tap", "320", "1380"])
        time.sleep(6)
        return True
    return False


def back_and_guard() -> None:
    """Press BACK, then make sure that didn't bounce us out of Hinge.

    A BACK on certain Hinge screens exits the app entirely (that's how we
    landed in the Play Store last run). After every recovery BACK, confirm
    Hinge is still foreground and relaunch it if not."""
    adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
    time.sleep(0.8)
    if not hinge_foreground():
        print("  ! BACK left Hinge -> relaunching")
        adb._run(["shell", "monkey", "-p", PKG, "-c",
                  "android.intent.category.LAUNCHER", "1"], capture=True)
        time.sleep(8)


adb.check_device()
print(f"FAST mode: {N} profiles, lines={len(LINES)}, NO Gemini.\n")

if not hinge_foreground():
    print("Hinge not foreground at start -> launching")
    adb._run(["shell", "monkey", "-p", PKG, "-c",
              "android.intent.category.LAUNCHER", "1"], capture=True)
    time.sleep(8)

sent = 0
fails = 0
t_start = time.monotonic()

for i in range(N):
    msg = LINES[i % len(LINES)]
    t0 = time.monotonic()
    label = f"[{i+1}/{N}]"
    try:
        # Clear any "isn't responding" dialog first -- the emulator ANRs under
        # load, and a blocking dialog makes every downstream tap useless.
        handle_anr()

        # Make sure we're still in Hinge before doing anything -- an ANR or a
        # stray nav can drop us out between profiles.
        if not hinge_foreground():
            print(f"{label} not in Hinge -> relaunching")
            adb._run(["shell", "monkey", "-p", PKG, "-c",
                      "android.intent.category.LAUNCHER", "1"], capture=True)
            time.sleep(8)

        # New profiles load at the top, so photo 1's heart is already in
        # view -- no scroll-back needed (that's the slow part we skip).
        # A leftover keyboard from the previous message can cover the heart at
        # the photo's bottom-right. One BACK press dismisses the keyboard
        # without exiting the app -- safe to do whenever the IME is shown.
        if "mInputShown=true" in (adb._run(
                ["shell", "dumpsys", "input_method"], capture=True) or b"").decode(
                "utf-8", "ignore"):
            back_and_guard()

        # Photo 1 often loads a beat after the card appears, showing a blank
        # white placeholder. The heart's white circle blends into that white
        # box and detection misses it -- so re-screenshot a few times to let
        # the image render before giving up.
        heart = None
        for attempt in range(4):
            shot = adb.screenshot()
            heart = vision.find_first_heart(shot)
            if heart is not None:
                break
            time.sleep(1.2)
        if heart is None:
            # If a Send Like button is on screen, we're stuck in a leftover
            # compose box (state desync) -- the skip tap won't dismiss it.
            # Press back to close compose and retry the next profile instead.
            if vision.find_send_like(shot) is not None:
                print(f"{label} stuck in compose -> back out")
                back_and_guard()
                adb.jitter_sleep("after_skip"); continue
            fn = f"noheart_{i+1:02d}.png"
            with open(fn, "wb") as fh:
                fh.write(shot)
            print(f"{label} no heart after 4 tries -> skip  (saved {fn})"); fails += 1
            x, y = config.COORDS["skip_button"]; adb.tap(x, y)
            adb.jitter_sleep("after_skip"); continue

        adb.tap(*heart)
        adb.jitter_sleep("after_tap")

        # The compose box renders a beat after the heart tap -- a single
        # screenshot often misses the Send Like button, which then leaves the
        # box open and trips the compose-recovery next round (two lost
        # profiles per miss). Retry to let it appear.
        send = None
        for attempt in range(4):
            send = vision.find_send_like(adb.screenshot())
            if send is not None:
                break
            time.sleep(1.0)
        if send is None:
            # Compose may be open but slow -- back out so it doesn't linger
            # into the next profile (guard relaunches if back exits Hinge).
            print(f"{label} no Send Like after retries -> back out"); fails += 1
            back_and_guard()
            adb.jitter_sleep("after_skip"); continue

        comment = vision.find_comment_input(send)
        adb.tap(*comment)
        adb.jitter_sleep("after_tap")
        adb.input_text(msg)
        time.sleep(2.5)  # let the typed text land
        send = vision.find_send_like(adb.screenshot()) or send
        adb.tap(*send)
        adb.jitter_sleep("after_like_sent")
        sent += 1
        print(f"{label} liked + sent  ({time.monotonic()-t0:.0f}s)  msg: {msg[:35]}")
    except Exception as e:
        print(f"{label} FAIL: {e!r}")
        fails += 1

elapsed = time.monotonic() - t_start
print(f"\nDONE: {sent}/{N} sent, {fails} fails, {elapsed:.0f}s total "
      f"({elapsed/max(N,1):.0f}s/profile)")
