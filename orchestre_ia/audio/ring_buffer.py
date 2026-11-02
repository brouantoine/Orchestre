"""Tampon circulaire mono float32, partagé entre le thread audio et les consommateurs.

- `write` est appelé depuis le callback PortAudio : il ne fait qu'une copie mémoire
  sous verrou très court, sans allocation de grande taille.
- `read` consomme les échantillons dans l'ordre (thread de traitement).
- `latest` lit la fenêtre la plus récente sans consommer (fenêtres d'analyse).
Si le consommateur prend du retard, les plus anciens échantillons sont écrasés
et le compteur `overruns` est incrémenté.
"""

from __future__ import annotations

import threading

import numpy as np


class AudioRingBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity doit être > 0")
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._capacity = capacity
        self._written = 0  # nombre total d'échantillons écrits (monotone)
        self._read_pos = 0  # position absolue du prochain échantillon à lire
        self._cond = threading.Condition(threading.Lock())
        self._closed = False
        self.overruns = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def available(self) -> int:
        with self._cond:
            return self._written - self._read_pos

    @property
    def total_written(self) -> int:
        with self._cond:
            return self._written

    def write(self, data: np.ndarray) -> None:
        n_total = len(data)
        if n_total == 0:
            return
        data = data[-self._capacity :]
        n = len(data)
        with self._cond:
            start = (self._written + (n_total - n)) % self._capacity
            end = start + n
            if end <= self._capacity:
                self._buf[start:end] = data
            else:
                k = self._capacity - start
                self._buf[start:] = data[:k]
                self._buf[: n - k] = data[k:]
            self._written += n_total
            if self._written - self._read_pos > self._capacity:
                self.overruns += 1
                self._read_pos = self._written - self._capacity
            self._cond.notify_all()

    def read(self, n: int, timeout: float | None = None) -> np.ndarray | None:
        """Consomme exactement `n` échantillons ; retourne None si délai dépassé ou tampon fermé."""
        if n > self._capacity:
            raise ValueError("n dépasse la capacité du tampon")
        with self._cond:
            ok = self._cond.wait_for(
                lambda: self._closed or self._written - self._read_pos >= n, timeout
            )
            if not ok or self._written - self._read_pos < n:
                return None
            out = self._copy_range(self._read_pos, n)
            self._read_pos += n
            return out

    def latest(self, n: int) -> np.ndarray:
        """Les `n` derniers échantillons (moins s'il n'y en a pas assez), sans consommer."""
        with self._cond:
            n = min(n, self._written, self._capacity)
            return self._copy_range(self._written - n, n)

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _copy_range(self, absolute_start: int, n: int) -> np.ndarray:
        start = absolute_start % self._capacity
        end = start + n
        if end <= self._capacity:
            return self._buf[start:end].copy()
        k = self._capacity - start
        return np.concatenate((self._buf[start:], self._buf[: n - k]))
