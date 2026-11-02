"""Mesure de niveau (RMS, crête) en dBFS avec balistique de VU-mètre."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SILENCE_DB = -100.0
CLIP_THRESHOLD = 0.999


def amplitude_to_db(value: float) -> float:
    if value <= 0.0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * float(np.log10(value)))


def db_to_amplitude(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def rms_dbfs(block: np.ndarray) -> float:
    if block.size == 0:
        return SILENCE_DB
    x = block.astype(np.float64, copy=False)
    return amplitude_to_db(float(np.sqrt(np.mean(x * x))))


def peak_dbfs(block: np.ndarray) -> float:
    if block.size == 0:
        return SILENCE_DB
    return amplitude_to_db(float(np.max(np.abs(block))))


@dataclass(frozen=True)
class LevelReading:
    rms_db: float
    peak_db: float
    held_peak_db: float
    clipping: bool


class LevelMeter:
    """VU-mètre : montée instantanée, descente à `release_db_per_s`, crête maintenue `hold_s`."""

    def __init__(self, release_db_per_s: float = 30.0, hold_s: float = 1.5) -> None:
        self.release_db_per_s = release_db_per_s
        self.hold_s = hold_s
        self._rms = SILENCE_DB
        self._peak = SILENCE_DB
        self._held = SILENCE_DB
        self._held_age = 0.0

    def update(self, block: np.ndarray, dt: float, raw_peak: float | None = None) -> LevelReading:
        rms = rms_dbfs(block)
        peak = peak_dbfs(block)
        fall = self.release_db_per_s * dt
        self._rms = max(rms, self._rms - fall)
        self._peak = max(peak, self._peak - fall)
        self._held_age += dt
        if peak >= self._held or self._held_age > self.hold_s:
            self._held = peak
            self._held_age = 0.0
        clip_source = raw_peak if raw_peak is not None else float(np.max(np.abs(block))) if block.size else 0.0
        return LevelReading(self._rms, self._peak, self._held, clip_source >= CLIP_THRESHOLD)
