"""Écoute d'apprentissage, étude des séances, mémoire musicale et usage par l'harmonie."""

import json
import time

import numpy as np
import pytest
import soundfile as sf

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.core.config import AppConfig
from orchestre_ia.learning import study
from orchestre_ia.learning.listening import SegmentedRecorder, load_info, new_session_dir
from orchestre_ia.learning.memory import LearnedHarmony, MusicMemory, load_learned_harmony, roman
from tests.fakes import fake_factory, sine
from tests.music_fixtures import render_progression

SR = 48000
G_MAJOR_SONG = [(7, False), (2, False), (4, True), (0, False)]  # Sol Ré Mim Do
EB_MAJOR_SONG = [(3, False), (10, False), (0, True), (8, False)]  # Mib Sib Dom Lab


def _block(value: float = 0.3, n: int = 512) -> np.ndarray:
    return np.full(n, value, dtype=np.float32)


# ------------------------------------------------------------- enregistrement
def test_segmented_recorder_rotates_parts(tmp_path):
    rec = SegmentedRecorder(tmp_path, segment_seconds=0.1)
    rec.start()
    for _ in range(30):
        rec.write(_block(), SR)
    parts = rec.stop()
    assert [p.name for p in parts] == ["partie_001.wav", "partie_002.wav", "partie_003.wav"]
    total = sum(len(sf.read(p, dtype="float32")[0]) for p in parts)
    assert total == 30 * 512 == rec.frames_written
    assert rec.duration_s == pytest.approx(30 * 512 / SR)


def test_segmented_recorder_new_part_when_samplerate_changes(tmp_path):
    rec = SegmentedRecorder(tmp_path)
    rec.start()
    rec.write(_block(), 48000)
    rec.write(_block(), 44100)
    parts = rec.stop()
    assert [sf.info(p).samplerate for p in parts] == [48000, 44100]


def test_clipping_ignores_microphone_click(tmp_path):
    rec = SegmentedRecorder(tmp_path)
    rec.start()
    rec.write(_block(1.0), SR)  # déclic d'ouverture
    for _ in range(60):
        rec.write(_block(0.2), SR)
    rec.write(_block(1.0), SR)  # vraie saturation
    rec.stop()
    assert rec.clipped_blocks == 1
    assert rec.peak == pytest.approx(1.0)


def test_session_dir_names_are_unique(tmp_path):
    a = new_session_dir(tmp_path, "Louange du dimanche")
    b = new_session_dir(tmp_path, "Louange du dimanche")
    assert a != b and a.name.endswith("louange_du_dimanche")


def test_learn_listen_command_records_a_session():
    from orchestre_ia.app.application import run_learning_listen
    from orchestre_ia.core.paths import listening_dir

    before = set(listening_dir().glob("*")) if listening_dir().exists() else set()
    code = run_learning_listen(
        AppConfig(), None, "louange test", minutes=0.01, stream_factory=fake_factory(sine(220, 0.3), speed=4.0)
    )
    assert code == 0
    (session,) = set(listening_dir().glob("*")) - before
    info = load_info(session)
    assert info is not None and info.label == "louange test" and info.ended_at is not None
    assert info.segments == ["partie_001.wav"] and info.duration_s > 0.5
    data, sr = sf.read(session / "partie_001.wav", dtype="float32")
    assert sr == 48000 and np.max(np.abs(data)) == pytest.approx(0.3, abs=0.01)  # pas de filtre ni de gain
    json.loads((session / "seance.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ étude
@pytest.fixture(scope="module")
def two_songs_result():
    sr = 22050
    song_a = render_progression(G_MAJOR_SONG, bpm=80, repeats=3, sr=sr)
    gap = np.random.default_rng(0).normal(0, 1e-4, 12 * sr).astype(np.float32)  # pause (prière)
    song_b = render_progression(EB_MAJOR_SONG, bpm=96, repeats=4, sr=sr)
    y = np.concatenate([song_a, gap, song_b])
    return study.study_features(study.beat_features(y, sr), len(y) / sr)


def test_study_finds_each_song_key_tempo_and_progression(two_songs_result):
    pieces = two_songs_result.pieces
    assert len(pieces) == 2
    first, second = pieces
    assert first.key == Key(7, False) and second.key == Key(3, False)
    assert first.tempo == pytest.approx(80, abs=5) and second.tempo == pytest.approx(96, abs=6)
    for piece in pieces:
        progression = piece.typical_progression()
        doubled = ["I", "V", "vi", "IV"] * 2
        assert any(doubled[i : i + 4] == progression for i in range(4)), progression
    assert first.end_s < second.start_s


def test_study_ignores_audio_without_music():
    sr = 22050
    noise = np.random.default_rng(1).normal(0, 0.05, 40 * sr).astype(np.float32)
    assert study.study_features(study.beat_features(noise, sr), 40).pieces == []


def test_viterbi_penalizes_flickering():
    scores = np.array([[1.0, 1.0, 0.9, 1.0, 1.0], [0.0, 0.0, 1.0, 0.0, 0.0]])
    assert study.viterbi_constant_switch(scores, 0.5).tolist() == [0, 0, 0, 0, 0]
    assert study.viterbi_constant_switch(scores, 0.0).tolist() == [0, 0, 1, 0, 0]


# ------------------------------------------------------------------ mémoire
def test_memory_stores_replaces_and_forgets(tmp_path, two_songs_result):
    path = tmp_path / "memoire.sqlite"
    with MusicMemory(path) as memory:
        memory.store("seance-1", "louange", two_songs_result)
        once = memory.learned()
        memory.store("seance-1", "louange", two_songs_result)  # réétude : remplace
        assert memory.learned().transitions == once.transitions
        assert memory.is_studied("seance-1")
        assert any("I→V" in line or "V→vi" in line for line in memory.summary_lines())
    learned = load_learned_harmony(path)
    assert learned is not None
    assert learned.transition_probability(False, "7", "9m") > 0.5  # V -> vi
    assert learned.usage_share(False, "0") == pytest.approx(0.25, abs=0.08)
    with MusicMemory(path) as memory:
        assert memory.forget("seance-1")
    assert load_learned_harmony(path) is None


def test_roman_numerals():
    assert [roman(t) for t in ("0", "2m", "5", "7", "9m", "10", "3")] == ["I", "ii", "IV", "V", "vi", "bVII", "bIII"]


def test_learned_borrowed_chord_becomes_acceptable():
    """Une équipe qui joue souvent I -> bVII : l'orchestre l'adopte au lieu de le fuir."""
    c_major = Key(0, False)
    learned = LearnedHarmony(
        transitions={(False, "0", "10"): 150, (False, "10", "5"): 150, (False, "5", "0"): 150},
        usage={(False, "0"): 400.0, (False, "10"): 250.0, (False, "5"): 300.0},
    )
    evidence = np.zeros(12)
    evidence[[10, 2, 5]] = [0.4, 0.3, 0.4]  # Sib, Ré, Fa chantés
    choices = []
    for memory in (None, learned):
        engine = HarmonyEngine(learned=memory)
        engine.current = Chord(0, "maj", 1)
        decision = engine.decide(evidence, c_major, 0.8)
        assert decision is not None
        choices.append(decision.chord.name)
    assert choices[0] != "La#" and choices[1] == "La#"


def test_harmony_without_memory_is_unchanged():
    engine_a, engine_b = HarmonyEngine(), HarmonyEngine(learned=LearnedHarmony())
    evidence = np.zeros(12)
    evidence[[7, 11, 2]] = 0.5
    key = Key(0, False)
    for engine in (engine_a, engine_b):
        engine.current = Chord(0, "maj", 1)
    a = engine_a.decide(evidence, key, 0.7)
    b = engine_b.decide(evidence, key, 0.7)
    assert a is not None and b is not None and a.chord == b.chord and a.score == pytest.approx(b.score)


# ----------------------------------------------------------- commande d'étude
def test_learn_study_command(tmp_path, capsys):
    from orchestre_ia.app.application import run_learning_study
    from orchestre_ia.core.paths import learning_dir
    from orchestre_ia.learning.listening import ListeningInfo, save_info

    session = tmp_path / "2026-11-08_10-00_louange"
    session.mkdir()
    sf.write(session / "partie_001.wav", render_progression(G_MAJOR_SONG, repeats=3, sr=22050), 22050)
    save_info(session, ListeningInfo(label="louange", device="test", started_at="2026-11-08T10:00:00", ended_at="x"))

    assert run_learning_study(str(session), force=False) == 0
    out = capsys.readouterr().out
    assert "Sol majeur" in out and "Ce que l'orchestre a appris" in out
    info = load_info(session)
    assert info is not None and info.studied
    assert load_learned_harmony(learning_dir() / "memoire.sqlite") is not None

    assert run_learning_study(str(session), force=False) == 0
    assert "Déjà étudiée" in capsys.readouterr().out


def test_learn_study_waits_for_running_session(tmp_path, capsys):
    from orchestre_ia.app.application import run_learning_study
    from orchestre_ia.learning.listening import ListeningInfo, save_info

    session = tmp_path / "en_cours"
    session.mkdir()
    sf.write(session / "partie_001.wav", np.zeros(22050, dtype=np.float32), 22050)
    save_info(session, ListeningInfo(label="louange", device="test", started_at=time.strftime("%Y-%m-%dT%H:%M:%S")))
    assert run_learning_study(str(session), force=False) == 0
    assert "Écoute en cours" in capsys.readouterr().out


# ------------------------------------------------------- tonalité et évaluation
def test_piece_key_reads_chords_like_a_musician():
    flat = np.ones((12, 20))
    assert study.piece_key(flat, np.array([9 + 12, 7] * 10)) == Key(9, True)  # Lam-Sol : i-bVII en La mineur
    assert study.piece_key(flat, np.array([2, 9, 7, 2] * 5)) == Key(2, False)  # Ré La Sol Ré
    assert study.piece_key(flat, np.array([4 + 12, 0, 7, 2] * 5)) == Key(7, False)  # Mim Do Sol Ré


def test_learned_habits_improve_next_chord_guess():
    from orchestre_ia.learning.evaluation import evaluate_next_chord

    # une équipe qui fait toujours I -> bVII -> IV -> I : les règles génériques ne l'attendent pas
    runs = [("0", 4.0), ("10", 4.0), ("5", 4.0)] * 20
    few = [study.Piece(0, 60, Key(t, False), 120, list(runs), []) for t in (0, 2, 7, 9)]
    many = [study.Piece(0, 60, Key(t, False), 120, list(runs), []) for t in range(12)]
    early, trained = evaluate_next_chord(few), evaluate_next_chord(many)
    assert early is not None and trained is not None and trained.changes == 12 * 59
    # peu d'exemples : la mémoire ne pèse qu'en partie ; beaucoup : elle s'impose
    assert early.generic_top1 <= early.learned_top1 < trained.learned_top1
    assert trained.learned_top1 > 0.9 > trained.generic_top1


def test_predict_next_does_not_disturb_current_chord():
    engine = HarmonyEngine()
    engine.current = Chord(7, "maj", 5)
    guesses = engine.predict_next(Key(0, False), Chord(0, "maj"))
    assert len(guesses) == 3 and all(not (g.root == 0 and g.quality == "maj") for g in guesses)
    assert engine.current == Chord(7, "maj", 5)
