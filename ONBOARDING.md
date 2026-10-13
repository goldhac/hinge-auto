# Quick start (Windows, ~45 min)

The short path from a clean Windows PC to your first run. For the full
explanation of modes, backends and calibration, see [README.md](./README.md).

> **Read first.** Automating Hinge breaks its Terms of Service and can get
> the account banned with no appeal. Use a throwaway account. The bot
> sends real likes and messages to real people — start with a dry run.

## 1. Install the tools

Open PowerShell (a normal one, not as Administrator) and run:

```
winget install Python.Python.3.13 Git.Git Google.PlatformTools Google.AndroidStudio
```

Then **close and reopen the terminal** so `python`, `git` and `adb` are on PATH.

Use 64-bit Python. Some dependencies don't ship 32-bit Windows builds.

## 2. Turn on virtualization (one time)

The Android emulator needs Windows Hypervisor Platform. In PowerShell **as
Administrator**:

```
dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart
```

Restart the PC. (Virtualization must also be on in the BIOS; most PCs ship
with it on.)

## 3. Create the emulator

1. Open Android Studio → **More Actions → Virtual Device Manager → +**.
2. Pick **Pixel 10** (or Pixel 9 — same 1080×2424 screen).
3. System image: **API 34, Google Play, x86_64**. Finish.
4. Press ▶ to boot it. In the emulator: Play Store → sign in → install
   **Hinge** → log in → open the **Discover** tab.

Check it's visible:

```
adb devices
```

You should see `emulator-5554   device`.

## 4. Get the code

```
git clone https://github.com/goldhac/hinge-auto.git
cd hinge-auto
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 5. Add an API key

The default judge is **Gemini**. Get a key at
<https://aistudio.google.com/apikey> (pick **Create key in new project** to
get the free tier), then create a `.env` file in the repo folder:

```
GEMINI_API_KEY=AIza...
```

`.env` is git-ignored, so it never gets committed. Prefer Claude? Put
`ANTHROPIC_API_KEY=sk-ant-...` in `.env` and set `JUDGE_BACKEND = "anthropic"`
in `config.py`.

## 6. Set your style (optional)

- **Who to like:** `ACTIVE_MODE` in `config.py`. `akp` likes almost
  everyone; see `modes/` for stricter examples.
- **Your own openers:** create `modes/_akp_local.py` (git-ignored):

  ```python
  PREMADES = [
      {"id": "mine", "message": "your favourite opener here",
       "use_when": "When to use it, in plain English.", "max_uses": 25},
  ]
  ```

## 7. First run — dry run

In `config.py` set `DRY_RUN = True`, then with Hinge open on **Discover**:

```
.venv\Scripts\python main.py
```

It judges profiles and logs the opener it *would* send, without liking or
typing anything. Note that dry run still taps ✕, so those profiles leave your
queue. Check the decisions in `debug/session_log.jsonl`.

## 8. Go live

Set `DRY_RUN = False`. Set how many likes to send per run with
`MAX_LIKES_PER_SESSION` (free Hinge allows about 8 a day; Hinge+ has no cap).
Set `MAX_PROFILES_PER_SESSION` a little higher, because skips count against it.

```
.venv\Scripts\python main.py
```

Each like takes about 70 seconds and costs about $0.01 in API usage.

## 9. The 8-reply limit

When **8 or more** matches are waiting for your reply, Hinge blocks all likes.
The bot detects this, prints `STOPPING`, and exits. To keep going, reply to
those matches, or hide them from the Matches tab:

```
.venv\Scripts\python hide_matches.py 2
```

This hides every "Your turn" chat except the 2 newest (it never unmatches).
Hidden chats come back when they get new activity. Near the limit, Hinge may
undo hides, and then replying is the only way through.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `adb` / `python` "not recognized" | Open a **new** terminal after installing. |
| `adb devices` shows `offline`, or the emulator hangs on boot | Close it and cold-boot: Device Manager → ⋮ → **Cold Boot Now**. |
| `402 ... prepayment credits are depleted` | That Google project is out of credits. Add credits, or make a key in a **new** project. |
| `couldn't find photo-1 heart` on every profile | The Hinge UI or screen size changed. Run `python calibrate.py` (see README). |
| Bot keeps skipping the same screen | A popup or a match notification pulled it off Discover. It retaps Discover by itself; if it's still stuck, go back to Discover yourself and rerun. |
| Run dies after a while | Don't start the emulator from a tool that kills child processes. Launch it from Android Studio or its own terminal. |

Stop the bot any time with **Ctrl+C**.
