#!/usr/bin/env python3
"""Entraînement NEAT sans interface graphique.

Utile pour faire évoluer une population sur un serveur ou pour produire un
génome réutilisable, avec exactement la même physique que l'interface web.

Exemples :
    python train.py --generations 30
    python train.py --generations 50 --map map3.png --speed-report 10
    python train.py --generations 100 --save runs/meilleur_genome.pkl
"""

from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path

import neat

from simulation import settings
from simulation.evaluation import GenerationEvaluator
from simulation.pygame_support import load_sprite
from simulation.track import Track


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Entraînement NEAT headless (même physique que l'interface web)."
    )
    parser.add_argument("--generations", type=int, default=20, help="nombre de générations")
    parser.add_argument(
        "--map", default=settings.DEFAULT_MAP, help="carte PNG de assets/maps/"
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=settings.GENERATION_MAX_FRAMES,
        help="frames maximum par génération",
    )
    parser.add_argument("--population", type=int, default=None, help="taille de population")
    parser.add_argument("--seed", type=int, default=None, help="graine aléatoire")
    parser.add_argument("--config", default=str(settings.NEAT_CONFIG_PATH), help="config.txt")
    parser.add_argument(
        "--save",
        default="runs/best_genome.pkl",
        help="fichier de sortie du meilleur génome (pickle)",
    )
    parser.add_argument("--quiet", action="store_true", help="masquer le détail NEAT")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    track = Track(settings.map_path(args.map))
    sprite = load_sprite()
    config = neat.config.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        args.config,
    )
    if args.population:
        config.pop_size = args.population

    population = neat.Population(config, seed=args.seed)
    if not args.quiet:
        population.add_reporter(neat.StdOutReporter(True))

    evaluator = GenerationEvaluator(track, sprite, args.frames)
    started = time.perf_counter()
    generation_counter = {"value": 0}

    def eval_genomes(genomes, neat_config) -> None:
        generation_counter["value"] += 1
        generation_started = time.perf_counter()
        result = evaluator.evaluate(genomes, neat_config)
        duration = time.perf_counter() - generation_started
        print(
            f"génération {generation_counter['value']:4d} | "
            f"meilleure {result.best_fitness:9.1f} | "
            f"moyenne {result.mean_fitness:9.1f} | "
            f"vivantes {result.alive_at_end:3d}/{len(genomes):3d} | "
            f"frames {result.frames:5d} | {duration:6.2f}s",
            flush=True,
        )

    print(
        f"Entraînement sur {track.name} ({track.width}x{track.height}), "
        f"population {config.pop_size}, {args.generations} générations"
    )
    best = population.run(eval_genomes, args.generations)
    elapsed = time.perf_counter() - started

    if best is not None:
        output = Path(args.save)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(pickle.dumps(best))
        print(
            f"\nTerminé en {elapsed:.1f}s — meilleure fitness {float(best.fitness or 0.0):.1f} "
            f"(génome {best.key}) enregistré dans {output}"
        )
    else:
        print(f"\nTerminé en {elapsed:.1f}s — aucun génome retourné")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
