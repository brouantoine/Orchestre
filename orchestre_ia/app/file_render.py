"""Accompagnement d'un enregistrement : rejoue un fichier WAV dans toute la chaîne
(capture → analyse → chef d'orchestre → synthèse) en temps réel, et écrit un
fichier mixé voix + orchestre. Sert au diagnostic et à la validation sur de vrais
enregistrements, sans micro ni haut-parleurs.

    python -m orchestre_ia --accompany-file enregistrement.wav --style gospel
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from orchestre_ia.app.session import MusicSession
from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.conductor.conductor import AccompanimentSettings, ConductorUpdate
from orchestre_ia.core.events import EventBus
from orchestre_ia.synthesis.output import AudioOutputEngine


class _RealtimeStream:
    """Flux simulé cadencé en temps réel (thread), commun entrée/sortie."""

    def __init__(self, samplerate: int, blocksize: int, channels: int, callback) -> None:
        self.samplerate, self.blocksize, self.channels, self.callback = samplerate, blocksize, channels, callback
        self.latency = blocksize / samplerate
        self.active = False
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        period = self.blocksize / self.samplerate
        next_t = time.perf_counter()
        while not self._halt.is_set():
            if not self._step():
                break
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)

    def _step(self) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        self._halt.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.active = False

    def close(self) -> None:
        pass


class FileInputStream(_RealtimeStream):
    def __init__(self, data: np.ndarray, **kw) -> None:
        super().__init__(kw["samplerate"], kw["blocksize"], kw["channels"], kw["callback"])
        self.data = data
        self.pos = 0

    def _step(self) -> bool:
        block = self.data[self.pos : self.pos + self.blocksize]
        if len(block) < self.blocksize:
            block = np.pad(block, (0, self.blocksize - len(block)))
        self.pos += self.blocksize
        self.callback(np.repeat(block[:, None], self.channels, axis=1), self.blocksize, None, None)
        return True


class RecordingOutputStream(_RealtimeStream):
    def __init__(self, **kw) -> None:
        super().__init__(kw["samplerate"], kw["blocksize"], kw["channels"], kw["callback"])
        self.blocks: list[np.ndarray] = []

    def _step(self) -> bool:
        out = np.zeros((self.blocksize, self.channels), dtype=np.float32)
        self.callback(out, self.blocksize, None, None)
        self.blocks.append(out)
        return True


def accompany_file(
    path: Path,
    out_path: Path,
    settings: AccompanimentSettings,
    voice_gain: float = 1.0,
    on_update=None,
) -> dict:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    voice = data.mean(axis=1)
    bus = EventBus()
    input_stream: dict = {}
    output_stream: dict = {}

    def input_factory(**kw):
        s = FileInputStream(voice, **kw)
        input_stream["s"] = s
        return s

    def output_factory(**kw):
        s = RecordingOutputStream(**kw)
        output_stream["s"] = s
        return s

    capture = AudioCaptureEngine(bus, stream_factory=input_factory)
    output = AudioOutputEngine(bus, stream_factory=output_factory)
    session = MusicSession(bus, capture=capture, output=output, settings=settings)
    updates: list[ConductorUpdate] = []
    bus.subscribe(ConductorUpdate, updates.append)
    if on_update is not None:
        bus.subscribe(ConductorUpdate, on_update)

    ok = session.start(CaptureSettings(device_name=path.name, samplerate=sr, blocksize=512), headphones=True)
    if not ok:
        raise RuntimeError("démarrage de la session impossible")
    synth_name = output.backend.name if output.backend else "aucun"
    # Les deux flux démarrent à quelques ms d'écart : on mesure ce décalage pour le mixage.
    duration = len(voice) / sr
    time.sleep(duration + 0.5)
    session.stop()

    accomp = np.concatenate(output_stream["s"].blocks) if output_stream["s"].blocks else np.zeros((0, 2), np.float32)
    if sr != 48000:
        from scipy.signal import resample_poly

        accomp = resample_poly(accomp, sr, 48000, axis=0).astype(np.float32)
    n = min(len(voice), len(accomp))
    mix = accomp[:n] * 0.9 + (voice[:n, None] * voice_gain)
    peak = float(np.max(np.abs(mix))) if n else 1.0
    if peak > 0.98:
        mix /= peak / 0.98
    sf.write(str(out_path), mix, sr)

    chords = [u.chord for u in updates if u.piano_active and u.chord != "—"]
    changes = [c for i, c in enumerate(chords) if i == 0 or c != chords[i - 1]]
    first_play = next((i for i, u in enumerate(updates) if u.piano_active), None)
    return {
        "duration_s": duration,
        "output": out_path,
        "chord_sequence": changes,
        "key": updates[-1].key if updates else "—",
        "drums_used": any(u.drums_active for u in updates),
        "rhythmic_used": any(u.rhythmic for u in updates),
        "piano_started_at_update": first_play,
        "updates": len(updates),
        "callback_errors": output.callback_errors,
        "synth": synth_name,
    }
