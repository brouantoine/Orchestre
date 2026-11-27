"""Verrouillage de grille : repérage, jeu en avance, lâcher quand le chant change, reprise."""

import numpy as np

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.conductor.lock import ProgressionLock

C, AM, F, G = Chord(0, "maj"), Chord(9, "min"), Chord(5, "maj"), Chord(7, "maj")
DM, EM = Chord(2, "min"), Chord(4, "min")


def feed(lock, chords, start=0, dur=4):
    """Joue `chords` (un changement tous les `dur` temps) ; retourne le temps suivant."""
    beat = start
    for chord in chords:
        lock.observe(chord, beat)
        beat += dur
    return beat


def test_locks_on_last_chord_of_second_round_and_plays_ahead():
    lock = ProgressionLock(detection_lag=0)
    feed(lock, [C, AM, F, G])
    assert not lock.locked
    feed(lock, [C, AM, F], start=16)
    assert not lock.locked
    lock.observe(G, 28)  # dernier accord du 2e tour : la grille est reconnue
    assert lock.locked and lock.cycle.names() == "Do → Lam → Fa → Sol"
    # la grille est rejouée sans rien entendre, pile sur les temps
    assert [lock.expected(b).name for b in (28, 31, 32, 35, 36, 40, 44, 48)] == [
        "Sol", "Sol", "Do", "Do", "Lam", "Fa", "Sol", "Do"
    ]


def test_grid_is_advanced_by_the_listening_delay():
    """Changements entendus 2 temps après avoir été chantés : la grille verrouillée change avec le chanteur."""
    lock = ProgressionLock()  # retard d'écoute par défaut : 2 temps
    feed(lock, [C, AM, F, G, C, AM, F, G], start=2)
    assert lock.locked
    assert lock.expected(28).name == "Sol"  # Sol entendu au temps 30, joué dès le temps 28
    assert lock.expected(32).name == "Do" and lock.expected(36).name == "Lam"


def test_irregular_changes_are_not_advanced():
    lock = ProgressionLock()
    beat = 0
    for _ in range(2):
        for chord, dur in ((C, 3), (AM, 5), (F, 4), (G, 4)):  # changements à des endroits variés
            lock.observe(chord, beat)
            beat += dur
    assert lock.locked
    assert lock.expected(28).name == "Sol" and lock.expected(32).name == "Do"


def test_different_durations_do_not_lock():
    lock = ProgressionLock(detection_lag=0)
    beat = feed(lock, [C, AM, F, G], dur=4)
    for chord, dur in ((C, 4), (AM, 2), (F, 4), (G, 4)):  # Lam écourté au 2e tour
        lock.observe(chord, beat)
        beat += dur
    lock.observe(C, beat)
    assert not lock.locked


def test_two_chord_vamp_locks():
    lock = ProgressionLock(detection_lag=0)
    feed(lock, [AM, G, AM, G, AM], dur=2)
    assert lock.locked and lock.cycle.beats == 4


def test_unlocks_only_after_repeated_contradiction():
    lock = ProgressionLock(detection_lag=0)
    feed(lock, [C, AM, F, G, C, AM, F, G, C])
    assert lock.locked
    assert not lock.check(expected_score=0.9, best_score=0.95)  # léger écart : on garde
    assert not lock.check(expected_score=0.1, best_score=0.9)  # une contradiction : on garde
    assert not lock.check(expected_score=0.8, best_score=0.9)  # le chant revient : compteur remis à zéro
    assert not lock.check(expected_score=0.1, best_score=0.9)
    assert lock.check(expected_score=0.0, best_score=0.9)  # deux de suite : grille lâchée
    assert not lock.locked and lock.expected(100) is None


def test_unconfirmed_grid_is_forgotten():
    """Grille contredite dès le début : c'était une erreur d'écoute, elle n'est pas reprise plus tard."""
    lock = ProgressionLock(detection_lag=0)
    feed(lock, [C, AM, F, G, C, AM, F, G])
    assert lock.check(0.0, 0.9) is False and lock.check(0.0, 0.9) is True
    assert lock.known == []


def test_known_progression_is_resumed_quickly():
    """Après un pont, le refrain revient : deux accords reconnus suffisent pour reprendre la grille."""
    lock = ProgressionLock(detection_lag=0)
    beat = feed(lock, [C, AM, F, G, C, AM, F, G, C])
    for _ in range(4):
        lock.check(0.9, 0.9)  # le chant confirme la grille pendant 2 mesures
    lock.check(0.0, 0.9)
    assert lock.check(0.0, 0.9)  # puis le chant change (pont)
    beat = feed(lock, [DM, EM, F], start=beat + 4)  # pont, sans répétition
    assert not lock.locked
    beat = feed(lock, [C, AM], start=beat)  # retour du refrain
    lock.observe(F, beat)
    assert lock.locked
    assert lock.expected(beat).name == "Fa" and lock.expected(beat + 4).name == "Sol"
    assert lock.expected(beat + 8).name == "Do"


def test_reset_forgets_known_progressions():
    lock = ProgressionLock(detection_lag=0)
    feed(lock, [C, AM, F, G, C, AM, F, G, C])
    lock.reset()
    assert not lock.locked and lock.known == []


def test_fit_ignores_context_and_follow_updates_engine():
    engine = HarmonyEngine()
    evidence = np.zeros(12)
    evidence[[2, 5, 9]] = 1.0  # Ré Fa La
    key = Key(0, False)
    assert engine.fit(DM, evidence, key) == engine.best_fit(evidence, key) > engine.fit(C, evidence, key)
    engine.follow(C, key)
    engine.follow(AM, key)
    assert engine.current.name == "Lam" and engine.current.degree == 6 and engine.previous.name == "Do"
    assert engine.song_move(F) == (0.0, 0.0)  # Lam → Fa jamais entendu
