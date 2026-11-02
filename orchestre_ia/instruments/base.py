"""Contrat commun des instruments : le chef d'orchestre leur demande quoi jouer, temps par temps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.instruments.styles import Style
from orchestre_ia.midi.events import MidiNote


@dataclass(frozen=True)
class PlayContext:
    beat: int  # index absolu du temps
    beat_in_bar: int  # 0-3
    bar: int
    chord: Chord
    chord_changed: bool
    key: Key | None
    style: Style
    intensity: float  # 0 (très doux) à 1 (plein)
    rhythmic: bool  # False = jeu libre (tempo non établi)
    fill: bool = False  # dernier temps d'une phrase : relance
    phrase_start: bool = False


@dataclass(frozen=True)
class NoteOff:
    channel: int
    note: int
    beat: float


class Instrument(Protocol):
    name: str

    def play_beat(self, ctx: PlayContext) -> tuple[list[MidiNote], list[NoteOff]]: ...

    def release_all(self, beat: float) -> list[NoteOff]: ...
