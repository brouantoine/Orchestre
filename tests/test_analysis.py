"""Tests de l'analyse musicale : théorie, hauteur, notes, diapason, tonalité, tempo."""

import numpy as np
import pytest

from orchestre_ia.analysis.key import KeyEstimator
from orchestre_ia.analysis.notes import NoteSegmenter
from orchestre_ia.analysis.pitch import YinPitchDetector
from orchestre_ia.analysis.tempo import TempoEstimator
from orchestre_ia.analysis.theory import Key, diatonic_chords, midi_to_hz, note_name
from orchestre_ia.analysis.tracker import PitchFrame, PitchTracker

SR = 48000


def voice_tone(midi: float, seconds: float, amp=0.2, vibrato_cents=0.0, sr=SR):
    t = np.arange(int(sr * seconds)) / sr
    f = midi_to_hz(midi) * 2 ** (vibrato_cents / 1200 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f) / sr
    return sum(amp / k * np.sin(k * phase) for k in range(1, 6)).astype(np.float32)


# ------------------------------------------------------------------ théorie
def test_note_names():
    assert note_name(60) == "Do4"
    assert note_name(63) == "Ré#4"
    assert note_name(69) == "La4"


def test_diatonic_chords_major_and_minor():
    names = [c.name for c in diatonic_chords(Key(0, False))]
    assert names == ["Do", "Rém", "Mim", "Fa", "Sol", "Lam", "Sidim"]
    minor = [c.name for c in diatonic_chords(Key(3, True))]  # Ré# mineur
    assert minor[0] == "Ré#m" and "La#" in minor  # V majeur ajouté


# ------------------------------------------------------------------ hauteur
@pytest.mark.parametrize("freq", [82.4, 110.0, 196.0, 330.0, 523.3, 880.0])
def test_yin_accuracy_with_strong_harmonics(freq):
    sr = 16000
    t = np.arange(1024) / sr
    x = sum((0.9 if k == 2 else 1 / k) * np.sin(2 * np.pi * freq * k * t) for k in range(1, 7))
    f0, conf = YinPitchDetector(sr).detect(x.astype(np.float32))
    assert abs(1200 * np.log2(f0 / freq)) < 10  # < 10 cents, pas d'erreur d'octave
    assert conf > 0.9


def test_yin_rejects_noise_and_silence():
    d = YinPitchDetector(16000)
    noise = np.random.default_rng(1).standard_normal(1024).astype(np.float32)
    assert d.detect(noise)[0] == 0.0
    assert d.detect(np.zeros(1024, np.float32))[0] == 0.0


def test_tracker_independent_of_block_size():
    signal = voice_tone(57, 1.0)  # La3
    results = []
    for block in (256, 512, 1024):
        tr = PitchTracker(SR)
        frames = [f for i in range(0, len(signal) - block + 1, block) for f in tr.process(signal[i : i + block])]
        voiced = [f.midi for f in frames if f.voiced]
        results.append(np.median(voiced))
        assert len(voiced) > 0.8 * len(frames)
    assert max(results) - min(results) < 0.05
    assert results[0] == pytest.approx(57, abs=0.1)


def test_tracker_works_at_44100():
    tr = PitchTracker(44100)
    sig = voice_tone(60, 0.5, sr=44100)
    frames = [f for i in range(0, len(sig) - 511, 512) for f in tr.process(sig[i : i + 512])]
    assert np.median([f.midi for f in frames if f.voiced]) == pytest.approx(60, abs=0.1)


# ------------------------------------------------------------------ notes
def run_segmenter(melody, offset_cents=0.0, vibrato=0.0, gap=0.05):
    tr = PitchTracker(SR)
    seg = NoteSegmenter(hop_s=tr.hop / tr.samplerate)
    audio = []
    for midi, dur in melody:
        audio.append(voice_tone(midi + offset_cents / 100, dur, vibrato_cents=vibrato))
        audio.append(np.zeros(int(SR * gap), np.float32))
    audio = np.concatenate(audio + [np.zeros(SR // 2, np.float32)])
    notes = []
    for i in range(0, len(audio) - 511, 512):
        for f in tr.process(audio[i : i + 512]):
            notes += seg.process(f)[0]
    return notes, seg


def test_segmenter_finds_melody():
    melody = [(60, 0.4), (62, 0.4), (64, 0.4), (65, 0.4), (67, 0.8)]
    notes, _ = run_segmenter(melody)
    assert [n.midi for n in notes] == [60, 62, 64, 65, 67]
    assert notes[-1].duration == pytest.approx(0.8, abs=0.08)


def test_vibrato_does_not_split_notes():
    notes, _ = run_segmenter([(57, 1.5), (59, 1.5)], vibrato=45)
    assert [n.midi for n in notes] == [57, 59]


def test_personal_tuning_is_corrected():
    # chanteur constamment 40 cents trop haut : sans correction, Do4+40 hésiterait avec Do#4
    melody = [(60, 0.5), (62, 0.5), (64, 0.5), (60, 0.5), (62, 0.5), (64, 0.5), (65, 0.5), (67, 0.5)]
    notes, seg = run_segmenter(melody, offset_cents=40)
    assert seg.tuning.offset_cents == pytest.approx(40, abs=8)
    assert [n.midi for n in notes][-4:] == [62, 64, 65, 67]


# ------------------------------------------------------------------ tonalité
def feed_scale(est, pcs, seconds_each=0.5, rounds=4):
    for _ in range(rounds):
        for pc in pcs:
            est.add(pc, seconds_each)


def test_key_c_major():
    est = KeyEstimator()
    feed_scale(est, [0, 2, 4, 5, 7, 9, 11, 0, 4, 7])
    k = est.estimate(0.0)
    assert k.key == Key(0, False)
    assert k.confidence > 0.3


def test_key_minor():
    est = KeyEstimator()
    feed_scale(est, [9, 11, 0, 2, 4, 5, 7, 9, 0, 4, 9])  # La mineur
    assert est.estimate(0.0).key == Key(9, True)


def test_passing_note_does_not_change_key():
    est = KeyEstimator()
    feed_scale(est, [0, 2, 4, 5, 7, 9, 11, 0, 4, 7])
    est.estimate(0.0)
    est.add(6, 0.5)  # Fa# de passage
    est.add(1, 0.3)
    assert est.estimate(1.0).key == Key(0, False)


def test_real_modulation_is_followed_after_delay():
    est = KeyEstimator(half_life_s=10, switch_s=4)
    feed_scale(est, [0, 2, 4, 5, 7, 9, 11, 0, 4, 7])
    assert est.estimate(0.0).key == Key(0, False)
    t = 0.0
    results = []
    for _ in range(12):  # longue section en Sol majeur (Fa#)
        for pc in [7, 9, 11, 0, 2, 4, 6, 7, 11, 2]:
            est.add(pc, 0.5)
        t += 5
        results.append(est.estimate(t).key)
    assert results[0] == Key(0, False) or results[1] == Key(0, False)  # pas de bascule immédiate
    assert results[-1] == Key(7, False)


# ------------------------------------------------------------------ tempo
def test_tempo_regular_onsets():
    rng = np.random.default_rng(0)
    est = TempoEstimator()
    for i in range(24):
        est.add_onset(i * 0.6 + rng.normal(0, 0.012))  # 100 BPM, ±12 ms humain
    t = est.estimate()
    assert t.bpm == pytest.approx(100, rel=0.04)
    assert t.confidence > 0.5


def test_tempo_eighth_notes_resolve_to_beat():
    est = TempoEstimator()
    for i in range(32):
        est.add_onset(i * 0.3)  # croches à 100 BPM
    assert est.estimate().bpm == pytest.approx(100, rel=0.05)


def test_tempo_free_singing_has_low_confidence():
    rng = np.random.default_rng(3)
    est = TempoEstimator()
    t = 0.0
    for _ in range(20):
        t += rng.uniform(0.25, 1.4)
        est.add_onset(t)
    assert est.estimate().confidence < 0.5


def test_tempo_needs_enough_onsets():
    est = TempoEstimator()
    for i in range(4):
        est.add_onset(i * 0.5)
    assert est.estimate() is None


def test_pitchframe_midi():
    assert PitchFrame(0, 440.0, 1, -20).midi == pytest.approx(69)
    assert not PitchFrame(0, 0.0, 0, -80).voiced
