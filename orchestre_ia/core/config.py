"""Configuration persistante de l'application (JSON, écriture atomique).

Le périphérique est mémorisé par son nom et son pilote (host API), pas par son
index : les index PortAudio changent quand on branche/débranche un appareil.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_SAMPLERATES = (44100, 48000)
SUPPORTED_BLOCKSIZES = (128, 256, 512, 1024, 2048)
GAIN_RANGE_DB = (-24.0, 24.0)


@dataclass
class AudioConfig:
    input_device_name: str | None = None
    input_hostapi: str | None = None
    samplerate: int = 48000
    blocksize: int = 512  # ~10,7 ms à 48 kHz
    gain_db: float = 0.0
    highpass_enabled: bool = True
    highpass_hz: float = 80.0

    def validate(self) -> None:
        if self.samplerate not in SUPPORTED_SAMPLERATES:
            self.samplerate = 48000
        if self.blocksize not in SUPPORTED_BLOCKSIZES:
            self.blocksize = 512
        lo, hi = GAIN_RANGE_DB
        self.gain_db = float(min(hi, max(lo, self.gain_db)))
        self.highpass_hz = float(min(300.0, max(20.0, self.highpass_hz)))


DRUM_MODES = ("auto", "on", "off")
TEMPO_MODES = ("auto", "manual")


@dataclass
class AccompanimentConfig:
    style: str = "variete"
    drums_mode: str = "auto"
    tempo_mode: str = "auto"
    manual_bpm: float = 90.0
    headphones: bool = False
    master_volume: float = 0.8
    piano_volume: float = 0.8
    bass_volume: float = 0.8
    drums_volume: float = 0.7
    output_device_name: str | None = None
    output_hostapi: str | None = None

    def validate(self) -> None:
        from orchestre_ia.instruments.styles import DEFAULT_STYLE, STYLES

        if self.style not in STYLES:
            self.style = DEFAULT_STYLE
        if self.drums_mode not in DRUM_MODES:
            self.drums_mode = "auto"
        if self.tempo_mode not in TEMPO_MODES:
            self.tempo_mode = "auto"
        self.manual_bpm = float(min(200.0, max(40.0, self.manual_bpm)))
        for name in ("master_volume", "piano_volume", "bass_volume", "drums_volume"):
            setattr(self, name, float(min(1.0, max(0.0, getattr(self, name)))))


@dataclass
class UIConfig:
    last_view: str = "studio"


@dataclass
class AppConfig:
    version: int = 1
    audio: AudioConfig = field(default_factory=AudioConfig)
    accompaniment: AccompanimentConfig = field(default_factory=AccompanimentConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """Charge la configuration ; en cas de fichier absent ou corrompu, retourne les valeurs par défaut."""
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            cfg = cls(
                version=int(raw.get("version", 1)),
                audio=_from_dict(AudioConfig, raw.get("audio", {})),
                accompaniment=_from_dict(AccompanimentConfig, raw.get("accompaniment", {})),
                ui=_from_dict(UIConfig, raw.get("ui", {})),
            )
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Configuration illisible (%s) : valeurs par défaut utilisées.", exc)
            return cls()
        cfg.audio.validate()
        cfg.accompaniment.validate()
        return cfg

    def save(self, path: Path) -> None:
        """Écriture atomique : fichier temporaire puis remplacement."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(self), indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _from_dict(kind: type, data: dict[str, Any]):
    if not isinstance(data, dict):
        return kind()
    known = {f.name for f in fields(kind)}
    return kind(**{k: v for k, v in data.items() if k in known})
