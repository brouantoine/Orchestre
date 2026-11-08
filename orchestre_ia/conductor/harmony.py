"""Moteur harmonique : choisit l'accord qui accompagne le mieux ce qui vient d'être chanté.

Score de chaque accord candidat (24 accords majeurs/mineurs + quelques enrichis) :
- adéquation : les notes chantées appartiennent-elles à l'accord ?
- contexte tonal : accords de la tonalité favorisés, d'autant plus que la
  tonalité est sûre (fonctionne donc aussi pour une chanson inconnue, sans tonalité établie) ;
- continuité : bonus pour garder l'accord en cours (évite les changements nerveux) ;
- enchaînements usuels : V→I, IV→V, etc. ;
- mémoire apprise (séances écoutées, `orchestre_ia.learning`) : remplace peu à peu
  les règles génériques par les habitudes réellement entendues, y compris les
  accords d'emprunt devenus familiers (bVII, III…).
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class HarmonyDecision:
    chord: Chord
    score: float
    alternatives: tuple[tuple[Chord, float], ...]


class HarmonyEngine:
    def __init__(
        self, stay_bonus: float = 0.15, min_evidence: float = 0.15, learned: LearnedHarmony | None = None
    ) -> None:
        self.stay_bonus = stay_bonus
        self.min_evidence = min_evidence
        self.learned = learned
        self.current: Chord | None = None

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
        if key is not None:
            diatonic = chord.degree > 0
            outside_penalty = -0.6
            prior = DEGREE_PRIOR.get(chord.degree, 0.0)
            progression = 0.0
            if self.current is not None and diatonic:
                progression = PROGRESSION_BONUS.get((self.current.degree, chord.degree), 0.0)
            trust = self.learned.reliability(key.minor) if self.learned is not None else 0.0
            if self.learned is not None and trust > 0:
                share = self.learned.usage_share(key.minor, _token(chord, key))
                # accord d'emprunt souvent entendu : il n'est plus traité comme une fausse note
                outside_penalty *= 1.0 - trust * min(1.0, share / 0.05)
                prior = (1 - trust) * prior + trust * self.learned.usage_prior(key, chord)
                if self.current is not None and not same:
                    learned_move = self.learned.transition_bonus(key, self.current, chord)
                    progression = (1 - trust) * progression + trust * learned_move
            s += key_confidence * (0.15 if diatonic else outside_penalty)
            s += key_confidence * prior
            s += progression
        if same:
            s += self.stay_bonus
        return s

    def predict_next(self, key: Key, current: Chord, top: int = 3) -> list[Chord]:
        """Accords suivants les plus attendus après `current`, sans rien entendre (évaluation)."""
        previous, self.current = self.current, self._with_degree(current, key)
        try:
            candidates = [
                self._with_degree(c, key)
                for c in ALL_TRIADS
                if not (c.root == current.root and c.quality == current.triad_quality)
            ]
            ranked = sorted(candidates, key=lambda c: self.context(c, key, 1.0), reverse=True)
        finally:
            self.current = previous
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
        self.current = best
        return HarmonyDecision(best, best_score, tuple(scored[1:4]))

    def reset(self) -> None:
        self.current = None


def _token(chord: Chord, key: Key) -> str:
    from orchestre_ia.learning.memory import chord_token

    return chord_token(chord, key)
