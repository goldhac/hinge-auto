"""One-off: capture the CURRENT profile, judge it, print the result.
Does NOT like or skip. Safe to run on a live Discover screen.
"""
from dotenv import load_dotenv
load_dotenv()

import time
import config
import adb
from main import capture_profile
from judge_common import load_backend

print(f"device:  {adb.check_device()}")
print(f"backend: {config.JUDGE_BACKEND} ({config.GEMINI_MODEL})")
print(f"mode:    {config.MODE_NAME}")
print("capturing current profile (scrolling through it)...")
frames = capture_profile()
print(f"captured {len(frames)} frames")

judge = load_backend().judge
t = time.monotonic()
d = judge(frames)
dt = time.monotonic() - t

print("\n===== GEMINI DECISION =====")
print(f"name:       {d.name}")
print(f"decision:   {d.decision}  (confidence: {d.confidence})")
print(f"reasoning:  {d.reasoning}")
print(f"message:    {d.message!r}")
print(f"archetype:  {d.message_archetype}")
print(f"skip_reason:{d.skip_reason}")
print(f"prompt_ref: {d.prompt_referenced}")
print(f"latency:    {dt:.1f}s   tokens: {d.usage}")
print("===========================")
print("(no like/skip was performed)")
