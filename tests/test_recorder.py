import numpy as np
import pytest
import soundfile as sf

from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.audio.recorder import SessionRecorder
from tests.fakes import fake_factory, sine


def test_recorder_writes_wav(tmp_path):
    rec = SessionRecorder(tmp_path)
    path = rec.start(48000)
    block = (0.5 * np.sin(2 * np.pi * 440 * np.arange(512) / 48000)).astype(np.float32)
    for _ in range(100):
        rec.write(block, 48000)
    assert rec.stop() == path
    data, sr = sf.read(path, dtype="float32")
    assert sr == 48000
    assert len(data) == 51200
    assert rec.duration_s == pytest.approx(51200 / 48000)
    np.testing.assert_allclose(data[:512], block, atol=1e-4)  # PCM 16 bits


def test_stop_without_start_is_harmless(tmp_path):
    assert SessionRecorder(tmp_path).stop() is None


def test_recording_from_capture_engine(tmp_path, bus):
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(220, 0.3)))
    rec = SessionRecorder(tmp_path)
    assert engine.start(CaptureSettings(device_name="fake", highpass_hz=None))
    rec.start(engine.samplerate)
    remove = engine.add_consumer(rec.write)
    import time

    time.sleep(0.4)
    remove()
    engine.stop()
    path = rec.stop()
    data, sr = sf.read(path, dtype="float32")
    assert sr == 48000 and len(data) > 0 and len(data) % 512 == 0
    assert np.max(np.abs(data)) == pytest.approx(0.3, abs=0.01)
