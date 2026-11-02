"""Traitements de conditionnement du signal micro (temps réel, avec état)."""

from __future__ import annotations

import numpy as np
from scipy import signal


class HighPassFilter:
    """Filtre passe-haut Butterworth à état continu entre les blocs.

    Supprime les grondements (vibrations, souffle, ventilation) sous la voix.
    80 Hz est sous la fondamentale d'une voix de basse (~82 Hz, E2) avec une pente douce.
    """

    def __init__(self, cutoff_hz: float, samplerate: int, order: int = 2) -> None:
        self.cutoff_hz = cutoff_hz
        self._sos = signal.butter(order, cutoff_hz, btype="highpass", fs=samplerate, output="sos")
        self._zi = np.zeros((self._sos.shape[0], 2))

    def process(self, block: np.ndarray) -> np.ndarray:
        out, self._zi = signal.sosfilt(self._sos, block, zi=self._zi)
        return out.astype(np.float32, copy=False)

    def reset(self) -> None:
        self._zi[:] = 0.0
