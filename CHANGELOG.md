# Changelog

Changes in this fork (`goldhac/hinge-auto`) relative to upstream
`TerraByte-Dev/hinge-auto`.

## Gemini judge backend

- Added [`judge_gemini.py`](./judge_gemini.py): a third judge backend that
  calls Gemini through its OpenAI-compatible endpoint. Forces the
  `submit_decision` tool so every profile returns a structured decision, and
  falls back from `gemini-2.5-flash` to `gemini-2.5-pro` when flash fails to
  emit a tool call.
- Wired `"gemini"` into [`judge_common.load_backend`](./judge_common.py) and
  added `GEMINI_MODEL` to [`config.py`](./config.py). Reads `GEMINI_API_KEY`
  from `.env`. Roughly 1¢/profile on the flash model.

## Persona: `akp` mode + voice

- [`modes/akp.py`](./modes/akp.py): a like-leaning rubric (default to LIKE,
  only skip clear non-starters) paired with verbatim premade openers.
- [`voice/akp.py`](./voice/akp.py): a lowercase, flirty-confident,
  hyperbolic opener voice.
- `PREMADE_MAX_USES` in `config.py` + de-dup logic in
  [`main.py`](./main.py): caps how many times any single premade opener is
  sent per session, so the judge writes fresh lines once a premade is used
  up instead of spamming the same canned opener.

## `fast_like.py` — blind-like speed mode

A no-LLM mode that likes photo 1 and drops a rotating premade opener, built
to test like+message throughput at speed (`python fast_like.py [N]`). It was
hardened against every failure mode hit during live runs:

- **Photo-load retry** — a freshly loaded card often shows a blank white
  placeholder before the image renders; the heart's white circle blends into
  it and detection misses. Re-screenshots up to 4× to let the photo load.
- **Compose-box recovery** — if a leftover "Send Like" box is open from the
  previous profile, backs out of it instead of tapping into dead space.
- **Stuck-keyboard dismiss** — checks the IME state and dismisses a leftover
  keyboard that would otherwise cover the heart.
- **Foreground guard** — a recovery BACK can exit Hinge entirely; after every
  back-press (and at the top of each profile) it verifies Hinge is still the
  resumed app and relaunches if not. Stops a single stray back from
  cascading out of the app.
- **ANR handling** — detects the system "isn't responding" dialog and taps
  *Wait* to keep the app alive under emulator load.
- **Send-Like retry** — the compose box renders a beat after the heart tap;
  retries the Send-Like detection so a slow box isn't misread as a failure.

Clean runs land 24–25 of 25 profiles liked + messaged.

## Diagnostics

- [`heart_diag.py`](./heart_diag.py): dumps every white blob the heart
  detector considers, with the accept/reject reason — to tell a genuinely
  blank screen apart from a detection miss.
- [`test_dry.py`](./test_dry.py): captures the current profile, runs the
  judge, prints the decision, and likes/skips nothing.

## Tooling

- `.gitignore`: excludes `*.log` (run logs can contain profile text and, if
  tooling echoes it, the API key) and `.claude/`, in addition to the
  existing `.env` / `*.png` / `debug/` rules.
