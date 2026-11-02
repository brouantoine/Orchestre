"""Enregistrement local de la voix dans un fichier WAV (sur demande explicite).

L'écriture disque se fait dans un thread dédié : un ralentissement du disque ne
peut pas retarder le traitement audio. Les fichiers restent sur l'ordinateur
(dossier utilisateur), ils ne sont jamais transmis.
"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)


class SessionRecorder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._file: sf.SoundFile | None = None
        self.path: Path | None = None
        self.frames_written = 0
        self._samplerate = 0

    @property
    def is_recording(self) -> bool:
        return self._thread is not None

    def start(self, samplerate: int) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = self.directory / f"session_{stamp}.wav"
        self._file = sf.SoundFile(self.path, mode="w", samplerate=samplerate, channels=1, subtype="PCM_16")
        self.frames_written = 0
        self._samplerate = samplerate
        self._thread = threading.Thread(target=self._writer, name="audio-recorder", daemon=True)
        self._thread.start()
        log.info("Enregistrement démarré : %s", self.path)
        return self.path

    def write(self, block: np.ndarray, samplerate: int = 0) -> None:
        """Compatible avec AudioCaptureEngine.add_consumer : ne bloque jamais."""
        if self._thread is not None:
            self._queue.put(block.copy())

    def stop(self) -> Path | None:
        thread = self._thread
        if thread is None:
            return None
        self._queue.put(None)
        thread.join(timeout=5.0)
        self._thread = None
        if self._file is not None:
            self._file.close()
            self._file = None
        log.info("Enregistrement terminé : %s (%.1f s)", self.path, self.duration_s)
        return self.path

    @property
    def duration_s(self) -> float:
        return self.frames_written / self._samplerate if self._samplerate else 0.0

    def _writer(self) -> None:
        while True:
            block = self._queue.get()
            if block is None:
                return
            try:
                assert self._file is not None
                self._file.write(np.clip(block, -1.0, 1.0))
                self.frames_written += len(block)
            except Exception:
                log.exception("Erreur d'écriture de l'enregistrement")
                return
