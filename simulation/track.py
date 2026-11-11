"""Chargement et interrogation de la carte (piste)."""

from __future__ import annotations

from pathlib import Path

import pygame

from . import settings
from .pygame_support import ensure_headless_display


class Track:
    """Une carte de course et ses requêtes pixel.

    La carte est une image PNG sur fond blanc : tout pixel blanc est une
    bordure, donc une collision. C'est la règle exacte du script d'origine.

    Améliorations apportées sans changer la règle :

    * les coordonnées hors de l'image sont considérées comme une bordure au
      lieu de lever ``IndexError`` (l'original plantait si une voiture sortait
      de la carte) ;
    * la comparaison se fait sur les canaux RGB : selon le format interne de la
      surface, ``get_at`` renvoie 3 ou 4 valeurs, ce qui rendait la comparaison
      fragile.
    """

    __slots__ = ("name", "path", "surface", "width", "height")

    def __init__(self, path: str | Path) -> None:
        ensure_headless_display()
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Carte introuvable : {self.path}")
        self.name = self.path.name
        # ``convert()`` accélère fortement les accès pixel (comme dans l'original).
        self.surface = pygame.image.load(str(self.path)).convert()
        self.width, self.height = self.surface.get_size()

    # -- Requêtes -----------------------------------------------------------
    def rgb_at(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Couleur RGB du pixel, ou ``None`` si hors de la carte."""
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        return tuple(self.surface.get_at((int(x), int(y)))[:3])

    def is_border_at(self, x: float, y: float) -> bool:
        """Vrai si le point est une bordure (ou sort de la carte).

        Appelé une fois par pixel et par radar : la version « chaude » évite la
        construction d'un tuple intermédiaire tout en gardant exactement la même
        règle (comparaison sur les canaux RGB).
        """
        x = int(x)
        y = int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return True
        pixel = self.surface.get_at((x, y))
        red, green, blue = settings.BORDER_RGB
        return pixel[0] == red and pixel[1] == green and pixel[2] == blue

    def is_border(self, point: tuple[float, float] | list[float]) -> bool:
        """Variante lisible de :meth:`is_border_at` pour un point ``(x, y)``."""
        return self.is_border_at(point[0], point[1])

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "url": f"/media/maps/{self.name}",
        }

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"Track(name={self.name!r}, size={self.width}x{self.height})"
