import numpy as np
import pytest

from orchestre_ia.audio.dsp import HighPassFilter
from orchestre_ia.audio.level import SILENCE_DB, LevelMeter, peak_dbfs, rms_dbfs

SR = 48000


def tone(freq, amp, seconds=0.5):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_rms_of_sine():
    # sinus d'amplitude 0,5 -> RMS = 0,5/√2 -> -9,03 dBFS
    assert rms_dbfs(tone(440, 0.5)) == pytest.approx(-9.03, abs=0.05)


def test_peak_of_sine():
    assert peak_dbfs(tone(440, 0.5)) == pytest.approx(-6.02, abs=0.05)


def test_silence_floor():
    assert rms_dbfs(np.zeros(512, np.float32)) == SILENCE_DB
    assert rms_dbfs(np.zeros(0, np.float32)) == SILENCE_DB


def test_meter_release_and_clipping():
    meter = LevelMeter(release_db_per_s=30.0)
    loud = tone(440, 1.0, 0.01)
    r = meter.update(loud, 0.01)
    assert r.clipping
    assert r.rms_db == pytest.approx(-3.0, abs=0.1)
    quiet = np.zeros(480, np.float32)
    r = meter.update(quiet, 0.1)  # descend de 3 dB en 0,1 s
    assert r.rms_db == pytest.approx(-6.0, abs=0.1)
    assert not r.clipping


def test_highpass_removes_rumble_keeps_voice():
    hpf = HighPassFilter(80.0, SR)
    rumble = tone(25, 0.5, 1.0)
    out = np.concatenate([hpf.process(b) for b in np.array_split(rumble, 100)])
    # après le transitoire initial, -18 dB environ à 25 Hz pour un ordre 2
    assert rms_dbfs(out[SR // 2 :]) < rms_dbfs(rumble) - 15

    hpf.reset()
    voice = tone(440, 0.5, 1.0)
    out = np.concatenate([hpf.process(b) for b in np.array_split(voice, 100)])
    assert rms_dbfs(out[SR // 2 :]) == pytest.approx(rms_dbfs(voice), abs=0.3)


def test_highpass_blockwise_equals_whole_signal():
    """L'état entre blocs doit rendre le traitement par blocs identique au traitement global."""
    x = np.random.default_rng(0).standard_normal(4096).astype(np.float32)
    whole = HighPassFilter(80.0, SR).process(x)
    hpf = HighPassFilter(80.0, SR)
    blocks = np.concatenate([hpf.process(b) for b in np.split(x, 8)])
    np.testing.assert_allclose(blocks, whole, atol=1e-5)
