"""Événements publiés par le moteur d'analyse musicale."""

from __future__ import annotations

from dataclasses import dataclass

from orchestre_ia.analysis.key import KeyEstimate
from orchestre_ia.analysis.notes import Note
from orchestre_ia.analysis.tempo import TempoEstimate
from orchestre_ia.core.events import Event


@dataclass(frozen=True, slots=True)
class PitchUpdate(Event):
    """Hauteur instantanée (≈30 par seconde)."""

    f0: float
    midi: float  # corrigé du diapason personnel ; 0 si non voisé
    note: int | None  # note en cours (segmentée) ou None
    tuning_cents: float


@dataclass(frozen=True, slots=True)
class NoteFinished(Event):
    note: Note


@dataclass(frozen=True, slots=True)
class KeyUpdate(Event):
    estimate: KeyEstimate


@dataclass(frozen=True, slots=True)
class TempoUpdate(Event):
    estimate: TempoEstimate | None
