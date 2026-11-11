#!/usr/bin/env python3
"""Génère les fixtures de parité à partir de l'implémentation Pygame d'origine.

Le script exécute le ``Car`` du ``main.py`` d'origine (fourni avec ``--legacy``)
et enregistre ses états frame par frame, en le pilotant avec une politique
déterministe (suivi de bord / suivi d'anneau). Les tests rejouent ensuite
exactement la même séquence d'actions avec le modèle refactorisé : si un seul
calcul de physique, de collision, de radar ou de récompense avait changé, la
comparaison échouerait.

Usage :
    python tools/parity_fixtures.py --legacy /chemin/vers/main.py \
        --output tests/fixtures --assets assets

Le script attend l'ancien projet (main.py + car.png + map.png) intact.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
RING_CENTER = (960.0, 540.0)
RING_RADIUS = 360.0


def load_legacy(main_py: Path):
    """Importe le module ``main.py`` original en mode headless."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    spec = importlib.util.spec_from_file_location("legacy_main", main_py)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Impossible d'importer {main_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["legacy_main"] = module
    spec.loader.exec_module(module)
    return module


def build_arena(path: Path) -> pygame.Surface:
    """Arène ouverte : fond blanc (bordure) et grande zone de route sombre."""
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill((255, 255, 255))
    pygame.draw.rect(surface, (12, 20, 32), pygame.Rect(120, 120, 1680, 840))
    pygame.image.save(surface, str(path))
    return surface


def build_ring(path: Path) -> pygame.Surface:
    """Anneau routier : parfait pour tester les virages et les radars."""
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill((255, 255, 255))
    pygame.draw.circle(surface, (18, 26, 38), RING_CENTER, 470)
    pygame.draw.circle(surface, (255, 255, 255), RING_CENTER, 250)
    pygame.image.save(surface, str(path))
    return surface


def wrap_angle(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi


def follow_wall(car) -> int:
    """Politique déterministe : garde le mur à gauche, accélère dans les lignes droites."""
    if not car.radars:
        return 3  # première frame : aucun capteur encore disponible
    data = car.get_data()  # gauche, avant-gauche, avant, avant-droit, droite
    if data[2] <= 6:
        return 0  # virage à gauche
    if car.speed >= 24:
        return 2  # ralentir
    return 3  # accélérer


def follow_ring(car) -> int:
    """Politique géométrique : suit le cercle de l'anneau, sens horaire."""
    center_x, center_y = RING_CENTER
    delta_x = car.center[0] - center_x
    delta_y = car.center[1] - center_y
    radius = math.hypot(delta_x, delta_y)
    theta = math.atan2(delta_y, delta_x)

    desired = theta + math.pi / 2  # tangente (sens horaire à l'écran)
    if radius < RING_RADIUS - 20:
        desired -= 0.30  # trop près du centre : viser l'extérieur
    elif radius > RING_RADIUS + 20:
        desired += 0.30  # trop près du bord externe : viser l'intérieur

    current = -math.radians(car.angle)  # orientation actuelle à l'écran
    error = wrap_angle(desired - current)

    if error > 0.05:
        return 1  # tourner à droite (angle -= 10)
    if error < -0.05:
        return 0  # tourner à gauche (angle += 10)
    if car.speed > 24:
        return 2
    return 3


def record(car, game_map: pygame.Surface, frames: int, policy) -> list[dict]:
    """Rejoue les actions et capture l'état après chaque ``update``."""
    samples: list[dict] = []
    for _ in range(frames):
        choice = policy(car)
        # Reproduction exacte du switch de ``run_simulation`` (main.py).
        if choice == 0:
            car.angle += 10
        elif choice == 1:
            car.angle -= 10
        elif choice == 2:
            if car.speed - 2 >= 12:
                car.speed -= 2
        else:
            car.speed += 2

        car.update(game_map)
        samples.append(
            {
                "choice": choice,
                "position": list(car.position),
                "center": list(car.center),
                "angle": car.angle,
                "speed": car.speed,
                "distance": car.distance,
                "time": car.time,
                "alive": car.alive,
                "corners": [list(point) for point in car.corners],
                "radars": [
                    [int(radar[0][0]), int(radar[0][1]), int(radar[1])]
                    for radar in car.radars
                ],
                "data": car.get_data(),
                "reward": car.get_reward(),
            }
        )
        if not car.alive:
            break
    return samples


def write_fixture(
    output: Path, name: str, legacy, track_name: str, samples: list[dict], start
) -> None:
    payload = {
        "track": track_name,
        "start": list(start),
        "car_size": [legacy.CAR_SIZE_X, legacy.CAR_SIZE_Y],
        "frames": samples,
    }
    (output / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True, help="main.py original")
    parser.add_argument("--assets", default="assets", help="dossier contenant map.png")
    parser.add_argument("--output", default="tests/fixtures", help="dossier de sortie")
    parser.add_argument("--frames", type=int, default=400, help="frames à enregistrer")
    args = parser.parse_args(argv)

    legacy_path = Path(args.legacy).resolve()
    assets = Path(args.assets).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    previous_cwd = Path.cwd()
    os.chdir(legacy_path.parent)  # Car() charge car.png depuis le cwd d'origine
    try:
        legacy = load_legacy(legacy_path)

        # 1. Carte réelle du projet, pilotée par suivi de bord.
        real_map = pygame.image.load(str(assets / "maps" / "map.png")).convert()
        real_car = legacy.Car()
        real_start = list(real_car.position)
        real_samples = record(real_car, real_map, args.frames, follow_wall)
        write_fixture(
            output, "map_trajectory.json", legacy, "map.png", real_samples, real_start
        )

        # 2. Arène ouverte : trajectoire longue, vitesses variées.
        arena_path = output / "arena.png"
        arena = build_arena(arena_path).convert()
        arena_car = legacy.Car()
        arena_car.position = [300, 300]
        arena_samples = record(arena_car, arena, args.frames, follow_wall)
        write_fixture(
            output, "arena_trajectory.json", legacy, "arena.png", arena_samples, [300, 300]
        )

        # 3. Anneau : virages continus, radars courts et longs.
        ring_path = output / "ring.png"
        ring = build_ring(ring_path).convert()
        ring_car = legacy.Car()
        ring_car.position = [RING_CENTER[0] - 30, RING_CENTER[1] - RING_RADIUS - 30]
        ring_samples = record(ring_car, ring, args.frames, follow_ring)
        write_fixture(
            output,
            "ring_trajectory.json",
            legacy,
            "ring.png",
            ring_samples,
            [RING_CENTER[0] - 30, RING_CENTER[1] - RING_RADIUS - 30],
        )
    finally:
        os.chdir(previous_cwd)

    print(f"map.png : {len(real_samples)} frames enregistrées")
    print(f"arena   : {len(arena_samples)} frames enregistrées")
    print(f"ring    : {len(ring_samples)} frames enregistrées")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
