"""Serveur Flask : la simulation est calculée en Python, rendue dans le navigateur.

Lancement :
    python app.py                    # http://127.0.0.1:5000
    HOST=0.0.0.0 PORT=3000 python app.py

Variables d'environnement :
    HOST            interface d'écoute (127.0.0.1 par défaut)
    PORT            port d'écoute (5000 par défaut)
    SIM_AUTOSTART   1 pour démarrer la simulation au lancement (défaut : 1)
    LOG_LEVEL       niveau de log (INFO par défaut)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from simulation import settings
from simulation.engine import SimulationEngine

logger = logging.getLogger(__name__)


def create_app(
    engine: SimulationEngine | None = None, *, autostart: bool | None = None
) -> Flask:
    """Construit l'application Flask (factory, utilisable par les tests)."""
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.json.ensure_ascii = False

    simulation = engine or SimulationEngine()
    app.extensions["simulation"] = simulation

    if autostart is None:
        autostart = os.environ.get("SIM_AUTOSTART", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
    if autostart and simulation.status == "idle":
        simulation.start()

    # -- Pages -------------------------------------------------------------
    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/healthz")
    def healthz() -> Response:
        snapshot = simulation.snapshot()
        return jsonify(
            {
                "status": "ok",
                "simulation": snapshot["status"],
                "generation": snapshot["generation"],
                "map": snapshot["map"]["name"],
            }
        )

    # -- Configuration -----------------------------------------------------
    @app.get("/api/config")
    def api_config() -> Response:
        snapshot = simulation.snapshot()
        return jsonify(
            {
                "maps": settings.available_maps(),
                "speeds": list(settings.SPEED_CHOICES),
                "fps": settings.TARGET_FPS,
                "frame_limit": settings.GENERATION_MAX_FRAMES,
                "max_generations": settings.MAX_GENERATIONS,
                "population": simulation.population_size,
                "actions": list(settings.ACTION_NAMES),
                "radar_angles": list(settings.RADAR_ANGLES),
                "sensor_count": settings.SENSOR_COUNT,
                "car_size": [settings.CAR_SIZE_X, settings.CAR_SIZE_Y],
                "border_rgb": list(settings.BORDER_RGB),
                "map": snapshot["map"],
                "track": snapshot["track"],
            }
        )

    @app.get("/api/state")
    def api_state() -> Response:
        return jsonify(simulation.snapshot())

    @app.get("/api/history")
    def api_history() -> Response:
        snapshot = simulation.snapshot()
        return jsonify(
            {
                "history": simulation.history(),
                "generation": snapshot["generation"],
                "best_fitness": snapshot["best_fitness"],
                "best_genome": snapshot["best_genome"],
            }
        )

    # -- Flux temps réel ---------------------------------------------------
    @app.get("/api/stream")
    def api_stream() -> Response:
        """Flux SSE : une ligne JSON par frame publiée par le moteur."""

        def generate():
            last_seq = 0
            yield "retry: 2000\n\n"
            while True:
                item = simulation.wait_for_frame(last_seq, timeout=15.0)
                if item is None:
                    # Keep-alive pour traverser les proxys sans fermer la connexion.
                    yield ": keep-alive\n\n"
                    continue
                last_seq, snapshot = item
                payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                yield f"data: {payload}\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # -- Commandes ---------------------------------------------------------
    def _guard(action) -> Response:  # type: ignore[no-untyped-def]
        try:
            return jsonify(action())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except (TypeError, KeyError) as exc:
            return jsonify({"error": f"Requête invalide : {exc}"}), 400

    @app.post("/api/start")
    def api_start() -> Response:
        return _guard(simulation.start)

    @app.post("/api/pause")
    def api_pause() -> Response:
        return _guard(simulation.pause)

    @app.post("/api/resume")
    def api_resume() -> Response:
        return _guard(simulation.resume)

    @app.post("/api/reset")
    def api_reset() -> Response:
        return _guard(simulation.reset)

    @app.post("/api/settings")
    def api_settings() -> Response:
        payload: dict[str, Any] = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Corps JSON attendu"}), 400

        def apply() -> dict[str, Any]:
            if "speed" in payload:
                simulation.set_speed(float(payload["speed"]))
            if "map" in payload:
                simulation.set_map(str(payload["map"]))
            return simulation.snapshot()

        return _guard(apply)

    # -- Téléchargement du meilleur génome ---------------------------------
    @app.get("/api/best-genome")
    def api_best_genome() -> Response:
        payload = simulation.best_genome()
        if payload is None:
            return jsonify({"error": "Aucun génome enregistré pour l'instant"}), 404
        data, stat = payload
        generation = stat.get("generation", "x")
        return Response(
            data,
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="best_genome_gen{generation}.pkl"',
                "Cache-Control": "no-store",
            },
        )

    # -- Images (carte, sprite) --------------------------------------------
    @app.get("/media/<path:filename>")
    def media(filename: str) -> Response:
        return send_from_directory(settings.ASSETS_DIR, filename, max_age=3600)

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
    )
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    application = create_app()
    # use_reloader=False : le moteur NEAT tourne dans un thread, on veut un
    # seul processus pour ne pas lancer deux évolutions concurrentes.
    logger.info("Simulation disponible sur http://%s:%s", host, port)
    application.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)


if __name__ == "__main__":
    main()
