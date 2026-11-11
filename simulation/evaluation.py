"""Boucle d'évaluation d'une génération.

Une seule implémentation, partagée par le serveur web (avec pause, vitesse et
publication des frames) et par l'entraînement en ligne de commande. L'ordre des
opérations est celui du script Pygame d'origine :

1. créer un réseau par génome, remettre la fitness à zéro, créer une voiture ;
2. pour chaque voiture : activer le réseau, appliquer l'action, avancer ;
3. cumuler la récompense, arrêter quand plus aucune voiture n'est en vie ;
4. arrêter au bout de ``max_frames`` frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import neat
import pygame

from . import settings
from .car import Car
from .track import Track


@dataclass(frozen=True)
class GenerationResult:
    """Bilan d'une génération évaluée."""

    frames: int
    alive_at_end: int
    fitnesses: tuple[float, ...]

    @property
    def best_fitness(self) -> float:
        return max(self.fitnesses) if self.fitnesses else 0.0

    @property
    def mean_fitness(self) -> float:
        return sum(self.fitnesses) / len(self.fitnesses) if self.fitnesses else 0.0


class FrameObserver(Protocol):
    """Crochet d'observation (contrôle de la boucle et envoi des frames)."""

    def before_step(self) -> None:
        """Appelé avant chaque frame ; peut lever pour interrompre."""

    def on_frame(self, cars: Sequence[Car], alive: int, frames: int) -> None:
        """Appelé après chaque frame tant que la génération continue."""


class GenerationEvaluator:
    """Évalue une liste de génomes sur une carte donnée."""

    __slots__ = ("track", "sprite", "max_frames")

    def __init__(
        self,
        track: Track,
        sprite: pygame.Surface,
        max_frames: int = settings.GENERATION_MAX_FRAMES,
    ) -> None:
        self.track = track
        self.sprite = sprite
        self.max_frames = max_frames

    def create_population(
        self, genomes: Sequence[tuple[int, neat.DefaultGenome]], config: neat.Config
    ) -> tuple[list[neat.nn.FeedForwardNetwork], list[Car]]:
        """Réseaux et voitures, dans l'ordre exact des génomes."""
        nets: list[neat.nn.FeedForwardNetwork] = []
        cars: list[Car] = []
        for _, genome in genomes:
            nets.append(neat.nn.FeedForwardNetwork.create(genome, config))
            genome.fitness = 0
            cars.append(Car(self.sprite, self.track))
        return nets, cars

    def evaluate(
        self,
        genomes: Sequence[tuple[int, neat.DefaultGenome]],
        config: neat.Config,
        observer: FrameObserver | None = None,
    ) -> GenerationResult:
        nets, cars = self.create_population(genomes, config)

        counter = 0
        still_alive = 0

        while True:
            if observer is not None:
                observer.before_step()

            # 1. Décision du réseau puis application de l'action.
            for index, car in enumerate(cars):
                output = nets[index].activate(car.get_data())
                choice = output.index(max(output))
                car.apply_action(choice)

            # 2. Physique et récompense des voitures encore en vie.
            still_alive = 0
            for index, car in enumerate(cars):
                if car.is_alive():
                    still_alive += 1
                    car.update(self.track)
                    genomes[index][1].fitness += car.get_reward()

            if still_alive == 0:
                break

            counter += 1
            if counter == self.max_frames:
                break

            if observer is not None:
                observer.on_frame(cars, still_alive, counter)

        fitnesses = tuple(float(genome.fitness or 0.0) for _, genome in genomes)
        return GenerationResult(frames=counter, alive_at_end=still_alive, fitnesses=fitnesses)
