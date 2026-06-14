"""akp mode — like-leaning, paired with the akp flirty voice."""

NAME = "akp"
DESCRIPTION = "Like almost everyone; open in a lowercase flirty-confident voice."

AGE_MIN = None
AGE_MAX = None

# Use the akp voice (voice/akp.py).
MESSAGE_VOICE = "akp"

# Caps come from config.py for this run.
MAX_LIKES_PER_SESSION = None
MAX_PROFILES_PER_SESSION = None

# Verbatim openers the judge may drop instead of writing fresh. Sent
# EXACTLY as written. The lines shipped here are GENERIC placeholders -- put
# your own openers in a gitignored `modes/_akp_local.py` (a `PREMADES` list)
# and they override these automatically, keeping personal lines out of
# version control.
PREMADES = [
    {
        "id": "striking",
        "message": "had to stop scrolling on that first photo",
        "use_when": "Good fit whenever one photo is genuinely striking -- a "
                    "strong portrait or standout pic. Use it freely on those.",
    },
    {
        "id": "funny",
        "message": "something tells me youd win every joke-off we ever had",
        "use_when": "Good fit when her prompts show humor or she reads as "
                    "funny/witty. Use it freely on those profiles.",
    },
]

try:  # personal openers live in a gitignored local file, if it exists
    from modes._akp_local import PREMADES as _LOCAL_PREMADES
    PREMADES = _LOCAL_PREMADES
except ImportError:
    pass

# Like-leaning rubric: default to LIKE, only skip on clear non-starters.
PREFERENCES = """
Default decision: LIKE. The user wants to like almost everyone and open a
conversation. Be generous.

Only SKIP when one of these clearly applies:
  - The profile is obviously fake, a bot, or spam/promotional.
  - The profile is essentially empty (no readable prompts AND only one
    usable photo) so there is nothing to reference in an opener.
  - The profile states an explicit hard dealbreaker about who they want
    (e.g. clearly not seeking the user's gender).

In every other case, decide LIKE and write an opener per the message
rubric. When in doubt, LIKE.

Balance two kinds of openers:
  - The PREMADE lines are the user's favorites -- use them often, on any
    profile where their use_when fits (a striking photo -> the "striking"
    premade; a funny vibe -> the "funny" premade). Lean into them when they
    fit.
  - Otherwise, write a FRESH, profile-specific opener per the message
    rubric. When a premade doesn't naturally fit, always write fresh
    rather than forcing one.
Roughly: reach for a premade when it genuinely fits, write fresh the rest
of the time. Avoid using the same premade on a long unbroken streak.

For reasoning, keep it to one short sentence naming the specific photo or
prompt the opener references.
"""
