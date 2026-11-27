"""Verrouillage de grille : une fois la progression trouvée, l'orchestre la tient en rythme.

Comme un musicien qui a compris la grille d'un chant :
- repérage : quand la même suite d'accords (2 à 8 accords, mêmes durées en temps)
  revient une deuxième fois — dès son dernier accord —, la grille est verrouillée ;
- recalage : un changement chanté n'est entendu qu'au point de décision suivant
  (2 temps plus tard : il faut avoir entendu les notes du nouvel accord). Si tous les
  changements repérés tombent au même endroit de la mesure, la grille verrouillée est
  avancée d'autant : elle change d'accord en même temps que le chanteur, plus après lui ;
- jeu : l'orchestre rejoue la grille de lui-même, change d'accord pile sur le temps
  (il n'attend plus d'avoir entendu la voix) et garde la cadence pendant les respirations ;
- surveillance : à chaque point de décision où l'on chante, l'accord prévu est comparé
  à ce qui est chanté ; nettement contredit deux fois de suite (≈ une mesure), la grille
  est lâchée — le chant change (pont, autre partie) — et l'orchestre se remet à suivre ;
- mémoire : les grilles déjà jouées dans le chant sont gardées ; quand l'une revient
  (le refrain), deux accords reconnus suffisent pour la reprendre. Une grille lâchée
  avant d'avoir tenu 2 mesures sans contradiction était fausse (erreur d'écoute) : oubliée.

Uniquement en jeu rythmé : sans tempo, il n'y a pas de cadence à tenir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestre_ia.analysis.theory import Chord

log = logging.getLogger(__name__)

MIN_CHORDS, MAX_CHORDS = 2, 8
MAX_CYCLE_BEATS = 32
UNLOCK_MARGIN = 0.3  # écart de score (adéquation au chant) au-delà duquel l'accord prévu est contredit
UNLOCK_CHECKS = 2  # contradictions consécutives avant de lâcher la grille
RELOCK_MATCH = 2  # accords reconnus pour reprendre une grille déjà jouée
DETECTION_LAG = 2  # temps entre un changement chanté et le point de décision qui l'entend
CONFIRM_CHECKS = 4  # vérifications réussies (≈ 2 mesures) pour qu'une grille soit tenue pour juste

Segment = tuple[tuple[int, str], int]  # ((fondamentale, qualité), durée en temps)


def _triad(chord: Chord) -> tuple[int, str]:
    return chord.root, chord.triad_quality


@dataclass(frozen=True)
class Cycle:
    chords: tuple[Chord, ...]
    durations: tuple[int, ...]

    @property
    def beats(self) -> int:
        return sum(self.durations)

    def segments(self) -> list[Segment]:
        return [(_triad(c), d) for c, d in zip(self.chords, self.durations)]

    def names(self) -> str:
        return " → ".join(c.name for c in self.chords)


class ProgressionLock:
    def __init__(self, detection_lag: int = DETECTION_LAG) -> None:
        self.detection_lag = detection_lag
        self.reset()

    def reset(self) -> None:
        """Nouveau chant : grille et mémoire des grilles oubliées."""
        self._changes: list[tuple[Chord, int]] = []  # (accord, temps où il commence)
        self.cycle: Cycle | None = None
        self._start = 0  # temps où commence un tour de grille
        self._misses = 0
        self._hits = 0
        self.known: list[Cycle] = []

    def unlock(self) -> None:
        """Grille lâchée (changement de mode, silence) : la mémoire des grilles est gardée."""
        self.cycle = None
        self._misses = 0
        self._hits = 0
        self._changes = []

    @property
    def locked(self) -> bool:
        return self.cycle is not None

    # ------------------------------------------------------------ repérage
    def observe(self, chord: Chord, beat: int) -> bool:
        """Un accord commence au temps `beat` (jeu non verrouillé). Retourne True si la grille se verrouille."""
        if self._changes and _triad(self._changes[-1][0]) == _triad(chord):
            return False
        self._changes.append((chord, beat))
        self._changes = self._changes[-(2 * MAX_CHORDS + 2):]
        segments = [
            (_triad(c), nxt - b) for (c, b), (_, nxt) in zip(self._changes, self._changes[1:])
        ]
        return self._detect_repeat(beat) or self._detect_known(segments, chord, beat)

    def _detect_repeat(self, beat: int) -> bool:
        """Le tour en cours (jusqu'à l'accord qui commence) refait le tour précédent."""
        changes = self._changes
        for n in range(MIN_CHORDS, MAX_CHORDS + 1):
            if len(changes) < 2 * n:
                break
            prev_round, this_round = changes[-2 * n:-n], changes[-n:]
            if [_triad(c) for c, _ in prev_round] != [_triad(c) for c, _ in this_round]:
                continue
            durations = tuple(b2 - b1 for (_, b1), (_, b2) in zip(changes[-2 * n:], changes[-2 * n + 1:]))
            prev_durations, this_durations = durations[:n], durations[n:]  # le dernier accord n'a pas encore de durée
            if prev_durations[:n - 1] != this_durations or sum(prev_durations) > MAX_CYCLE_BEATS:
                continue
            cycle = Cycle(tuple(c for c, _ in prev_round), prev_durations)
            self._lock(cycle, beat, "repérée", start=this_round[0][1], change_beats=[b for _, b in changes[-2 * n:]])
            return True
        return False

    def _detect_known(self, segments: list[Segment], chord: Chord, beat: int) -> bool:
        if len(segments) < RELOCK_MATCH:
            return False
        recent = segments[-RELOCK_MATCH:]
        for cycle in self.known:
            segs = cycle.segments()
            n = len(segs)
            for i in range(n):
                window = [segs[(i + k) % n] for k in range(RELOCK_MATCH)]
                nxt = (i + RELOCK_MATCH) % n
                if window == recent and segs[nxt][0] == _triad(chord):
                    start = beat - sum(cycle.durations[:nxt])
                    self._lock(cycle, beat, "reprise", start=start, change_beats=[b for _, b in self._changes])
                    return True
        return False

    def _lock(self, cycle: Cycle, beat: int, how: str, start: int, change_beats: list[int]) -> None:
        lag = self.detection_lag
        step = max(1, lag)
        if len({b % 4 for b in change_beats}) != 1 or any(d % step for d in cycle.durations):
            lag = 0  # changements irréguliers : pas de recalage hasardeux
        self.cycle = cycle
        self._start = start - lag
        self._misses = 0
        self._hits = 0
        if cycle not in self.known:
            self.known.append(cycle)
        log.info("Grille %s : %s (%d temps%s)", how, cycle.names(), cycle.beats,
                 f", avancée de {lag} temps sur l'écoute" if lag else "")

    # ------------------------------------------------------------ jeu
    def expected(self, beat: int) -> Chord | None:
        """Accord de la grille au temps `beat` (None si non verrouillée)."""
        if self.cycle is None:
            return None
        pos = (beat - self._start) % self.cycle.beats
        for chord, dur in zip(self.cycle.chords, self.cycle.durations):
            if pos < dur:
                return chord
            pos -= dur
        return self.cycle.chords[-1]

    def check(self, expected_score: float, best_score: float) -> bool:
        """Compare l'accord prévu au meilleur accord pour le chant. Retourne True si la grille est lâchée."""
        if self.cycle is None:
            return False
        if best_score - expected_score > UNLOCK_MARGIN:
            self._misses += 1
        else:
            self._misses = 0
            self._hits += 1
        if self._misses >= UNLOCK_CHECKS:
            cycle = self.cycle
            if self._hits < CONFIRM_CHECKS and cycle in self.known:
                self.known.remove(cycle)  # jamais confirmée : erreur d'écoute, pas un changement de partie
                log.info("Grille lâchée et oubliée (jamais confirmée par le chant) : %s", cycle.names())
            else:
                log.info("Grille lâchée : le chant ne suit plus %s", cycle.names())
            self.unlock()
            return True
        return False
