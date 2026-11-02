"""Événements publiés par le moteur audio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orchestre_ia.core.events import Event


class CaptureState(Enum):
    STOPPED = "arrêté"
    STARTING = "démarrage"
    RUNNING = "écoute"
    ERROR = "erreur"


@dataclass(frozen=True, slots=True)
class CaptureStateChanged(Event):
    state: CaptureState
    message: str = ""


@dataclass(frozen=True, slots=True)
class AudioLevelEvent(Event):
    rms_db: float
    peak_db: float
    held_peak_db: float
    clipping: bool
    voice_active: bool
    noise_floor_db: float


@dataclass(frozen=True, slots=True)
class VoiceActivityChanged(Event):
    active: bool


@dataclass(frozen=True, slots=True)
class CaptureStats(Event):
    device_name: str
    samplerate: int
    blocksize: int
    channels: int
    input_latency_ms: float
    block_ms: float
    processing_ms_avg: float
    processing_ms_max: float
    input_overflows: int
    buffer_overruns: int
    callback_errors: int
