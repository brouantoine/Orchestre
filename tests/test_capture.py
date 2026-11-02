"""Tests du moteur de capture avec un flux simulé (déterministe, sans matériel)."""

import threading
import time

import numpy as np
import pytest

from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.audio.events import (
    AudioLevelEvent,
    CaptureState,
    CaptureStateChanged,
    CaptureStats,
    VoiceActivityChanged,
)
from tests.fakes import fake_factory, silence, sine


class Recorder:
    def __init__(self, bus):
        self.events = []
        self._lock = threading.Lock()
        for kind in (AudioLevelEvent, CaptureStateChanged, VoiceActivityChanged, CaptureStats):
            bus.subscribe(kind, self._add)

    def _add(self, e):
        with self._lock:
            self.events.append(e)

    def of(self, kind):
        with self._lock:
            return [e for e in self.events if isinstance(e, kind)]

    def wait_for(self, predicate, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.01)
        return False


SETTINGS = CaptureSettings(device=None, device_name="fake", samplerate=48000, blocksize=512, highpass_hz=80.0)


def test_start_stop_lifecycle(bus):
    rec = Recorder(bus)
    created = []
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3), created))
    assert engine.start(SETTINGS)
    assert engine.state == CaptureState.RUNNING
    assert rec.wait_for(lambda: len(rec.of(AudioLevelEvent)) >= 3)
    engine.stop()
    assert engine.state == CaptureState.STOPPED
    states = [e.state for e in rec.of(CaptureStateChanged)]
    assert states == [CaptureState.STARTING, CaptureState.RUNNING, CaptureState.STOPPED]
    assert created[0].closed and not created[0].active


def test_level_matches_signal(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.5)))
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: len(rec.of(AudioLevelEvent)) >= 10)
    engine.stop()
    last = rec.of(AudioLevelEvent)[-1]
    assert last.rms_db == pytest.approx(-9.03, abs=0.5)
    assert not last.clipping


def test_voice_activity_events(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(220, 0.2)))
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: any(e.active for e in rec.of(VoiceActivityChanged)))
    engine.stop()


def test_silence_produces_no_voice(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(silence()))
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: len(rec.of(AudioLevelEvent)) >= 5)
    engine.stop()
    assert not rec.of(VoiceActivityChanged)
    assert rec.of(AudioLevelEvent)[-1].rms_db == -100.0


def test_gain_applies_live(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.1)))
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: len(rec.of(AudioLevelEvent)) >= 5)
    before = rec.of(AudioLevelEvent)[-1].rms_db
    engine.set_gain_db(12.0)
    time.sleep(0.4)
    engine.stop()
    after = rec.of(AudioLevelEvent)[-1].rms_db
    assert after - before == pytest.approx(12.0, abs=0.5)


def test_clipping_detected_on_raw_input(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 1.0)))
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: any(e.clipping for e in rec.of(AudioLevelEvent)))
    engine.stop()


def test_consumers_receive_all_samples_in_order(bus):
    received = []
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3)))
    engine.add_consumer(lambda block, sr: received.append((len(block), sr)))
    engine.start(SETTINGS)
    time.sleep(0.4)
    engine.stop()
    assert len(received) > 5
    assert all(n == 512 and sr == 48000 for n, sr in received)


def test_latest_audio_window(bus):
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3)))
    engine.start(SETTINGS)
    time.sleep(0.5)
    window = engine.latest_audio(0.1)
    engine.stop()
    assert len(window) == 4800
    assert window.dtype == np.float32


def test_stats_are_published(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3)), stats_rate_hz=10)
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: len(rec.of(CaptureStats)) >= 2)
    engine.stop()
    s = rec.of(CaptureStats)[-1]
    assert s.samplerate == 48000 and s.blocksize == 512
    assert s.block_ms == pytest.approx(10.67, abs=0.01)
    assert s.input_latency_ms == pytest.approx(10.0)
    assert s.processing_ms_avg < s.block_ms  # traitement plus rapide que le temps réel


def test_open_failure_sets_error_state(bus):
    rec = Recorder(bus)

    def failing(**_):
        raise OSError("Périphérique occupé")

    engine = AudioCaptureEngine(bus, stream_factory=failing)
    assert not engine.start(SETTINGS)
    assert engine.state == CaptureState.ERROR
    assert "Périphérique occupé" in rec.of(CaptureStateChanged)[-1].message


def test_fallback_to_stereo_then_other_samplerate(bus):
    attempts = []
    inner = fake_factory(sine(440, 0.3))

    def picky(**kwargs):
        attempts.append((kwargs["samplerate"], kwargs["channels"]))
        if kwargs["samplerate"] != 44100 or kwargs["channels"] != 2:
            raise OSError("format non supporté")
        return inner(**kwargs)

    engine = AudioCaptureEngine(bus, stream_factory=picky)
    assert engine.start(SETTINGS)
    assert engine.samplerate == 44100
    engine.stop()
    assert attempts == [(48000, 1), (48000, 2), (44100, 1), (44100, 2)]


def test_device_disappearing_triggers_error(bus):
    rec = Recorder(bus)
    engine = AudioCaptureEngine(
        bus, stream_factory=fake_factory(sine(440, 0.3), stop_after_s=0.2), stall_timeout_s=0.3
    )
    engine.start(SETTINGS)
    assert rec.wait_for(lambda: engine.state == CaptureState.ERROR, timeout=3)
    assert "ne fournit plus" in rec.of(CaptureStateChanged)[-1].message
    engine.stop()  # sans effet de bord après une erreur


def test_restart_while_running(bus):
    created = []
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3), created))
    engine.start(SETTINGS)
    engine.start(SETTINGS)
    assert engine.state == CaptureState.RUNNING
    assert created[0].closed
    engine.stop()
    assert created[1].closed


def test_repeated_start_stop_is_stable(bus):
    engine = AudioCaptureEngine(bus, stream_factory=fake_factory(sine(440, 0.3)))
    for _ in range(20):
        assert engine.start(SETTINGS)
        time.sleep(0.01)
        engine.stop()
    assert engine.state == CaptureState.STOPPED
    assert not [t for t in threading.enumerate() if t.name == "audio-processing"]
