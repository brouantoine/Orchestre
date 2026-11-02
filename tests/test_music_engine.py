"""Tests harmonie, horloge, ordonnancement MIDI, piano, batterie, synthèse."""

import numpy as np
import pytest

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.clock import MusicClock
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.instruments.base import PlayContext
from orchestre_ia.instruments.drums import DrumEngine
from orchestre_ia.instruments.piano import BASS_HIGH, BASS_LOW, RIGHT_HIGH, RIGHT_LOW, PianoEngine, voice_chord
from orchestre_ia.instruments.styles import KICK, SNARE, STYLES, TOM_LOW
from orchestre_ia.midi.events import DRUM_CHANNEL, MidiNote, MidiScheduler
from orchestre_ia.synthesis.builtin import BuiltinSynth


def evidence(*pcs_weights):
    e = np.zeros(12)
    for pc, w in pcs_weights:
        e[pc] += w
    return e


# ------------------------------------------------------------------ harmonie
def test_harmony_picks_matching_chord():
    h = HarmonyEngine()
    d = h.decide(evidence((0, 1), (4, 1), (7, 1)), None, 0)
    assert d.chord.name == "Do"


def test_harmony_uses_key_context():
    h = HarmonyEngine()
    # La + Do : ambigu (Lam ou Fa) ; en La mineur, Lam doit gagner
    d = h.decide(evidence((9, 1), (0, 1)), Key(9, True), 0.9)
    assert d.chord.name == "Lam"
    assert d.chord.degree == 1


def test_harmony_is_stable_on_passing_note():
    h = HarmonyEngine()
    h.decide(evidence((0, 1), (4, 1), (7, 1)), Key(0, False), 0.8)
    d = h.decide(evidence((0, 0.6), (2, 0.3), (4, 0.6)), Key(0, False), 0.8)  # Ré de passage
    assert d.chord.name == "Do"


def test_harmony_waits_without_evidence():
    assert HarmonyEngine().decide(np.zeros(12), None, 0) is None


def test_harmony_prefers_diatonic_chords():
    h = HarmonyEngine()
    for pcs in ([0, 4], [2, 9], [7, 11], [5, 9], [4, 11]):
        d = h.decide(evidence(*[(p, 1) for p in pcs]), Key(0, False), 0.8)
        assert d.chord.degree > 0, d.chord.name


# ------------------------------------------------------------------ horloge
def test_clock_conversions():
    c = MusicClock(48000, bpm=120)
    assert c.sample_at_beat(1) == pytest.approx(24000)
    assert c.beat_at_sample(48000) == pytest.approx(2)


def test_tempo_change_is_continuous():
    c = MusicClock(48000, bpm=120)
    c.advance(48000, 10.0)  # 2 temps joués
    c.set_tempo(60)
    assert c.beat_at_sample(48000) == pytest.approx(2)
    assert c.beat_at_sample(96000) == pytest.approx(3)


def test_clock_align_puts_beat_on_singer_beat():
    c = MusicClock(48000, bpm=60)
    c.advance(0, 100.0)  # l'échantillon 0 sort à t=100 s
    c.align(100, beat_monotonic=100.13, next_beat_index=8)
    t8 = c.monotonic_at_beat(8)
    period = 0.6
    assert ((t8 - 100.13) / period) == pytest.approx(round((t8 - 100.13) / period), abs=1e-6)
    assert t8 > 100.25


# ------------------------------------------------------------------ MIDI
def test_scheduler_orders_offs_before_ons():
    s = MidiScheduler()
    s.add_note(MidiNote(0, 60, 100, 1.0, 1.0))
    s.add_note(MidiNote(0, 60, 100, 2.0, 1.0))
    msgs = s.pop_due(2.5)
    assert [(m.beat, m.kind) for m in msgs] == [(1.0, "on"), (2.0, "off"), (2.0, "on")]
    assert len(s) == 1
    s.clear()
    assert len(s) == 0


# ------------------------------------------------------------------ piano
def ctx(chord, beat=0, style="pop", rhythmic=True, changed=True, intensity=0.6, fill=False):
    return PlayContext(beat, beat % 4, beat // 4, chord, changed, Key(0, False), STYLES[style], intensity, rhythmic, fill)


def test_voicing_moves_minimally():
    c = voice_chord((0, 4, 7), None)
    f = voice_chord((5, 9, 0), c)  # Do -> Fa : le Do commun reste
    assert set(c) & set(f)
    assert sum(abs(a - b) for a, b in zip(sorted(c), sorted(f))) <= 5
    assert all(RIGHT_LOW <= n <= RIGHT_HIGH for n in f)


@pytest.mark.parametrize("style", list(STYLES))
def test_every_piano_style_plays_in_range(style):
    p = PianoEngine()
    chord = Chord(7, "maj", 5)
    played = []
    for b in range(4):
        notes, _ = p.play_beat(ctx(chord, b, style, changed=(b == 0)))
        played += notes
        for n in notes:
            assert b <= n.start < b + 1.6
            assert 24 <= n.note <= RIGHT_HIGH
    assert played
    assert any(BASS_LOW <= n.note <= BASS_HIGH + 12 for n in played)
    pcs = {n.note % 12 for n in played}
    assert pcs <= {7, 11, 2, 5, 6, 10}  # notes de Sol (7e éventuelle, approche jazz)


def test_free_mode_holds_then_releases_on_change():
    p = PianoEngine()
    notes, offs = p.play_beat(ctx(Chord(0, "maj", 1), 0, rhythmic=False))
    assert notes and all(n.duration == 0 for n in notes)  # tenues
    assert not offs
    notes2, offs2 = p.play_beat(ctx(Chord(0, "maj", 1), 1, rhythmic=False, changed=False))
    assert not notes2 and not offs2
    notes3, offs3 = p.play_beat(ctx(Chord(5, "maj", 4), 2, rhythmic=False))
    assert len(offs3) == len(notes)  # tout l'accord précédent est relâché
    assert all(o.beat < 2 for o in offs3)


def test_seventh_chords_in_gospel():
    p = PianoEngine()
    notes, _ = p.play_beat(ctx(Chord(7, "maj", 5), 0, "gospel"))
    assert 5 in {n.note % 12 for n in notes}  # Fa = 7e de Sol


# ------------------------------------------------------------------ batterie
@pytest.mark.parametrize("style", [s for s in STYLES if STYLES[s].drums])
def test_drums_follow_beat_grid(style):
    d = DrumEngine(seed=1)
    for b in range(4):
        notes, _ = d.play_beat(ctx(Chord(0, "maj"), 8 + b, style))
        for n in notes:
            assert n.channel == DRUM_CHANNEL
            assert 8 + b - 0.02 <= n.start < 8 + b + 1


def test_drums_light_intensity_removes_snare():
    d = DrumEngine(seed=1)
    notes = [n for b in range(4) for n in d.play_beat(ctx(Chord(0, "maj"), b, "pop", intensity=0.2))[0]]
    assert SNARE not in {n.note for n in notes}
    assert KICK in {n.note for n in notes}


def test_drum_fill_on_last_beat():
    d = DrumEngine(seed=1)
    notes, _ = d.play_beat(ctx(Chord(0, "maj"), 15, "pop", fill=True))
    assert TOM_LOW in {n.note for n in notes}


def test_no_drums_in_free_mode():
    assert DrumEngine().play_beat(ctx(Chord(0, "maj"), 0, "pop", rhythmic=False)) == ([], [])


# ------------------------------------------------------------------ synthèse
def test_builtin_synth_produces_sound_and_releases():
    s = BuiltinSynth(48000)
    s.program(9, 0, drums=True)
    assert np.abs(s.render(512)).max() == 0
    s.noteon(0, 60, 100)
    s.noteon(9, 36, 100)
    out = s.render(4800)
    assert out.shape == (4800, 2) and np.abs(out).max() > 0.01
    s.noteoff(0, 60)
    for _ in range(100):
        s.render(4800)
    assert np.abs(s.render(512)).max() < 1e-3


def test_builtin_synth_tuning_follows_singer():
    s = BuiltinSynth(48000)
    s.tune(0, 40)
    s.noteon(0, 69, 100)
    assert s._voices[-1].freq == pytest.approx(440 * 2 ** (40 / 1200))


def test_fluidsynth_backend_renders():
    try:
        from orchestre_ia.synthesis.fluid import FluidSynthBackend

        b = FluidSynthBackend(48000)
    except Exception as exc:
        pytest.skip(f"FluidSynth indisponible : {exc}")
    b.program(0, 0)
    b.noteon(0, 60, 100)
    out = b.render(9600)
    b.close()
    assert out.shape == (9600, 2) and np.abs(out).max() > 0.01
