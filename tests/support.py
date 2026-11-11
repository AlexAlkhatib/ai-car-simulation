"""Utilitaires partagés par les tests."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEAT_CONFIG = PROJECT_ROOT / "config.txt"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_tiny_config(directory: Path | str, *, pop_size: int = 6) -> Path:
    """Copie config.txt avec une population réduite (tests rapides)."""
    text = NEAT_CONFIG.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^pop_size\s*=.*$", f"pop_size = {pop_size}", text)
    path = Path(directory) / "config.txt"
    path.write_text(text, encoding="utf-8")
    return path
