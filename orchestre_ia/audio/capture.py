"""Moteur de capture micro temps réel.

Architecture des threads :

    [Thread PortAudio]  callback -> mixage mono -> AudioRingBuffer (copie seule)
                                                   |
    [Thread "audio-processing"]  lit des blocs -> passe-haut -> gain -> niveau, VAD
                                 -> tampon "processed" (fenêtres d'analyse)
                                 -> consommateurs (analyse de hauteur, phase 3)
                                 -> événements (bus) à fréquence limitée

Le callback PortAudio ne fait aucun calcul lourd, aucune journalisation et ne lève
jamais d'exception : c'est la condition pour éviter les coupures.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import sounddevice as sd

from orchestre_ia.audio.dsp import HighPassFilter
from orchestre_ia.audio.events import (
    AudioLevelEvent,
    CaptureState,
    CaptureStateChanged,
    CaptureStats,
    VoiceActivityChanged,
)
from orchestre_ia.audio.level import LevelMeter, db_to_amplitude
from orchestre_ia.audio.ring_buffer import AudioRingBuffer
from orchestre_ia.audio.vad import VadConfig, VoiceActivityDetector
from orchestre_ia.core.events import EventBus

log = logging.getLogger(__name__)

BlockConsumer = Callable[[np.ndarray, int], None]
StreamFactory = Callable[..., Any]


@dataclass(frozen=True)
class CaptureSettings:
    device: int | None = None  # index PortAudio ; None = périphérique par défaut
    device_name: str = "défaut système"
    samplerate: int = 48000
    blocksize: int = 512
    gain_db: float = 0.0
    highpass_hz: float | None = 80.0
    latency: str | float = "low"


def default_stream_factory(**kwargs: Any) -> sd.InputStream:
    """Crée un vrai flux PortAudio ; active la conversion automatique en WASAPI."""
    device = kwargs.get("device")
    try:
        info = sd.query_devices(device if device is not None else sd.default.device[0])
        hostapi = sd.query_hostapis(info["hostapi"])["name"]
        if hostapi == "Windows WASAPI":
            kwargs["extra_settings"] = sd.WasapiSettings(auto_convert=True)
    except Exception:  # l'ouverture réelle remontera l'erreur pertinente
        pass
    return sd.InputStream(**kwargs)


class AudioCaptureEngine:
    def __init__(
        self,
        bus: EventBus,
        stream_factory: StreamFactory = default_stream_factory,
        buffer_seconds: float = 10.0,
        level_rate_hz: float = 30.0,
        stats_rate_hz: float = 2.0,
        vad_config: VadConfig | None = None,
        stall_timeout_s: float = 1.0,
    ) -> None:
        self._bus = bus
        self._stream_factory = stream_factory
        self._buffer_seconds = buffer_seconds
        self._level_period = 1.0 / level_rate_hz
        self._stats_period = 1.0 / stats_rate_hz
        self._vad_config = vad_config
        self._stall_timeout = stall_timeout_s

        self._lock = threading.RLock()
        self._state = CaptureState.STOPPED
        self._stream: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._raw: AudioRingBuffer | None = None
        self._processed: AudioRingBuffer | None = None
        self._settings: CaptureSettings | None = None
        self._samplerate = 0
        self._channels = 0
        self._gain = 1.0
        self._consumers: list[BlockConsumer] = []
        self._consumers_lock = threading.Lock()
        self._vad: VoiceActivityDetector | None = None
        self._generation = 0

        # compteurs écrits par le callback (entiers : opérations atomiques sous le GIL)
        self._input_overflows = 0
        self._callback_errors = 0

    # ------------------------------------------------------------------ état
    @property
    def state(self) -> CaptureState:
        return self._state

    @property
    def samplerate(self) -> int:
        return self._samplerate

    @property
    def is_running(self) -> bool:
        return self._state == CaptureState.RUNNING

    def _set_state(self, state: CaptureState, message: str = "") -> None:
        self._state = state
        if state == CaptureState.ERROR:
            log.error("Capture audio en erreur : %s", message)
        else:
            log.info("Capture audio : %s %s", state.value, message)
        self._bus.publish(CaptureStateChanged(state=state, message=message))

    # ------------------------------------------------------------- contrôle
    def start(self, settings: CaptureSettings) -> bool:
        """Ouvre le micro et démarre l'écoute. Retourne True si la capture tourne."""
        with self._lock:
            if self._state in (CaptureState.RUNNING, CaptureState.STARTING):
                self._stop_locked(publish=False)
            self._set_state(CaptureState.STARTING, settings.device_name)
            self._generation += 1
            self._settings = settings
            self._gain = db_to_amplitude(settings.gain_db)
            self._input_overflows = 0
            self._callback_errors = 0
            self._stop_event.clear()

            try:
                self._stream, self._samplerate, self._channels = self._open_stream(settings)
            except Exception as exc:
                self._stream = None
                self._set_state(CaptureState.ERROR, f"Impossible d'ouvrir le micro : {exc}")
                return False

            capacity = int(self._samplerate * self._buffer_seconds)
            self._raw = AudioRingBuffer(capacity)
            self._processed = AudioRingBuffer(capacity)
            self._vad = VoiceActivityDetector(self._samplerate, self._vad_config)

            try:
                self._stream.start()
            except Exception as exc:
                self._close_stream()
                self._set_state(CaptureState.ERROR, f"Le flux audio n'a pas démarré : {exc}")
                return False

            self._thread = threading.Thread(target=self._process_loop, name="audio-processing", daemon=True)
            self._thread.start()
            self._set_state(
                CaptureState.RUNNING,
                f"{settings.device_name} @ {self._samplerate} Hz, {self._channels} canal(aux)",
            )
            return True

    def stop(self) -> None:
        with self._lock:
            self._stop_locked(publish=True)

    def _stop_locked(self, publish: bool) -> None:
        self._stop_event.set()
        if self._raw is not None:
            self._raw.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._close_stream()
        if publish and self._state != CaptureState.STOPPED:
            self._set_state(CaptureState.STOPPED)
        elif not publish:
            self._state = CaptureState.STOPPED

    def set_gain_db(self, gain_db: float) -> None:
        """Modifiable pendant l'écoute."""
        self._gain = db_to_amplitude(gain_db)

    def add_consumer(self, consumer: BlockConsumer) -> Callable[[], None]:
        """Reçoit chaque bloc traité (mono float32, samplerate) dans le thread de traitement."""
        with self._consumers_lock:
            self._consumers.append(consumer)

        def remove() -> None:
            with self._consumers_lock:
                if consumer in self._consumers:
                    self._consumers.remove(consumer)

        return remove

    def latest_audio(self, seconds: float) -> np.ndarray:
        """Dernières `seconds` de signal conditionné (pour les fenêtres d'analyse)."""
        buf = self._processed
        if buf is None or self._samplerate == 0:
            return np.zeros(0, dtype=np.float32)
        return buf.latest(int(seconds * self._samplerate))

    # ---------------------------------------------------------- interne
    def _open_stream(self, settings: CaptureSettings) -> tuple[Any, int, int]:
        """Essaie la fréquence demandée en mono, puis en stéréo, puis l'autre fréquence."""
        other = 44100 if settings.samplerate == 48000 else 48000
        candidates = [(settings.samplerate, 1), (settings.samplerate, 2), (other, 1), (other, 2)]
        last_error: Exception | None = None
        for samplerate, channels in candidates:
            try:
                stream = self._stream_factory(
                    device=settings.device,
                    samplerate=samplerate,
                    blocksize=settings.blocksize,
                    channels=channels,
                    dtype="float32",
                    latency=settings.latency,
                    callback=self._callback,
                )
                if (samplerate, channels) != candidates[0]:
                    log.warning("Configuration de repli : %d Hz, %d canal(aux)", samplerate, channels)
                return stream, samplerate, channels
            except Exception as exc:
                last_error = exc
                log.debug("Échec ouverture %d Hz / %d canaux : %s", samplerate, channels, exc)
        assert last_error is not None
        raise last_error

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        for action in ("stop", "close"):
            try:
                getattr(stream, action)()
            except Exception as exc:
                log.warning("Erreur à la fermeture du flux (%s) : %s", action, exc)

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        # Thread temps réel PortAudio : uniquement copie mémoire.
        try:
            if status:
                self._input_overflows += 1
            mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
            raw = self._raw
            if raw is not None:
                raw.write(mono)
        except Exception:
            self._callback_errors += 1

    def _process_loop(self) -> None:
        settings = self._settings
        raw = self._raw
        processed = self._processed
        vad = self._vad
        assert settings is not None and raw is not None and processed is not None and vad is not None
        sr = self._samplerate
        block = settings.blocksize
        dt = block / sr
        hpf = HighPassFilter(settings.highpass_hz, sr) if settings.highpass_hz else None
        meter = LevelMeter()

        last_level_pub = 0.0
        last_stats_pub = time.monotonic()
        last_data = time.monotonic()
        voice_prev = False
        proc_times: list[float] = []
        total_blocks = voice_blocks = 0
        max_rms = -100.0

        while not self._stop_event.is_set():
            data = raw.read(block, timeout=0.25)
            now = time.monotonic()
            if data is None:
                if self._stop_event.is_set():
                    break
                if now - last_data > self._stall_timeout:
                    self._handle_stall()
                    break
                continue
            last_data = now

            t0 = time.perf_counter()
            raw_peak = float(np.max(np.abs(data)))
            x = hpf.process(data) if hpf else data
            x = (x * self._gain).astype(np.float32, copy=False)
            reading = meter.update(x, dt, raw_peak=raw_peak)
            voice = vad.process(x)
            processed.write(x)

            with self._consumers_lock:
                consumers = list(self._consumers)
            for consumer in consumers:
                try:
                    consumer(x, sr)
                except Exception:
                    log.exception("Erreur dans un consommateur audio")
            proc_times.append((time.perf_counter() - t0) * 1000)
            total_blocks += 1
            voice_blocks += voice
            max_rms = max(max_rms, reading.rms_db)

            if voice != voice_prev:
                voice_prev = voice
                self._bus.publish(VoiceActivityChanged(active=voice))
            if now - last_level_pub >= self._level_period:
                last_level_pub = now
                self._bus.publish(
                    AudioLevelEvent(
                        rms_db=reading.rms_db,
                        peak_db=reading.peak_db,
                        held_peak_db=reading.held_peak_db,
                        clipping=reading.clipping,
                        voice_active=voice,
                        noise_floor_db=vad.noise_floor_db,
                    )
                )
            if now - last_stats_pub >= self._stats_period:
                last_stats_pub = now
                self._publish_stats(proc_times)
                proc_times = []

        if total_blocks:
            log.info(
                "Bilan de séance : %.1f s captées, voix détectée %.0f %% du temps, niveau max %.1f dBFS, "
                "débordements pilote %d, pertes tampon %d",
                total_blocks * dt,
                100.0 * voice_blocks / total_blocks,
                max_rms,
                self._input_overflows,
                raw.overruns,
            )

    def _publish_stats(self, proc_times: list[float]) -> None:
        settings = self._settings
        stream = self._stream
        if settings is None:
            return
        try:
            input_latency = float(stream.latency) * 1000 if stream is not None else 0.0
        except Exception:
            input_latency = 0.0
        self._bus.publish(
            CaptureStats(
                device_name=settings.device_name,
                samplerate=self._samplerate,
                blocksize=settings.blocksize,
                channels=self._channels,
                input_latency_ms=input_latency,
                block_ms=settings.blocksize / self._samplerate * 1000,
                processing_ms_avg=float(np.mean(proc_times)) if proc_times else 0.0,
                processing_ms_max=float(np.max(proc_times)) if proc_times else 0.0,
                input_overflows=self._input_overflows,
                buffer_overruns=self._raw.overruns if self._raw else 0,
                callback_errors=self._callback_errors,
            )
        )

    def _handle_stall(self) -> None:
        """Plus aucun échantillon : micro débranché ou pilote bloqué."""
        self._stop_event.set()
        generation = self._generation
        threading.Thread(
            target=self._fail_from_worker, args=(generation,), name="audio-stall", daemon=True
        ).start()

    def _fail_from_worker(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation or self._state != CaptureState.RUNNING:
                return  # une nouvelle session a démarré entre-temps, ou arrêt manuel
            self._close_stream()
            self._thread = None
            self._set_state(
                CaptureState.ERROR,
                "Le micro ne fournit plus de son (débranché ou utilisé par une autre application ?)",
            )
