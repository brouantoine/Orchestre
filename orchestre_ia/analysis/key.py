"""Estimation de tonalité (profils de Krumhansl-Kessler) avec mémoire et inertie.

- Histogramme des classes de hauteur pondéré par la durée chantée, avec oubli
  progressif (demi-vie ~30 s) : la tonalité suit les modulations réelles.
- Inertie : une nouvelle tonalité doit rester la meilleure pendant `switch_s`
  secondes ET dépasser l'ancienne d'une marge, sinon on garde l'ancienne.
  Une note de passage ou un ornement ne fait donc jamais changer de tonalité.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orchestre_ia.analysis.theory import Key

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass(frozen=True)
class KeyEstimate:
    key: Key
    confidence: float  # 0-1
    candidates: tuple[tuple[Key, float], ...]  # 3 meilleures (tonalité, corrélation)


def key_scores(histogram: np.ndarray) -> list[tuple[Key, float]]:
    if histogram.sum() <= 0 or np.allclose(histogram, histogram[0]):
        return []
    scores = []
    for tonic in range(12):
        scores.append((Key(tonic, False), float(np.corrcoef(histogram, np.roll(MAJOR_PROFILE, tonic))[0, 1])))
        scores.append((Key(tonic, True), float(np.corrcoef(histogram, np.roll(MINOR_PROFILE, tonic))[0, 1])))
    scores.sort(key=lambda s: s[1], reverse=True)
    return scores


class KeyEstimator:
    def __init__(
        self,
        half_life_s: float = 30.0,
        min_evidence_s: float = 3.0,
        switch_s: float = 4.0,
        switch_margin: float = 0.08,
        established_confidence: float = 0.2,
    ) -> None:
        self.established_confidence = established_confidence
        self.half_life_s = half_life_s
        self.min_evidence_s = min_evidence_s
        self.switch_s = switch_s
        self.switch_margin = switch_margin
        self.histogram = np.zeros(12)
        self.current: KeyEstimate | None = None
        self._challenger: Key | None = None
        self._challenger_since = 0.0

    @property
    def evidence_s(self) -> float:
        return float(self.histogram.sum())

    def add(self, pitch_class: int, duration_s: float) -> None:
        self.histogram *= 0.5 ** (duration_s / self.half_life_s)
        self.histogram[pitch_class % 12] += duration_s

    def decay(self, dt: float) -> None:
        self.histogram *= 0.5 ** (dt / self.half_life_s)

    def estimate(self, now: float) -> KeyEstimate | None:
        """Réévalue la tonalité. Retourne l'estimation retenue (stable) ou None."""
        if self.evidence_s < self.min_evidence_s:
            return self.current
        scores = key_scores(self.histogram)
        if not scores:
            return self.current
        best_key, best_score = scores[0]
        second = scores[1][1]
        evidence_factor = min(1.0, self.evidence_s / (3 * self.min_evidence_s))
        confidence = float(np.clip((best_score - second) / 0.25, 0, 1) * np.clip(best_score / 0.6, 0, 1) * evidence_factor)
        candidates = tuple(scores[:3])

        if self.current is None or self.current.confidence < self.established_confidence:
            # tonalité pas encore établie : on suit librement la meilleure hypothèse
            self.current = KeyEstimate(best_key, confidence, candidates)
            self._challenger = None
            return self.current

        current_score = next(s for k, s in scores if k == self.current.key)
        if best_key == self.current.key:
            self._challenger = None
            self.current = KeyEstimate(best_key, confidence, candidates)
        elif best_score - current_score >= self.switch_margin:
            if self._challenger != best_key:
                self._challenger, self._challenger_since = best_key, now
            elif now - self._challenger_since >= self.switch_s:
                self.current = KeyEstimate(best_key, confidence, candidates)
                self._challenger = None
        else:
            self._challenger = None
            # tonalité conservée, confiance réduite si une rivale s'approche
            conf = float(np.clip((current_score - second) / 0.25, 0, 1)) * evidence_factor
            self.current = KeyEstimate(self.current.key, max(0.0, conf), candidates)
        return self.current
