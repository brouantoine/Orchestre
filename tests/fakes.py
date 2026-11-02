"""Doublures de test : flux d'entrée PortAudio simulé, déterministe."""

from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np

SignalFn = Callable[[np.ndarray], np.ndarray]  # temps (s) -> échantillons mono


def sine(freq: float, amplitude: float) -> SignalFn:
    return lambda t: (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence() -> SignalFn:
    return lambda t: np.zeros_like(t, dtype=np.float32)


class FakeInputStream:
    """Imite sounddevice.InputStream : appelle le callback depuis un thread séparé.

    `speed` > 1 accélère le temps (les tests restent rapides).
    `stop_after_s` simule un micro qui cesse de fournir des données.
    """

    def __init__(
        self,
        *,
        samplerate: int,
        blocksize: int,
        channels: int,
        callback,
        signal_fn: SignalFn,
        speed: float = 4.0,
        stop_after_s: float | None = None,
        **_: object,
    ) -> None:
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback
        self.signal_fn = signal_fn
        self.speed = speed
        self.stop_after_s = stop_after_s
        self.latency = 0.010
        self.active = False
        self.closed = False
        self._thread: threading.Thread | None = None
        self._halt = threading.Event()

    def start(self) -> None:
        self.active = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        n = 0
        period = self.blocksize / self.samplerate / self.speed
        while not self._halt.is_set():
            t = (np.arange(self.blocksize) + n) / self.samplerate
            if self.stop_after_s is not None and t[0] >= self.stop_after_s:
                return  # le micro « disparaît » : plus aucun callback
            mono = self.signal_fn(t)
            block = np.repeat(mono[:, None], self.channels, axis=1)
            self.callback(block, self.blocksize, None, None)
            n += self.blocksize
            time.sleep(period)

    def stop(self) -> None:
        self._halt.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self.active = False

    def close(self) -> None:
        self.closed = True


def fake_factory(signal_fn: SignalFn, created: list | None = None, **options):
    def factory(**kwargs):
        stream = FakeInputStream(signal_fn=signal_fn, **options, **kwargs)
        if created is not None:
            created.append(stream)
        return stream

    return factory
