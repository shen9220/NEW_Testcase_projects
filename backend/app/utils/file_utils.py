import re
import os
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Remove unsafe characters from filename."""
    return re.sub(r"[^\w\s\-\.]", "", name).strip().replace(" ", "_")


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def safe_path(base: str, *parts: str) -> str:
    """Join paths and ensure the result is within base."""
    full = os.path.abspath(os.path.join(base, *parts))
    base_abs = os.path.abspath(base)
    if not full.startswith(base_abs):
        raise ValueError(f"Path traversal detected: {full}")
    return full
