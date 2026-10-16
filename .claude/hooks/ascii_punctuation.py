#!/usr/bin/env python3
"""Report non-ASCII punctuation in a Python file Claude just wrote, so Claude replaces it.

A PostToolUse hook for Write, Edit and MultiEdit: it reads the hook payload on stdin, checks the
written file and exits 2 with the offending lines on stderr, which Claude Code shows to Claude.
"""

import json
import sys
from pathlib import Path
from typing import Final

_EXIT_CLEAN: Final = 0
_EXIT_REPORT: Final = 2
_SUFFIXES: Final = frozenset({".py", ".pyi"})
_REPLACEMENT_BY_CHARACTER: Final = {
    "\u2190": "<-",
    "\u2192": "->",
    "\u2194": "<->",
    "\u21d2": "=>",
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
}


def main() -> None:
    """Exit 2 with a report when the written Python file holds non-ASCII punctuation."""
    payload = json.load(sys.stdin)
    path = Path(payload.get("tool_input", {}).get("file_path", ""))
    if path.suffix not in _SUFFIXES or not path.is_file():
        sys.exit(_EXIT_CLEAN)

    findings = [
        f"{path}:{line_number}: {character!r} -> {replacement!r}"
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for character, replacement in _REPLACEMENT_BY_CHARACTER.items()
        if character in line
    ]
    if not findings:
        sys.exit(_EXIT_CLEAN)

    print(
        'Write ASCII punctuation; a character a value needs is an escape like "\\u2014".',
        file=sys.stderr,
    )
    print("\n".join(findings), file=sys.stderr)
    sys.exit(_EXIT_REPORT)


if __name__ == "__main__":
    main()
