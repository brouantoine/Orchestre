"""Moteur d'analyse musicale temps réel (thread dédié).

Reçoit les blocs du moteur de capture, produit hauteur, notes, diapason,
tonalité et tempo, et tient à jour un instantané lisible par le chef d'orchestre.

Réécoute de l'accompagnement (haut-parleurs) : quand `headphones` est faux, les
trames dont la note correspond exactement à une note que l'orchestre joue en ce
moment sont exclues des indices harmoniques et de la détection de voix. Le piano
ne peut donc pas « s'auto-confirmer » ni se croire accompagné en s'entendant.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from orchestre_ia.analysis.echo import EchoGuard
from orchestre_ia.analysis.events import KeyUpdate, NoteFinished, PitchUpdate, TempoUpdate
from orchestre_ia.analysis.key import KeyEstimate, KeyEstimator
from orchestre_ia.analysis.notes import Note, NoteSegmenter
from orchestre_ia.analysis.tempo import TempoEstimate, TempoEstimator
from orchestre_ia.analysis.tracker import PitchFrame, PitchTracker
from orchestre_ia.core.events import EventBus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisSnapshot:
    key: KeyEstimate | None
    tempo: TempoEstimate | None
    current_note: int | None
    last_voice_monotonic: float  # dernier instant où une voix chantée a été entendue
    voice_level_db: float  # niveau moyen récent de la voix
    sung_seconds: float  # durée totale de chant voisé depuis le début
    tuning_cents: float = 0.0  # diapason personnel du chanteur


class AnalysisEngine:
    def __init__(self, bus: EventBus, pitch_rate_hz: float = 30.0) -> None:
        self._bus = bus
        self._pitch_period = 1.0 / pitch_rate_hz
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=500)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.headphones = False
        self.sounding_notes: Callable[[], set[int]] = lambda: set()
        self.output_level: Callable[[float, float], float] = lambda t0, t1: -100.0
        self._reset(48000)

    def _reset(self, samplerate: int) -> None:
        self.tracker = PitchTracker(samplerate)
        self.segmenter = NoteSegmenter(hop_s=self.tracker.hop / self.tracker.samplerate)
        self.keys = KeyEstimator()
        self.tempo = TempoEstimator()
        self.echo_guard = EchoGuard(lambda t0, t1: self.output_level(t0, t1))
        self._evidence: deque[tuple[float, int, float]] = deque()  # (monotonic, classe, poids)
        self._notes: deque[Note] = deque(maxlen=200)
        self._key: KeyEstimate | None = None
        self._tempo: TempoEstimate | None = None
        self._last_voice = 0.0
        self._levels: deque[float] = deque(maxlen=50)
        self._sung = 0.0
        self._clock_offset = 0.0  # monotonic - temps d'analyse
        self.dropped_blocks = 0

    # --------------------------------------------------------------- contrôle
    def start(self, samplerate: int) -> None:
        self.stop()
        with self._lock:
            self._reset(samplerate)
        self._queue = queue.Queue(maxsize=500)
        self._thread = threading.Thread(target=self._run, name="music-analysis", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.put(None)
        thread.join(timeout=2.0)
        self._thread = None

    def feed(self, block: np.ndarray, samplerate: int = 0) -> None:
        """Consommateur du moteur de capture : ne bloque jamais le thread audio."""
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            self.dropped_blocks += 1

    # ------------------------------------------------------------- lecture
    def snapshot(self) -> AnalysisSnapshot:
        with self._lock:
            return AnalysisSnapshot(
                key=self._key,
                tempo=self._tempo,
                current_note=self.segmenter.current,
                last_voice_monotonic=self._last_voice,
                voice_level_db=float(np.mean(self._levels)) if self._levels else -100.0,
                sung_seconds=self._sung,
                tuning_cents=self.segmenter.tuning.offset_cents,
            )

    def evidence(self, since_monotonic: float, now: float, half_life_s: float = 1.0) -> np.ndarray:
        """Poids par classe de hauteur chantée depuis `since`, les plus récents pesant plus."""
        hist = np.zeros(12)
        with self._lock:
            for t, pc, w in self._evidence:
                if t >= since_monotonic:
                    hist[pc] += w * 0.5 ** ((now - t) / half_life_s)
        return hist

    def to_monotonic(self, analysis_time: float) -> float:
        return analysis_time + self._clock_offset

    def recent_notes(self) -> list[Note]:
        with self._lock:
            return list(self._notes)

    # ------------------------------------------------------------- thread
    def _run(self) -> None:
        samples_in = 0
        last_pitch_pub = 0.0
        last_key_eval = 0.0
        last_tempo_eval = 0.0
        while True:
            block = self._queue.get()
            if block is None:
                break
            now = time.monotonic()
            samples_in += len(block)
            frames = self.tracker.process(block)
            # horloge : fin du bloc = maintenant
            self._clock_offset = now - samples_in / (self.tracker.samplerate * self.tracker.decimation)
            for frame in frames:
                self._handle_frame(frame)
            if frames and now - last_pitch_pub >= self._pitch_period:
                last_pitch_pub = now
                f = frames[-1]
                self._bus.publish(
                    PitchUpdate(
                        f0=f.f0,
                        midi=self.segmenter.corrected_midi(f) if f.voiced else 0.0,
                        note=self.segmenter.current,
                        tuning_cents=self.segmenter.tuning.offset_cents,
                    )
                )
            if now - last_key_eval >= 0.5:
                last_key_eval = now
                self._update_key(now)
            if now - last_tempo_eval >= 1.0:
                last_tempo_eval = now
                self._update_tempo()

    def _handle_frame(self, frame: PitchFrame) -> None:
        finished, started = self.segmenter.process(frame)
        mono_t = self.to_monotonic(frame.time)
        hop = self.segmenter.hop_s
        current = self.segmenter.current
        # Haut-parleurs : (1) trame trop faible par rapport à ce que joue l'orchestre
        # = fuite de l'orchestre ; (2) hauteur identique à une note jouée = réécoute.
        echo = False
        if not self.headphones:
            above_leak = self.echo_guard.is_voice(mono_t, frame.level_db)  # mesure aussi les pauses
            echo = frame.voiced and (
                not above_leak or (current is not None and current in self.sounding_notes())
            )
        with self._lock:
            if frame.voiced and not echo:
                self._last_voice = mono_t
                self._levels.append(frame.level_db)
                self._sung += hop
            if current is not None and frame.voiced and not echo:
                pc = current % 12
                self._evidence.append((mono_t, pc, hop))
                self.keys.add(pc, hop)
            while self._evidence and mono_t - self._evidence[0][0] > 8.0:
                self._evidence.popleft()
            for note in finished:
                self._notes.append(note)
        if started is not None:
            self.tempo.add_onset(frame.time - self.segmenter.confirm_s)
        for note in finished:
            self._bus.publish(NoteFinished(note=note))

    def _update_key(self, now: float) -> None:
        with self._lock:
            estimate = self.keys.estimate(now)
            changed = estimate is not None and estimate != self._key
            self._key = estimate
        if changed and estimate is not None:
            self._bus.publish(KeyUpdate(estimate=estimate))

    def _update_tempo(self) -> None:
        estimate = self.tempo.estimate()
        if estimate is not None:
            estimate = TempoEstimate(estimate.bpm, estimate.confidence, self.to_monotonic(estimate.phase_s))
        with self._lock:
            self._tempo = estimate
        self._bus.publish(TempoUpdate(estimate=estimate))
