"""Horloge musicale centrale, commune à tous les instruments.

Elle est cadencée par le compteur d'échantillons de la sortie audio (précision à
l'échantillon près) et reliée à time.monotonic() pour dialoguer avec l'analyse.
Un changement de tempo conserve la position musicale courante (pas de saut).
"""

from __future__ import annotations

import threading
import time


class MusicClock:
    def __init__(self, samplerate: int, bpm: float = 80.0, beats_per_bar: int = 4) -> None:
        self.samplerate = samplerate
        self.beats_per_bar = beats_per_bar
        self._lock = threading.Lock()
        self._bpm = bpm
        self._origin_sample = 0.0  # échantillon où se trouve le temps 0
        self._origin_beat = 0.0
        self._sample = 0  # échantillon actuellement joué (début du prochain bloc)
        self._sample_monotonic = time.monotonic()  # instant où `_sample` sort du haut-parleur

    @property
    def bpm(self) -> float:
        return self._bpm

    @property
    def samples_per_beat(self) -> float:
        return self.samplerate * 60.0 / self._bpm

    # ----------------------------------------------------- côté sortie audio
    def advance(self, sample: int, monotonic_at_dac: float) -> None:
        with self._lock:
            self._sample = sample
            self._sample_monotonic = monotonic_at_dac

    # ------------------------------------------------------------ conversions
    def beat_at_sample(self, sample: float) -> float:
        with self._lock:
            return self._origin_beat + (sample - self._origin_sample) / (self.samplerate * 60.0 / self._bpm)

    def sample_at_beat(self, beat: float) -> float:
        with self._lock:
            return self._origin_sample + (beat - self._origin_beat) * self.samplerate * 60.0 / self._bpm

    def sample_at_monotonic(self, t: float) -> float:
        with self._lock:
            return self._sample + (t - self._sample_monotonic) * self.samplerate

    def monotonic_at_beat(self, beat: float) -> float:
        sample = self.sample_at_beat(beat)
        with self._lock:
            return self._sample_monotonic + (sample - self._sample) / self.samplerate

    def current_beat(self) -> float:
        return self.beat_at_sample(self.sample_at_monotonic(time.monotonic()))

    # ---------------------------------------------------------------- réglages
    def set_tempo(self, bpm: float) -> None:
        """Change le tempo sans déplacer la position musicale actuelle."""
        bpm = float(min(220.0, max(40.0, bpm)))
        with self._lock:
            pivot = self._sample
            beat = self._origin_beat + (pivot - self._origin_sample) / (self.samplerate * 60.0 / self._bpm)
            self._origin_sample, self._origin_beat, self._bpm = pivot, beat, bpm

    def align(self, bpm: float, beat_monotonic: float, next_beat_index: float) -> None:
        """Cale l'horloge : le temps `next_beat_index` tombera sur un temps du chanteur.

        `beat_monotonic` est un instant (monotonic) correspondant à un temps chanté.
        """
        bpm = float(min(220.0, max(40.0, bpm)))
        period = 60.0 / bpm
        with self._lock:
            now_sample = self._sample
            now_t = self._sample_monotonic
        # prochain temps du chanteur après maintenant + 0,25 s de marge
        k = max(0, int((now_t + 0.25 - beat_monotonic) / period) + 1)
        target_t = beat_monotonic + k * period
        target_sample = now_sample + (target_t - now_t) * self.samplerate
        with self._lock:
            self._bpm = bpm
            self._origin_sample = target_sample
            self._origin_beat = next_beat_index
