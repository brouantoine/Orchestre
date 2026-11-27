"""Moteur harmonique : choisit l'accord qui accompagne le mieux ce qui vient d'être chanté.

Score de chaque accord candidat (24 accords majeurs/mineurs + quelques enrichis) :
- adéquation : les notes chantées appartiennent-elles à l'accord ?
- contexte tonal : accords de la tonalité favorisés, d'autant plus que la
  tonalité est sûre (fonctionne donc aussi pour une chanson inconnue, sans tonalité établie) ;
- continuité : bonus pour garder l'accord en cours (évite les changements nerveux) ;
- enchaînements usuels : V→I, IV→V, etc. ;
- mémoire apprise (séances écoutées, `orchestre_ia.learning`) : remplace peu à peu
  les règles génériques par les habitudes réellement entendues, y compris les
  accords d'emprunt devenus familiers (bVII, III…) ; les deux derniers accords comptent ;
- mémoire du chant en cours : les grilles déjà jouées depuis le début du chant
  (couplet, refrain, boucle) annoncent l'accord suivant ; le chant entendu garde le dernier mot.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from orchestre_ia.analysis.theory import Chord, Key, diatonic_chords

if TYPE_CHECKING:
    from orchestre_ia.learning.memory import LearnedHarmony

ALL_TRIADS = [Chord(root, q) for root in range(12) for q in ("maj", "min")]

# bonus d'enchaînement (degré précédent, degré suivant)
PROGRESSION_BONUS = {(5, 1): 0.12, (4, 5): 0.06, (4, 1): 0.06, (2, 5): 0.08, (6, 4): 0.04, (1, 4): 0.04, (1, 5): 0.04, (1, 6): 0.03}
DEGREE_PRIOR = {1: 0.12, 4: 0.07, 5: 0.08, 6: 0.03, 2: 0.02}

# Mémoire du chant en cours : un chant répète ses grilles (couplets, refrains, boucles).
# Mesure du 2026-11-26 sur des chants tenus à part (accord suivant, 1er choix / parmi 3) :
# louange 48 % / 86 % avec le corpus seul -> 72 % / 95 % avec le chant en cours ; pop 41 % -> 75 %.
# SONG_MEMORY_K : nombre d'observations à partir duquel le chant pèse autant que le reste (0,5 à 2 : équivalents).
SONG_MEMORY_K = 1.0
SONG_MEMORY_WEIGHT = 0.25  # même échelle que les enchaînements appris

Triad = tuple[int, str]


@dataclass(frozen=True)
class HarmonyDecision:
    chord: Chord
    score: float
    alternatives: tuple[tuple[Chord, float], ...]


class HarmonyEngine:
    def __init__(
        self,
        stay_bonus: float = 0.15,
        min_evidence: float = 0.15,
        learned: LearnedHarmony | None = None,
        song_memory: bool = True,
    ) -> None:
        self.stay_bonus = stay_bonus
        self.min_evidence = min_evidence
        self.learned = learned
        self.song_memory = song_memory
        self.current: Chord | None = None
        self.previous: Chord | None = None  # accord joué avant `current` (mémoire à deux accords)
        self._song: list[Triad] = []  # accords joués depuis le début du chant (sans répétition)
        self._song_moves: dict[Triad, Counter[Triad]] = {}
        self._song_contexts: dict[tuple[Triad, Triad], Counter[Triad]] = {}

    def remember(self, chord: Chord) -> None:
        """Ajoute un accord joué à la mémoire du chant en cours (indépendante de la tonalité)."""
        triad = _triad(chord)
        if self._song and self._song[-1] == triad:
            return
        if self._song:
            src = self._song[-1]
            self._song_moves.setdefault(src, Counter())[triad] += 1
            if len(self._song) >= 2:
                self._song_contexts.setdefault((self._song[-2], src), Counter())[triad] += 1
        self._song.append(triad)

    def song_move(self, chord: Chord) -> tuple[float, float]:
        """(poids, probabilité) que le chant en cours donne à l'enchaînement `current` -> `chord`.

        Interpolation à deux niveaux : enchaînements depuis l'accord en cours, puis depuis
        les deux derniers accords ; chaque niveau pèse n / (n + K) après n observations.
        """
        if not self.song_memory or self.current is None:
            return 0.0, 0.0
        src, dst = _triad(self.current), _triad(chord)
        levels = [self._song_moves.get(src)]
        if self.previous is not None:
            levels.append(self._song_contexts.get((_triad(self.previous), src)))
        weight, mixed = 0.0, 0.0
        for counts in levels:
            if not counts:
                continue
            n = sum(counts.values())
            lam = n / (n + SONG_MEMORY_K)
            mixed = (1 - lam) * mixed + lam * counts[dst] / n
            weight = 1 - (1 - weight) * (1 - lam)
        return (weight, mixed / weight) if weight > 0 else (0.0, 0.0)

    def _with_degree(self, chord: Chord, key: Key | None) -> Chord:
        if key is None:
            return Chord(chord.root, chord.quality, 0)
        for d in diatonic_chords(key):
            if d.root == chord.root and d.triad_quality == chord.triad_quality:
                return Chord(chord.root, chord.quality, d.degree)
        return Chord(chord.root, chord.quality, 0)

    def score(self, chord: Chord, evidence: np.ndarray, key: Key | None, key_confidence: float) -> float:
        total = evidence.sum()
        fit = 0.0
        pcs = chord.pcs
        for pc in range(12):
            w = evidence[pc]
            if w <= 0:
                continue
            if pc == chord.root:
                fit += 1.0 * w
            elif pc in pcs:
                fit += 0.85 * w
            elif key is not None and pc in key.scale:
                fit -= 0.25 * w  # note de passage dans la gamme : légère pénalité
            else:
                fit -= 0.6 * w
        return fit / total + self.context(chord, key, key_confidence)

    def context(self, chord: Chord, key: Key | None, key_confidence: float) -> float:
        """Part du score indépendante du chant : tonalité, habitudes apprises, enchaînement."""
        s = 0.0
        same = (
            self.current is not None
            and chord.root == self.current.root
            and chord.triad_quality == self.current.triad_quality
        )
        progression = 0.0
        if key is not None:
            diatonic = chord.degree > 0
            outside_penalty = -0.6
            prior = DEGREE_PRIOR.get(chord.degree, 0.0)
            if self.current is not None and diatonic:
                progression = PROGRESSION_BONUS.get((self.current.degree, chord.degree), 0.0)
            trust = self.learned.reliability(key.minor) if self.learned is not None else 0.0
            if self.learned is not None and trust > 0:
                share = self.learned.usage_share(key.minor, _token(chord, key))
                # accord d'emprunt souvent entendu : il n'est plus traité comme une fausse note
                outside_penalty *= 1.0 - trust * min(1.0, share / 0.05)
                prior = (1 - trust) * prior + trust * self.learned.usage_prior(key, chord)
                if self.current is not None and not same:
                    learned_move = self.learned.transition_bonus(key, self.current, chord, self.previous)
                    progression = (1 - trust) * progression + trust * learned_move
            s += key_confidence * (0.15 if diatonic else outside_penalty)
            s += key_confidence * prior
        if self.current is not None and not same:
            weight, p = self.song_move(chord)
            if weight > 0:
                progression = (1 - weight) * progression + weight * SONG_MEMORY_WEIGHT * p
        s += progression
        if same:
            s += self.stay_bonus
        return s

    def predict_next(self, key: Key, current: Chord, top: int = 3, previous: Chord | None = None) -> list[Chord]:
        """Accords suivants les plus attendus après `current` (et `previous`), sans rien entendre."""
        saved = self.current, self.previous
        self.current, self.previous = self._with_degree(current, key), previous
        try:
            candidates = [
                self._with_degree(c, key)
                for c in ALL_TRIADS
                if not (c.root == current.root and c.quality == current.triad_quality)
            ]
            ranked = sorted(candidates, key=lambda c: self.context(c, key, 1.0), reverse=True)
        finally:
            self.current, self.previous = saved
        return ranked[:top]

    def decide(self, evidence: np.ndarray, key: Key | None, key_confidence: float) -> HarmonyDecision | None:
        """Choisit l'accord ; None si trop peu de notes chantées (on garde l'accord en cours)."""
        if evidence.sum() < self.min_evidence:
            return None
        candidates = [self._with_degree(c, key) for c in ALL_TRIADS]
        scored = sorted(
            ((c, self.score(c, evidence, key, key_confidence)) for c in candidates),
            key=lambda cs: cs[1],
            reverse=True,
        )
        best, best_score = scored[0]
        if self.current is not None and not _same_triad(best, self.current):
            self.previous = self.current
        self.current = best
        self.remember(best)
        return HarmonyDecision(best, best_score, tuple(scored[1:4]))

    def reset(self) -> None:
        """Fin du chant : oublie l'accord en cours et la mémoire du chant."""
        self.current = None
        self.previous = None
        self._song.clear()
        self._song_moves.clear()
        self._song_contexts.clear()


def _triad(chord: Chord) -> Triad:
    return chord.root, chord.triad_quality


def _same_triad(a: Chord, b: Chord) -> bool:
    return a.root == b.root and a.triad_quality == b.triad_quality


def _token(chord: Chord, key: Key) -> str:
    from orchestre_ia.learning.memory import chord_token

    return chord_token(chord, key)
