"""Synthétiseur FluidSynth (LGPL 2.1, bibliothèque dynamique) + SoundFont General MIDI.

FluidSynth ne pilote pas lui-même la carte son : nous lui demandons des
échantillons dans le callback de sortie, ce qui garde une horloge unique.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOUNDFONT = PACKAGE_DIR / "resources" / "soundfonts" / "FluidR3Mono_GM.sf3"


def fluidsynth_dll_dirs() -> list[Path]:
    """Emplacements possibles de libfluidsynth : variable d'env., application figée, dossier vendor."""
    dirs = []
    env = os.environ.get("ORCHESTRE_IA_FLUIDSYNTH_DIR")
    if env:
        dirs.append(Path(env))
    if getattr(sys, "frozen", False):
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "fluidsynth")
    vendor = PACKAGE_DIR.parent / "vendor" / "fluidsynth"
    if vendor.exists():
        dirs.extend(sorted(vendor.glob("*/bin")))
    return [d for d in dirs if d.exists()]


_fluidsynth_module = None


def load_fluidsynth():
    """Importe pyfluidsynth après avoir rendu la DLL trouvable. Lève ImportError si absente."""
    global _fluidsynth_module
    if _fluidsynth_module is not None:
        return _fluidsynth_module
    for d in fluidsynth_dll_dirs():
        if sys.platform == "win32":
            os.add_dll_directory(str(d))
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    import fluidsynth  # noqa: PLC0415 (import différé volontaire)

    _fluidsynth_module = fluidsynth
    return fluidsynth


class FluidSynthBackend:
    name = "FluidSynth"

    def __init__(self, samplerate: int, soundfont: Path = DEFAULT_SOUNDFONT, gain: float = 0.9) -> None:
        if not soundfont.exists():
            raise FileNotFoundError(f"SoundFont introuvable : {soundfont}")
        fs_module = load_fluidsynth()
        self._synth = fs_module.Synth(gain=gain, samplerate=float(samplerate))
        self._sfid = self._synth.sfload(str(soundfont))
        if self._sfid < 0:
            raise RuntimeError(f"Chargement de la SoundFont impossible : {soundfont}")
        self.soundfont = soundfont
        log.info("FluidSynth prêt (%s, %d Hz)", soundfont.name, samplerate)

    def noteon(self, channel: int, note: int, velocity: int) -> None:
        self._synth.noteon(channel, note, velocity)

    def noteoff(self, channel: int, note: int) -> None:
        self._synth.noteoff(channel, note)

    def cc(self, channel: int, control: int, value: int) -> None:
        self._synth.cc(channel, control, value)

    def program(self, channel: int, program: int, drums: bool = False) -> None:
        self._synth.program_select(channel, self._sfid, 128 if drums else 0, program)

    def tune(self, channel: int, cents: float) -> None:
        # plage de pitch bend par défaut : ±2 demi-tons = ±8192
        value = int(round(max(-100.0, min(100.0, cents)) / 200.0 * 8191))
        self._synth.pitch_bend(channel, value)

    def all_notes_off(self) -> None:
        for ch in range(16):
            self._synth.cc(ch, 123, 0)  # All Notes Off (les notes s'éteignent naturellement)

    def render(self, frames: int) -> np.ndarray:
        raw = self._synth.get_samples(frames)
        return np.asarray(raw, dtype=np.float32).reshape(-1, 2) / 32768.0

    def close(self) -> None:
        try:
            self._synth.delete()
        except Exception:  # fermeture best-effort
            pass
