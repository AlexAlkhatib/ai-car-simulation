"""Simulation de voitures autonomes avec NEAT (moteur Python)."""

from __future__ import annotations

import os

# Pygame sert uniquement de moteur d'images (collisions/radars) : aucun affichage
# n'est nécessaire côté serveur. Ces variables doivent être posées avant le
# premier import de pygame, d'où leur place ici.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

__version__ = "2.0.0"

__all__ = ["__version__"]
