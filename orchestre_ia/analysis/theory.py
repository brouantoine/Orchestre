"""Théorie musicale de base : noms de notes, tonalités, gammes, accords diatoniques."""

from __future__ import annotations

import math
from dataclasses import dataclass

NOTE_NAMES = ("Do", "Do#", "Ré", "Ré#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si")

MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11)
MINOR_STEPS = (0, 2, 3, 5, 7, 8, 10)  # mineur naturel ; le V majeur est ajouté à part

CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
}
CHORD_SUFFIX = {"maj": "", "min": "m", "dim": "dim", "7": "7", "maj7": "maj7", "min7": "m7"}


def hz_to_midi(hz: float) -> float:
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def midi_to_hz(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def note_name(midi: int) -> str:
    """Nom français avec octave (Do4 = do central = MIDI 60)."""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def pc_name(pc: int) -> str:
    return NOTE_NAMES[pc % 12]


@dataclass(frozen=True)
class Key:
    tonic: int  # classe de hauteur 0-11 (0 = Do)
    minor: bool

    @property
    def name(self) -> str:
        return f"{pc_name(self.tonic)} {'mineur' if self.minor else 'majeur'}"

    @property
    def scale(self) -> tuple[int, ...]:
        steps = MINOR_STEPS if self.minor else MAJOR_STEPS
        return tuple((self.tonic + s) % 12 for s in steps)


@dataclass(frozen=True)
class Chord:
    root: int
    quality: str
    degree: int = 0  # 1-7 dans la tonalité courante, 0 si hors tonalité

    @property
    def pcs(self) -> tuple[int, ...]:
        return tuple((self.root + i) % 12 for i in CHORD_INTERVALS[self.quality])

    @property
    def name(self) -> str:
        return f"{pc_name(self.root)}{CHORD_SUFFIX[self.quality]}"

    @property
    def triad_quality(self) -> str:
        return {"7": "maj", "maj7": "maj", "min7": "min"}.get(self.quality, self.quality)


def diatonic_chords(key: Key) -> list[Chord]:
    """Accords à trois sons construits sur chaque degré (+ V majeur en mineur, cadence harmonique)."""
    scale = key.scale
    chords = []
    for degree in range(7):
        root = scale[degree]
        third = (scale[(degree + 2) % 7] - root) % 12
        fifth = (scale[(degree + 4) % 7] - root) % 12
        quality = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim"}.get((third, fifth), "maj")
        chords.append(Chord(root, quality, degree + 1))
    if key.minor:
        chords.append(Chord(scale[4], "maj", 5))  # V majeur (sensible)
    return chords
