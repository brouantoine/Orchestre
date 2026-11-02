"""Interface commune des synthétiseurs (FluidSynth, synthé intégré de secours)."""

from __future__ import annotations

from typing import Protocol

import numpy as np

# Programmes General MIDI utilisés
PROGRAM_ACOUSTIC_GRAND = 0
PROGRAM_ACOUSTIC_BASS = 32


class SynthBackend(Protocol):
    name: str

    def noteon(self, channel: int, note: int, velocity: int) -> None: ...
    def noteoff(self, channel: int, note: int) -> None: ...
    def cc(self, channel: int, control: int, value: int) -> None: ...
    def program(self, channel: int, program: int, drums: bool = False) -> None: ...
    def all_notes_off(self) -> None: ...
    def tune(self, channel: int, cents: float) -> None:
        """Décale l'accord du canal (cents, ±100) : l'orchestre s'aligne sur le diapason du chanteur."""
        ...
    def render(self, frames: int) -> np.ndarray:
        """Retourne `frames` échantillons stéréo float32, forme (frames, 2)."""
        ...
    def close(self) -> None: ...
