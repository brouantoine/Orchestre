"""Inventaire des microphones disponibles via PortAudio (sounddevice)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import sounddevice as sd

log = logging.getLogger(__name__)

# Ordre de préférence des pilotes Windows : WASAPI offre la latence la plus
# faible en mode partagé et la conversion de format automatique.
HOSTAPI_PRIORITY = ("Windows WASAPI", "Windows DirectSound", "MME", "Windows WDM-KS")


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: str
    channels: int
    default_samplerate: float
    is_default: bool

    @property
    def label(self) -> str:
        star = " ★" if self.is_default else ""
        return f"{self.name} — {self.hostapi}{star}"


def _hostapi_rank(name: str) -> int:
    try:
        return HOSTAPI_PRIORITY.index(name)
    except ValueError:
        return len(HOSTAPI_PRIORITY)


def _list_devices(backend: Any, direction: str) -> list[AudioDevice]:
    try:
        hostapis = backend.query_hostapis()
        devices = backend.query_devices()
    except Exception as exc:  # PortAudioError, OSError...
        log.error("Impossible d'interroger les périphériques audio : %s", exc)
        return []

    channels_key = f"max_{direction}_channels"
    defaults = {api.get(f"default_{direction}_device", -1) for api in hostapis}
    result = []
    for index, dev in enumerate(devices):
        if dev.get(channels_key, 0) <= 0:
            continue
        result.append(
            AudioDevice(
                index=index,
                name=str(dev["name"]),
                hostapi=hostapis[dev["hostapi"]]["name"],
                channels=int(dev[channels_key]),
                default_samplerate=float(dev.get("default_samplerate", 48000.0)),
                is_default=index in defaults,
            )
        )
    result.sort(key=lambda d: (_hostapi_rank(d.hostapi), not d.is_default, d.name.lower()))
    return result


def list_input_devices(backend: Any = sd) -> list[AudioDevice]:
    """Micros, triés par pilote préféré puis par nom. Liste vide si PortAudio est indisponible."""
    return _list_devices(backend, "input")


def list_output_devices(backend: Any = sd) -> list[AudioDevice]:
    """Sorties (haut-parleurs, casques), même ordre de préférence."""
    return _list_devices(backend, "output")


def find_device(devices: list[AudioDevice], name: str | None, hostapi: str | None) -> AudioDevice | None:
    if not name:
        return None
    for dev in devices:
        if dev.name == name and (hostapi is None or dev.hostapi == hostapi):
            return dev
    return None


def preferred_default(devices: list[AudioDevice]) -> AudioDevice | None:
    """Micro par défaut du pilote préféré (la liste est déjà triée)."""
    for dev in devices:
        if dev.is_default:
            return dev
    return devices[0] if devices else None
