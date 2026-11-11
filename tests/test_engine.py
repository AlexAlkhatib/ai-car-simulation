"""Tests du moteur : progression NEAT, pause, reprise, réinitialisation."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from simulation import settings
from simulation.engine import IDLE, PAUSED, RUNNING, SimulationEngine
from tests.support import make_tiny_config


def wait_until(predicate, timeout: float = 30.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class EngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.runs = self.dir / "runs"
        self.config = make_tiny_config(self.dir, pop_size=6)
        self.engine = SimulationEngine(
            map_name=settings.DEFAULT_MAP,
            speed=2.0,
            max_generations=50,
            generation_max_frames=40,
            config_path=self.config,
            runs_dir=self.runs,
            population_size=6,
            seed=1,
        )
        self.addCleanup(self.engine.shutdown)

    def _start_and_wait_generation(self, generation: int = 1) -> None:
        self.engine.start()
        self.assertTrue(
            wait_until(lambda: self.engine.snapshot()["generation"] >= generation),
            "la simulation n'a pas atteint la génération attendue",
        )

    def test_initial_snapshot(self) -> None:
        snapshot = self.engine.snapshot()
        self.assertEqual(snapshot["status"], IDLE)
        self.assertEqual(snapshot["generation"], 0)
        self.assertEqual(snapshot["population"], 6)
        self.assertEqual(snapshot["cars"], [])
        self.assertEqual(snapshot["map"]["name"], settings.DEFAULT_MAP)
        self.assertEqual(snapshot["car_size"], [settings.CAR_SIZE_X, settings.CAR_SIZE_Y])
        self.assertIsNone(snapshot["error"])

    def test_generations_advance(self) -> None:
        self._start_and_wait_generation(2)
        snapshot = self.engine.snapshot()
        self.assertEqual(snapshot["status"], RUNNING)
        self.assertGreaterEqual(snapshot["generation"], 2)
        self.assertLessEqual(len(snapshot["cars"]), 6)
        self.assertGreaterEqual(len(self.engine.history()), 1)

        first = self.engine.history()[0]
        self.assertEqual(first["generation"], 1)
        self.assertEqual(first["population"], 6)
        self.assertGreaterEqual(first["frames"], 1)
        self.assertGreaterEqual(first["duration"], 0.0)

    def test_generation_frame_limit(self) -> None:
        engine = SimulationEngine(
            speed=4.0,
            generation_max_frames=5,
            config_path=self.config,
            runs_dir=self.runs,
            population_size=4,
            seed=2,
            max_generations=10,
        )
        self.addCleanup(engine.shutdown)
        engine.start()
        self.assertTrue(wait_until(lambda: engine.snapshot()["generation"] >= 2))
        for stat in engine.history():
            self.assertLessEqual(stat["frames"], 5)

    def test_pause_freezes_the_simulation(self) -> None:
        self._start_and_wait_generation(1)
        self.assertTrue(wait_until(lambda: self.engine.snapshot()["frame"] > 0))

        paused = self.engine.pause()
        self.assertEqual(paused["status"], PAUSED)
        frame_before = paused["frame"]
        time.sleep(0.25)
        frame_after = self.engine.snapshot()["frame"]
        self.assertLessEqual(frame_after - frame_before, 2, "la simulation avance encore en pause")

        resumed = self.engine.resume()
        self.assertEqual(resumed["status"], RUNNING)
        self.assertTrue(
            wait_until(lambda: self.engine.snapshot()["frame"] != frame_after, timeout=10)
        )

    def test_reset_clears_state(self) -> None:
        self._start_and_wait_generation(1)
        snapshot = self.engine.reset()
        self.assertEqual(snapshot["status"], IDLE)
        self.assertEqual(snapshot["generation"], 0)
        self.assertEqual(snapshot["cars"], [])
        self.assertEqual(self.engine.history(), [])

    def test_best_genome_is_saved(self) -> None:
        self._start_and_wait_generation(1)
        self.assertTrue(wait_until(lambda: self.engine.best_genome() is not None))
        payload = self.engine.best_genome()
        assert payload is not None
        data, stat = payload
        self.assertGreater(len(data), 0)
        self.assertGreater(stat["fitness"], 0)
        self.assertEqual(stat["map"], settings.DEFAULT_MAP)
        self.assertTrue((self.runs / "best_genome.pkl").is_file())
        self.assertTrue((self.runs / "best_genome.json").is_file())

    def test_invalid_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.set_speed(3.0)
        with self.assertRaises(ValueError):
            self.engine.set_map("../config.txt")
        with self.assertRaises(ValueError):
            SimulationEngine(map_name="inconnue.png")

    def test_set_map_restarts_when_running(self) -> None:
        self._start_and_wait_generation(1)
        snapshot = self.engine.set_map("map2.png")
        self.assertEqual(snapshot["map"]["name"], "map2.png")
        self.assertIn(snapshot["status"], {RUNNING, IDLE})
        self.assertLessEqual(snapshot["generation"], 1)
        self.engine.shutdown()


if __name__ == "__main__":
    unittest.main()
