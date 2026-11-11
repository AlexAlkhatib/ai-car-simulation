"""Tests HTTP : pages, configuration, commandes, flux SSE et médias."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app import create_app
from simulation import settings
from simulation.engine import SimulationEngine
from tests.support import make_tiny_config


def wait_until(predicate, timeout: float = 30.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name)
        config = make_tiny_config(directory, pop_size=4)
        self.engine = SimulationEngine(
            speed=4.0,
            max_generations=20,
            generation_max_frames=20,
            config_path=config,
            runs_dir=directory / "runs",
            population_size=4,
            seed=3,
        )
        self.addCleanup(self.engine.shutdown)
        self.app = create_app(self.engine, autostart=False)
        self.client = self.app.test_client()

    def test_index_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Voitures autonomes", body)
        self.assertIn("sim-canvas", body)
        self.assertIn("app.js", body)

    def test_config_endpoint(self) -> None:
        payload = self.client.get("/api/config").get_json()
        self.assertIn(settings.DEFAULT_MAP, payload["maps"])
        self.assertEqual(payload["population"], 4)
        self.assertEqual(payload["sensor_count"], 5)
        self.assertEqual(len(payload["actions"]), 4)
        self.assertEqual(payload["fps"], settings.TARGET_FPS)
        self.assertIn(1.0, payload["speeds"])

    def test_state_endpoint_starts_idle(self) -> None:
        payload = self.client.get("/api/state").get_json()
        self.assertEqual(payload["status"], "idle")
        self.assertEqual(payload["generation"], 0)
        self.assertEqual(payload["cars"], [])

    def test_media_and_health(self) -> None:
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        media = self.client.get("/media/maps/map.png")
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.mimetype, "image/png")
        self.assertEqual(self.client.get("/media/car.png").status_code, 200)
        self.assertEqual(self.client.get("/media/../config.txt").status_code, 404)

    def test_stream_sends_sse_headers(self) -> None:
        response = self.client.get("/api/stream", buffered=False)
        self.assertEqual(response.mimetype, "text/event-stream")
        try:
            first = next(iter(response.response))
            self.assertIn(b"retry", first)
        finally:
            response.close()

    def test_commands_and_errors(self) -> None:
        started = self.client.post("/api/start")
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.get_json()["status"], "running")

        self.assertTrue(
            wait_until(lambda: self.engine.snapshot()["generation"] >= 1),
            "aucune génération calculée",
        )

        paused = self.client.post("/api/pause").get_json()
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(self.client.post("/api/resume").get_json()["status"], "running")

        speed = self.client.post("/api/settings", json={"speed": 2}).get_json()
        self.assertEqual(speed["speed"], 2.0)

        self.assertEqual(
            self.client.post("/api/settings", json={"map": "../config.txt"}).status_code, 400
        )
        self.assertEqual(
            self.client.post("/api/settings", json={"speed": "rapide"}).status_code, 400
        )

        reset = self.client.post("/api/reset").get_json()
        self.assertEqual(reset["status"], "idle")
        self.assertEqual(reset["generation"], 0)

    def test_history_and_best_genome(self) -> None:
        self.assertEqual(self.client.get("/api/best-genome").status_code, 404)

        self.client.post("/api/start")
        self.assertTrue(wait_until(lambda: self.engine.best_genome() is not None))

        history = self.client.get("/api/history").get_json()
        self.assertGreaterEqual(len(history["history"]), 1)
        self.assertGreater(history["best_fitness"], 0)

        download = self.client.get("/api/best-genome")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/octet-stream")
        self.assertIn("best_genome_gen", download.headers["Content-Disposition"])
        self.assertGreater(len(download.data), 0)


if __name__ == "__main__":
    unittest.main()
