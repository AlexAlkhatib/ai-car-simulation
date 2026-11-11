"""Parité bit à bit avec l'implémentation Pygame d'origine.

Les fixtures ont été produites par ``tools/parity_fixtures.py`` en exécutant le
``Car`` du ``main.py`` original. On rejoue la même séquence d'actions avec le
modèle refactorisé : la moindre divergence de physique, de collision, de radar
ou de récompense fait échouer le test.
"""

from __future__ import annotations

import json
import unittest

from simulation import settings
from simulation.car import Car
from simulation.pygame_support import load_sprite
from simulation.track import Track
from tests.support import FIXTURES

TOLERANCE = 1e-9


class ParityTest(unittest.TestCase):
    maxDiff = None

    def _track_for(self, payload: dict) -> Track:
        name = payload["track"]
        path = settings.MAPS_DIR / name if name == "map.png" else FIXTURES / name
        return Track(path)

    def _replay(self, fixture: str) -> int:
        payload = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
        track = self._track_for(payload)
        car = Car(load_sprite(), track)
        # Le générateur déplace la voiture après construction (comme l'original),
        # le centre n'est recalculé qu'au premier update.
        car.position = list(payload["start"])

        frames = payload["frames"]
        self.assertGreater(len(frames), 10, "fixture trop courte pour être utile")

        for index, expected in enumerate(frames):
            car.apply_action(expected["choice"])
            car.update(track)
            with self.subTest(fixture=fixture, frame=index):
                self.assertAlmostEqual(car.position[0], expected["position"][0], delta=TOLERANCE)
                self.assertAlmostEqual(car.position[1], expected["position"][1], delta=TOLERANCE)
                self.assertAlmostEqual(car.center[0], expected["center"][0], delta=TOLERANCE)
                self.assertAlmostEqual(car.center[1], expected["center"][1], delta=TOLERANCE)
                self.assertAlmostEqual(car.angle, expected["angle"], delta=TOLERANCE)
                self.assertAlmostEqual(car.speed, expected["speed"], delta=TOLERANCE)
                self.assertAlmostEqual(car.distance, expected["distance"], delta=TOLERANCE)
                self.assertAlmostEqual(car.get_reward(), expected["reward"], delta=TOLERANCE)
                self.assertEqual(car.time, expected["time"])
                self.assertEqual(car.alive, expected["alive"])
                self.assertEqual(car.get_data(), expected["data"])
                self.assertEqual(
                    [[int(r[0][0]), int(r[0][1]), int(r[1])] for r in car.radars],
                    expected["radars"],
                )
                for actual_corner, expected_corner in zip(car.corners, expected["corners"]):
                    self.assertAlmostEqual(actual_corner[0], expected_corner[0], delta=TOLERANCE)
                    self.assertAlmostEqual(actual_corner[1], expected_corner[1], delta=TOLERANCE)

        return len(frames)

    def test_real_map_trajectory_matches_original(self) -> None:
        self.assertGreaterEqual(self._replay("map_trajectory.json"), 100)

    def test_open_arena_trajectory_matches_original(self) -> None:
        self.assertGreaterEqual(self._replay("arena_trajectory.json"), 50)

    def test_ring_trajectory_matches_original(self) -> None:
        self.assertGreaterEqual(self._replay("ring_trajectory.json"), 100)


if __name__ == "__main__":
    unittest.main()
