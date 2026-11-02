"""Diapason personnel et segmentation des trames de hauteur en notes."""

from __future__ import annotations

import math
from dataclasses import dataclass

from orchestre_ia.analysis.tracker import PitchFrame


class TuningEstimator:
    """Estime l'écart moyen (en cents) du chanteur par rapport au La 440 Hz.

    Moyenne circulaire des écarts fractionnaires, pondérée et oubliée lentement :
    un chanteur constamment 40 cents trop bas sera « recalé » au lieu d'hésiter
    entre deux notes.
    """

    def __init__(self, half_life_s: float = 20.0) -> None:
        self.half_life_s = half_life_s
        self._c = 0.0
        self._s = 0.0
        self.weight = 0.0

    def update(self, midi: float, dt: float) -> None:
        decay = 0.5 ** (dt / self.half_life_s)
        angle = 2 * math.pi * (midi - round(midi))
        self._c = self._c * decay + math.cos(angle) * dt
        self._s = self._s * decay + math.sin(angle) * dt
        self.weight = self.weight * decay + dt

    @property
    def offset_cents(self) -> float:
        if self.weight < 1.0:  # au moins 1 s de chant avant de corriger
            return 0.0
        return math.atan2(self._s, self._c) / (2 * math.pi) * 100.0


@dataclass(frozen=True, slots=True)
class Note:
    midi: int
    start: float
    end: float
    cents: float  # écart moyen par rapport à la note tempérée (après correction du diapason)

    @property
    def duration(self) -> float:
        return self.end - self.start


class NoteSegmenter:
    """Machine à états : une note commence après `confirm_s` de hauteur stable,
    se poursuit tant que la hauteur reste à moins de `hold_semitones`, et se termine
    après un silence de plus de `gap_s` ou un changement confirmé de hauteur.
    Le vibrato (±50 cents) et les attaques glissées ne créent pas de fausses notes.
    """

    def __init__(
        self,
        hop_s: float = 0.010,
        confirm_s: float = 0.05,
        gap_s: float = 0.08,
        hold_semitones: float = 0.75,
        min_duration_s: float = 0.08,
    ) -> None:
        self.hop_s = hop_s
        self.confirm_s = confirm_s
        self.gap_s = gap_s
        self.hold = hold_semitones
        self.min_duration_s = min_duration_s
        self.tuning = TuningEstimator()
        self.current: int | None = None
        self._start = 0.0
        self._last_voiced = 0.0
        self._deviations: list[float] = []
        self._candidate: int | None = None
        self._candidate_since = 0.0

    def corrected_midi(self, frame: PitchFrame) -> float:
        return frame.midi - self.tuning.offset_cents / 100.0

    def process(self, frame: PitchFrame) -> tuple[list[Note], int | None]:
        """Retourne (notes terminées, note qui vient de commencer ou None)."""
        finished: list[Note] = []
        started: int | None = None
        t = frame.time

        if not frame.voiced:
            if self.current is not None and t - self._last_voiced > self.gap_s:
                finished += self._close(self._last_voiced)
            self._candidate = None
            return finished, None

        self.tuning.update(frame.midi, self.hop_s)
        m = self.corrected_midi(frame)
        self._last_voiced = t

        if self.current is not None and abs(m - self.current) <= self.hold:
            self._deviations.append(m - self.current)
            self._candidate = None
            return finished, None

        nearest = int(round(m))
        if self._candidate != nearest:
            self._candidate, self._candidate_since = nearest, t
        if t - self._candidate_since + self.hop_s >= self.confirm_s:
            if self.current is not None:
                finished += self._close(self._candidate_since)
            self.current = nearest
            self._start = self._candidate_since
            self._deviations = [m - nearest]
            self._candidate = None
            started = nearest
        return finished, started

    def flush(self, t: float) -> list[Note]:
        return self._close(min(t, self._last_voiced)) if self.current is not None else []

    def _close(self, end: float) -> list[Note]:
        midi, start = self.current, self._start
        devs = self._deviations
        self.current = None
        self._deviations = []
        if midi is None or end - start < self.min_duration_s:
            return []
        cents = 100.0 * sum(devs) / len(devs) if devs else 0.0
        return [Note(midi, start, end, cents)]
