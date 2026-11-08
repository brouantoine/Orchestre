"""Petits morceaux synthétiques (accords + basse + grosse caisse) pour tester l'étude."""

from __future__ import annotations

import numpy as np

NOTE_PC = {"Do": 0, "Ré": 2, "Mi": 4, "Fa": 5, "Sol": 7, "La": 9, "Si": 11}


def _tone(midi: float, n: int, sr: int, amp: float) -> np.ndarray:
    t = np.arange(n) / sr
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    env = np.exp(-t * 1.5) * (1 - np.exp(-t * 200))
    out = np.zeros(n)
    for k in range(1, 6):
        if f0 * k < sr / 2:
            out += np.sin(2 * np.pi * f0 * k * t) / k
    return amp * env * out


def _kick(n: int, sr: int) -> np.ndarray:
    t = np.arange(n) / sr
    freq = 50 + 80 * np.exp(-t * 30)
    return 0.6 * np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 18)


def render_progression(
    chords: list[tuple[int, bool]],
    bpm: float = 80.0,
    beats_per_chord: int = 4,
    repeats: int = 4,
    sr: int = 22050,
    lead_silence_s: float = 0.0,
) -> np.ndarray:
    """`chords` : (fondamentale 0-11, mineur ?). Retourne un signal mono float32."""
    beat = int(60.0 / bpm * sr)
    seq = chords * repeats
    out = np.zeros(int(lead_silence_s * sr) + beat * beats_per_chord * len(seq) + sr)
    pos = int(lead_silence_s * sr)
    for root, minor in seq:
        n = beat * beats_per_chord
        third = 3 if minor else 4
        block = _tone(36 + root, n, sr, 0.35) + _tone(48 + root, n, sr, 0.25)
        for interval in (0, third, 7):
            block += _tone(60 + root + interval, n, sr, 0.2)
        out[pos : pos + n] += block
        for b in range(beats_per_chord):
            out[pos + b * beat : pos + (b + 1) * beat] += _kick(beat, sr)
        pos += n
    out /= np.max(np.abs(out)) * 1.25
    return out.astype(np.float32)
