"""Mémoire à deux accords : l'accord suivant dépend aussi de l'avant-dernier accord."""

import numpy as np

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.learning.memory import (
    LearnedHarmony,
    MusicMemory,
    changes,
    count_contexts,
    learned_from,
)
from orchestre_ia.learning.study import Piece, StudyResult

C = Key(0, False)


def piece(tokens: list[str]) -> Piece:
    return Piece(0.0, 0.0, C, 0.0, [(t, 1.0) for t in tokens], [])


# Après I → V vient vi ; après IV → V vient I : seul le contexte permet de les distinguer.
SONG = ["0", "7", "9m", "5", "7", "0"] * 20


def test_changes_merges_repetitions():
    assert changes([("0", 2.0), ("0", 1.0), ("7", 1.0), ("0", 4.0)]) == ["0", "7", "0"]


def test_count_contexts():
    counts = count_contexts([piece(["0", "0", "7", "9m", "5"])])
    assert counts == {(0, "0", "7", "9m"): 1, (0, "7", "9m", "5"): 1}


def test_context_separates_what_one_chord_cannot():
    learned = learned_from([piece(SONG)])
    assert learned.transition_probability(False, "7", "9m", prev="0") > 0.8
    assert learned.transition_probability(False, "7", "0", prev="5") > 0.8
    # sans contexte, V est suivi à parts égales de vi et de I
    simple_vi = learned.transition_probability(False, "7", "9m")
    simple_i = learned.transition_probability(False, "7", "0")
    assert abs(simple_vi - simple_i) < 0.05


def test_unknown_context_falls_back_to_simple_transition():
    learned = learned_from([piece(SONG)])
    assert learned.transition_probability(False, "7", "9m", prev="2m") == learned.transition_probability(
        False, "7", "9m"
    )


def test_engine_uses_previous_chord():
    engine = HarmonyEngine(learned=learned_from([piece(SONG)] * 5))
    g = Chord(7, "maj")
    after_c = engine.predict_next(C, g, previous=Chord(0, "maj"))
    after_f = engine.predict_next(C, g, previous=Chord(5, "maj"))
    assert (after_c[0].root, after_c[0].triad_quality) == (9, "min")
    assert after_f[0].root == 0


def test_engine_remembers_previous_chord_while_playing():
    engine = HarmonyEngine()
    for pc in (0, 7):  # Do puis Sol chantés
        evidence = np.zeros(12)
        evidence[[pc, (pc + 4) % 12, (pc + 7) % 12]] = 1.0
        engine.decide(evidence, C, 1.0)
    assert engine.current.root == 7 and engine.previous.root == 0
    engine.reset()
    assert engine.current is None and engine.previous is None


def test_team_habit_survives_corpus_context():
    """Le corpus dit « I → V → vi », l'équipe joue toujours V → IV : l'équipe l'emporte."""
    prior = learned_from([piece(SONG)] * 50)
    team = learned_from([piece(["0", "5", "7", "5"] * 40)], base=LearnedHarmony(prior=prior))
    assert team.transition_probability(False, "7", "5", prev="0") > team.transition_probability(
        False, "7", "9m", prev="0"
    )


def test_contexts_are_stored_and_reloaded(tmp_path):
    with MusicMemory(tmp_path / "m.sqlite") as memory:
        memory.store("s", "louange", StudyResult(60.0, [piece(SONG)], 120))
        learned = memory.learned()
        assert learned.contexts[(False, "0", "7", "9m")] == 20
        assert memory.forget("s")
        assert memory.learned().contexts == {}


# ------------------------------------------------------------- mémoire du chant en cours
LOOP = [Chord(0, "maj"), Chord(9, "min"), Chord(5, "maj"), Chord(7, "maj")]  # Do Lam Fa Sol


def test_song_memory_learns_the_loop():
    engine = HarmonyEngine()
    for chord in LOOP * 2:
        engine.remember(chord)
    engine.current, engine.previous = Chord(5, "maj"), Chord(9, "min")
    weight, p = engine.song_move(Chord(7, "maj"))
    assert weight > 0.6 and p == 1.0
    assert engine.song_move(Chord(0, "maj"))[1] == 0.0


def test_song_memory_anticipates_an_unusual_progression():
    """Do → Lam est rare pour les règles génériques ; après deux tours de boucle, il est attendu."""
    plain, memory = HarmonyEngine(song_memory=False), HarmonyEngine()
    for chord in LOOP * 2:
        memory.remember(chord)
    c = Chord(0, "maj")
    assert plain.predict_next(C, c, previous=Chord(7, "maj"))[0].root != 9
    best = memory.predict_next(C, c, previous=Chord(7, "maj"))[0]
    assert (best.root, best.triad_quality) == (9, "min")


def test_sung_notes_still_override_song_memory():
    engine = HarmonyEngine()
    for chord in LOOP * 3:
        engine.remember(chord)
    engine.current, engine.previous = Chord(0, "maj"), Chord(7, "maj")
    evidence = np.zeros(12)
    evidence[[2, 5, 9]] = 1.0  # Ré Fa La chantés : Rém, pas Lam
    decision = engine.decide(evidence, C, 1.0)
    assert (decision.chord.root, decision.chord.triad_quality) == (2, "min")


def test_decide_feeds_song_memory_and_reset_forgets():
    engine = HarmonyEngine()
    for pc, minor in ((0, False), (7, False), (0, False)):
        evidence = np.zeros(12)
        evidence[[pc, (pc + (3 if minor else 4)) % 12, (pc + 7) % 12]] = 1.0
        engine.decide(evidence, C, 1.0)
    engine.current, engine.previous = Chord(0, "maj"), None
    assert engine.song_move(Chord(7, "maj")) == (0.5, 1.0)  # Do → Sol entendu une fois
    engine.reset()
    engine.current = Chord(0, "maj")
    assert engine.song_move(Chord(7, "maj")) == (0.0, 0.0)
