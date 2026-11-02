"""Synthétiseur intégré de secours (NumPy pur), utilisé si FluidSynth est indisponible.

Son volontairement simple : piano à harmoniques amorties, basse, batterie à
base de bruit et de sinus balayés. Il garantit que l'accompagnement reste
audible sur toute machine, sans dépendance native.
"""

from __future__ import annotations

import numpy as np

from orchestre_ia.analysis.theory import midi_to_hz


class _Voice:
    __slots__ = ("channel", "note", "amp", "freq", "phase", "age", "released", "release_age", "kind", "rng")

    def __init__(self, channel: int, note: int, velocity: int, kind: str) -> None:
        self.channel, self.note, self.kind = channel, note, kind
        self.amp = (velocity / 127.0) ** 1.5 * 0.25
        self.freq = midi_to_hz(note)
        self.phase = 0.0
        self.age = 0
        self.released = False
        self.release_age = 0
        self.rng = np.random.default_rng(note)


class BuiltinSynth:
    name = "Synthé intégré"

    def __init__(self, samplerate: int) -> None:
        self.sr = samplerate
        self._voices: list[_Voice] = []
        self._volume = {ch: 1.0 for ch in range(16)}
        self._drum_channels = {9}
        self._tuning = {ch: 1.0 for ch in range(16)}

    def noteon(self, channel: int, note: int, velocity: int) -> None:
        if channel in self._drum_channels:
            kind = "kick" if note in (35, 36) else "snare" if note in (37, 38, 39, 40) else "tom" if note in (41, 43, 45, 47, 48, 50) else "hat"
        else:
            kind = "tone"
            for v in self._voices:
                if v.channel == channel and v.note == note and not v.released:
                    v.released = True
        voice = _Voice(channel, note, velocity, kind)
        voice.freq *= self._tuning.get(channel, 1.0)
        self._voices.append(voice)
        if len(self._voices) > 64:
            self._voices = self._voices[-64:]

    def noteoff(self, channel: int, note: int) -> None:
        for v in self._voices:
            if v.channel == channel and v.note == note and v.kind == "tone":
                v.released = True

    def cc(self, channel: int, control: int, value: int) -> None:
        if control == 7:
            self._volume[channel] = value / 127.0
        elif control in (120, 123):
            for v in self._voices:
                if v.channel == channel:
                    v.released = True

    def program(self, channel: int, program: int, drums: bool = False) -> None:
        if drums:
            self._drum_channels.add(channel)

    def tune(self, channel: int, cents: float) -> None:
        self._tuning[channel] = 2 ** (max(-100.0, min(100.0, cents)) / 1200)

    def all_notes_off(self) -> None:
        for v in self._voices:
            v.released = True

    def render(self, frames: int) -> np.ndarray:
        out = np.zeros(frames, dtype=np.float64)
        n = np.arange(frames)
        alive = []
        for v in self._voices:
            t = (v.age + n) / self.sr
            vol = v.amp * self._volume.get(v.channel, 1.0)
            if v.kind == "tone":
                env = np.exp(-t * (1.2 + v.freq / 600))
                if v.released:
                    env *= np.exp(-(v.release_age + n) / (0.12 * self.sr))
                w = 2 * np.pi * v.freq * t
                sig = np.sin(w) + 0.4 * np.sin(2 * w) * np.exp(-t * 3) + 0.15 * np.sin(3 * w) * np.exp(-t * 5)
                done = env[-1] < 1e-4
            elif v.kind == "kick":
                env = np.exp(-t * 18)
                sig = np.sin(2 * np.pi * (50 * t + 60 * (1 - np.exp(-t * 30)) / 30))
                done = t[-1] > 0.4
            elif v.kind in ("snare", "tom"):
                env = np.exp(-t * (25 if v.kind == "snare" else 12))
                noise = v.rng.standard_normal(frames) * (0.7 if v.kind == "snare" else 0.2)
                sig = noise + np.sin(2 * np.pi * (180 if v.kind == "snare" else v.freq / 2) * t)
                done = t[-1] > 0.5
            else:
                env = np.exp(-t * (60 if v.note != 46 else 12))
                sig = np.diff(v.rng.standard_normal(frames + 1)) * 0.5
                done = t[-1] > 0.4
            out += vol * env * sig
            v.age += frames
            if v.released:
                v.release_age += frames
            if not done:
                alive.append(v)
        self._voices = alive
        mono = np.tanh(out).astype(np.float32)
        return np.column_stack((mono, mono))

    def close(self) -> None:
        self._voices.clear()
