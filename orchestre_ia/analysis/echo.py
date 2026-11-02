"""Garde anti-réécoute : distinguer la voix de l'orchestre entendu par le micro.

Avec des haut-parleurs, le micro capte aussi l'accompagnement. Le niveau capté
de cette « fuite » est proportionnel au niveau joué : micro_dB ≈ sortie_dB + couplage.

Le couplage est estimé par statistique de minimum : sur les 8 dernières secondes,
le plus petit écart (micro - sortie) correspond aux instants où seul l'orchestre
était capté (respirations, fins de phrases). Une trame n'est retenue comme voix
que si elle dépasse la fuite attendue d'une marge (6 dB par défaut).
"""

from __future__ import annotations

from collections import deque
from typing import Callable

OUTPUT_ACTIVE_DB = -60.0


class EchoGuard:
    def __init__(
        self,
        output_level: Callable[[float, float], float],
        margin_db: float = 6.0,
        window_s: float = 8.0,
        initial_coupling_db: float = 0.0,
    ) -> None:
        self.output_level = output_level
        self.margin_db = margin_db
        self.window_s = window_s
        self.initial_coupling_db = initial_coupling_db
        self._ratios: deque[tuple[float, float]] = deque()
        self._last_sample = -1.0

    @property
    def coupling_db(self) -> float:
        if not self._ratios:
            return self.initial_coupling_db
        return min(r for _, r in self._ratios)

    def is_voice(self, t: float, mic_level_db: float) -> bool:
        """`t` : instant monotonic de la trame micro ; `mic_level_db` : son niveau."""
        out_db = self.output_level(t - 0.2, t + 0.03)
        if out_db <= OUTPUT_ACTIVE_DB:
            return True  # l'orchestre est silencieux : tout ce qui est capté vient de la pièce
        ratio = mic_level_db - out_db
        if t - self._last_sample >= 0.1:
            self._last_sample = t
            self._ratios.append((t, ratio))
            while self._ratios and t - self._ratios[0][0] > self.window_s:
                self._ratios.popleft()
        return ratio > self.coupling_db + self.margin_db
