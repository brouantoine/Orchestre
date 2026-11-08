"""Écriture de petits fichiers audio compressés (m4a / webm) pour tester la lecture FFmpeg."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def write_compressed(path: Path, y: np.ndarray, sr: int, codec: str = "aac") -> Path:
    """Encode `y` (mono float32) avec PyAV : 'aac' pour .m4a, 'libopus' pour .webm."""
    import av

    rate = 48000 if codec == "libopus" else sr
    if rate != sr:
        import librosa

        y = librosa.resample(y, orig_sr=sr, target_sr=rate)
    with av.open(str(path), "w") as container:
        stream = container.add_stream(codec, rate=rate, layout="mono")
        frame = av.AudioFrame.from_ndarray(np.asarray(y, dtype=np.float32).reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = rate
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return path
