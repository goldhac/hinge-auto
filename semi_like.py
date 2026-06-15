"""Semi (hybrid) mode -- mix fast premade openers with Gemini-judged ones.

Most profiles get a fast blind-like with one of your premade lines; a
fraction get the full Gemini treatment (capture the profile, judge it, write
a custom opener). The two are interleaved so it doesn't run as two obvious
blocks. Stops cleanly if Hinge's reply gate kicks in.

Usage:  python semi_like.py [TOTAL] [GEMINI]
  TOTAL   total profiles            (default 30)
  GEMINI  how many use the Gemini judge; the rest use your premade lines
          (default 10)

Example:  python semi_like.py 30 10   # 20 your-lines + 10 Gemini-judged
"""
import sys

import hinge_helpers as H

TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 30
GEMINI = int(sys.argv[2]) if len(sys.argv) > 2 else 10
H.run_semi(TOTAL, GEMINI)
