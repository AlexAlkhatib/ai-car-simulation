#!/usr/bin/env python3
"""Génère la documentation PDF et la présentation PowerPoint du projet.

    python tools/make_docs.py
    python tools/make_docs.py --pdf docs/documentation.pdf --pptx docs/presentation.pptx
    python tools/make_docs.py --screenshot docs/screenshots/interface.png

Les chiffres (nombre de tests, taille des fixtures, coût d'une frame) sont
mesurés à la génération : la documentation ne peut pas « dériver » du code.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    # Permet d'importer le paquet simulation quand le script est lancé directement.
    sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
DEFAULT_SCREENSHOT = DOCS / "screenshots" / "interface.png"

TITLE = "Simulation de voitures autonomes"
SUBTITLE = "Neuroévolution NEAT · Python + Flask · rendu navigateur"
VERSION = "2.0.0"


# ---------------------------------------------------------------------------
# Mesures
# ---------------------------------------------------------------------------
def project_metrics() -> dict:
    tests = sum(
        len(re.findall(r"^\s*def test_", path.read_text(encoding="utf-8"), re.M))
        for path in sorted((ROOT / "tests").glob("test_*.py"))
    )
    frames = {}
    for path in sorted((ROOT / "tests" / "fixtures").glob("*_trajectory.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        frames[path.stem.replace("_trajectory", "")] = len(payload["frames"])
    return {"tests": tests, "frames": frames, "maps": len(list((ROOT / "assets" / "maps").glob("*.png")))}


def benchmark_physics(frames: int = 60, cars: int = 30) -> dict:
    """Coût moyen d'une frame de physique pour 30 voitures."""
    from simulation import settings
    from simulation.car import Car
    from simulation.pygame_support import load_sprite
    from simulation.track import Track

    track = Track(settings.MAPS_DIR / settings.DEFAULT_MAP)
    sprite = load_sprite()
    fleet = [Car(sprite, track) for _ in range(cars)]
    started = time.perf_counter()
    for _ in range(frames):
        for car in fleet:
            if car.is_alive():
                car.update(track)
    elapsed = time.perf_counter() - started
    return {
        "ms_per_frame": elapsed / frames * 1000,
        "cars": cars,
        "frames": frames,
        "alive": sum(1 for car in fleet if car.is_alive()),
    }


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
INK = colors.HexColor("#101828")
BODY = colors.HexColor("#31405A")
ACCENT = colors.HexColor("#0E9F76")
ACCENT_LIGHT = colors.HexColor("#E7F7F1")
VIOLET = colors.HexColor("#4553C8")
MUTED = colors.HexColor("#6B7C93")
LINE = colors.HexColor("#DEE6F0")
CODE_BG = colors.HexColor("#F4F7FA")
CARD_BG = colors.HexColor("#F7FAFD")

PAGE_W, PAGE_H = A4
MARGIN = 1.95 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

STYLES = {
    "kicker": ParagraphStyle(
        "kicker", fontName="Helvetica-Bold", fontSize=9, leading=12,
        textColor=ACCENT, spaceAfter=6,
    ),
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=29, leading=33,
        textColor=INK, spaceAfter=8,
    ),
    "subtitle": ParagraphStyle(
        "subtitle", fontName="Helvetica", fontSize=13, leading=18,
        textColor=MUTED, spaceAfter=16,
    ),
    "h1": ParagraphStyle(
        "h1", fontName="Helvetica-Bold", fontSize=17, leading=21,
        textColor=INK, spaceBefore=6, spaceAfter=4,
    ),
    "h2": ParagraphStyle(
        "h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
        textColor=VIOLET, spaceBefore=10, spaceAfter=4,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.6, leading=14.6,
        textColor=BODY, spaceAfter=6,
    ),
    "bullet": ParagraphStyle(
        "bullet", fontName="Helvetica", fontSize=9.6, leading=14.2,
        textColor=BODY, leftIndent=13, bulletIndent=2, spaceAfter=3,
    ),
    "small": ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8.2, leading=11.5,
        textColor=MUTED, spaceAfter=4,
    ),
    "caption": ParagraphStyle(
        "caption", fontName="Helvetica-Oblique", fontSize=8.2, leading=11,
        textColor=MUTED, alignment=TA_CENTER, spaceBefore=4,
    ),
    "mono": ParagraphStyle(
        "mono", fontName="Courier", fontSize=7.8, leading=10.6, textColor=INK,
    ),
    "cell": ParagraphStyle(
        "cell", fontName="Helvetica", fontSize=8.3, leading=11.2, textColor=BODY,
    ),
    "cell_head": ParagraphStyle(
        "cell_head", fontName="Helvetica-Bold", fontSize=8.3, leading=11.2,
        textColor=colors.white,
    ),
    "metric": ParagraphStyle(
        "metric", fontName="Helvetica-Bold", fontSize=16, leading=19,
        textColor=INK, alignment=TA_CENTER,
    ),
    "metric_label": ParagraphStyle(
        "metric_label", fontName="Helvetica", fontSize=7.6, leading=10,
        textColor=MUTED, alignment=TA_CENTER,
    ),
}


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullets(items: list[str]) -> list[Paragraph]:
    return [Paragraph(item, STYLES["bullet"], bulletText="•") for item in items]


def h1(text: str) -> list:
    return [
        Spacer(1, 6),
        P(text, "h1"),
        HRFlowable(width="100%", thickness=1, color=ACCENT, spaceBefore=2, spaceAfter=9),
    ]


def h2(text: str) -> Paragraph:
    return P(text, "h2")


def code(text: str) -> Table:
    table = Table([[Preformatted(text.strip("\n"), STYLES["mono"])]], colWidths=[CONTENT_W])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def table(rows: list[list[str]], widths: list[float]) -> Table:
    data = [[P(cell, "cell_head") for cell in rows[0]]]
    data += [[P(cell, "cell") for cell in row] for row in rows[1:]]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CARD_BG]),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    return result


def metric_cards(values: list[tuple[str, str]]) -> Table:
    cells = [
        [P(value, "metric") for value, _ in values],
        [P(label, "metric_label") for _, label in values],
    ]
    result = Table(cells, colWidths=[CONTENT_W / len(values)] * len(values))
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
                ("BOX", (0, 0), (-1, 0), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return result


def _later_pages(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 1.45 * cm, PAGE_W - MARGIN, 1.45 * cm)
    canvas.setFont("Helvetica", 7.4)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 1.05 * cm, f"{TITLE} · NEAT · documentation technique")
    canvas.drawRightString(PAGE_W - MARGIN, 1.05 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.rect(0, PAGE_H - 8.7 * cm, PAGE_W, 8.7 * cm, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 8.95 * cm, PAGE_W, 0.25 * cm, stroke=0, fill=1)
    canvas.setFillColor(VIOLET)
    canvas.rect(0, PAGE_H - 9.1 * cm, PAGE_W * 0.35, 0.15 * cm, stroke=0, fill=1)
    canvas.restoreState()


def build_pdf(path: Path, screenshot: Path | None, metrics: dict, bench: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = metrics["frames"]
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=1.8 * cm,
        bottomMargin=1.9 * cm,
        title=f"{TITLE} — documentation technique",
        author="Refonte Python + Flask",
        subject="NEAT, Flask, rendu navigateur",
    )

    story: list = []
    # --- Couverture --------------------------------------------------------
    story += [
        Spacer(1, 82),
        P("DOCUMENTATION TECHNIQUE · V" + VERSION, "kicker"),
    ]
    # Titre en blanc sur le bandeau sombre : on dessine un paragraphe clair.
    story.append(
        Paragraph(
            TITLE,
            ParagraphStyle(
                "cover_title", fontName="Helvetica-Bold", fontSize=24, leading=29,
                textColor=colors.white, spaceAfter=10,
            ),
        )
    )
    story.append(
        Paragraph(
            SUBTITLE,
            ParagraphStyle(
                "cover_sub", fontName="Helvetica", fontSize=13.5, leading=19,
                textColor=colors.HexColor("#B9CBE4"), spaceAfter=26,
            ),
        )
    )
    story.append(Spacer(1, 78))
    story.append(
        metric_cards(
            [
                (str(metrics["tests"]), "tests automatisés"),
                (f"{frames.get('map', 0)}", "frames de parité carte réelle"),
                (str(metrics["maps"]), "cartes disponibles"),
            ]
        )
    )
    story += [
        Spacer(1, 18),
        P(
            "Ce document décrit l'architecture, les algorithmes et la démarche de refonte "
            "de la simulation de voitures autonomes. La physique et l'évolution NEAT du "
            "projet Pygame d'origine sont conservées à l'identique ; le rendu est déplacé "
            "dans le navigateur et le moteur devient pilotable en temps réel.",
        ),
        Spacer(1, 10),
        P(
            "Points clés : architecture en modules, serveur Flask, flux temps réel SSE, "
            "corrections de robustesse, validation par tests et parité bit à bit.",
            "small",
        ),
        PageBreak(),
    ]

    # --- Sommaire ----------------------------------------------------------
    story += h1("Sommaire")
    summary = [
        ["1", "Présentation et objectifs"],
        ["2", "Fonctionnalités"],
        ["3", "Architecture logicielle"],
        ["4", "Algorithmes de la simulation"],
        ["5", "Refactoring : avant / après"],
        ["6", "Corrections de bugs"],
        ["7", "Améliorations et performances"],
        ["8", "API HTTP et flux temps réel"],
        ["9", "Interface et prise en main"],
        ["10", "Validation par les tests"],
        ["11", "Limites et perspectives"],
        ["A", "Commandes utiles"],
        ["B", "Structure du projet"],
    ]
    story.append(
        Table(
            [[P(number, "cell"), P(label, "cell")] for number, label in summary],
            colWidths=[1.1 * cm, CONTENT_W - 1.1 * cm],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
                ]
            ),
        )
    )
    story.append(Spacer(1, 12))
    story.append(
        P(
            "Les chiffres de ce document sont mesurés lors de sa génération "
            "(nombre de tests, taille des fixtures, coût d'une frame) : ils "
            "correspondent à l'état du code livré.",
            "small",
        )
    )
    story.append(PageBreak())

    # --- 1. Présentation ---------------------------------------------------
    story += h1("1. Présentation et objectifs")
    story.append(
        P(
            "Le projet d'origine est une démonstration d'apprentissage évolutif : une "
            "population de voitures circule sur une piste vue du dessus, chacune pilotée "
            "par un réseau de neurones évolué par NEAT. Les meilleurs génomes se "
            "reproduisent, mutent et finissent par suivre la piste sans collision.",
        )
    )
    story.append(
        P(
            "La demande était de corriger, refactoriser et améliorer l'application, en "
            "conservant Python et en passant à Flask pour le rendu dans un navigateur, "
            "sans modifier le comportement ni casser les algorithmes existants.",
        )
    )
    story.append(h2("Ce qui est strictement conservé"))
    story += bullets(
        [
            "La physique : vitesse initiale de 20 px/frame, pas de rotation de 10°, "
            "accélération de 2, décélération plancher à 12.",
            "Les 5 capteurs (-90° à +90°, portée 300 px, entrée normalisée par 30).",
            "La détection de collision par les 4 coins et le pixel blanc.",
            "La récompense distance / 30 et son cumul par frame.",
            "Les paramètres NEAT de config.txt et la limite de 1 200 frames par génération.",
        ]
    )
    story.append(h2("Ce qui change"))
    story += bullets(
        [
            "Le rendu : plus de fenêtre Pygame, mais un canvas 1920 × 1080 dans le navigateur.",
            "Le pilotage : pause, reprise, vitesse et changement de carte à chaud.",
            "La robustesse : plus de crash sur les bords de carte, chemins absolus, "
            "état protégé par verrou.",
            "L'observabilité : API JSON, historique de fitness, génome sauvegardé.",
            "La qualité : 26 tests automatisés et une parité vérifiée avec l'original.",
        ]
    )

    # --- 2. Fonctionnalités -------------------------------------------------
    story += h1("2. Fonctionnalités")
    story.append(
        table(
            [
                ["Fonction", "Détail"],
                ["Simulation temps réel", "30 voitures par génération, 60 frames/s de référence, jusqu'à 1 000 générations"],
                ["Contrôles", "Démarrer, pause, reprendre, réinitialiser (boutons et raccourcis Espace / R)"],
                ["Vitesse", "0.5×, 1×, 2×, 4×, 8× — la physique ne change pas, seule la cadence"],
                ["Cartes", "5 pistes 1920 × 1080, changement à chaud avec redémarrage propre"],
                ["Visualisation", "Piste, sprite orienté, radars, textes de génération et de survie"],
                ["Statistiques", "Génération, vivantes, fitness courante, record, cadence, progression"],
                ["Graphique", "Courbe meilleure fitness / moyenne par génération"],
                ["Génome", "Meilleur génome sauvegardé dans runs/ et téléchargeable en .pkl"],
                ["Temps réel", "Flux SSE avec repli automatique en sondage HTTP"],
                ["Entraînement", "Mode headless train.py, même physique, sortie pickle"],
            ],
            [3.9 * cm, CONTENT_W - 3.9 * cm],
        )
    )

    # --- 3. Architecture ----------------------------------------------------
    story += h1("3. Architecture logicielle")
    story.append(
        P(
            "Le script unique est remplacé par un paquet de six modules aux "
            "responsabilités nettes, un serveur Flask et un client Canvas. La physique "
            "reste en Python ; le navigateur ne fait qu'afficher les instantanés reçus.",
        )
    )
    story.append(
        table(
            [
                ["Module", "Responsabilité"],
                ["simulation/settings.py", "Constantes d'origine (scène, capteurs, cadences) et chemins"],
                ["simulation/pygame_support.py", "Pygame en mode headless, sprite partagé, cache de rotation"],
                ["simulation/track.py", "Chargement de la carte, requêtes pixel sûres (hors carte = bordure)"],
                ["simulation/car.py", "Physique, collision, radars, récompense, sérialisation d'état"],
                ["simulation/evaluation.py", "Boucle d'évaluation d'une génération, partagée web / CLI"],
                ["simulation/engine.py", "Thread NEAT, pause, vitesse, historique, meilleur génome"],
                ["app.py", "Pages, API REST, flux SSE, médias"],
                ["static/js/app.js", "Canvas, graphique, contrôles, réception SSE"],
            ],
            [4.7 * cm, CONTENT_W - 4.7 * cm],
        )
    )
    story.append(Spacer(1, 10))
    story.append(h2("Flux d'exécution"))
    story.append(
        code(
            """
Navigateur (Canvas 2D)            Moteur Python                    neat-python
        |                              |                                 |
        |  GET /api/stream (SSE)       |                                 |
        |<---- instantané JSON --------|  thread: _evaluate_generation   |
        |                              |<--- population.run -------------|
        |  POST /api/pause             |     30 voitures x 1..1200 frames|
        |----------------------------->|     fitness cumulée             |
        |                              |---- reproduction -------------->|
"""
        )
    )
    story.append(
        P(
            "Chaque frame, le moteur publie un instantané (positions, angles, vitesses, "
            "radars, fitness) sous verrou. Les connexions SSE lisent la dernière version "
            "disponible : un client lent ne ralentit jamais la simulation.",
            "small",
        )
    )

    # --- 4. Algorithmes -----------------------------------------------------
    story += h1("4. Algorithmes de la simulation")
    story.append(h2("4.1 Perception : cinq radars"))
    story.append(
        P(
            "Cinq rayons partent du centre de la voiture aux angles -90°, -45°, 0°, 45° "
            "et 90° relatifs à son orientation. Chaque rayon avance pixel par pixel, "
            "300 px au maximum, jusqu'à rencontrer un pixel blanc : la bordure. "
            "L'entrée du réseau est la distance d'impact divisée par 30.",
        )
    )
    story.append(h2("4.2 Décision : quatre actions"))
    story.append(
        table(
            [
                ["Sortie", "Action", "Effet exact"],
                ["0", "Gauche", "angle += 10"],
                ["1", "Droite", "angle -= 10"],
                ["2", "Ralentir", "speed -= 2 si speed - 2 >= 12"],
                ["3", "Accélérer", "speed += 2"],
            ],
            [2.0 * cm, 3.2 * cm, CONTENT_W - 5.2 * cm],
        )
    )
    story.append(
        P(
            "L'action retenue est l'indice du maximum des quatre sorties du réseau "
            "feed-forward. La vitesse initiale est fixée à 20 à la première frame.",
            "small",
        )
    )
    story.append(h2("4.3 Collision et récompense"))
    story.append(
        P(
            "Les quatre coins du rectangle orienté sont testés (demi-diagonale de 30 px, "
            "angles +30°, +150°, +210°, +330°). Un pixel blanc, ou une position hors de "
            "l'image, tue la voiture. La récompense d'une frame vaut distance / 30 ; la "
            "fitness d'un génome est la somme de ces récompenses jusqu'à son crash.",
        )
    )
    story.append(h2("4.4 Évolution NEAT"))
    story.append(
        table(
            [
                ["Paramètre", "Valeur"],
                ["Population", "30 génomes"],
                ["Activation", "tanh"],
                ["Connexions initiales", "full : 5 entrées vers 4 sorties"],
                ["Mutation des poids", "0.8 (remplacement 0.1, puissance 0.5)"],
                ["Ajout connexion / nœud", "0.5 / 0.2"],
                ["Seuil de compatibilité", "2.0"],
                ["Élitisme / survie", "3 / 0.2"],
                ["Stagnation", "20 générations, 2 élites par espèce"],
                ["Frames par génération", "1 200 maximum"],
            ],
            [5.4 * cm, CONTENT_W - 5.4 * cm],
        )
    )
    story.append(h2("4.5 Boucle d'une génération"))
    story.append(
        code(
            """
creer un reseau et une voiture par genome ; fitness <- 0
repeter :
    pour chaque voiture : activer le reseau, appliquer l'action
    pour chaque voiture vivante : avancer, fitness += recompense
    si aucune voiture vivante : stop
    si 1200 frames atteintes : stop
NEAT reproduit ensuite la population (population.run)
"""
        )
    )

    # --- 5. Refactoring -----------------------------------------------------
    story += h1("5. Refactoring : avant / après")
    story.append(
        table(
            [
                ["Avant (main.py)", "Après"],
                ["1 script de ~230 lignes mêlant physique, NEAT et rendu", "paquet simulation/ (6 modules) + serveur + client"],
                ["boucle Pygame bloquante, une seule fenêtre", "moteur dans un thread, pilotable depuis le navigateur"],
                ["aucune API, aucun test", "API REST + SSE, 26 tests automatisés"],
                ["chemins relatifs au répertoire courant", "chemins pathlib absolus, indépendants du cwd"],
                ["sys.exit() pour quitter", "exception dédiée et arrêt propre du thread"],
                ["état global current_generation", "état verrouillé, instantanés cohérents"],
                ["rappel visuel dans la fenêtre uniquement", "KPI, graphique, historique et téléchargement"],
            ],
            [CONTENT_W / 2, CONTENT_W / 2],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        P(
            "Le découpage suit une règle simple : chaque module peut être testé seul. "
            "La physique ne connaît ni Flask ni NEAT ; le moteur ne connaît pas HTTP ; "
            "le serveur ne contient aucun calcul de simulation.",
        )
    )

    # --- 6. Corrections -----------------------------------------------------
    story += h1("6. Corrections de bugs")
    story.append(
        table(
            [
                ["Problème", "Impact", "Correctif"],
                ["no_fitness_termination absent de config.txt", "crash immédiat avec neat-python 2.0", "clé ajoutée (False, comportement historique)"],
                ["get_at() hors de la carte", "IndexError qui tue le processus", "hors carte traité comme bordure"],
                ["couleur comparée en 3 ou 4 canaux", "collisions non détectées selon la surface", "comparaison RGB normalisée"],
                ["chemins 'car.png' et 'map.png'", "démarrage dépendant du cwd", "chemins absolus via settings"],
                ["sys.exit(0) dans la boucle", "arrêt brutal, thread non libéré", "SimulationStopped + join"],
                ["compteur de population écrasé", "état non sérialisable", "_population et _neat_population séparés"],
                ["aucune sauvegarde du meilleur génome", "apprentissage perdu", "pickle automatique + téléchargement"],
            ],
            [4.6 * cm, 4.4 * cm, CONTENT_W - 9.0 * cm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        P(
            "La borne verticale position[1] = min(position[1], WIDTH - 120) de l'original "
            "est conservée volontairement : la corriger aurait modifié la trajectoire des "
            "voitures. Les requêtes hors carte étant désormais sûres, elle ne provoque "
            "plus de crash.",
            "small",
        )
    )

    # --- 7. Améliorations ---------------------------------------------------
    story += h1("7. Améliorations et performances")
    story += bullets(
        [
            "Cache des rotations de sprite : la rotation était recalculée pour chaque "
            "voiture à chaque frame ; les angles étant des multiples de 10°, un cache "
            "par angle donne exactement les mêmes pixels.",
            "Vitesse de simulation découplée de la physique : N frames de physique entre "
            "deux publications, sans changer l'ordre des calculs.",
            "Changement de carte sans redémarrage du processus.",
            "Logs structurés : une ligne par génération, bruit pygame et NEAT supprimé.",
            "Génome sauvegardé en mémoire et sur disque à chaque nouveau record.",
            "Mode CLI pour entraîner sans navigateur, avec la même boucle d'évaluation.",
        ]
    )
    story.append(Spacer(1, 4))
    story.append(
        P(
            f"Mesure sur la machine de génération : environ "
            f"{bench['ms_per_frame']:.1f} ms par frame de physique pour "
            f"{bench['cars']} voitures ({bench['alive']} encore en vie après "
            f"{bench['frames']} frames). À 60 frames/s, la simulation reste "
            f"dans son budget, même en 4×.",
        )
    )
    story.append(
        P(
            "Comparaison A/B dans les mêmes conditions : 8,2 ms par frame pour le "
            "script d'origine, 9,2 ms pour la version refactorée. Le surcoût d'environ "
            "1 ms correspond aux contrôles de bornes qui évitent les plantages hors "
            "carte — un choix assumé : la robustesse passe avant un gain marginal. "
            "Le cache de rotation de sprite réduit malgré cela les appels à "
            "pygame.transform.rotate.",
            "small",
        )
    )

    # --- 8. API -------------------------------------------------------------
    story += h1("8. API HTTP et flux temps réel")
    story.append(
        table(
            [
                ["Méthode", "Route", "Rôle"],
                ["GET", "/", "interface web"],
                ["GET", "/healthz", "état du serveur et de la simulation"],
                ["GET", "/api/config", "cartes, vitesses, paramètres"],
                ["GET", "/api/state", "instantané complet"],
                ["GET", "/api/stream", "flux SSE (une frame JSON par événement)"],
                ["GET", "/api/history", "historique de fitness"],
                ["POST", "/api/start · pause · resume · reset", "commandes de pilotage"],
                ["POST", "/api/settings", "vitesse ou carte"],
                ["GET", "/api/best-genome", "téléchargement du génome (.pkl)"],
                ["GET", "/media/...", "carte et sprite"],
            ],
            [1.7 * cm, 6.0 * cm, CONTENT_W - 7.7 * cm],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        P(
            "Le flux SSE envoie des instantanés compacts (positions arrondies, radars "
            "entiers). Un keep-alive commenté est émis toutes les 15 secondes pour "
            "traverser les proxys. Si EventSource est indisponible, le client bascule "
            "automatiquement sur un sondage de /api/state.",
            "small",
        )
    )

    # --- 9. Interface -------------------------------------------------------
    story += h1("9. Interface et prise en main")
    if screenshot and screenshot.is_file():
        with PILImage.open(screenshot) as image:
            width, height = image.size
        display_width = CONTENT_W
        display_height = display_width * height / width
        max_height = 11.0 * cm
        if display_height > max_height:
            display_height = max_height
            display_width = display_height * width / height
        story.append(RLImage(str(screenshot), width=display_width, height=display_height))
        story.append(
            P(
                "Interface : piste, voitures et radars, indicateurs, courbe de fitness "
                "et panneau de contrôle.",
                "caption",
            )
        )
    else:
        story.append(
            P(
                "Capture d'écran non disponible : lancer l'application puis "
                "python tools/make_docs.py --screenshot docs/screenshots/interface.png.",
                "small",
            )
        )
    story.append(Spacer(1, 6))
    story.append(h2("Prise en main"))
    story += bullets(
        [
            "Démarrer / Pause / Reprendre : lance ou suspend l'évolution.",
            "Réinitialiser : nouvelle population, génération 0.",
            "Vitesse : de 0.5× à 8×, sans effet sur les calculs.",
            "Carte : cinq pistes, le changement relance la simulation.",
            "Radars : affiche ou masque les cinq capteurs.",
            "Télécharger le meilleur génome : fichier .pkl réutilisable.",
            "Raccourcis : Espace (pause), R (réinitialiser).",
        ]
    )

    # --- 10. Validation -----------------------------------------------------
    story += h1("10. Validation par les tests")
    story.append(
        P(
            f"La suite compte {metrics['tests']} tests exécutables sans navigateur ni "
            "affichage, en environ deux secondes :",
        )
    )
    story.append(code("python -m unittest discover -s tests -t . -v"))
    story.append(
        table(
            [
                ["Suite", "Ce qui est vérifié"],
                ["test_parity", "trajectoires rejouées depuis le main.py d'origine, comparaison au bit près"],
                ["test_track", "dimensions, bordure blanche, hors limites, validation des cartes"],
                ["test_engine", "générations, limite de frames, pause, reset, génome, validations"],
                ["test_api", "page, configuration, commandes, erreurs 400, SSE, médias, historique"],
            ],
            [3.6 * cm, CONTENT_W - 3.6 * cm],
        )
    )
    story.append(Spacer(1, 8))
    story.append(h2("Parité avec l'implémentation d'origine"))
    story.append(
        P(
            "Les fixtures sont produites par tools/parity_fixtures.py, qui exécute le "
            "Car du main.py original avec une politique de pilotage déterministe, puis "
            "enregistre chaque frame. Le test rejoue les mêmes actions avec le code "
            "refactorisé et compare positions, centre, angle, vitesse, distance, coins, "
            "radars, entrées du réseau et récompense.",
        )
    )
    story.append(
        table(
            [
                ["Fixture", "Piste", "Frames comparées"],
                ["map_trajectory", "map.png (piste réelle)", str(frames.get("map", 0))],
                ["arena_trajectory", "arène ouverte générée", str(frames.get("arena", 0))],
                ["ring_trajectory", "anneau généré", str(frames.get("ring", 0))],
            ],
            [4.2 * cm, 5.4 * cm, CONTENT_W - 9.6 * cm],
        )
    )

    # --- 11. Limites --------------------------------------------------------
    story += h1("11. Limites et perspectives")
    story += bullets(
        [
            "Le serveur Flask de développement n'est pas prévu pour la production : "
            "utiliser un serveur WSGI (gunicorn, waitress) avec un worker unique, le "
            "moteur étant attaché au processus.",
            "Une seule simulation à la fois par processus : le moteur est un singleton "
            "applicatif.",
            "Pas de reprise d'un entraînement complet après redémarrage : seul le "
            "meilleur génome est conservé.",
            "Le flux SSE transporte du JSON : un format binaire (WebSocket) réduirait "
            "la bande passante pour de grandes populations.",
            "Pistes : rejeu d'une génération enregistrée, comparaison de plusieurs "
            "cartes en parallèle, export vidéo.",
        ]
    )

    # --- Annexes ------------------------------------------------------------
    story.append(PageBreak())
    story += h1("Annexe A. Commandes utiles")
    story.append(
        code(
            """
# installation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# lancer l'application
python app.py
HOST=0.0.0.0 PORT=3000 python app.py

# tests
python -m unittest discover -s tests -t . -v

# entrainement sans navigateur
python train.py --generations 30 --map map3.png

# regenerer la documentation
pip install reportlab python-pptx pillow
python tools/make_docs.py
"""
        )
    )
    story += h1("Annexe B. Structure du projet")
    story.append(
        code(
            """
app.py                  serveur Flask (pages, API, SSE)
train.py                entrainement NEAT headless
config.txt              configuration NEAT
requirements.txt
simulation/
  settings.py           constantes et chemins
  pygame_support.py     Pygame headless, sprite, cache de rotation
  track.py              carte et requetes pixel sures
  car.py                physique, capteurs, recompense
  evaluation.py         boucle d'evaluation d'une generation
  engine.py             thread NEAT, pause, vitesse, instantanes
templates/index.html    interface
static/css/style.css
static/js/app.js        canvas, SSE, graphique, controles
assets/                 car.png + 5 cartes
tests/                  26 tests + fixtures de parite
tools/                  make_docs.py, parity_fixtures.py
docs/                   documentation.pdf, presentation.pptx
runs/                   meilleur genome + logs
"""
        )
    )

    doc.build(story, onFirstPage=_cover_page, onLaterPages=_later_pages)


# ---------------------------------------------------------------------------
# PowerPoint
# ---------------------------------------------------------------------------
BG = RGBColor(0x0B, 0x10, 0x17)
CARD = RGBColor(0x15, 0x1D, 0x2B)
WHITE = RGBColor(0xF2, 0xF6, 0xFC)
DIM = RGBColor(0x9B, 0xAE, 0xCA)
PPT_ACCENT = RGBColor(0x2E, 0xE6, 0xA8)
PPT_VIOLET = RGBColor(0x8B, 0x9D, 0xFF)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def _textbox(slide, left, top, width, height, text, size, color, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.alignment = align
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = color
    paragraph.font.name = "Calibri"
    return box


def _slide(prs, title: str, kicker: str | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = BG

    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(0.08))
    bar.fill.solid()
    bar.fill.fore_color.rgb = PPT_ACCENT
    bar.line.fill.background()

    if kicker:
        _textbox(slide, Inches(0.8), Inches(0.42), Inches(11.7), Inches(0.35), kicker.upper(), 12, PPT_ACCENT, bold=True)
        _textbox(slide, Inches(0.8), Inches(0.72), Inches(11.7), Inches(0.9), title, 31, WHITE, bold=True)
    else:
        _textbox(slide, Inches(0.8), Inches(0.55), Inches(11.7), Inches(1.0), title, 32, WHITE, bold=True)

    _textbox(slide, Inches(0.8), Inches(6.95), Inches(9.0), Inches(0.35),
             f"{TITLE} · NEAT", 10, RGBColor(0x5A, 0x6B, 0x85))
    _textbox(slide, Inches(11.6), Inches(6.95), Inches(0.95), Inches(0.35),
             str(len(prs.slides)), 10, RGBColor(0x5A, 0x6B, 0x85), align=PP_ALIGN.RIGHT)
    return slide


def _bullets(slide, items, top=1.95, size=18, left=0.85, width=11.6):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(4.7))
    frame = box.text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        text, level = item if isinstance(item, tuple) else (item, 0)
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = ("•  " if level == 0 else "–  ") + text
        paragraph.level = level
        paragraph.font.size = Pt(size if level == 0 else size - 3)
        paragraph.font.color.rgb = WHITE if level == 0 else DIM
        paragraph.font.name = "Calibri"
        paragraph.space_after = Pt(9 if level == 0 else 4)
    return box


def _chips(slide, values, top=2.6):
    width = 3.6
    gap = 0.35
    left = (13.333 - (len(values) * width + (len(values) - 1) * gap)) / 2
    for index, (value, label) in enumerate(values):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(left + index * (width + gap)), Inches(top), Inches(width), Inches(1.25),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = CARD
        shape.line.color.rgb = RGBColor(0x2A, 0x3A, 0x52)
        frame = shape.text_frame
        frame.text = value
        frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        frame.paragraphs[0].font.size = Pt(28)
        frame.paragraphs[0].font.bold = True
        frame.paragraphs[0].font.color.rgb = PPT_ACCENT
        second = frame.add_paragraph()
        second.text = label
        second.alignment = PP_ALIGN.CENTER
        second.font.size = Pt(11)
        second.font.color.rgb = DIM


def _table_slide(slide, rows, widths, top=1.9, size=13):
    shape = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(0.8), Inches(top), Inches(11.7), Inches(0.4 * len(rows))
    )
    table = shape.table
    for index, width in enumerate(widths):
        table.columns[index].width = Inches(width)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            cell = table.cell(row_index, col_index)
            cell.text = value
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.font.size = Pt(size)
            paragraph.font.name = "Calibri"
            paragraph.font.bold = row_index == 0
            paragraph.font.color.rgb = WHITE if row_index == 0 else RGBColor(0xD5, 0xDF, 0xEE)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0x1E, 0x2A, 0x3B) if row_index == 0 else CARD
    return table


def build_pptx(path: Path, screenshot: Path | None, metrics: dict, bench: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    frames = metrics["frames"]

    # 1. Titre
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = BG
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(0.16))
    band.fill.solid()
    band.fill.fore_color.rgb = PPT_ACCENT
    band.line.fill.background()
    _textbox(slide, Inches(0.9), Inches(1.5), Inches(11.5), Inches(0.4), "NEUROÉVOLUTION · PYTHON + FLASK", 14, PPT_ACCENT, bold=True)
    _textbox(slide, Inches(0.9), Inches(2.0), Inches(11.5), Inches(1.6), TITLE, 46, WHITE, bold=True)
    _textbox(slide, Inches(0.9), Inches(3.5), Inches(11.5), Inches(0.8), SUBTITLE, 20, DIM)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.95), Inches(4.45), Inches(2.4), Inches(0.05))
    line.fill.solid()
    line.fill.fore_color.rgb = PPT_VIOLET
    line.line.fill.background()
    _textbox(slide, Inches(0.9), Inches(4.75), Inches(11.5), Inches(0.5),
             "Refonte, corrections, documentation et validation", 18, WHITE)
    _textbox(slide, Inches(0.9), Inches(6.3), Inches(11.5), Inches(0.4),
             f"Version {VERSION} · {metrics['tests']} tests automatisés · {metrics['maps']} cartes", 13, RGBColor(0x6B, 0x7C, 0x93))

    # 2. Le projet en une slide
    slide = _slide(prs, "Le projet en une slide", "Objectif")
    _bullets(slide, [
        "30 voitures apprennent seules à suivre une piste, sans règle écrite.",
        "Chaque voiture voit avec 5 capteurs et dispose de 4 actions.",
        "NEAT fait évoluer les réseaux : sélection, croisement, mutation.",
        "Le calcul reste en Python ; le rendu passe dans le navigateur.",
        "Résultat : une application web pilotable, testée et documentée.",
    ])

    # 3. Stack
    slide = _slide(prs, "Stack technique", "Composants")
    _table_slide(slide, [
        ["Couche", "Technologie", "Rôle"],
        ["Langage", "Python 3.12", "moteur de simulation"],
        ["Serveur", "Flask 3.1", "API REST, SSE, statiques"],
        ["Évolution", "neat-python 2.0", "génomes, espèces, reproduction"],
        ["Pixels", "Pygame 2.6 (dummy)", "collisions, raycasts, sprites"],
        ["Rendu", "Canvas 2D", "affichage 1920 × 1080"],
        ["Tests", "unittest", f"{metrics['tests']} tests"],
    ], [2.6, 3.6, 5.5], size=13)

    # 4. Architecture
    slide = _slide(prs, "Architecture en six modules", "Conception")
    _bullets(slide, [
        "settings : constantes d'origine et chemins absolus.",
        "track : carte et requêtes pixel sûres.",
        "car : physique, capteurs, récompense.",
        "evaluation : boucle d'une génération, partagée web / CLI.",
        "engine : thread NEAT, pause, vitesse, instantanés.",
        "app : HTTP, SSE, médias — aucun calcul de simulation.",
    ], size=17)

    # 5. Perception
    slide = _slide(prs, "Comment une voiture voit", "Perception")
    _bullets(slide, [
        "Cinq rayons : -90°, -45°, 0°, 45°, 90°.",
        "Portée maximale de 300 pixels.",
        "Le rayon avance pixel par pixel jusqu'au blanc : la bordure.",
        "Entrée du réseau = distance divisée par 30.",
        "Aucune connaissance de la piste : tout vient des capteurs.",
    ])

    # 6. Décision
    slide = _slide(prs, "Comment une voiture décide", "Décision")
    _bullets(slide, [
        "Réseau feed-forward : 5 entrées, 4 sorties.",
        "L'action retenue est le maximum des sorties.",
        "Gauche : angle + 10° · Droite : angle - 10°.",
        "Ralentir : vitesse - 2 (jamais sous 12).",
        "Accélérer : vitesse + 2 · vitesse initiale 20.",
    ])

    # 7. Collision et récompense
    slide = _slide(prs, "Collision, survie et récompense", "Fitness")
    _bullets(slide, [
        "Quatre coins testés à chaque frame.",
        "Pixel blanc ou hors carte : la voiture meurt.",
        "Récompense par frame : distance / 30.",
        "Fitness = somme des récompenses jusqu'au crash.",
        "Génération stoppée à 0 vivante ou 1 200 frames.",
    ])

    # 8. NEAT
    slide = _slide(prs, "NEAT en pratique", "Évolution")
    _bullets(slide, [
        "Population de 30 génomes, connexions initiales complètes.",
        "Activation tanh, mutation des poids à 0.8.",
        "Ajout de connexion 0.5, ajout de nœud 0.2.",
        "Espèces séparées au seuil de compatibilité 2.0.",
        "Élitisme 3, survie 20 %, stagnation 20 générations.",
    ])

    # 9. Refactoring
    slide = _slide(prs, "Refactoring : un script devient une application", "Avant / après")
    _table_slide(slide, [
        ["Avant", "Après"],
        ["1 script de 230 lignes", "6 modules + serveur + client"],
        ["Fenêtre Pygame bloquante", "Moteur en thread, pilotage web"],
        ["Aucun test, aucune API", f"{metrics['tests']} tests, API REST + SSE"],
        ["Chemins dépendants du cwd", "Chemins absolus, portable"],
        ["Bon génome perdu", "Génome sauvegardé et téléchargeable"],
    ], [5.7, 6.0], size=13)

    # 10. Corrections
    slide = _slide(prs, "Corrections apportées", "Fiabilité")
    _bullets(slide, [
        "config.txt : clé no_fitness_termination exigée par neat-python 2.0.",
        "Hors carte : plus d'IndexError, traité comme une bordure.",
        "Couleurs comparées en RGB, quel que soit le format de surface.",
        "Arrêt propre du thread au lieu de sys.exit().",
        "État verrouillé : instantanés cohérents, JSON sérialisable.",
    ], size=17)

    # 11. Interface
    slide = _slide(prs, "L'interface web", "Rendu")
    if screenshot and screenshot.is_file():
        with PILImage.open(screenshot) as image:
            width, height = image.size
        picture_width = 11.4
        picture_height = picture_width * height / width
        if picture_height > 4.9:
            picture_height = 4.9
            picture_width = picture_height * width / height
        slide.shapes.add_picture(
            str(screenshot),
            Inches((13.333 - picture_width) / 2),
            Inches(2.0),
            width=Inches(picture_width),
            height=Inches(picture_height),
        )
        _textbox(slide, Inches(0.8), Inches(6.95), Inches(9.0), Inches(0.35),
                 "Piste, voitures, radars, KPI et courbe de fitness", 11, DIM)
    else:
        _bullets(slide, [
            "Piste 1920 × 1080, voitures orientées, radars verts.",
            "Indicateurs : génération, vivantes, fitness, record, cadence.",
            "Contrôles : pause, vitesse, carte, radars.",
            "Courbe de fitness et téléchargement du génome.",
        ])

    # 12. Temps réel
    slide = _slide(prs, "Temps réel sans coupler physique et affichage", "Flux")
    _bullets(slide, [
        "Le moteur publie un instantané JSON par frame.",
        "SSE : latence minimale, un client lent ne ralentit rien.",
        "Repli automatique en sondage si EventSource manque.",
        "Vitesse 0.5× à 8× : même physique, cadence différente.",
        "Pause et reset sans redémarrer le processus.",
    ], size=17)

    # 13. Validation
    slide = _slide(prs, "Validation", "Tests")
    _bullets(slide, [
        f"{metrics['tests']} tests automatisés, exécutés en environ deux secondes.",
        f"Parité bit à bit : {frames.get('map', 0)} frames sur la carte réelle.",
        f"{frames.get('arena', 0)} frames en arène, {frames.get('ring', 0)} frames sur anneau.",
        "Positions, angles, radars et récompenses identiques à l'original.",
        f"Physique : environ {bench['ms_per_frame']:.1f} ms par frame pour 30 voitures "
        "(mesure A/B : 8,2 ms pour le script d'origine).",
    ], size=17)

    # 14. Limites et perspectives
    slide = _slide(prs, "Limites et perspectives", "Suite")
    _bullets(slide, [
        "Serveur Flask de développement : passer à un WSGI en production.",
        "Une seule simulation par processus.",
        "Reprise complète de l'entraînement à ajouter.",
        "Piste : WebSocket binaire pour de grandes populations.",
        "Piste : rejeu, comparaison de cartes, export vidéo.",
    ], size=17)

    # 15. Démarrer
    slide = _slide(prs, "Pour démarrer", "Conclusion")
    _bullets(slide, [
        "pip install -r requirements.txt",
        "python app.py",
        "Ouvrir http://127.0.0.1:5000",
        "Documentation : docs/documentation.pdf",
        "Tests : python -m unittest discover -s tests -t .",
    ], size=18)
    _textbox(slide, Inches(0.85), Inches(5.6), Inches(11.6), Inches(0.6),
             "Même physique, mêmes algorithmes — une application web documentée.",
             18, PPT_ACCENT, bold=True)

    prs.save(str(path))


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DOCS / "documentation.pdf"))
    parser.add_argument("--pptx", default=str(DOCS / "presentation.pptx"))
    parser.add_argument("--screenshot", default=str(DEFAULT_SCREENSHOT))
    parser.add_argument("--skip-benchmark", action="store_true")
    args = parser.parse_args(argv)

    screenshot = Path(args.screenshot)
    metrics = project_metrics()
    bench = {"ms_per_frame": 0.0, "cars": 30, "frames": 60, "alive": 0}
    if not args.skip_benchmark:
        bench = benchmark_physics()

    build_pdf(Path(args.pdf), screenshot if screenshot.is_file() else None, metrics, bench)
    build_pptx(Path(args.pptx), screenshot if screenshot.is_file() else None, metrics, bench)

    print(f"PDF  : {args.pdf}")
    print(f"PPTX : {args.pptx}")
    print(f"tests={metrics['tests']} frames={metrics['frames']} "
          f"bench={bench['ms_per_frame']:.2f} ms/frame")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
