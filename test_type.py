"""Type a long string into a compose box and screenshot it, WITHOUT sending.
Verifies adb.input_text completeness. Backs out at the end (no like spent)."""
import time
import adb
import vision

heart = vision.find_first_heart(adb.screenshot())
if heart is None:
    print("no heart on screen"); raise SystemExit
adb.tap(*heart)
time.sleep(2.5)
send = vision.find_send_like(adb.screenshot())
if send is None:
    print("no compose box"); raise SystemExit
comment = vision.find_comment_input(send)
adb.tap(*comment)
time.sleep(1.5)
MSG = "this is a deliberately long test line to verify the full text lands"
print(f"typing {len(MSG)} chars: {MSG!r}")
adb.input_text(MSG)
time.sleep(1.0)
with open("typed_test.png", "wb") as f:
    f.write(adb.screenshot())
print("screenshot saved -> typed_test.png")
# back out without sending (dismiss keyboard + close compose)
adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
time.sleep(0.6)
adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
print("backed out (nothing sent)")
