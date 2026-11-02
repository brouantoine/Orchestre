"""Styles d'accompagnement : jeu de piano + rythme de batterie + paramètres.

Les rythmes sont écrits sur une grille de 16 doubles-croches par mesure de 4 temps.
Ce sont des bases fidèles aux conventions de chaque genre, à affiner avec des
musiciens de chaque style (voir TODO.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Notes General MIDI de la batterie
KICK, SIDESTICK, SNARE, CLAP = 36, 37, 38, 39
HH_CLOSED, HH_PEDAL, HH_OPEN = 42, 44, 46
TOM_LOW, TOM_MID, TOM_HIGH = 45, 47, 50
CRASH, RIDE, RIDE_BELL = 49, 51, 53
TAMBOURINE, COWBELL, SHAKER = 54, 56, 70

Pattern = dict[int, list[tuple[int, int]]]  # instrument -> [(pas 0-15, vélocité)]


def steps(*positions: int, vel: int = 100) -> list[tuple[int, int]]:
    return [(p, vel) for p in positions]


def accented(strong: tuple[int, ...], weak: tuple[int, ...], hi: int = 100, lo: int = 70) -> list[tuple[int, int]]:
    return sorted([(p, hi) for p in strong] + [(p, lo) for p in weak])


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    piano: str  # nom du jeu de piano (instruments/piano.py)
    drums: Pattern
    default_bpm: float
    swing: float = 0.0  # 0 = droit ; 0.33 ≈ ternaire
    drums_by_default: bool = True
    seventh_chords: bool = False  # enrichir les accords (7e)
    extra: dict = field(default_factory=dict)


STYLES: dict[str, Style] = {
    "variete": Style(
        "variete", "Variété", "ballade",
        {KICK: steps(0, 8, vel=95), SNARE: steps(4, 12, vel=85),
         HH_CLOSED: accented((0, 4, 8, 12), (2, 6, 10, 14))},
        84,
    ),
    "pop": Style(
        "pop", "Pop", "pop",
        {KICK: steps(0, 6, 8, vel=100), SNARE: steps(4, 12, vel=100),
         HH_CLOSED: accented((0, 4, 8, 12), (2, 6, 10, 14))},
        100,
    ),
    "gospel": Style(
        "gospel", "Gospel", "gospel",
        {KICK: steps(0, 7, 10, vel=100), SNARE: steps(4, 12, vel=105), CLAP: steps(4, 12, vel=80),
         HH_CLOSED: accented((0, 4, 8, 12), (2, 6, 10, 14), 90, 60)},
        78, swing=0.2, seventh_chords=True,
    ),
    "zouglou": Style(
        "zouglou", "Zouglou", "zouglou",
        {KICK: steps(0, 4, 8, 12, vel=100), SNARE: steps(4, 12, vel=90), SIDESTICK: steps(7, 15, vel=75),
         SHAKER: accented((0, 4, 8, 12), (1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15), 85, 55)},
        104,
    ),
    "jazz": Style(
        "jazz", "Jazz", "jazz",
        {RIDE: accented((0, 4, 8, 12), (6, 14), 90, 75), HH_PEDAL: steps(4, 12, vel=70),
         KICK: steps(0, vel=45), SNARE: steps(14, vel=45)},
        120, swing=0.33, seventh_chords=True,
    ),
    "rnb": Style(
        "rnb", "R&B", "rnb",
        {KICK: steps(0, 3, 10, vel=100), SNARE: steps(4, 12, vel=95),
         HH_CLOSED: accented((0, 2, 4, 6, 8, 10, 12, 14), (1, 3, 5, 7, 9, 11, 13, 15), 80, 50)},
        72, swing=0.15, seventh_chords=True,
    ),
    "classique": Style(
        "classique", "Classique", "classique",
        {}, 72, drums_by_default=False,
    ),
    "afro": Style(
        "afro", "Afro", "afro",
        {KICK: steps(0, 6, 8, 14, vel=100), SNARE: steps(4, 12, vel=80), SIDESTICK: steps(3, 7, 11, vel=75),
         SHAKER: accented((0, 4, 8, 12), (2, 6, 10, 14, 3, 7, 11, 15), 80, 55), COWBELL: steps(2, 10, vel=60)},
        102,
    ),
    "reggae": Style(
        "reggae", "Reggae", "reggae",
        {KICK: steps(8, vel=105), SIDESTICK: steps(8, vel=95),
         HH_CLOSED: accented((2, 6, 10, 14), (0, 4, 8, 12), 85, 60)},
        76, swing=0.2,
    ),
    "soul": Style(
        "soul", "Soul", "soul",
        {KICK: steps(0, 8, 10, vel=100), SNARE: steps(4, 12, vel=100), TAMBOURINE: steps(4, 12, vel=70),
         HH_CLOSED: accented((0, 4, 8, 12), (2, 6, 10, 14))},
        92, swing=0.1, seventh_chords=True,
    ),
}

DEFAULT_STYLE = "variete"
