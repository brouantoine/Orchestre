"""Moteur de piano : choix des renversements (conduite des voix) et jeux par style.

- Main droite : accord dans le registre médium (Sol3-Ré5), renversement choisi pour
  bouger le moins possible d'un accord à l'autre (comme un pianiste).
- Main gauche : fondamentale grave (Do2-Si2), quinte, octave, basse marchante en jazz.
- Jeu libre (tempo inconnu) : nappes d'accords arpégés à chaque changement d'harmonie.
"""

from __future__ import annotations

from orchestre_ia.analysis.theory import Chord
from orchestre_ia.instruments.base import NoteOff, PlayContext
from orchestre_ia.midi.events import BASS_CHANNEL, PIANO_CHANNEL, MidiNote

RIGHT_LOW, RIGHT_HIGH = 55, 76
BASS_LOW, BASS_HIGH = 36, 47

# (position en temps dans la mesure, partie, durée en temps, vélocité relative)
Hit = tuple[float, str, float, float]
PATTERNS: dict[str, list[Hit]] = {
    "ballade": [
        (0, "bass", 2.0, 0.9), (0, "chord", 1.9, 0.6), (2, "bass8", 2.0, 0.7),
        (0.5, "arp1", 0.5, 0.55), (1.0, "arp2", 0.5, 0.55), (1.5, "arp3", 0.5, 0.5),
        (2.5, "arp1", 0.5, 0.55), (3.0, "arp2", 0.5, 0.55), (3.5, "arp3", 0.5, 0.5),
    ],
    "pop": [
        (0, "bass", 1.9, 0.9), (2, "bass", 1.9, 0.8),
        (0, "chord", 0.9, 0.8), (1, "chord", 0.9, 0.6), (2, "chord", 0.9, 0.75), (3, "chord", 0.9, 0.6),
    ],
    "gospel": [
        (0, "bass", 1.4, 0.95), (1.5, "bass8", 0.5, 0.7), (2, "bass", 1.9, 0.85),
        (0, "chord", 1.0, 0.85), (1.5, "chord", 0.5, 0.65), (2.75, "chord", 0.25, 0.6), (3, "chord", 1.0, 0.8),
    ],
    "jazz": [
        (0, "bass", 0.95, 0.8), (1, "bass3", 0.95, 0.7), (2, "bass5", 0.95, 0.75), (3, "bassapp", 0.95, 0.7),
        (0, "chord", 0.6, 0.7), (1.5, "chord", 0.4, 0.65),
    ],
    "rnb": [
        (0, "bass", 1.5, 0.9), (2.5, "bass", 1.4, 0.8),
        (0, "chord", 1.5, 0.75), (2.5, "chord", 1.4, 0.65),
    ],
    "classique": [
        (0, "bass", 4.0, 0.8),
        (0, "alb0", 0.5, 0.6), (0.5, "alb2", 0.5, 0.5), (1, "alb1", 0.5, 0.5), (1.5, "alb2", 0.5, 0.5),
        (2, "alb0", 0.5, 0.6), (2.5, "alb2", 0.5, 0.5), (3, "alb1", 0.5, 0.5), (3.5, "alb2", 0.5, 0.5),
    ],
    "afro": [
        (0, "bass", 1.4, 0.9), (1.5, "bass", 0.9, 0.75), (2.5, "bass5", 1.0, 0.75),
        (0, "chord", 0.5, 0.75), (0.75, "chord", 0.5, 0.6), (1.5, "chord", 0.5, 0.7),
        (2.5, "chord", 0.5, 0.65), (3.25, "chord", 0.5, 0.6),
    ],
    "reggae": [
        (0, "bass", 0.75, 0.9), (2.5, "bass5", 0.5, 0.75), (3, "bass", 0.75, 0.75),
        (1, "chord", 0.3, 0.75), (3, "chord", 0.3, 0.75),
    ],
    "soul": [
        (0, "bass", 1.4, 0.9), (1.5, "bass5", 0.5, 0.7), (2, "bass", 1.9, 0.85),
        (0, "chord", 0.9, 0.6), (1, "chord", 0.9, 0.75), (3, "chord", 0.9, 0.75),
    ],
    "zouglou": [
        (0, "bass", 0.9, 0.9), (1, "bass5", 0.9, 0.75), (2, "bass", 0.9, 0.85), (3, "bass5", 0.9, 0.75),
        (0.5, "chord", 0.3, 0.7), (1.5, "chord", 0.3, 0.65), (2.5, "chord", 0.3, 0.7), (3.5, "chord", 0.3, 0.65),
    ],
}


def chord_pitch_classes(chord: Chord, sevenths: bool) -> tuple[int, ...]:
    if not sevenths or chord.quality not in ("maj", "min"):
        return chord.pcs
    if chord.quality == "min":
        ext = 10
    elif chord.degree == 5:
        ext = 10  # dominante : 7e mineure
    else:
        ext = 11  # majeur : 7e majeure
    return chord.pcs + ((chord.root + ext) % 12,)


def voice_chord(pcs: tuple[int, ...], previous: list[int] | None) -> list[int]:
    """Renversement qui minimise le déplacement par rapport à l'accord précédent."""
    options = []
    for inversion in range(len(pcs)):
        order = pcs[inversion:] + pcs[:inversion]
        for octave_start in (RIGHT_LOW, RIGHT_LOW + 12):
            first = octave_start + (order[0] - octave_start) % 12
            notes = [first]
            for pc in order[1:]:
                n = notes[-1] + 1
                while n % 12 != pc:
                    n += 1
                notes.append(n)
            if notes[-1] <= RIGHT_HIGH:
                options.append(notes)
    if not options:
        return sorted(RIGHT_LOW + (pc - RIGHT_LOW) % 12 for pc in pcs)
    if not previous:
        return min(options, key=lambda v: abs(sum(v) / len(v) - 64))
    prev_center = sum(previous) / len(previous)

    def movement(v: list[int]) -> float:
        # distance de chaque note à la note la plus proche de l'accord précédent
        return sum(min(abs(n - p) for p in previous) for n in v) + 0.5 * abs(sum(v) / len(v) - prev_center)

    return min(options, key=movement)


def bass_note(pc: int, previous: int | None) -> int:
    candidates = [n for n in range(BASS_LOW, BASS_HIGH + 1) if n % 12 == pc]
    if previous is None:
        return candidates[0]
    return min(candidates, key=lambda n: abs(n - previous))


class PianoEngine:
    name = "Piano"

    def __init__(self) -> None:
        self.voicing: list[int] = []
        self.bass: int | None = None
        self._held: list[tuple[int, int]] = []  # notes tenues sans fin programmée (jeu libre)
        self._chord: Chord | None = None
        self.last_played: list[int] = []

    def _velocity(self, rel: float, intensity: float) -> int:
        return int(max(30, min(124, rel * (75 + 50 * intensity))))

    def release_all(self, beat: float) -> list[NoteOff]:
        offs = [NoteOff(ch, n, beat) for ch, n in self._held]
        self._held = []
        return offs

    def _revoice(self, ctx: PlayContext) -> None:
        pcs = chord_pitch_classes(ctx.chord, ctx.style.seventh_chords)
        self.voicing = voice_chord(pcs, self.voicing or None)
        self.bass = bass_note(ctx.chord.root, self.bass)
        self._chord = ctx.chord

    def play_beat(self, ctx: PlayContext) -> tuple[list[MidiNote], list[NoteOff]]:
        notes: list[MidiNote] = []
        offs: list[NoteOff] = []
        if ctx.chord_changed or self._chord is None:
            offs += self.release_all(ctx.beat - 0.02)
            self._revoice(ctx)

        if not ctx.rhythmic:
            # Jeu libre : accord arpégé tenu à chaque changement, relancé doucement toutes les 2 mesures
            if ctx.chord_changed or not self._held or ctx.beat % 8 == 0:
                offs += self.release_all(ctx.beat - 0.02)
                vel = self._velocity(0.85, ctx.intensity)
                notes.append(MidiNote(BASS_CHANNEL, self.bass, vel, ctx.beat, 0))
                self._held.append((BASS_CHANNEL, self.bass))
                for i, n in enumerate(self.voicing):
                    notes.append(MidiNote(PIANO_CHANNEL, n, vel - 8, ctx.beat + 0.06 * (i + 1), 0))
                    self._held.append((PIANO_CHANNEL, n))
            self.last_played = list(self.voicing)
            return notes, offs

        offs += self.release_all(ctx.beat - 0.02)
        pattern = PATTERNS.get(ctx.style.piano, PATTERNS["ballade"])
        bar_start = ctx.beat - ctx.beat_in_bar
        for pos, part, dur, rel in pattern:
            if not (ctx.beat_in_bar <= pos < ctx.beat_in_bar + 1):
                continue
            start = bar_start + self._swing(pos, ctx.style.swing)
            vel = self._velocity(rel, ctx.intensity)
            if ctx.intensity < 0.3 and part.startswith("arp") and pos % 1 != 0:
                continue  # jeu allégé quand le chanteur est très doux
            for ch, n in self._resolve(part):
                notes.append(MidiNote(ch, n, vel, start, dur * 0.95))
        self.last_played = list(self.voicing)
        return notes, offs

    def _resolve(self, part: str) -> list[tuple[int, int]]:
        v, b = self.voicing, self.bass if self.bass is not None else 36
        root_pc = self._chord.root if self._chord else 0
        pcs = self._chord.pcs if self._chord else (0, 4, 7)
        if part == "chord":
            return [(PIANO_CHANNEL, n) for n in v]
        if part == "bass":
            return [(BASS_CHANNEL, b)]
        if part == "bass8":
            return [(BASS_CHANNEL, b + 12)]
        if part == "bass5":
            return [(BASS_CHANNEL, b + (pcs[2] - root_pc) % 12)]
        if part == "bass3":
            return [(BASS_CHANNEL, b + (pcs[1] - root_pc) % 12)]
        if part == "bassapp":
            return [(BASS_CHANNEL, b + 11)]  # approche chromatique vers la fondamentale à l'octave
        if part.startswith("arp"):
            idx = int(part[3:])
            return [(PIANO_CHANNEL, v[idx % len(v)])]
        if part.startswith("alb"):
            idx = int(part[3:])
            low = sorted(n - 12 for n in v[:3])
            return [(PIANO_CHANNEL, low[idx % len(low)])]
        return []

    @staticmethod
    def _swing(pos: float, swing: float) -> float:
        frac = pos % 1
        if abs(frac - 0.5) < 1e-6:
            return pos + swing * 0.5
        return pos

    def ending(self, beat: float, chord: Chord, intensity: float) -> list[MidiNote]:
        """Accord final tenu (conclusion)."""
        self.voicing = voice_chord(chord.pcs, self.voicing or None)
        self.bass = bass_note(chord.root, self.bass)
        vel = self._velocity(0.8, intensity)
        notes = [MidiNote(BASS_CHANNEL, self.bass, vel, beat, 4.0)]
        notes += [MidiNote(PIANO_CHANNEL, n, vel - 6, beat + 0.05 * i, 4.0) for i, n in enumerate(self.voicing)]
        return notes
