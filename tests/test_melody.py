"""Main droite mélodique : registre, gamme, discrétion pendant le chant, motifs, jeu libre."""

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.instruments.base import PlayContext
from orchestre_ia.instruments.melody import HIGH, LOW, MelodyEngine
from orchestre_ia.instruments.styles import STYLES
from orchestre_ia.midi.events import MELODY_CHANNEL

C = Key(0, False)
PROGRESSION = [Chord(0, "maj", 1), Chord(9, "min", 6), Chord(5, "maj", 4), Chord(7, "maj", 5)]


def play(engine, bars=16, singing=False, style="gospel", rhythmic=True, intensity=0.7):
    notes = []
    for beat in range(bars * 4):
        bar, bib = divmod(beat, 4)
        chord = PROGRESSION[bar % 4]
        ctx = PlayContext(beat, bib, bar, chord, bib == 0, C, STYLES[style], intensity, rhythmic,
                          fill=bar % 4 == 3, phrase_start=bar % 4 == 0, singing=singing)
        notes += [(n, chord) for n in engine.play_beat(ctx)[0]]
    return notes


def test_notes_stay_in_register_scale_and_channel():
    for style in STYLES:
        for note, chord in play(MelodyEngine(seed=1), style=STYLES[style].key):
            assert LOW <= note.note <= HIGH
            assert note.channel == MELODY_CHANNEL
            assert note.note % 12 in set(C.scale) | set(chord.pcs)


def test_quiet_while_singing_busier_in_gaps():
    singing = play(MelodyEngine(seed=2), singing=True)
    gaps = play(MelodyEngine(seed=2), singing=False)
    assert 0 < len(singing) < len(gaps) / 3
    assert max(n.velocity for n, _ in singing) < min(n.velocity for n, _ in gaps)


def test_strong_beats_are_chord_tones():
    for note, chord in play(MelodyEngine(seed=3)):
        pos = note.start % 4
        if abs(pos - round(pos)) < 1e-6 and round(pos) % 2 == 0:
            assert note.note % 12 in chord.pcs


def test_motif_rhythm_repeats_within_a_phrase():
    """Même rythme d'une mesure à l'autre dans une phrase : un riff, pas des notes au hasard."""
    notes = [n for n, _ in play(MelodyEngine(seed=4), bars=4, style="afro")]
    by_bar = {}
    for n in notes:
        if n.start < 12:  # la 4e mesure se termine par une relance
            by_bar.setdefault(int(n.start // 4), []).append(round(n.start % 4, 3))
    rhythms = list(by_bar.values())
    assert len(rhythms) == 3 and rhythms[0] == rhythms[1] == rhythms[2]


def test_fill_runs_down_at_end_of_phrase():
    notes = [n for n, _ in play(MelodyEngine(seed=5), bars=4) if n.start >= 15]
    assert len(notes) == 4
    pitches = [n.note for n in notes]
    assert pitches == sorted(pitches, reverse=True)


def test_reproducible_with_seed():
    assert play(MelodyEngine(seed=7)) == play(MelodyEngine(seed=7))


def test_silent_when_very_soft():
    assert play(MelodyEngine(seed=8), intensity=0.1) == []


def test_free_mode_ornaments_only_on_chord_change():
    notes = play(MelodyEngine(seed=9), bars=4, rhythmic=False)
    assert notes
    assert {int(n.start) for n, _ in notes} <= {0, 4, 8, 12}  # temps des changements d'accord
