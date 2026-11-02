"""Tests d'intégration : sortie audio et accompagnement complet d'un chant simulé."""

import threading
import time

import numpy as np
import pytest

from orchestre_ia.app.session import MusicSession
from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.conductor.conductor import AccompanimentSettings, ConductorState, ConductorUpdate
from orchestre_ia.midi.events import MidiNote
from orchestre_ia.synthesis.builtin import BuiltinSynth
from orchestre_ia.synthesis.output import AudioOutputEngine
from tests.fakes import FakeInputStream
from tests.test_analysis import voice_tone


class FakeOutputStream:
    """Sortie simulée : appelle le callback en temps réel et garde le signal produit."""

    def __init__(self, *, samplerate, blocksize, channels, callback, **_):
        self.samplerate, self.blocksize, self.channels, self.callback = samplerate, blocksize, channels, callback
        self.latency = 0.01
        self.blocks = []
        self._halt = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        period = self.blocksize / self.samplerate
        nxt = time.perf_counter()
        while not self._halt.is_set():
            out = np.zeros((self.blocksize, self.channels), np.float32)
            self.callback(out, self.blocksize, None, None)
            self.blocks.append(out)
            nxt += period
            time.sleep(max(0, nxt - time.perf_counter()))

    def stop(self):
        self._halt.set()
        if self._thread:
            self._thread.join(1)

    def close(self):
        pass


def test_output_engine_plays_scheduled_note_sample_accurately(bus):
    streams = []

    def factory(**kw):
        s = FakeOutputStream(**kw)
        streams.append(s)
        return s

    out = AudioOutputEngine(bus, backend_factory=BuiltinSynth, stream_factory=factory)
    assert out.start()
    out.clock.set_tempo(120)
    beat = out.clock.current_beat() + 1.0  # dans 0,5 s
    target_sample = out.clock.sample_at_beat(beat)
    out.scheduler.add_note(MidiNote(0, 69, 110, beat, 0.5))
    time.sleep(1.2)
    out.stop()
    audio = np.concatenate(streams[0].blocks)[:, 0]
    onset = int(np.argmax(np.abs(audio) > 0.01))
    assert abs(onset - target_sample) < 48  # < 1 ms d'erreur
    assert out.callback_errors == 0


def sung_melody_factory(signal):
    def factory(**kw):
        return FakeInputStream(signal_fn=signal, speed=1.0, **kw)

    return factory


@pytest.mark.parametrize("tempo_mode", ["auto", "manual"])
def test_full_accompaniment_of_simulated_singer(bus, tempo_mode):
    # Mélodie en Do majeur, notes sur une grille de 100 BPM (0,6 s)
    melody = [60, 64, 67, 64, 65, 69, 67, 65, 64, 62, 60, 62, 64, 67, 72, 67] * 2
    gap = np.zeros(int(48000 * 0.1), np.float32)
    audio = np.concatenate([np.concatenate([voice_tone(m, 0.5), gap]) for m in melody])
    audio = np.concatenate([audio, np.zeros(48000 * 10, np.float32)])

    def signal(t):
        idx = np.clip((t * 48000).astype(int), 0, len(audio) - 1)
        return audio[idx]

    updates = []
    bus.subscribe(ConductorUpdate, updates.append)
    settings = AccompanimentSettings(style="pop", drums_mode="on", tempo_mode=tempo_mode, manual_bpm=100)
    capture = AudioCaptureEngine(bus, stream_factory=sung_melody_factory(signal))
    output = AudioOutputEngine(bus, backend_factory=BuiltinSynth, stream_factory=lambda **kw: FakeOutputStream(**kw))
    session = MusicSession(bus, capture=capture, output=output, settings=settings)
    assert session.start(CaptureSettings(device_name="chanteur simulé"), headphones=True)
    time.sleep(12)
    playing = [u for u in updates if u.state == ConductorState.PLAYING and u.chord != "—"]
    session.stop()

    assert playing, "le piano n'est jamais entré"
    first_play = next(u for u in updates if u.state == ConductorState.PLAYING)
    assert first_play.timestamp - updates[0].timestamp < 6.0  # entrée rapide
    chords = {u.chord for u in playing}
    diatonic = {"Do", "Rém", "Mim", "Fa", "Sol", "Lam", "Sidim"}
    assert chords <= diatonic, chords
    assert playing[-1].key == "Do majeur"
    if tempo_mode == "manual":
        assert any(u.drums_active for u in playing)
        assert all(u.rhythmic for u in playing)
    assert output.callback_errors == 0
    assert session.conductor.state == ConductorState.IDLE


def test_pause_silences_and_resume_listens(bus):
    output = AudioOutputEngine(bus, backend_factory=BuiltinSynth, stream_factory=lambda **kw: FakeOutputStream(**kw))
    capture = AudioCaptureEngine(bus, stream_factory=sung_melody_factory(lambda t: np.zeros_like(t, dtype=np.float32)))
    session = MusicSession(bus, capture=capture, output=output)
    session.start(CaptureSettings(device_name="silence"))
    session.pause()
    assert session.paused
    assert len(output.scheduler) == 0
    session.resume()
    assert session.conductor.state == ConductorState.LISTENING
    session.stop()
