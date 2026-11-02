"""Événements MIDI planifiés en temps musical (temps = beats) et file d'attente thread-safe."""

from __future__ import annotations

import heapq
import itertools
import threading
from dataclasses import dataclass, field

PIANO_CHANNEL = 0
BASS_CHANNEL = 1  # main gauche du piano sur un canal séparé (volume indépendant)
DRUM_CHANNEL = 9  # canal 10 en numérotation General MIDI


@dataclass(frozen=True, slots=True)
class MidiNote:
    """Note à jouer : début et durée en temps (beats)."""

    channel: int
    note: int
    velocity: int
    start: float
    duration: float


@dataclass(order=True, slots=True)
class ScheduledMessage:
    beat: float
    priority: int  # 0 = note off avant 1 = note on au même instant
    seq: int
    kind: str = field(compare=False)  # "on" | "off" | "cc"
    channel: int = field(compare=False)
    data1: int = field(compare=False)
    data2: int = field(compare=False)


class MidiScheduler:
    """File de messages triés par temps. Le thread de sortie audio dépile ce qui est dû."""

    def __init__(self) -> None:
        self._heap: list[ScheduledMessage] = []
        self._lock = threading.Lock()
        self._seq = itertools.count()

    def add_note(self, n: MidiNote) -> None:
        velocity = max(1, min(127, int(n.velocity)))
        with self._lock:
            heapq.heappush(self._heap, ScheduledMessage(n.start, 1, next(self._seq), "on", n.channel, n.note, velocity))
            if n.duration > 0:
                heapq.heappush(
                    self._heap, ScheduledMessage(n.start + n.duration, 0, next(self._seq), "off", n.channel, n.note, 0)
                )

    def add_off(self, channel: int, note: int, beat: float) -> None:
        with self._lock:
            heapq.heappush(self._heap, ScheduledMessage(beat, 0, next(self._seq), "off", channel, note, 0))

    def pop_due(self, until_beat: float) -> list[ScheduledMessage]:
        out = []
        with self._lock:
            while self._heap and self._heap[0].beat < until_beat:
                out.append(heapq.heappop(self._heap))
        return out

    def clear(self) -> None:
        with self._lock:
            self._heap.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)
