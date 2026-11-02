"""Sortie audio de l'orchestre : horloge, ordonnancement MIDI, synthèse, mixage.

Le callback de sortie est le cœur temps réel de l'accompagnement :
1. il met à jour l'horloge musicale (compteur d'échantillons) ;
2. il dépile les messages MIDI dus pendant ce bloc ;
3. il découpe le rendu aux instants exacts de chaque message
   (précision à l'échantillon : la batterie reste en place) ;
4. il applique le volume général et écrit le bloc.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import sounddevice as sd

from orchestre_ia.conductor.clock import MusicClock
from orchestre_ia.core.events import Event, EventBus
from orchestre_ia.midi.events import BASS_CHANNEL, DRUM_CHANNEL, PIANO_CHANNEL, MidiScheduler, ScheduledMessage
from orchestre_ia.synthesis.backend import PROGRAM_ACOUSTIC_GRAND, SynthBackend
from orchestre_ia.synthesis.builtin import BuiltinSynth

log = logging.getLogger(__name__)

BackendFactory = Callable[[int], SynthBackend]


@dataclass(frozen=True, slots=True)
class OutputStateChanged(Event):
    running: bool
    message: str = ""
    synth_name: str = ""
    latency_ms: float = 0.0


def default_backend_factory(samplerate: int) -> SynthBackend:
    """FluidSynth si disponible, sinon le synthé intégré (journalisé)."""
    try:
        from orchestre_ia.synthesis.fluid import FluidSynthBackend

        return FluidSynthBackend(samplerate)
    except Exception as exc:
        log.warning("FluidSynth indisponible (%s) : synthé intégré utilisé.", exc)
        return BuiltinSynth(samplerate)


class AudioOutputEngine:
    def __init__(
        self,
        bus: EventBus,
        backend_factory: BackendFactory = default_backend_factory,
        stream_factory: Callable[..., Any] = sd.OutputStream,
    ) -> None:
        self._bus = bus
        self._backend_factory = backend_factory
        self._stream_factory = stream_factory
        self.scheduler = MidiScheduler()
        self.clock = MusicClock(48000)
        self.backend: SynthBackend | None = None
        self._stream: Any = None
        self._sample = 0
        self._master = 0.8
        self._lock = threading.Lock()
        self._sounding: dict[int, set[int]] = {}
        self._sounding_lock = threading.Lock()
        self.underflows = 0
        self.callback_errors = 0
        self.latency_ms = 0.0
        self.tuning_cents = 0.0
        self._channel_volumes = {PIANO_CHANNEL: 100, BASS_CHANNEL: 100, DRUM_CHANNEL: 100}
        # niveau de sortie récent (instant de sortie au haut-parleur, dBFS) pour estimer la réécoute
        self._levels: deque[tuple[float, float]] = deque(maxlen=1200)
        self._levels_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self, device: int | None = None, samplerate: int = 48000, blocksize: int = 512) -> bool:
        self.stop()
        try:
            backend = self._backend_factory(samplerate)
            backend.program(PIANO_CHANNEL, PROGRAM_ACOUSTIC_GRAND)
            backend.program(BASS_CHANNEL, PROGRAM_ACOUSTIC_GRAND)
            backend.program(DRUM_CHANNEL, 0, drums=True)
            for ch, vol in self._channel_volumes.items():
                backend.cc(ch, 7, vol)
            self.backend = backend
            self.clock = MusicClock(samplerate)
            self.scheduler.clear()
            self._sample = 0
            with self._sounding_lock:
                self._sounding = {}
            stream = self._stream_factory(
                device=device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=2,
                dtype="float32",
                latency="low",
                callback=self._callback,
            )
            stream.start()
            self._stream = stream
            try:
                self.latency_ms = float(stream.latency) * 1000
            except Exception:
                self.latency_ms = 0.0
        except Exception as exc:
            log.error("Sortie audio impossible : %s", exc)
            self._close()
            self._bus.publish(OutputStateChanged(running=False, message=f"Sortie audio impossible : {exc}"))
            return False
        log.info("Sortie audio démarrée (%s, latence %.0f ms)", backend.name, self.latency_ms)
        self._bus.publish(OutputStateChanged(running=True, synth_name=backend.name, latency_ms=self.latency_ms))
        return True

    def stop(self) -> None:
        if self._stream is None and self.backend is None:
            return
        self._close()
        self._bus.publish(OutputStateChanged(running=False))

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            for action in ("stop", "close"):
                try:
                    getattr(stream, action)()
                except Exception as exc:
                    log.warning("Fermeture de la sortie (%s) : %s", action, exc)
        backend, self.backend = self.backend, None
        if backend is not None:
            backend.close()
        self.scheduler.clear()

    # ----------------------------------------------------------- réglages
    def set_master_volume(self, value: float) -> None:
        self._master = float(min(1.0, max(0.0, value)))

    def set_channel_volume(self, channel: int, value: float) -> None:
        midi_value = int(round(min(1.0, max(0.0, value)) * 127))
        self._channel_volumes[channel] = midi_value
        backend = self.backend
        if backend is not None:
            backend.cc(channel, 7, midi_value)

    def set_tuning(self, cents: float) -> None:
        """Accorde piano et basse sur le chanteur (la batterie n'est pas concernée)."""
        self.tuning_cents = float(cents)
        backend = self.backend
        if backend is not None:
            for ch in (PIANO_CHANNEL, BASS_CHANNEL):
                backend.tune(ch, cents)

    def silence(self) -> None:
        """Coupe immédiatement tout ce qui est prévu et laisse résonner/s'éteindre les notes."""
        self.scheduler.clear()
        backend = self.backend
        if backend is not None:
            backend.all_notes_off()
        with self._sounding_lock:
            self._sounding = {}

    def level_between(self, t0: float, t1: float) -> float:
        """Niveau de sortie maximal (dBFS) entre deux instants monotonic ; -100 si silence."""
        with self._levels_lock:
            values = [db for t, db in self._levels if t0 <= t <= t1]
        return max(values) if values else -100.0

    def sounding_notes(self) -> set[int]:
        """Notes de piano/basse en cours (pour filtrer leur réécoute par le micro)."""
        with self._sounding_lock:
            return set().union(*(notes for ch, notes in self._sounding.items() if ch != DRUM_CHANNEL)) if self._sounding else set()

    # ----------------------------------------------------------- temps réel
    def _apply(self, backend: SynthBackend, m: ScheduledMessage) -> None:
        if m.kind == "on":
            backend.noteon(m.channel, m.data1, m.data2)
            with self._sounding_lock:
                self._sounding.setdefault(m.channel, set()).add(m.data1)
        elif m.kind == "off":
            backend.noteoff(m.channel, m.data1)
            with self._sounding_lock:
                self._sounding.get(m.channel, set()).discard(m.data1)

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        try:
            if status:
                self.underflows += 1
            backend = self.backend
            if backend is None:
                outdata.fill(0)
                return
            dac_delay = 0.0
            try:
                dac_delay = max(0.0, float(time_info.outputBufferDacTime - time_info.currentTime))
            except Exception:
                pass
            start = self._sample
            clock = self.clock
            dac_time = time.monotonic() + dac_delay
            clock.advance(start, dac_time)
            messages = self.scheduler.pop_due(clock.beat_at_sample(start + frames))
            pos = 0
            for m in messages:
                offset = int(min(frames, max(0, round(clock.sample_at_beat(m.beat) - start))))
                if offset > pos:
                    outdata[pos:offset] = backend.render(offset - pos)
                    pos = offset
                self._apply(backend, m)
            if pos < frames:
                outdata[pos:frames] = backend.render(frames - pos)
            np.multiply(outdata, self._master, out=outdata)
            np.tanh(outdata, out=outdata)  # limiteur doux : jamais de saturation numérique
            self._sample = start + frames
            rms = float(np.sqrt(np.mean(outdata[:, 0] * outdata[:, 0])))
            level_db = 20.0 * np.log10(rms) if rms > 1e-5 else -100.0
            with self._levels_lock:
                self._levels.append((dac_time, level_db))
        except Exception:
            self.callback_errors += 1
            outdata.fill(0)
