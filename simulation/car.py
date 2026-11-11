"""Modèle physique d'une voiture autonome.

Le comportement (vitesse initiale, rotation, capteurs, récompense) est
strictement celui de ``main.py`` : même arithmétique, même ordre d'opérations,
afin que les génomes évoluent exactement de la même manière.
"""

from __future__ import annotations

import math

import pygame

from . import settings
from .pygame_support import rotated_sprite
from .track import Track


class Car:
    """Une voiture : position, orientation, capteurs et distance parcourue."""

    __slots__ = (
        "sprite",
        "rotated_sprite",
        "track",
        "position",
        "angle",
        "speed",
        "speed_set",
        "center",
        "radars",
        "alive",
        "distance",
        "time",
        "corners",
    )

    def __init__(self, sprite: pygame.Surface, track: Track) -> None:
        self.sprite = sprite
        self.rotated_sprite = sprite
        self.track = track

        self.position: list[float] = list(settings.START_POSITION)
        self.angle = 0.0
        self.speed = 0.0
        self.speed_set = False

        self.center: list[float] = [
            self.position[0] + settings.CAR_SIZE_X / 2,
            self.position[1] + settings.CAR_SIZE_Y / 2,
        ]

        #: Liste de ``[[x, y], distance]`` remplie à chaque frame.
        self.radars: list[list[object]] = []
        self.alive = True
        self.distance = 0.0
        self.time = 0
        #: Les 4 coins du rectangle orienté, recalculés à chaque frame.
        self.corners: list[list[float]] = []

    # -- Rendu (côté serveur, uniquement pour l'export/les tests) -----------
    def draw(self, screen: pygame.Surface) -> None:
        """Dessine la voiture (utilisé par le rendu de secours Pygame)."""
        screen.blit(self.rotated_sprite, self.position)
        self.draw_radar(screen)

    def draw_radar(self, screen: pygame.Surface) -> None:
        for radar in self.radars:
            position = radar[0]
            pygame.draw.line(screen, (0, 255, 0), self.center, position, 1)
            pygame.draw.circle(screen, (0, 255, 0), position, settings.RADAR_DOT_RADIUS)

    # -- Simulation ---------------------------------------------------------
    def apply_action(self, choice: int) -> None:
        """Applique la sortie du réseau de neurones (0..3).

        Reprend mot pour mot la logique de ``run_simulation`` :
        gauche / droite / ralentir (jamais sous 12) / accélérer.
        """
        if choice == 0:
            self.angle += 10  # Gauche
        elif choice == 1:
            self.angle -= 10  # Droite
        elif choice == 2:
            if self.speed - 2 >= 12:
                self.speed -= 2  # Ralentir
        else:
            self.speed += 2  # Accélérer

    def check_collision(self, track: Track) -> None:
        """Crash si l'un des 4 coins touche la bordure blanche."""
        self.alive = True
        for point in self.corners:
            if track.is_border(point):
                self.alive = False
                break

    def check_radar(self, degree: int, track: Track) -> None:
        """Lance un rayon jusqu'à la bordure et mémorise le point d'impact."""
        length = 0
        x = int(
            self.center[0]
            + math.cos(math.radians(360 - (self.angle + degree))) * length
        )
        y = int(
            self.center[1]
            + math.sin(math.radians(360 - (self.angle + degree))) * length
        )

        # Avance tant qu'on ne touche pas la bordure (300 px maximum).
        while not track.is_border_at(x, y) and length < settings.RADAR_MAX_LENGTH:
            length = length + 1
            x = int(
                self.center[0]
                + math.cos(math.radians(360 - (self.angle + degree))) * length
            )
            y = int(
                self.center[1]
                + math.sin(math.radians(360 - (self.angle + degree))) * length
            )

        distance = int(
            math.sqrt(math.pow(x - self.center[0], 2) + math.pow(y - self.center[1], 2))
        )
        self.radars.append([(x, y), distance])

    def update(self, track: Track) -> None:
        """Avance d'une frame : mouvement, coins, collision, capteurs."""
        # Vitesse initiale : 20 px/frame, une seule fois.
        if not self.speed_set:
            self.speed = 20
            self.speed_set = True

        # Sprite orienté + déplacement horizontal (20 px de marge minimale).
        self.rotated_sprite = rotated_sprite(self.angle)
        self.position[0] += math.cos(math.radians(360 - self.angle)) * self.speed
        self.position[0] = max(self.position[0], 20)
        self.position[0] = min(self.position[0], settings.WIDTH - 120)

        self.distance += self.speed
        self.time += 1

        # Déplacement vertical. La borne d'origine utilise WIDTH : comportement
        # conservé tel quel (les requêtes hors carte sont simplement traitées
        # comme une bordure par Track).
        self.position[1] += math.sin(math.radians(360 - self.angle)) * self.speed
        self.position[1] = max(self.position[1], 20)
        self.position[1] = min(self.position[1], settings.WIDTH - 120)

        self.center = [
            int(self.position[0]) + settings.CAR_SIZE_X / 2,
            int(self.position[1]) + settings.CAR_SIZE_Y / 2,
        ]

        # Les 4 coins du rectangle orienté (demi-diagonale = côté / 2).
        length = 0.5 * settings.CAR_SIZE_X
        left_top = [
            self.center[0] + math.cos(math.radians(360 - (self.angle + 30))) * length,
            self.center[1] + math.sin(math.radians(360 - (self.angle + 30))) * length,
        ]
        right_top = [
            self.center[0] + math.cos(math.radians(360 - (self.angle + 150))) * length,
            self.center[1] + math.sin(math.radians(360 - (self.angle + 150))) * length,
        ]
        left_bottom = [
            self.center[0] + math.cos(math.radians(360 - (self.angle + 210))) * length,
            self.center[1] + math.sin(math.radians(360 - (self.angle + 210))) * length,
        ]
        right_bottom = [
            self.center[0] + math.cos(math.radians(360 - (self.angle + 330))) * length,
            self.center[1] + math.sin(math.radians(360 - (self.angle + 330))) * length,
        ]
        self.corners = [left_top, right_top, left_bottom, right_bottom]

        self.check_collision(track)
        self.radars.clear()

        for degree in settings.RADAR_ANGLES:
            self.check_radar(degree, track)

    # -- Sorties ------------------------------------------------------------
    def get_data(self) -> list[int]:
        """Les 5 entrées du réseau : distance de chaque radar / 30."""
        return_values = [0, 0, 0, 0, 0]
        for index, radar in enumerate(self.radars):
            return_values[index] = int(int(radar[1]) / 30)
        return return_values

    def is_alive(self) -> bool:
        return self.alive

    def get_reward(self) -> float:
        """Récompense cumulée : distance parcourue / demi-largeur du sprite."""
        return self.distance / (settings.CAR_SIZE_X / 2)

    def to_state(self) -> dict[str, object]:
        """Instantané compact envoyé au navigateur."""
        return {
            "x": round(self.position[0], 1),
            "y": round(self.position[1], 1),
            "angle": round(self.angle, 2),
            "speed": round(self.speed, 2),
            "alive": self.alive,
            "fitness": round(self.get_reward(), 2),
            "radars": [
                [int(radar[0][0]), int(radar[0][1]), int(radar[1])]
                for radar in self.radars
            ],
        }
