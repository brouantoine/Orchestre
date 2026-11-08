"""Écoute d'apprentissage : enregistre une séance entière (louange, répétition)
pour que l'orchestre en tire ses leçons ensuite (`orchestre_ia.learning.study`).

- Mode muet : aucun son n'est joué, utilisable pendant un culte.
- Pas de filtre passe-haut : la basse et la grosse caisse sont gardées, elles
  portent l'harmonie et le tempo.
- WAV découpés en parties (5 min par défaut) et entête mis à jour toutes les
  2 s : une coupure de courant ne perd que les dernières secondes.
- Tout reste sur l'ordinateur, rien n'est transmis.
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

CLIP_LEVEL = 0.999
SESSION_FILE = "seance.json"


@dataclass
class ListeningInfo:
    label: str
    device: str
    started_at: str
    samplerate: int = 0
    ended_at: str | None = None
    duration_s: float = 0.0
    segments: list[str] = field(default_factory=list)
    clipped_blocks: int = 0
    peak: float = 0.0
    restarts: int = 0
    studied: bool = False


class SegmentedRecorder:
    """Consommateur de blocs audio qui écrit des WAV successifs `partie_001.wav`, …

    `write` ne bloque jamais : l'écriture disque a lieu dans un thread dédié.
    """

    def __init__(self, directory: Path, segment_seconds: float = 300.0, flush_seconds: float = 2.0) -> None:
        self.directory = directory
        self.segment_seconds = segment_seconds
        self.flush_seconds = flush_seconds
        self.segments: list[Path] = []
        self.frames_written = 0
        self.clipped_blocks = 0
        self.peak = 0.0
        self.samplerate = 0
        self._queue: queue.Queue[tuple[np.ndarray, int] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._file: sf.SoundFile | None = None
        self._segment_frames = 0
        self._since_flush = 0
        self._on_segment: list = []

    @property
    def is_recording(self) -> bool:
        return self._thread is not None

    @property
    def duration_s(self) -> float:
        return self.frames_written / self.samplerate if self.samplerate else 0.0

    def on_segment(self, callback) -> None:
        """`callback(path)` appelé (thread d'écriture) à chaque nouvelle partie."""
        self._on_segment.append(callback)

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._writer, name="learning-recorder", daemon=True)
        self._thread.start()

    def write(self, block: np.ndarray, samplerate: int) -> None:
        if self._thread is not None:
            self._queue.put((block.copy(), samplerate))

    def stop(self) -> list[Path]:
        thread = self._thread
        if thread is None:
            return self.segments
        self._queue.put(None)
        thread.join(timeout=10.0)
        self._thread = None
        self._close_file()
        return self.segments

    # ------------------------------------------------------------ interne
    def _open_next(self, samplerate: int) -> None:
        self._close_file()
        path = self.directory / f"partie_{len(self.segments) + 1:03d}.wav"
        self._file = sf.SoundFile(path, mode="w", samplerate=samplerate, channels=1, subtype="PCM_16")
        self.samplerate = samplerate
        self._segment_frames = 0
        self._since_flush = 0
        self.segments.append(path)
        log.info("Écoute d'apprentissage : nouvelle partie %s", path.name)
        for callback in self._on_segment:
            try:
                callback(path)
            except Exception:
                log.exception("Erreur dans le rappel de nouvelle partie")

    def _close_file(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                log.exception("Fermeture de la partie impossible")
            self._file = None

    def _writer(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            block, samplerate = item
            try:
                if (
                    self._file is None
                    or samplerate != self.samplerate
                    or self._segment_frames >= self.segment_seconds * samplerate
                ):
                    self._open_next(samplerate)
                assert self._file is not None
                peak = float(np.max(np.abs(block))) if len(block) else 0.0
                self.peak = max(self.peak, peak)
                if peak >= CLIP_LEVEL and self.frames_written >= 0.5 * samplerate:
                    self.clipped_blocks += 1  # le déclic d'ouverture du micro ne compte pas
                self._file.write(np.clip(block, -1.0, 1.0))
                self.frames_written += len(block)
                self._segment_frames += len(block)
                self._since_flush += len(block)
                if self._since_flush >= self.flush_seconds * samplerate:
                    self._file.flush()  # met à jour l'entête WAV
                    self._since_flush = 0
            except Exception:
                log.exception("Erreur d'écriture de l'écoute d'apprentissage")


def new_session_dir(base: Path, label: str, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label.strip().lower()) or "ecoute"
    path = base / f"{stamp}_{safe}"
    n = 2
    while path.exists():
        path = base / f"{stamp}_{safe}_{n}"
        n += 1
    path.mkdir(parents=True)
    return path


def save_info(directory: Path, info: ListeningInfo) -> None:
    tmp = directory / (SESSION_FILE + ".tmp")
    tmp.write_text(json.dumps(asdict(info), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(directory / SESSION_FILE)


def load_info(directory: Path) -> ListeningInfo | None:
    path = directory / SESSION_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {k: v for k, v in data.items() if k in ListeningInfo.__dataclass_fields__}
    return ListeningInfo(**known)


def keep_awake(enable: bool) -> None:
    """Empêche Windows de se mettre en veille pendant l'écoute (l'écran peut s'éteindre)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        es_continuous, es_system_required = 0x80000000, 0x00000001
        flags = es_continuous | (es_system_required if enable else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
    except Exception:
        log.warning("Impossible de bloquer la mise en veille")
