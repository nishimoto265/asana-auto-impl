"""Shared directory-name sanitisation logic.

Used by both poll_asana.py (Python) and run_task.sh (via helper script)
to ensure consistent work_dir computation.
"""

import re


def to_safe_dirname(name: str) -> str:
    """Convert a task name to a filesystem-safe directory name.

    Replaces characters that are invalid on common filesystems,
    collapses whitespace and repeated hyphens, and strips leading/trailing hyphens.
    Japanese and other Unicode characters are preserved.
    """
    s = re.sub(r'[/:*?"<>|\\]', "-", name)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")
