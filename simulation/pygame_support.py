"""Initialisation de Pygame en mode « headless ».

Pygame n'est plus utilisé pour afficher la simulation (c'est le navigateur qui
s'en charge) mais reste le moteur de vérité pour deux choses critiques :

* le chargement des PNG et les requêtes pixel ``Surface.get_at`` utilisées par
  la détection de collision et les radars ;
* la rotation des sprites (``pygame.transform.rotate``), identique à l'original.

Le pilote vidéo « dummy » évite d'avoir besoin d'un écran ou d'un serveur X.
"""

from __future__ import annotations

import os

# Doit être défini AVANT l'import de pygame (sinon le message de bienvenue
# s'affiche dans les logs du serveur web).
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (import volontairement après les variables d'env)

from . import settings  # noqa: E402

_initialised = False


def ensure_headless_display() -> None:
    """Initialise Pygame et une surface d'affichage 1x1 invisible.

    Une surface d'affichage est indispensable pour que ``Surface.convert()``
    fonctionne : l'original convertissait la carte et le sprite pour accélérer
    les accès pixel, on conserve donc exactement la même démarche.
    """
    global _initialised
    if _initialised:
        return
    pygame.init()
    # Surface minimale : aucun rendu n'est fait côté serveur.
    pygame.display.set_mode((1, 1))
    _initialised = True


_sprite_cache: pygame.Surface | None = None


def load_sprite() -> pygame.Surface:
    """Charge ``assets/car.png`` une seule fois et le met à l'échelle 60x60.

    Le sprite est partagé entre toutes les voitures : ``rotate_center`` renvoie
    toujours une nouvelle surface et ne modifie jamais celle-ci.
    """
    global _sprite_cache
    if _sprite_cache is None:
        ensure_headless_display()
        sprite = pygame.image.load(str(settings.CAR_SPRITE_PATH)).convert_alpha()
        _sprite_cache = pygame.transform.scale(
            sprite, (settings.CAR_SIZE_X, settings.CAR_SIZE_Y)
        )
    return _sprite_cache


_rotation_cache: dict[tuple[int, int], pygame.Surface] = {}


def rotated_sprite(angle: int | float) -> pygame.Surface:
    """Sprite tourné, mis en cache.

    ``rotate_center`` recalcule la rotation de chaque voiture à chaque frame
    (30 voitures x 60 fps). Les angles étant des multiples de 10 degrés, un
    cache rend le même pixel pour le même angle : optimisation pure, aucun
    impact sur la simulation.
    """
    key = (settings.CAR_SIZE_X, int(angle) % 360)
    cached = _rotation_cache.get(key)
    if cached is None:
        cached = _rotate_center(load_sprite(), key[1])
        _rotation_cache[key] = cached
    return cached


def _rotate_center(image: pygame.Surface, angle: float) -> pygame.Surface:
    """Rotation autour du centre en conservant la taille d'origine.

    Reproduit à l'identique ``Car.rotate_center`` du script original.
    """
    rectangle = image.get_rect()
    rotated_image = pygame.transform.rotate(image, angle)
    rotated_rectangle = rectangle.copy()
    rotated_rectangle.center = rotated_image.get_rect().center
    return rotated_image.subsurface(rotated_rectangle).copy()
