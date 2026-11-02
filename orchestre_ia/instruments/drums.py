"""Moteur de batterie : rythmes par style, intensité, relances (fills), cymbale d'entrée.

Niveaux d'intensité :
- < 0,35 : seulement charleston/cymbale/shaker + grosse caisse sur le 1 (accompagnement léger) ;
- ≥ 0,35 : rythme complet ;
- ≥ 0,75 : charleston ouvert en fin de mesure et crash en début de phrase.
Une légère humanisation (vélocité, ±5 ms) évite l'effet « boîte à rythmes ».
"""

from __future__ import annotations

import random

from orchestre_ia.instruments.base import NoteOff, PlayContext
from orchestre_ia.instruments.styles import (
    CRASH,
    HH_CLOSED,
    HH_OPEN,
    KICK,
    RIDE,
    SHAKER,
    SNARE,
    TOM_HIGH,
    TOM_LOW,
    TOM_MID,
)
from orchestre_ia.midi.events import DRUM_CHANNEL, MidiNote

LIGHT_INSTRUMENTS = {HH_CLOSED, RIDE, SHAKER}
FILL = [(12, SNARE, 95), (13, TOM_HIGH, 95), (14, TOM_MID, 100), (15, TOM_LOW, 105)]


class DrumEngine:
    name = "Batterie"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def release_all(self, beat: float) -> list[NoteOff]:
        return []  # les sons de batterie s'éteignent d'eux-mêmes

    def play_beat(self, ctx: PlayContext) -> tuple[list[MidiNote], list[NoteOff]]:
        pattern = ctx.style.drums
        if not pattern or not ctx.rhythmic:
            return [], []
        first_step = ctx.beat_in_bar * 4
        bar_start = ctx.beat - ctx.beat_in_bar
        hits: list[tuple[int, int, int]] = []  # (pas, instrument, vélocité)
        light = ctx.intensity < 0.35
        fill_now = ctx.fill and ctx.beat_in_bar == 3 and not light

        for instrument, step_list in pattern.items():
            for step, vel in step_list:
                if not (first_step <= step < first_step + 4):
                    continue
                if fill_now and step >= 12 and instrument not in LIGHT_INSTRUMENTS:
                    continue
                if light and instrument not in LIGHT_INSTRUMENTS and not (instrument == KICK and step == 0):
                    continue
                hits.append((step, instrument, vel))

        if fill_now:
            hits = [h for h in hits if h[0] < 12] + FILL
        if ctx.intensity >= 0.75 and ctx.beat_in_bar == 3 and HH_CLOSED in pattern and not fill_now:
            hits = [h for h in hits if not (h[1] == HH_CLOSED and h[0] == 14)] + [(14, HH_OPEN, 85)]
        if ctx.phrase_start and ctx.beat_in_bar == 0 and not light:
            hits.append((0, CRASH, 95))

        scale = 0.6 + 0.4 * ctx.intensity
        notes = []
        for step, instrument, vel in hits:
            pos = step / 4.0
            if step % 4 == 2:
                pos += ctx.style.swing * 0.5  # croche swinguée
            elif step % 2 == 1:
                pos += ctx.style.swing * 0.25
            jitter = self._rng.uniform(-0.01, 0.01)
            velocity = int(max(15, min(127, vel * scale + self._rng.uniform(-6, 6))))
            notes.append(MidiNote(DRUM_CHANNEL, instrument, velocity, bar_start + pos + jitter, 0.1))
        return notes, []
