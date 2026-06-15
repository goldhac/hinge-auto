"""Unified runner -- pick the run mode.

  python run.py fast  [N]              Blind-like with your premade lines.
                                       Fastest (~17s/profile), no Gemini.

  python run.py semi  [TOTAL] [GEMINI] Hybrid: TOTAL profiles, GEMINI of them
                                       get a fresh Gemini-judged opener, the
                                       rest use your premade lines (interleaved).
                                       Defaults: TOTAL=30, GEMINI=10.

  python run.py judge [N]              Every profile Gemini-judged (custom
                                       opener or skip). Slowest (~85s/profile),
                                       highest quality. Premades stay available.

All modes share the same failure-mode guards (ANR dialogs, match popups,
reply-gate auto-stop, foreground recovery) from hinge_helpers. The persona
(rubric + voice) is whatever config.ACTIVE_MODE points at -- see modes/.

Examples:
  python run.py fast 25
  python run.py semi 50 17
  python run.py judge 20
"""
import sys

import hinge_helpers as H

USAGE = "usage: python run.py {fast|semi|judge} [args]  (see file header)"


def main(argv: list[str]) -> int:
    if not argv:
        print(USAGE)
        return 2
    mode, rest = argv[0].lower(), argv[1:]
    if mode == "fast":
        H.run_fast(int(rest[0]) if rest else 10)
    elif mode == "semi":
        total = int(rest[0]) if len(rest) > 0 else 30
        gemini = int(rest[1]) if len(rest) > 1 else 10
        H.run_semi(total, gemini)
    elif mode == "judge":
        H.run_judge(int(rest[0]) if rest else 10)
    else:
        print(f"unknown mode {mode!r}\n{USAGE}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
