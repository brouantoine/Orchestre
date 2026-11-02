"""Estimation du tempo à partir des attaques de notes chantées.

Autocorrélation d'un train d'impulsions (une impulsion par début de note, poids
selon la durée), dans la plage 55-160 BPM, avec une préférence douce autour de
90 BPM pour départager les multiples (double/moitié de tempo).
La confiance mesure la régularité réelle : un chant libre (rubato) obtient une
confiance faible, et la batterie n'entre pas dans ce cas.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

RESOLUTION_S = 0.01


@dataclass(frozen=True)
class TempoEstimate:
    bpm: float
    confidence: float
    phase_s: float  # instant d'un temps (pour caler l'horloge musicale)


class TempoEstimator:
    def __init__(self, window_s: float = 16.0, min_onsets: int = 8, bpm_range=(55.0, 160.0)) -> None:
        self.window_s = window_s
        self.min_onsets = min_onsets
        self.bpm_range = bpm_range
        self.onsets: deque[tuple[float, float]] = deque()  # (instant, poids)

    def add_onset(self, t: float, weight: float = 1.0) -> None:
        self.onsets.append((t, weight))
        while self.onsets and t - self.onsets[0][0] > self.window_s:
            self.onsets.popleft()

    def estimate(self) -> TempoEstimate | None:
        if len(self.onsets) < self.min_onsets:
            return None
        times = np.array([o[0] for o in self.onsets])
        weights = np.array([o[1] for o in self.onsets])
        start = times[0]
        n = int((times[-1] - start) / RESOLUTION_S) + 1
        train = np.zeros(n + 1)
        idx = np.round((times - start) / RESOLUTION_S).astype(int)
        np.add.at(train, idx, weights)
        # flou gaussien de ±30 ms : tolère l'imprécision humaine
        kernel = np.exp(-0.5 * (np.arange(-6, 7) / 3.0) ** 2)
        train = np.convolve(train, kernel, mode="same")

        lo_bpm, hi_bpm = self.bpm_range
        lags = np.arange(int(60 / hi_bpm / RESOLUTION_S), int(60 / lo_bpm / RESOLUTION_S) + 1)
        if lags[-1] >= len(train):
            return None
        energy = float(np.dot(train, train))
        ac = np.array([np.dot(train[:-lag], train[lag:]) for lag in lags]) / max(energy, 1e-12)
        # renforce les lags dont les multiples sont aussi périodiques (structure de mesure)
        bpms = 60.0 / (lags * RESOLUTION_S)
        prior = np.exp(-0.5 * (np.log2(bpms / 90.0) / 0.6) ** 2)
        score = ac * prior
        best = int(np.argmax(score))
        lag = lags[best]
        bpm = float(60.0 / (lag * RESOLUTION_S))

        # confiance : proportion d'attaques tombant près d'un temps de la grille trouvée
        period = lag * RESOLUTION_S
        phases = np.angle(np.sum(weights * np.exp(2j * np.pi * times / period)))
        phase_s = float((phases / (2 * np.pi)) * period) % period
        # distance de chaque attaque au plus proche demi-temps (les croches comptent)
        rel = ((times - phase_s) / (period / 2)) % 1.0
        dist = np.minimum(rel, 1 - rel) * period / 2
        on_grid = float(np.sum(weights * (dist < 0.06)) / np.sum(weights))
        confidence = float(np.clip((on_grid - 0.5) / 0.4, 0, 1) * np.clip(ac[best] / 0.3, 0, 1))
        return TempoEstimate(bpm, confidence, phase_s)
