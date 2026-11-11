"""Moteur de simulation pilotable depuis le web.

Le moteur exécute NEAT dans un thread dédié et publie un instantané de l'état à
chaque frame. Il expose pause / reprise / réinitialisation / changement de
vitesse sans jamais modifier la logique d'évolution : ``population.run`` reste
l'unique boucle de reproduction de neat-python.
"""

from __future__ import annotations

import configparser
import functools
import json
import logging
import pickle
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import neat
from neat.reporting import BaseReporter

from . import settings
from .car import Car
from .evaluation import FrameObserver, GenerationEvaluator, GenerationResult
from .pygame_support import load_sprite
from .track import Track

logger = logging.getLogger(__name__)

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
FINISHED = "finished"
ERROR = "error"


class SimulationStopped(Exception):
    """Interruption volontaire (arrêt ou réinitialisation) de la boucle."""


@dataclass(frozen=True)
class GenerationStat:
    """Statistiques conservées pour l'historique et le graphique."""

    generation: int
    best_fitness: float
    mean_fitness: float
    alive_at_end: int
    population: int
    frames: int
    duration: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "best": round(self.best_fitness, 2),
            "mean": round(self.mean_fitness, 2),
            "alive": self.alive_at_end,
            "population": self.population,
            "frames": self.frames,
            "duration": round(self.duration, 3),
        }


@dataclass
class _Run:
    """Identité d'une exécution : un arrêt ciblé, jamais un état global."""

    id: int
    stop: threading.Event


class _EngineObserver:
    """Relie la boucle d'évaluation aux contrôles du moteur."""

    __slots__ = ("engine", "run")

    def __init__(self, engine: "SimulationEngine", run: _Run) -> None:
        self.engine = engine
        self.run = run

    def before_step(self) -> None:
        self.engine._before_step(self.run)

    def on_frame(self, cars: list[Car], alive: int, frames: int) -> None:
        self.engine._on_frame(self.run, cars, alive, frames)


class _QuietReporter(BaseReporter):
    """Rapporteur compact : évite le bruit du StdOutReporter de neat-python."""

    def __init__(self) -> None:
        self._generation = 0

    def start_generation(self, generation: int) -> None:
        self._generation = generation
        logger.debug("NEAT génération interne %s", generation)

    def post_evaluate(self, config, population, species, best_genome) -> None:
        fitness = float(best_genome.fitness or 0.0) if best_genome else 0.0
        logger.debug(
            "NEAT génération %s : meilleure fitness %.1f (%s espèces)",
            self._generation,
            fitness,
            len(species.species),
        )


class SimulationEngine:
    """Pilote la population NEAT et publie l'état pour l'interface web."""

    def __init__(
        self,
        *,
        map_name: str = settings.DEFAULT_MAP,
        speed: float = 1.0,
        max_generations: int = settings.MAX_GENERATIONS,
        generation_max_frames: int = settings.GENERATION_MAX_FRAMES,
        config_path: str | Path = settings.NEAT_CONFIG_PATH,
        runs_dir: str | Path = settings.RUNS_DIR,
        population_size: int | None = None,
        seed: int | None = None,
    ) -> None:
        settings.map_path(map_name)  # validation immédiate
        if speed not in settings.SPEED_CHOICES:
            raise ValueError(f"Vitesse inconnue : {speed!r}")

        self._map_name = map_name
        self._speed = float(speed)
        self._max_generations = int(max_generations)
        self._generation_max_frames = int(generation_max_frames)
        self._config_path = Path(config_path)
        self._runs_dir = Path(runs_dir)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._neat_population: neat.Population | None = None
        self._population_size = int(population_size or self._read_config_population())
        self._seed = seed

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)

        self._thread: threading.Thread | None = None
        self._run: _Run | None = None
        self._run_counter = 0

        self._status = IDLE
        self._generation = 0
        self._population = 0
        self._frame = 0
        self._alive = 0
        self._current_best = 0.0
        self._best_fitness = 0.0
        self._cars: list[dict[str, Any]] = []
        self._frame_seq = 0
        self._history: list[GenerationStat] = []
        self._error: str | None = None

        self._neat_config: neat.Config | None = None
        self._track: Track | None = None
        self._best_genome_bytes: bytes | None = None
        self._best_genome_stat: dict[str, Any] | None = None
        self._generation_started = 0.0

    # -- API publique -------------------------------------------------------
    @property
    def map_name(self) -> str:
        with self._condition:
            return self._map_name

    @property
    def status(self) -> str:
        with self._condition:
            return self._status

    @property
    def population_size(self) -> int:
        with self._condition:
            return self._population or self._population_size

    def start(self) -> dict[str, Any]:
        """Démarre l'évolution, ou reprend si la simulation est en pause."""
        with self._condition:
            if self._status == PAUSED:
                self._status = RUNNING
                self._bump_locked()
                return self._snapshot_locked()
            if self._status == RUNNING:
                return self._snapshot_locked()
            needs_reset = self._status in (FINISHED, ERROR)
        if needs_reset:
            self.reset()
        return self._launch()

    def pause(self) -> dict[str, Any]:
        with self._condition:
            if self._status == RUNNING:
                self._status = PAUSED
                self._bump_locked()
            return self._snapshot_locked()

    def resume(self) -> dict[str, Any]:
        with self._condition:
            if self._status == PAUSED:
                self._status = RUNNING
                self._bump_locked()
            return self._snapshot_locked()

    def reset(self, map_name: str | None = None) -> dict[str, Any]:
        """Arrête tout et repart de la génération 0."""
        self._shutdown()
        with self._condition:
            self._run = None
            self._run_counter += 1
            if map_name is not None:
                self._map_name = map_name
            self._status = IDLE
            self._generation = 0
            self._population = self._population_size
            self._frame = 0
            self._alive = 0
            self._current_best = 0.0
            self._best_fitness = 0.0
            self._cars = []
            self._history.clear()
            self._error = None
            self._neat_config = None
            self._track = None
            self._best_genome_bytes = None
            self._best_genome_stat = None
            self._bump_locked()
            return self._snapshot_locked()

    def set_speed(self, speed: float) -> dict[str, Any]:
        """Change le multiplicateur de vitesse (physique inchangée)."""
        speed = float(speed)
        if speed not in settings.SPEED_CHOICES:
            raise ValueError(f"Vitesse inconnue : {speed!r}")
        with self._condition:
            self._speed = speed
            self._bump_locked()
            return self._snapshot_locked()

    def set_map(self, map_name: str) -> dict[str, Any]:
        """Change de carte ; relance automatiquement si la simulation tournait."""
        settings.map_path(map_name)  # validation
        with self._condition:
            was_active = self._status in (RUNNING, PAUSED)
        self.reset(map_name=map_name)
        if was_active:
            self.start()
        return self.snapshot()

    def shutdown(self) -> None:
        """Arrête le thread (utilisé par les tests et l'extinction du serveur)."""
        self._shutdown()
        with self._condition:
            self._status = IDLE
            self._bump_locked()

    # -- Lecture d'état -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return self._snapshot_locked()

    def history(self) -> list[dict[str, Any]]:
        with self._condition:
            return [stat.as_dict() for stat in self._history]

    def best_genome(self) -> tuple[bytes, dict[str, Any]] | None:
        with self._condition:
            if self._best_genome_bytes is None:
                return None
            return self._best_genome_bytes, dict(self._best_genome_stat or {})

    def wait_for_frame(
        self, last_seq: int, timeout: float = 15.0
    ) -> tuple[int, dict[str, Any]] | None:
        """Attend la frame suivante (utilisé par le flux SSE)."""
        with self._condition:
            deadline = time.monotonic() + timeout
            while self._frame_seq <= last_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(min(remaining, 1.0))
            return self._frame_seq, self._snapshot_locked()

    # -- Interne ------------------------------------------------------------
    def _bump_locked(self) -> None:
        self._frame_seq += 1
        self._condition.notify_all()

    def _snapshot_locked(self) -> dict[str, Any]:
        track = self._track
        map_info = (
            track.as_dict()
            if track is not None
            else {
                "name": self._map_name,
                "width": settings.WIDTH,
                "height": settings.HEIGHT,
                "url": f"/media/maps/{self._map_name}",
            }
        )
        return {
            "seq": self._frame_seq,
            "status": self._status,
            "generation": self._generation,
            "max_generations": self._max_generations,
            "population": self._population or self._population_size,
            "alive": self._alive,
            "frame": self._frame,
            "frame_limit": self._generation_max_frames,
            "speed": self._speed,
            "best_fitness": round(self._best_fitness, 2),
            "current_best": round(self._current_best, 2),
            "map": map_info,
            "track": {"width": settings.WIDTH, "height": settings.HEIGHT},
            "car_size": [settings.CAR_SIZE_X, settings.CAR_SIZE_Y],
            "start_position": list(settings.START_POSITION),
            "sensor_count": settings.SENSOR_COUNT,
            "action_count": settings.ACTION_COUNT,
            "history_count": len(self._history),
            "best_genome": dict(self._best_genome_stat) if self._best_genome_stat else None,
            "error": self._error,
            "cars": self._cars,
        }

    def _launch(self) -> dict[str, Any]:
        with self._condition:
            self._run_counter += 1
            run = _Run(id=self._run_counter, stop=threading.Event())
            self._run = run
            self._status = RUNNING
            self._error = None
            self._cars = []
            self._frame = 0
            self._generation_started = time.perf_counter()
            thread = threading.Thread(
                target=self._run_population,
                args=(run,),
                name=f"neat-simulation-{run.id}",
                daemon=True,
            )
            self._thread = thread
            self._bump_locked()
        thread.start()
        return self.snapshot()

    def _shutdown(self, timeout: float = 5.0) -> None:
        """Demande l'arrêt du thread puis attend sa fin (sans tenir le verrou)."""
        with self._condition:
            run = self._run
            if run is not None:
                run.stop.set()
            thread = self._thread
            self._thread = None
            self._condition.notify_all()
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _check(self, run: _Run) -> None:
        """Lève si l'exécution n'est plus la courante (verrou supposé tenu)."""
        if self._run is not run or run.stop.is_set():
            raise SimulationStopped

    def _read_config_population(self) -> int:
        """Lit ``pop_size`` dans config.txt (sans charger tout NEAT)."""
        parser = configparser.ConfigParser()
        try:
            parser.read(self._config_path, encoding="utf-8")
            return parser.getint("NEAT", "pop_size")
        except (OSError, configparser.Error, ValueError):
            return 0

    def _build_neat_config(self) -> neat.Config:
        if self._neat_config is None:
            config = neat.config.Config(
                neat.DefaultGenome,
                neat.DefaultReproduction,
                neat.DefaultSpeciesSet,
                neat.DefaultStagnation,
                str(self._config_path),
            )
            if self._population_size:
                config.pop_size = self._population_size
            self._neat_config = config
        return self._neat_config

    def _ensure_track(self) -> Track:
        with self._condition:
            if self._track is None or self._track.name != self._map_name:
                self._track = Track(settings.map_path(self._map_name))
            return self._track

    # -- Thread d'évolution -------------------------------------------------
    def _run_population(self, run: _Run) -> None:
        try:
            config = self._build_neat_config()
            with self._condition:
                self._check(run)
                self._population = config.pop_size
                self._population_size = config.pop_size
                self._bump_locked()

            population = neat.Population(config, seed=self._seed)
            population.add_reporter(_QuietReporter())
            # Attention : ne pas écraser self._population (taille affichée).
            self._neat_population = population

            best = population.run(
                functools.partial(self._evaluate_generation, run=run),
                self._max_generations,
            )

            with self._condition:
                if self._run is not run or run.stop.is_set():
                    return
                if best is not None:
                    self._store_best_genome(best, self._generation)
                self._status = FINISHED
                self._cars = []
                self._alive = 0
                self._bump_locked()
                logger.info("Évolution terminée après %s générations", self._generation)
        except SimulationStopped:
            logger.debug("Simulation interrompue")
        except Exception as exc:  # noqa: BLE001 - on remonte l'erreur à l'IHM
            logger.exception("Erreur pendant l'évolution NEAT")
            with self._condition:
                if self._run is run and not run.stop.is_set():
                    self._status = ERROR
                    self._error = f"{type(exc).__name__}: {exc}"
                    self._bump_locked()

    def _evaluate_generation(
        self,
        genomes: list[tuple[int, neat.DefaultGenome]],
        config: neat.Config,
        run: _Run,
    ) -> None:
        evaluator = GenerationEvaluator(
            self._ensure_track(), load_sprite(), self._generation_max_frames
        )

        with self._condition:
            self._check(run)
            self._generation += 1
            self._frame = 0
            self._alive = len(genomes)
            self._current_best = 0.0
            self._generation_started = time.perf_counter()
            self._bump_locked()

        result = evaluator.evaluate(genomes, config, observer=_EngineObserver(self, run))
        self._record_generation(genomes, result, run)

    def _before_step(self, run: _Run) -> None:
        """Attend la fin d'une pause et vérifie qu'on doit continuer."""
        with self._condition:
            self._check(run)
            while self._status == PAUSED:
                self._condition.wait(0.25)
                self._check(run)

    def _on_frame(self, run: _Run, cars: list[Car], alive: int, frames: int) -> None:
        """Publie une frame et respecte la cadence demandée.

        Le multiplicateur de vitesse ne fait que regrouper plusieurs frames de
        physique entre deux publications : les calculs restent identiques.
        """
        with self._condition:
            self._check(run)
            speed = self._speed
            batch = max(1, int(round(speed)))
            publish = frames % batch == 0
            if publish:
                self._frame = frames
                self._alive = alive
                self._cars = [car.to_state() for car in cars]
                self._current_best = max((car.get_reward() for car in cars), default=0.0)
                self._bump_locked()

        if publish:
            # Cadence cible : TARGET_FPS * vitesse frames de physique / seconde.
            run.stop.wait(batch / (settings.TARGET_FPS * speed))

    def _record_generation(
        self,
        genomes: list[tuple[int, neat.DefaultGenome]],
        result: GenerationResult,
        run: _Run,
    ) -> None:
        duration = time.perf_counter() - self._generation_started
        with self._condition:
            self._check(run)
            stat = GenerationStat(
                generation=self._generation,
                best_fitness=result.best_fitness,
                mean_fitness=result.mean_fitness,
                alive_at_end=result.alive_at_end,
                population=len(genomes),
                frames=result.frames,
                duration=duration,
            )
            self._history.append(stat)
            self._current_best = result.best_fitness
            self._alive = result.alive_at_end
            self._frame = result.frames
            self._cars = []

            if result.best_fitness > self._best_fitness:
                self._best_fitness = result.best_fitness
                best_genome = max(
                    genomes, key=lambda item: float(item[1].fitness or 0.0)
                )[1]
                self._store_best_genome(best_genome, stat.generation)

            logger.info(
                "Génération %s : meilleure fitness %.1f, moyenne %.1f, %s/%s vivantes, %.2fs",
                stat.generation,
                stat.best_fitness,
                stat.mean_fitness,
                stat.alive_at_end,
                stat.population,
                duration,
            )
            self._bump_locked()

    def _store_best_genome(self, genome: neat.DefaultGenome, generation: int) -> None:
        """Conserve le meilleur génome en mémoire (téléchargement) et sur disque."""
        try:
            payload = pickle.dumps(genome)
        except (pickle.PickleError, TypeError) as exc:  # pragma: no cover - rare
            logger.warning("Génome non sérialisable : %s", exc)
            return

        stat = {
            "generation": generation,
            "fitness": round(float(genome.fitness or 0.0), 2),
            "map": self._map_name,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._best_genome_bytes = payload
        self._best_genome_stat = stat
        try:
            (self._runs_dir / "best_genome.pkl").write_bytes(payload)
            (self._runs_dir / "best_genome.json").write_text(
                json.dumps(stat, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - disque en lecture seule
            logger.warning("Sauvegarde du meilleur génome impossible : %s", exc)
