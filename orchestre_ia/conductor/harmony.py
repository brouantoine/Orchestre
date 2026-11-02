"""Moteur harmonique : choisit l'accord qui accompagne le mieux ce qui vient d'être chanté.

Score de chaque accord candidat (24 accords majeurs/mineurs + quelques enrichis) :
- adéquation : les notes chantées appartiennent-elles à l'accord ?
- contexte tonal : accords de la tonalité favorisés, d'autant plus que la
  tonalité est sûre (fonctionne donc aussi pour une chanson inconnue, sans tonalité établie) ;
- continuité : bonus pour garder l'accord en cours (évite les changements nerveux) ;
- enchaînements usuels : V→I, IV→V, etc.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orchestre_ia.analysis.theory import Chord, Key, diatonic_chords

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
    def __init__(self, stay_bonus: float = 0.15, min_evidence: float = 0.15) -> None:
        self.stay_bonus = stay_bonus
        self.min_evidence = min_evidence
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
        s = fit / total
        if key is not None:
            diatonic = chord.degree > 0
            s += key_confidence * (0.15 if diatonic else -0.6)
            s += key_confidence * DEGREE_PRIOR.get(chord.degree, 0.0)
            if self.current is not None and diatonic:
                s += PROGRESSION_BONUS.get((self.current.degree, chord.degree), 0.0)
        if self.current is not None and chord.root == self.current.root and chord.triad_quality == self.current.triad_quality:
            s += self.stay_bonus
        return s

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
