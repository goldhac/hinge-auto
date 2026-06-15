"""Fast blind-like mode -- NO Gemini, NO judging, NO 7-frame capture.

For each profile: like photo 1, drop one of the user's premade lines
(rotating), advance. Built to test like+message SUCCESS RATE at speed.

All the per-profile logic and the failure-mode guards (ANR, match popup,
reply gate, foreground recovery) live in hinge_helpers, shared with
semi_like.py.

Usage:  python fast_like.py [N]      (default N = 10)
"""
import sys

import hinge_helpers as H

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
H.run_fast(N)
