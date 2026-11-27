"""Main droite mélodique du piano : motifs, réponses et relances au-dessus des accords.

Un pianiste accompagnateur ne fait pas que plaquer des accords : sa main droite
joue de petites phrases qui donnent du relief, sans couvrir le chanteur.

- Registre au-dessus de la voix et des accords (Do5 à Sol6 environ).
- Un motif par phrase de 4 mesures, écrit en pas de gamme autour d'une note de
  l'accord : rejoué sur chaque accord (les temps forts tombent sur une note de
  l'accord), légèrement varié d'une phrase à l'autre — un « riff » cohérent.
- Pendant le chant : discret (une courte réponse en fin de mesure, doucement).
- Pendant une respiration ou un silence : le motif entier, puis une relance
  qui descend vers la phrase suivante.
- Rythme selon le style : triolets (gospel), contretemps (afro, zouglou), croches…
- Jeu libre (tempo inconnu) : un petit ornement à chaque changement d'accord.

Les choix aléatoires passent par un générateur à graine : reproductible en test.
"""

from __future__ import annotations

import random

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.instruments.base import NoteOff, PlayContext
from orchestre_ia.midi.events import MELODY_CHANNEL, MidiNote

LOW, HIGH = 72, 91  # Do5 - Sol6
SINGING_VELOCITY = 0.42  # réponses discrètes pendant le chant
GAP_VELOCITY = 0.68

# Positions (en temps, dans un temps) des notes d'un motif selon le style du piano.
RHYTHM_CELLS: dict[str, list[tuple[float, ...]]] = {
    "ballade": [(0.0, 0.5), (0.5,), (0.0,)],
    "pop": [(0.0, 0.5), (0.5,), (0.0, 0.75)],
    "gospel": [(0.0, 1 / 3, 2 / 3), (2 / 3,), (0.0, 2 / 3)],
    "jazz": [(0.0, 2 / 3), (2 / 3,), (0.0,)],
    "rnb": [(0.25, 0.75), (0.75,), (0.0, 0.5, 0.75)],
    "classique": [(0.0, 0.5), (0.0, 0.25, 0.5, 0.75), (0.0,)],
    "afro": [(0.25, 0.75), (0.0, 0.5, 0.75), (0.5,)],
    "reggae": [(0.5,), (0.5, 0.75), (0.0,)],
    "soul": [(0.0, 0.5), (0.5, 0.75), (0.0,)],
    "zouglou": [(0.25, 0.75), (0.5, 0.75), (0.0, 0.5)],
}

Motif = list[tuple[float, int]]  # (position dans la mesure en temps, pas de gamme depuis l'ancre)


class MelodyEngine:
    name = "Main droite"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.last_note: int | None = None
        self._motif: Motif = []
        self._motif_bar = -1

    def release_all(self, beat: float) -> list[NoteOff]:
        return []  # chaque note a sa durée : rien à couper

    def reset(self) -> None:
        self.last_note = None
        self._motif = []
        self._motif_bar = -1

    # ------------------------------------------------------------ hauteurs
    @staticmethod
    def _pool(chord: Chord, key: Key | None) -> list[int]:
        """Notes utilisables : gamme de la tonalité + notes de l'accord (emprunts compris)."""
        pcs = set(chord.pcs)
        if key is not None:
            # notes de la gamme qui ne frottent pas d'un demi-ton avec l'accord
            pcs |= {pc for pc in key.scale if all((pc - c) % 12 not in (1, 11) for c in chord.pcs)}
        else:
            pcs |= {(chord.root + 2) % 12, (chord.root + (9 if chord.triad_quality == "maj" else 8)) % 12}
        return [n for n in range(LOW, HIGH + 1) if n % 12 in pcs]

    @staticmethod
    def _chord_tones(chord: Chord) -> list[int]:
        return [n for n in range(LOW, HIGH + 1) if n % 12 in chord.pcs]

    def _anchor(self, chord: Chord) -> int:
        """Note de l'accord la plus proche de la dernière note jouée (mouvement conjoint)."""
        tones = self._chord_tones(chord)
        target = self.last_note if self.last_note is not None else 79
        return min(tones, key=lambda n: (abs(n - target), n))

    @staticmethod
    def _step(pool: list[int], note: int, steps: int) -> int:
        nearest = min(range(len(pool)), key=lambda i: abs(pool[i] - note))
        return pool[max(0, min(len(pool) - 1, nearest + steps))]

    def _render(self, chord: Chord, key: Key | None, steps: int, strong: bool) -> int:
        pool = self._pool(chord, key)
        note = self._step(pool, self._anchor(chord), steps)
        if strong:  # temps fort : toujours une note de l'accord
            note = min(self._chord_tones(chord), key=lambda n: (abs(n - note), n))
        return note

    # ------------------------------------------------------------ motifs
    def _new_motif(self, style_piano: str) -> Motif:
        cells = RHYTHM_CELLS.get(style_piano, RHYTHM_CELLS["ballade"])
        motif: Motif = []
        contour = 0
        for beat in range(4):
            cell = self._rng.choice(cells)
            for pos in cell:
                contour += self._rng.choice((-2, -1, -1, 1, 1, 2))
                contour = max(-4, min(4, contour))
                motif.append((beat + pos, contour))
        return motif

    def _vary(self, motif: Motif) -> Motif:
        if not motif:
            return motif
        varied = list(motif)
        i = self._rng.randrange(len(varied))
        pos, steps = varied[i]
        varied[i] = (pos, max(-4, min(4, steps + self._rng.choice((-1, 1)))))
        return varied

    def _motif_for(self, ctx: PlayContext) -> Motif:
        phrase = ctx.bar // 4
        if phrase != self._motif_bar:
            self._motif = self._vary(self._motif) if self._motif and phrase % 2 else self._new_motif(ctx.style.piano)
            self._motif_bar = phrase
        return self._motif

    # ------------------------------------------------------------ jeu
    def _velocity(self, rel: float, intensity: float) -> int:
        return int(max(25, min(115, rel * (70 + 50 * intensity))))

    def play_beat(self, ctx: PlayContext) -> tuple[list[MidiNote], list[NoteOff]]:
        if ctx.intensity < 0.15:
            return [], []
        if not ctx.rhythmic:
            return self._free(ctx), []
        motif = self._motif_for(ctx)
        events = [(pos, steps) for pos, steps in motif if ctx.beat_in_bar <= pos < ctx.beat_in_bar + 1]
        if ctx.singing:
            # discret : seulement la fin de la mesure (réponse), et pas à chaque mesure
            if ctx.beat_in_bar != 3 or ctx.bar % 2 == 0:
                return [], []
            events = events[-2:]
            rel = SINGING_VELOCITY
        else:
            rel = GAP_VELOCITY
            if ctx.fill and ctx.beat_in_bar == 3:
                return self._run_down(ctx), []
        bar_start = ctx.beat - ctx.beat_in_bar
        notes = []
        for i, (pos, steps) in enumerate(events):
            strong = abs(pos - round(pos)) < 1e-6 and int(round(pos)) % 2 == 0
            note = self._render(ctx.chord, ctx.key, steps, strong)
            nxt = events[i + 1][0] if i + 1 < len(events) else ctx.beat_in_bar + 1
            dur = max(0.2, (nxt - pos) * 0.9)
            notes.append(MidiNote(MELODY_CHANNEL, note, self._velocity(rel, ctx.intensity), bar_start + pos, dur))
            self.last_note = note
        return notes, []

    def _run_down(self, ctx: PlayContext) -> list[MidiNote]:
        """Relance de fin de phrase : quatre doubles-croches qui descendent vers l'accord."""
        pool = self._pool(ctx.chord, ctx.key)
        start = self._step(pool, self._anchor(ctx.chord), 3)
        notes = []
        for i in range(4):
            note = self._step(pool, start, -i)
            notes.append(MidiNote(MELODY_CHANNEL, note, self._velocity(GAP_VELOCITY - 0.04 * i, ctx.intensity),
                                  ctx.beat + 0.25 * i, 0.24))
            self.last_note = note
        return notes

    def _free(self, ctx: PlayContext) -> list[MidiNote]:
        """Jeu libre : ornement montant vers une note de l'accord à chaque changement."""
        if not ctx.chord_changed:
            return []
        tones = self._chord_tones(ctx.chord)
        top = self._anchor(ctx.chord)
        below = [n for n in tones if n < top][-2:]
        figure = below + [top] if not ctx.singing else [top]
        rel = SINGING_VELOCITY if ctx.singing else GAP_VELOCITY
        notes = []
        for i, note in enumerate(figure):
            start = ctx.beat + 0.3 + 0.18 * i
            notes.append(MidiNote(MELODY_CHANNEL, note, self._velocity(rel, ctx.intensity), start,
                                  1.5 if i == len(figure) - 1 else 0.3))
        self.last_note = top
        return notes
