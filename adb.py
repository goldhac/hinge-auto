"""Thin wrapper around `adb` commands."""

import random
import shlex
import subprocess
import time

import config


def _run(args: list[str], capture: bool = False) -> bytes | None:
    cmd = ["adb"] + args
    # adb occasionally fails a single call transiently (exit 1 on a swipe)
    # and one hiccup shouldn't kill a whole session -- retry a few times.
    # Never retry `input text`: a partial first attempt would double-type.
    attempts = 1 if "text" in args else 3
    for i in range(attempts):
        try:
            result = subprocess.run(cmd, capture_output=capture, check=True)
            return result.stdout if capture else None
        except subprocess.CalledProcessError:
            if i == attempts - 1:
                raise
            time.sleep(1.0)


def hide_keyboard() -> None:
    """Dismiss the soft keyboard if it's up. Only sends BACK when the IME
    reports shown -- a BACK with no keyboard would close the compose card."""
    out = _run(["shell", "dumpsys", "input_method"], capture=True).decode()
    if "mInputShown=true" in out:
        _run(["shell", "input", "keyevent", "KEYCODE_BACK"])
        time.sleep(0.8)


def check_device() -> str:
    """Raise if no device is connected. Return the serial of the first device."""
    out = _run(["devices"], capture=True).decode()
    lines = [l for l in out.splitlines()[1:] if l.strip() and "\tdevice" in l]
    if not lines:
        raise RuntimeError(
            "No ADB device found. Start your emulator and run `adb devices`."
        )
    return lines[0].split("\t")[0]


def screenshot() -> bytes:
    """Return PNG bytes of the current screen."""
    return _run(["exec-out", "screencap", "-p"], capture=True)


def tap(x: int, y: int) -> None:
    _run(["shell", "input", "tap", str(x), str(y)])


def input_text(text: str) -> None:
    """Type `text` into the currently focused field via `adb shell input text`.

    Types in small chunks with brief pauses. A single `input text` of a long
    string silently drops characters when the device is under load (the host
    emulator stalls and its input buffer overflows), which sent truncated
    openers. Chunking keeps each command small so the buffer keeps up.

    Single-quotes each chunk with shlex so $, `, ", and spaces survive the
    device shell. Caller should keep text plain ASCII — emoji and the chars
    \\ " $ ` should be filtered upstream (the model is instructed to avoid
    them) since `input text` itself only sends keyevents.
    """
    CHUNK = 10
    for i in range(0, len(text), CHUNK):
        piece = text[i:i + CHUNK]
        _run(["shell", f"input text {shlex.quote(piece)}"])
        time.sleep(0.25)


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
    _run(["shell", "input", "swipe",
          str(x1), str(y1), str(x2), str(y2), str(duration_ms)])


def scroll_down() -> None:
    c = config.COORDS
    swipe(*c["scroll_from"], *c["scroll_to"], c["scroll_duration_ms"])


def scroll_up() -> None:
    c = config.COORDS
    swipe(*c["scroll_to"], *c["scroll_from"], c["scroll_duration_ms"])


def jitter_sleep(key: str) -> None:
    lo, hi = config.DELAYS[key]
    time.sleep(random.uniform(lo, hi))
