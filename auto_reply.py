"""Reply to every 'Your turn' chat on Hinge, so the 8-waiting reply gate
never blocks likes.

  python auto_reply.py            one pass, then back to Discover
  python auto_reply.py --every 30 a pass every 30 minutes until Ctrl+C

main.py also calls reply_all() by itself when likes get blocked and every
AUTO_REPLY_EVERY likes. Don't run this loop while main.py is running: they
would both drive the same emulator.

Gemini reads a screenshot of each chat and writes one short reply in your
style. If she asks for your number or socials, or to lock in a real
time/place, it does NOT answer: it logs 'needs_you' and leaves that chat for
you. Every reply and flag goes to debug/replies_log.jsonl.
"""

import argparse
import base64
import datetime
import html
import json
import re
import time

from dotenv import load_dotenv

import adb
import config
import hide_matches as hm
from judge_gemini import _client

LOG = "debug/replies_log.jsonl"
MATCHES_TAB, DISCOVER_TAB = (753, 2278), (115, 2277)
NODE = re.compile(r'<node\b[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')

PROMPT = """You are replying for the user (a guy) in a Hinge chat. The screenshot
shows the chat: the match's messages are on the LEFT, his on the RIGHT.
Write his next message, replying to her latest message(s).

Style: all lowercase, casual, short (under 20 words), a little flirty and
playful, and usually end with an easy question so the chat keeps going. No
emoji, no apostrophes, no quotes, no hashtags. Never say you are a bot or AI.
Do not repeat something he already said in the chat. Keep it clean: no
sexual innuendo. Never invent facts about him (places he has been, his job,
his age, his plans); if she asks about his life, flip it back playfully with
a question instead of making something up.

Set needs_you=true and leave reply empty if she asks for his number, socials
or contact details, asks to set a specific date/time/place to meet, says
something serious (upset, safety, money, explicit), or the chat is unreadable.
Light vague talk about hanging out someday is fine to answer.

Answer with JSON only: {"name": "<her name>", "her_last": "<her last message>",
"reply": "<his reply>", "needs_you": false, "why": "<short reason if needs_you>"}"""


def _nodes():
    adb._run(["shell", "uiautomator", "dump", "/sdcard/ar.xml"], capture=True)
    x = adb._run(["shell", "cat", "/sdcard/ar.xml"], capture=True).decode("utf-8", "ignore")
    return [(html.unescape(t), int(a), int(b), int(c), int(d))
            for t, a, b, c, d in NODE.findall(x) if t.strip()]


def _back():
    adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
    time.sleep(1.5)


def _log(**rec):
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **rec}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _clean(text: str) -> str:
    # adb `input text` can't type emoji, and \ " $ ` break the device shell.
    text = text.encode("ascii", "ignore").decode()
    return re.sub(r'[\\"$`\']', "", text).strip()


def _write_reply(png: bytes) -> dict:
    b64 = base64.b64encode(png).decode()
    r = _client().chat.completions.create(
        model=config.GEMINI_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        temperature=0.7,
    )
    raw = r.choices[0].message.content or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"needs_you": True, "why": "model gave no JSON"}
    out = json.loads(m.group(0))
    u = r.usage
    out["tokens"] = [getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0)]
    return out


def _chat_field():
    return next((((a + c) // 2, (b + d) // 2) for t, a, b, c, d in _nodes()
                 if t.startswith("Send a message")), None)


def _reply_open_chat(row_name: str) -> str:
    """Reply in the chat that's open. Returns 'sent', 'needs_you' or 'fail'."""
    if not _chat_field():
        adb.tap(540, 1610)   # 'You matched / View note' card sits over new chats
        time.sleep(2)
        if not _chat_field():
            _log(to=row_name, status="fail", why="no message field")
            return "fail"
    adb.hide_keyboard()
    out = _write_reply(adb.screenshot())
    text = _clean(out.get("reply", ""))
    name = out.get("name") or row_name
    if out.get("needs_you") or not text:
        _log(to=name, status="needs_you", her_last=out.get("her_last"), why=out.get("why"), tokens=out.get("tokens"))
        print(f"  {name}: left for you ({out.get('why')})")
        return "needs_you"

    adb.tap(*_chat_field()); time.sleep(1)
    adb.input_text(text); time.sleep(1)
    typed = [(b + d) // 2 for t, a, b, c, d in _nodes() if t == text]
    if not typed:
        _log(to=name, status="fail", message=text, why="typed text not found; not sent")
        return "fail"
    adb.tap(983, typed[0]); time.sleep(2.5)   # unlabeled send arrow right of the field
    sent = any(t == "Sent" for t, *_ in _nodes())
    _log(to=name, status="sent" if sent else "unconfirmed", her_last=out.get("her_last"),
         message=text, tokens=out.get("tokens"))
    print(f"  {name}: \"{out.get('her_last')}\" -> {text}" + ("" if sent else "  (send unconfirmed)"))
    return "sent" if sent else "fail"


def reply_all(max_chats: int = 15) -> int:
    """Reply to every 'Your turn' chat. Returns how many replies were sent.
    Ends back on the Discover tab."""
    adb.hide_keyboard()
    adb.tap(*MATCHES_TAB); time.sleep(3)
    if hm.your_turn_count() is None:   # off Hinge (a stray BACK can exit it): relaunch
        adb._run(["shell", "monkey", "-p", "co.hinge.app", "-c", "android.intent.category.LAUNCHER", "1"], capture=True)
        time.sleep(8)
        adb.tap(*MATCHES_TAB); time.sleep(3)
    print(f"[auto-reply] your turn: {hm.your_turn_count()}")
    done = set()              # one reply per chat per pass
    sent, passed = 0, set()   # passed = chats left for the user or that failed
    for _ in range(max_chats):
        rows = [r for r in hm._your_turn_rows() if r[0] not in passed and r[0] not in done]
        if not rows:
            break
        name, y = rows[0]
        adb.tap(540, y); time.sleep(3)
        try:
            status = _reply_open_chat(name)
        except Exception as e:
            _log(to=name, status="fail", why=repr(e))
            status = "fail"
        done.add(name)
        if status == "sent":
            sent += 1
        else:
            passed.add(name)
        adb.hide_keyboard(); _back()
        adb.tap(*MATCHES_TAB); time.sleep(2)   # re-anchor on the list (never a 2nd BACK: it can exit Hinge)
    print(f"[auto-reply] sent {sent}, left for you: {sorted(passed) or 'none'}, "
          f"your turn now: {hm.your_turn_count()}")
    adb.tap(*DISCOVER_TAB); time.sleep(4)
    return sent


if __name__ == "__main__":
    load_dotenv(override=True)
    p = argparse.ArgumentParser()
    p.add_argument("--every", type=float, default=0, help="minutes between passes; 0 = one pass")
    a = p.parse_args()
    while True:
        reply_all()
        if not a.every:
            break
        print(f"[auto-reply] next pass in {a.every:g} min")
        time.sleep(a.every * 60)
