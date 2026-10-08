"""`python -m alert TITLE MESSAGE`, or `--failed UNIT` from a systemd OnFailure= hook."""

from __future__ import annotations

import argparse
import subprocess
import sys

from alert import alert

# the end of the unit's log is usually the reason, and a notification has room for a few lines
TAIL = 6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failed", metavar="UNIT", help="a systemd unit that just failed")
    parser.add_argument("title", nargs="?")
    parser.add_argument("message", nargs="?", default="")
    args = parser.parse_args(argv)

    if args.failed:
        tail = subprocess.run(
            ["journalctl", "--unit", args.failed, "--lines", str(TAIL), "--no-pager", "--output", "cat"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        alert(f"{args.failed} failed", tail or "no log lines", urgent=True)
        return 0
    if not args.title:
        parser.error("a title, or --failed UNIT")
    alert(args.title, args.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
