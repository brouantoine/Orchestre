"""Étude d'une bibliothèque de chants : un dossier de fichiers audio, un chant par fichier.

- Formats : WAV, FLAC, OGG, MP3 (libsndfile) ; M4A, WEBM, OPUS, AAC, MP4… (PyAV / FFmpeg).
- Plusieurs chants sont étudiés en même temps, chacun dans son propre processus.
- Reprise : un chant déjà étudié est sauté, même renommé ou déplacé (empreinte du
  contenu) ; un doublon dans le dossier n'est compté qu'une fois.
- Seuls les résultats (tonalité, tempo, suite d'accords) sont gardés, jamais le son.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from orchestre_ia.learning import study
from orchestre_ia.learning.memory import MusicMemory
from orchestre_ia.learning.study import BeatFeatures, StudyResult

log = logging.getLogger(__name__)

SOUNDFILE_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3", ".aif", ".aiff"}
AUDIO_EXTENSIONS = SOUNDFILE_EXTENSIONS | {".m4a", ".webm", ".opus", ".aac", ".mp4", ".mkv", ".wma"}
CHUNK_S = 300.0  # étude par tranches de 5 min : mémoire bornée même pour un long fichier
MAX_SONG_S = 20 * 60.0  # compilations : seules les 20 premières minutes
MIN_SONG_S = 10.0


@dataclass
class SongOutcome:
    path: str
    result: StudyResult | None
    error: str | None
    seconds: float


@dataclass
class LibraryReport:
    found: int = 0
    studied: int = 0
    skipped: int = 0
    duplicates: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def default_workers() -> int:
    """Processus d'étude en parallèle : laisse 2 cœurs libres, 6 au plus (≈ 0,5 Go chacun)."""
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def find_songs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)


def fingerprint(path: Path) -> str:
    """Empreinte du contenu (taille + début + fin du fichier) : indépendante du nom et du dossier."""
    digest = hashlib.sha1()
    size = path.stat().st_size
    digest.update(str(size).encode())
    with path.open("rb") as handle:
        digest.update(handle.read(1 << 20))
        if size > 2 << 20:
            handle.seek(-(1 << 20), os.SEEK_END)
            digest.update(handle.read(1 << 20))
    return "chant:" + digest.hexdigest()[:20]


def load_audio(path: Path, sr: int = study.SR, max_s: float = MAX_SONG_S) -> np.ndarray:
    """Signal mono float32 à `sr` Hz (au plus `max_s` secondes)."""
    limit = int(max_s * sr)
    if path.suffix.lower() in SOUNDFILE_EXTENSIONS:
        try:
            import soundfile as sf

            with sf.SoundFile(path) as handle:
                native = handle.samplerate
                frames = min(handle.frames, int(max_s * native)) if handle.frames > 0 else -1
                y = handle.read(frames, dtype="float32", always_2d=True).mean(axis=1)
            if native != sr:
                import librosa

                y = librosa.resample(y, orig_sr=native, target_sr=sr)
            return np.asarray(y[:limit], dtype=np.float32)
        except Exception:
            log.debug("libsndfile ne lit pas %s, essai avec FFmpeg", path.name)

    import av

    chunks: list[np.ndarray] = []
    total = 0
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sr)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                samples = out.to_ndarray().reshape(-1)
                chunks.append(samples)
                total += len(samples)
            if total >= limit:
                break
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    y = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return np.asarray(y[:limit], dtype=np.float32)


def study_song(path_str: str) -> SongOutcome:
    """Étudie un chant (exécuté dans un processus d'étude). Ne lève jamais d'exception."""
    started = time.monotonic()
    path = Path(path_str)
    try:
        y = load_audio(path)
        if len(y) < MIN_SONG_S * study.SR:
            return SongOutcome(path_str, None, "trop court ou illisible", time.monotonic() - started)
        features = BeatFeatures()
        chunk = int(CHUNK_S * study.SR)
        for start in range(0, len(y), chunk):
            features.extend(study.beat_features(y[start : start + chunk], study.SR), start / study.SR)
        result = study.study_features(features, len(y) / study.SR)
        return SongOutcome(path_str, result, None, time.monotonic() - started)
    except Exception as exc:
        return SongOutcome(path_str, None, f"{type(exc).__name__} : {exc}", time.monotonic() - started)


def study_library(
    folder: Path,
    memory: MusicMemory,
    workers: int | None = None,
    force: bool = False,
    on_song: Callable[[int, int, Path, SongOutcome], None] | None = None,
) -> LibraryReport:
    """Étudie tous les chants nouveaux du dossier et range leurs leçons dans `memory`.

    Chaque chant est enregistré dès qu'il est étudié : une interruption (Ctrl+C)
    ne perd que les chants en cours, la reprise saute ceux déjà faits.
    """
    report = LibraryReport()
    todo: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path in find_songs(folder):
        report.found += 1
        try:
            source = fingerprint(path)
        except OSError as exc:
            report.errors.append((path.name, str(exc)))
            continue
        if source in seen:
            report.duplicates += 1
        elif memory.is_studied(source) and not force:
            report.skipped += 1
        else:
            todo.append((path, source))
        seen.add(source)

    def record(index: int, path: Path, source: str, outcome: SongOutcome) -> None:
        if outcome.result is not None:
            memory.store(source, path.stem, outcome.result)
            report.studied += 1
        else:
            report.errors.append((path.name, outcome.error or "erreur inconnue"))
        if on_song:
            on_song(index, len(todo), path, outcome)

    workers = workers or default_workers()
    if workers <= 1 or len(todo) <= 1:
        for i, (path, source) in enumerate(todo, 1):
            record(i, path, source, study_song(str(path)))
        return report

    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures: dict[Future[SongOutcome], tuple[Path, str]] = {
            pool.submit(study_song, str(path)): (path, source) for path, source in todo
        }
        for i, future in enumerate(as_completed(futures), 1):
            path, source = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:  # processus d'étude tombé (mémoire insuffisante…)
                outcome = SongOutcome(str(path), None, f"{type(exc).__name__} : {exc}", 0.0)
            record(i, path, source, outcome)
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return report
