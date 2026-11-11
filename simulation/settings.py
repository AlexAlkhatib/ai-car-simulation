"""Constantes et chemins du projet de simulation.

Toutes les valeurs numériques proviennent du script Pygame d'origine
(``main.py``) et sont conservées à l'identique afin de ne pas modifier le
comportement de la simulation ni de l'évolution NEAT.
"""

from __future__ import annotations

from pathlib import Path

# --- Chemins ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
CAR_SPRITE_PATH = ASSETS_DIR / "car.png"
NEAT_CONFIG_PATH = PROJECT_ROOT / "config.txt"
RUNS_DIR = PROJECT_ROOT / "runs"

# --- Géométrie de la scène -------------------------------------------------
WIDTH = 1920
HEIGHT = 1080

CAR_SIZE_X = 60
CAR_SIZE_Y = 60

#: Position de départ d'une voiture (coin supérieur gauche du sprite).
START_POSITION: tuple[float, float] = (830.0, 920.0)

#: Couleur de bordure : toucher un pixel blanc = collision.
BORDER_RGB: tuple[int, int, int] = (255, 255, 255)

# --- Capteurs (radars) -----------------------------------------------------
#: Angles des 5 capteurs, en degrés relatifs à l'orientation de la voiture.
RADAR_ANGLES: tuple[int, ...] = tuple(range(-90, 120, 45))
#: Portée maximale d'un radar (en pixels).
RADAR_MAX_LENGTH = 300
#: Rayon des cercles dessinés à l'extrémité des radars.
RADAR_DOT_RADIUS = 5

# --- Boucle de simulation --------------------------------------------------
#: Cadence de référence de la boucle d'origine (``clock.tick(60)``).
TARGET_FPS = 60
#: Limite de frames par génération (``counter == 30 * 40``).
GENERATION_MAX_FRAMES = 30 * 40
#: Nombre maximal de générations (``population.run(run_simulation, 1000)``).
MAX_GENERATIONS = 1000
#: Vitesses de simulation proposées dans l'interface (multiplicateur).
SPEED_CHOICES: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)

# --- Actions du réseau -----------------------------------------------------
ACTION_NAMES: tuple[str, ...] = ("gauche", "droite", "ralentir", "accélérer")
ACTION_COUNT = len(ACTION_NAMES)
SENSOR_COUNT = len(RADAR_ANGLES)

DEFAULT_MAP = "map.png"


def available_maps() -> list[str]:
    """Liste triée des cartes PNG disponibles dans ``assets/maps``."""
    if not MAPS_DIR.is_dir():
        return []
    return sorted(p.name for p in MAPS_DIR.glob("*.png") if p.is_file())


def map_path(name: str) -> Path:
    """Chemin absolu d'une carte, en refusant tout nom hors de ``assets/maps``."""
    candidate = (MAPS_DIR / name).resolve()
    if candidate.parent != MAPS_DIR.resolve() or candidate.suffix.lower() != ".png":
        raise ValueError(f"Carte invalide : {name!r}")
    if not candidate.is_file():
        raise ValueError(f"Carte introuvable : {name!r}")
    return candidate
