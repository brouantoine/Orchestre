"""Détection d'activité vocale (VAD) adaptée au chant.

Trois critères combinés :
1. Le niveau RMS dépasse le plancher de bruit estimé d'une marge (dB).
2. Le niveau dépasse un minimum absolu (évite les déclenchements sur bruit très faible).
3. L'énergie est concentrée dans la bande vocale (80 Hz - 3 kHz) : un bruit large
   bande (souffle, ventilateur) est rejeté.

Hystérésis : il faut `attack_ms` de signal valide pour ouvrir, et la détection reste
active `hangover_ms` après la fin (les consonnes et respirations ne coupent pas).
Le plancher de bruit descend immédiatement et remonte lentement.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orchestre_ia.audio.level import rms_dbfs


@dataclass
class VadConfig:
    margin_db: float = 10.0
    min_level_db: float = -55.0
    voice_band_hz: tuple[float, float] = (80.0, 3000.0)
    min_band_ratio: float = 0.5
    attack_ms: float = 30.0
    hangover_ms: float = 300.0
    initial_floor_db: float = -60.0
    floor_rise_db_per_s: float = 3.0
    floor_rise_while_voiced_db_per_s: float = 0.3


class VoiceActivityDetector:
    def __init__(self, samplerate: int, config: VadConfig | None = None) -> None:
        self.samplerate = samplerate
        self.config = config or VadConfig()
        self.noise_floor_db = self.config.initial_floor_db
        self.active = False
        self.last_band_ratio = 0.0
        self._valid_ms = 0.0
        self._invalid_ms = 0.0

    def band_ratio(self, block: np.ndarray) -> float:
        spectrum = np.abs(np.fft.rfft(block * np.hanning(len(block)))) ** 2
        total = float(spectrum.sum())
        if total <= 1e-20:
            return 0.0
        freqs = np.fft.rfftfreq(len(block), 1.0 / self.samplerate)
        lo, hi = self.config.voice_band_hz
        return float(spectrum[(freqs >= lo) & (freqs <= hi)].sum() / total)

    def process(self, block: np.ndarray) -> bool:
        cfg = self.config
        dt = len(block) / self.samplerate
        level = rms_dbfs(block)
        self.last_band_ratio = self.band_ratio(block)

        candidate = (
            level > self.noise_floor_db + cfg.margin_db
            and level > cfg.min_level_db
            and self.last_band_ratio >= cfg.min_band_ratio
        )

        # Plancher de bruit : descente immédiate, remontée lente.
        if level < self.noise_floor_db:
            self.noise_floor_db = level
        else:
            rate = cfg.floor_rise_while_voiced_db_per_s if candidate else cfg.floor_rise_db_per_s
            self.noise_floor_db = min(level, self.noise_floor_db + rate * dt)

        if candidate:
            self._valid_ms += dt * 1000
            self._invalid_ms = 0.0
            if self._valid_ms >= cfg.attack_ms:
                self.active = True
        else:
            self._invalid_ms += dt * 1000
            self._valid_ms = 0.0
            if self._invalid_ms >= cfg.hangover_ms:
                self.active = False
        return self.active
