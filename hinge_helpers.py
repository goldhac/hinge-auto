"""Shared helpers for the Hinge automation runners (fast_like / semi_like).

Two things live here:

1. Guards for the failure modes we hit during live runs -- ANR "isn't
   responding" dialogs, the "You matched with X" modal, Hinge's reply gate,
   and getting bounced out of the app by a stray BACK.
2. Reusable single-profile routines: `fast_like_one` (blind like + premade
   opener) and `judge_one` (full Gemini-judged capture + custom opener),
   plus the `run_fast` / `run_semi` loops that drive them.

Keeping both runners on the same code means a fix to a guard helps both.
"""
import re
import time

from dotenv import load_dotenv
load_dotenv()

import adb
import config
import vision

PKG = "co.hinge.app"


# ---------------------------------------------------------------- guards ----

def hinge_foreground() -> bool:
    """True if Hinge is the currently resumed (foreground) app."""
    out = (adb._run(["shell", "dumpsys", "activity", "activities"],
                    capture=True) or b"").decode("utf-8", "ignore")
    for line in out.splitlines():
        if "ResumedActivity" in line:
            return PKG in line
    return PKG in out  # fallback: package appears anywhere in the dump


def ensure_hinge() -> None:
    """Launch Hinge and wait for it if it isn't the foreground app."""
    if not hinge_foreground():
        print("  Hinge not foreground -> launching")
        adb._run(["shell", "monkey", "-p", PKG, "-c",
                  "android.intent.category.LAUNCHER", "1"], capture=True)
        time.sleep(8)


def handle_anr() -> bool:
    """If a system 'X isn't responding' (ANR) dialog covers the screen, tap
    'Wait' to keep the app alive. The dialog window is named 'Application Not
    Responding: <pkg>', so we detect it from the window dump. We tap the LOWER
    button ('Wait', ~y1380); biasing low means a misfire misses into dead
    space rather than hitting 'Close app' just above it."""
    out = (adb._run(["shell", "dumpsys", "window", "windows"],
                    capture=True) or b"").decode("utf-8", "ignore")
    if "not responding" in out.lower():
        print("  ! ANR dialog -> tapping Wait, pausing for app to recover")
        adb._run(["shell", "input", "tap", "320", "1380"])
        time.sleep(6)
        return True
    return False


def _ui_dump() -> str:
    """Dump the current UI hierarchy as XML (text + bounds per node)."""
    adb._run(["shell", "uiautomator", "dump", "/sdcard/_ui.xml"], capture=True)
    return (adb._run(["shell", "cat", "/sdcard/_ui.xml"],
                     capture=True) or b"").decode("utf-8", "ignore")


def _tap_node_text(xml: str, want: str) -> bool:
    """Tap the center of the first node whose text == want. Reads exact bounds
    from the dump, so no coordinate guessing."""
    for tag in re.findall(r"<node\b[^>]*?>", xml):
        if f'text="{want}"' in tag:
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', tag)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                adb.tap((x1 + x2) // 2, (y1 + y2) // 2)
                return True
    return False


def back_and_guard() -> None:
    """Press BACK, then make sure that didn't bounce us out of Hinge.

    A BACK on certain Hinge screens exits the app entirely. After every
    recovery BACK, confirm Hinge is still foreground and relaunch if not."""
    adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
    time.sleep(0.8)
    if not hinge_foreground():
        print("  ! BACK left Hinge -> relaunching")
        adb._run(["shell", "monkey", "-p", PKG, "-c",
                  "android.intent.category.LAUNCHER", "1"], capture=True)
        time.sleep(8)


def check_overlay() -> str:
    """Inspect the current UI for a known blocking overlay (one dump, both
    checks). Returns:
      'gate'  -- Hinge's reply gate ("too many people waiting for your
                 reply"); likes are blocked, the caller should STOP.
      'match' -- a 'You matched with X' modal; dismissed here (tap Cancel,
                 which does NOT unmatch -- the match stays in the inbox).
      ''      -- nothing recognized/handled.
    """
    xml = _ui_dump()
    low = xml.lower()
    if "waiting for your reply" in low or "waiting for your response" in low:
        return "gate"
    if "matched with" in low or 'text="View note"' in xml:
        for label in ("Cancel", "Close", "Maybe later", "Not now", "No thanks"):
            if _tap_node_text(xml, label):
                print(f"  ! match popup -> dismissed ({label}); match kept in inbox")
                time.sleep(1.5)
                return "match"
        print("  ! match popup (no Cancel button) -> backing out")
        back_and_guard()
        return "match"
    return ""


def _dismiss_leftover_keyboard() -> None:
    """A leftover keyboard from a prior message can cover the heart. One BACK
    dismisses it without exiting the app -- safe whenever the IME is shown."""
    shown = "mInputShown=true" in (adb._run(
        ["shell", "dumpsys", "input_method"], capture=True) or b"").decode(
        "utf-8", "ignore")
    if shown:
        back_and_guard()


# ------------------------------------------------ single-profile routines ----

def fast_like_one(msg: str, idx: int, total: int) -> str:
    """Blind-like the current profile: like photo 1, drop `msg`, advance.
    Returns one of: 'sent', 'gate', 'match', 'skip', 'fail'."""
    label = f"[{idx + 1}/{total}]"
    t0 = time.monotonic()
    try:
        handle_anr()
        ensure_hinge()
        _dismiss_leftover_keyboard()

        # Photo 1 often loads a beat after the card; its heart blends into the
        # white loading placeholder. Re-screenshot a few times before giving up.
        heart = None
        for _ in range(4):
            shot = adb.screenshot()
            heart = vision.find_first_heart(shot)
            if heart is not None:
                break
            time.sleep(1.2)
        if heart is None:
            overlay = check_overlay()
            if overlay == "gate":
                return "gate"
            if overlay == "match":
                adb.jitter_sleep("after_skip")
                return "match"
            if vision.find_send_like(shot) is not None:
                print(f"{label} stuck in compose -> back out")
                back_and_guard()
                adb.jitter_sleep("after_skip")
                return "skip"
            fn = f"noheart_{idx + 1:02d}.png"
            with open(fn, "wb") as fh:
                fh.write(shot)
            print(f"{label} no heart after 4 tries -> skip  (saved {fn})")
            x, y = config.COORDS["skip_button"]
            adb.tap(x, y)
            adb.jitter_sleep("after_skip")
            return "skip"

        adb.tap(*heart)
        adb.jitter_sleep("after_tap")

        # The compose box renders a beat after the heart tap -- retry so a slow
        # box isn't misread as a failure (which would leave it open).
        send = None
        for _ in range(4):
            send = vision.find_send_like(adb.screenshot())
            if send is not None:
                break
            time.sleep(1.0)
        if send is None:
            print(f"{label} no Send Like after retries -> back out")
            back_and_guard()
            adb.jitter_sleep("after_skip")
            return "skip"

        comment = vision.find_comment_input(send)
        adb.tap(*comment)
        adb.jitter_sleep("after_tap")
        adb.input_text(msg)
        time.sleep(2.5)  # let the typed text land
        send = vision.find_send_like(adb.screenshot()) or send
        adb.tap(*send)
        adb.jitter_sleep("after_like_sent")
        print(f"{label} FAST  liked + sent  ({time.monotonic() - t0:.0f}s)  "
              f"msg: {msg[:35]}")
        return "sent"
    except Exception as e:
        print(f"{label} FAST FAIL: {e!r}")
        return "fail"


def judge_one(idx: int, total: int, fresh_only: bool = True) -> str:
    """Full Gemini-judged profile: capture frames, judge, like with a custom
    opener or skip. Returns 'sent', 'gate', 'skip', or 'fail'.

    fresh_only=True hides premades so the judge writes a profile-specific
    opener (used by semi mode, where the fast slots already cover premades).
    fresh_only=False leaves premades available (pure judge mode)."""
    import main as M  # reuse the orchestrator's capture/judge/act helpers
    label = f"[{idx + 1}/{total}]"
    t0 = time.monotonic()
    try:
        handle_anr()
        ensure_hinge()
        overlay = check_overlay()
        if overlay == "gate":
            return "gate"
        # (a 'match' overlay was dismissed in check_overlay; capture proceeds)

        frames = M.capture_profile()
        decision = None
        # In semi mode the Gemini slots exist to produce FRESH, profile-
        # specific openers (the fast slots already cover premades), so hide
        # premades from the judge. In pure judge mode, leave them available.
        saved_premades = config.PREMADES
        if fresh_only:
            config.PREMADES = []
        try:
            for attempt in range(3):
                try:
                    decision = M.judge(frames)
                    break
                except Exception as e:
                    print(f"{label} judge attempt {attempt + 1}/3 failed: {e}")
                    if attempt < 2:
                        time.sleep(4 * (attempt + 1))
        finally:
            config.PREMADES = saved_premades
        if decision is None:
            print(f"{label} GEMINI judge failed 3x -> skip")
            M.do_skip()
            return "skip"

        tail = (decision.message or decision.skip_reason or "")[:45]
        print(f"{label} GEMINI {decision.decision} ({decision.name}) :: {tail}")
        if decision.decision == "like":
            M.do_like(decision.message)
            print(f"  GEMINI liked + sent  ({time.monotonic() - t0:.0f}s)")
            return "sent"
        M.do_skip()
        return "skip"
    except Exception as e:
        print(f"{label} GEMINI FAIL: {e!r}")
        try:
            M.do_skip()
        except Exception:
            pass
        return "fail"


# --------------------------------------------------------------- loops ----

def _premade_lines() -> list[str]:
    """Premade opener messages for the fast slots, each repeated by its
    optional 'weight' (default 1) so better-performing lines come up more
    often in the rotation."""
    out = []
    for p in config.PREMADES:
        out.extend([p["message"]] * max(1, int(p.get("weight", 1))))
    return out or [""]


def _semi_schedule(total: int, gemini: int) -> list[str]:
    """Interleave `gemini` Gemini-judged slots evenly across `total` profiles;
    the rest are fast. For 30/10 this yields a clean 1-in-3 spacing."""
    gemini = max(0, min(gemini, total))
    sched, g = [], 0
    for i in range(total):
        target = (i + 1) * gemini / total
        if g < target and g < gemini:
            sched.append("gemini")
            g += 1
        else:
            sched.append("fast")
    return sched


def run_fast(n: int) -> None:
    adb.check_device()
    lines = _premade_lines()
    print(f"FAST mode: {n} profiles, lines={len(lines)}, NO Gemini.\n")
    ensure_hinge()
    sent = others = 0
    t_start = time.monotonic()
    for i in range(n):
        status = fast_like_one(lines[i % len(lines)], i, n)
        if status == "gate":
            print(f"[{i + 1}/{n}] REPLY GATE -- Hinge blocked likes. Stopping; "
                  f"reply to / end some matches to unlock likes.")
            break
        if status == "sent":
            sent += 1
        else:
            others += 1
    elapsed = time.monotonic() - t_start
    print(f"\nDONE: {sent}/{n} sent, {others} not-sent, {elapsed:.0f}s total "
          f"({elapsed / max(n, 1):.0f}s/profile)")


def run_judge(n: int) -> None:
    adb.check_device()
    print(f"JUDGE mode: {n} profiles, ALL Gemini-judged.\n")
    ensure_hinge()
    sent = skipped = fails = 0
    t_start = time.monotonic()
    for i in range(n):
        status = judge_one(i, n, fresh_only=False)
        if status == "gate":
            print(f"[{i + 1}/{n}] REPLY GATE -- Hinge blocked likes. Stopping; "
                  f"reply to / end some matches to unlock likes.")
            break
        if status == "sent":
            sent += 1
        elif status == "fail":
            fails += 1
        else:
            skipped += 1
    elapsed = time.monotonic() - t_start
    print(f"\nDONE: {sent} liked, {skipped} skipped, {fails} fails over "
          f"{sent + skipped + fails} profiles, {elapsed:.0f}s total.")


def run_semi(total: int, gemini: int) -> None:
    adb.check_device()
    sched = _semi_schedule(total, gemini)
    nfast, ngem = sched.count("fast"), sched.count("gemini")
    print(f"SEMI mode: {total} profiles -> {nfast} FAST (your lines) + "
          f"{ngem} GEMINI-judged, interleaved.\n")
    ensure_hinge()
    lines = _premade_lines()
    sent = skipped = fails = 0
    fast_i = 0
    t_start = time.monotonic()
    for i, kind in enumerate(sched):
        if kind == "fast":
            status = fast_like_one(lines[fast_i % len(lines)], i, total)
            fast_i += 1
        else:
            status = judge_one(i, total)
        if status == "gate":
            print(f"[{i + 1}/{total}] REPLY GATE -- Hinge blocked likes. "
                  f"Stopping; reply to / end some matches to unlock likes.")
            break
        if status == "sent":
            sent += 1
        elif status == "fail":
            fails += 1
        else:  # skip / match
            skipped += 1
    elapsed = time.monotonic() - t_start
    done = sent + skipped + fails
    print(f"\nDONE: {sent} liked, {skipped} skipped, {fails} fails over "
          f"{done} profiles, {elapsed:.0f}s total.")
