"""Suivi de hauteur continu : décimation ~16 kHz, trames glissantes, YIN, lissage."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import signal

from orchestre_ia.analysis.pitch import YinPitchDetector
from orchestre_ia.analysis.theory import hz_to_midi
from orchestre_ia.audio.level import rms_dbfs


@dataclass(frozen=True, slots=True)
class PitchFrame:
    time: float  # secondes depuis le début de l'écoute (horloge des échantillons)
    f0: float  # Hz, 0 si non voisé
    confidence: float
    level_db: float

    @property
    def voiced(self) -> bool:
        return self.f0 > 0

    @property
    def midi(self) -> float:
        return hz_to_midi(self.f0) if self.f0 > 0 else 0.0


class PitchTracker:
    """Transforme des blocs audio (fréquence d'entrée quelconque) en trames de hauteur toutes les 10 ms."""

    def __init__(
        self,
        input_samplerate: int,
        target_samplerate: int = 16000,
        frame_size: int = 1024,
        hop_s: float = 0.010,
        min_confidence: float = 0.6,
        min_level_db: float = -50.0,
        median_frames: int = 5,
    ) -> None:
        self.decimation = max(1, round(input_samplerate / target_samplerate))
        self.samplerate = input_samplerate / self.decimation
        self.frame_size = frame_size
        self.hop = int(round(self.samplerate * hop_s))
        self.min_confidence = min_confidence
        self.min_level_db = min_level_db
        self.detector = YinPitchDetector(self.samplerate, frame_size)
        if self.decimation > 1:
            self._sos = signal.cheby1(8, 0.05, 0.8 / self.decimation, output="sos")
            self._zi = np.zeros((self._sos.shape[0], 2))
        self._phase = 0  # décalage de décimation entre les blocs
        self._buffer = np.zeros(0, dtype=np.float32)
        self._consumed = 0  # échantillons décimés déjà sortis du tampon
        self._recent_midi: deque[float] = deque(maxlen=median_frames)

    def process(self, block: np.ndarray) -> list[PitchFrame]:
        if self.decimation > 1:
            filtered, self._zi = signal.sosfilt(self._sos, block, zi=self._zi)
            down = filtered[self._phase :: self.decimation].astype(np.float32)
            self._phase = (self._phase - len(block)) % self.decimation
        else:
            down = block.astype(np.float32)
        self._buffer = np.concatenate((self._buffer, down))

        frames = []
        while len(self._buffer) >= self.frame_size:
            frame = self._buffer[: self.frame_size]
            center = self._consumed + self.frame_size / 2
            frames.append(self._analyze(frame, center / self.samplerate))
            self._buffer = self._buffer[self.hop :]
            self._consumed += self.hop
        return frames

    def _analyze(self, frame: np.ndarray, t: float) -> PitchFrame:
        level = rms_dbfs(frame)
        if level < self.min_level_db:
            self._recent_midi.clear()
            return PitchFrame(t, 0.0, 0.0, level)
        f0, conf = self.detector.detect(frame)
        if f0 <= 0 or conf < self.min_confidence:
            self._recent_midi.clear()
            return PitchFrame(t, 0.0, conf, level)
        midi = hz_to_midi(f0)
        # Correction d'octave : un saut isolé d'environ ±12 demi-tons est replié.
        if self._recent_midi:
            ref = float(np.median(self._recent_midi))
            jump = midi - ref
            if abs(abs(jump) - 12) < 1.0:
                midi -= 12 * np.sign(jump)
        self._recent_midi.append(midi)
        smoothed = float(np.median(self._recent_midi))  # médiane : supprime les erreurs ponctuelles
        return PitchFrame(t, 440.0 * 2 ** ((smoothed - 69) / 12), conf, level)
