"""Tests sur le VRAI matériel audio. Ignorés automatiquement si aucun micro n'est disponible.

Exclure : pytest -m "not hardware"
"""

import threading
import time

import pytest

from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.audio.devices import list_input_devices, preferred_default
from orchestre_ia.audio.events import AudioLevelEvent, CaptureState, CaptureStats

pytestmark = pytest.mark.hardware

DEVICES = list_input_devices()
DEFAULT = preferred_default(DEVICES)


@pytest.mark.skipif(DEFAULT is None, reason="aucun micro détecté")
def test_real_microphone_capture(bus):
    levels, stats = [], []
    lock = threading.Lock()

    def on_level(e):
        with lock:
            levels.append(e)

    bus.subscribe(AudioLevelEvent, on_level)
    bus.subscribe(CaptureStats, stats.append)
    engine = AudioCaptureEngine(bus)
    ok = engine.start(CaptureSettings(device=DEFAULT.index, device_name=DEFAULT.name))
    assert ok, "le micro par défaut n'a pas pu être ouvert"
    time.sleep(2.0)
    state = engine.state
    engine.stop()

    assert state == CaptureState.RUNNING
    assert len(levels) >= 30  # ~30 mesures/s
    assert stats, "aucune statistique publiée"
    s = stats[-1]
    assert s.buffer_overruns == 0
    assert s.processing_ms_avg < s.block_ms
    print(
        f"\n[matériel] {DEFAULT.label} : {s.samplerate} Hz, {s.channels} canaux, "
        f"latence entrée {s.input_latency_ms + s.block_ms:.1f} ms, "
        f"traitement {s.processing_ms_avg:.3f} ms, niveau max {max(e.rms_db for e in levels):.1f} dBFS"
    )


@pytest.mark.skipif(not DEVICES, reason="aucun micro détecté")
def test_every_listed_wasapi_or_mme_device_opens(bus):
    """Chaque micro WASAPI/MME proposé dans l'interface doit pouvoir s'ouvrir."""
    failures = []
    for dev in DEVICES:
        if dev.hostapi not in ("Windows WASAPI", "MME"):
            continue
        engine = AudioCaptureEngine(bus)
        if not engine.start(CaptureSettings(device=dev.index, device_name=dev.name)):
            failures.append(dev.label)
        time.sleep(0.3)
        engine.stop()
    assert not failures, f"périphériques non ouvrables : {failures}"
