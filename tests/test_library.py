"""Étude d'une bibliothèque de chants (dossier de fichiers audio)."""

import shutil

import numpy as np
import pytest
import soundfile as sf

from orchestre_ia.analysis.theory import Key
from orchestre_ia.learning import study
from orchestre_ia.learning.evaluation import evaluate_folds, pieces_by_source
from orchestre_ia.learning.library import find_songs, fingerprint, load_audio, study_library
from orchestre_ia.learning.memory import MusicMemory
from tests.audio_files import write_compressed
from tests.music_fixtures import render_progression

SR = 22050
G_SONG = [(7, False), (2, False), (4, True), (0, False)]  # Sol Ré Mim Do : I V vi IV
F_SONG = [(5, False), (10, False), (7, True), (0, False)]  # Fa Sib Solm Do : I IV ii V


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    folder = tmp_path_factory.mktemp("chants")
    (folder / "louange").mkdir()
    sf.write(folder / "chant sol.wav", render_progression(G_SONG, bpm=80, repeats=3, sr=SR), SR)
    write_compressed(folder / "louange" / "chant fa.m4a", render_progression(F_SONG, bpm=90, repeats=3, sr=SR), SR)
    shutil.copy(folder / "chant sol.wav", folder / "louange" / "copie du chant sol.wav")  # doublon
    (folder / "abime.mp3").write_bytes(b"ce n'est pas du son" * 100)
    (folder / "pochette.jpg").write_bytes(b"image")
    return folder


def test_find_songs_is_recursive_and_ignores_other_files(library):
    names = [p.name for p in find_songs(library)]
    assert names == ["abime.mp3", "chant sol.wav", "chant fa.m4a", "copie du chant sol.wav"]


def test_fingerprint_follows_content_not_name(library):
    assert fingerprint(library / "chant sol.wav") == fingerprint(library / "louange" / "copie du chant sol.wav")
    assert fingerprint(library / "chant sol.wav") != fingerprint(library / "louange" / "chant fa.m4a")


def test_load_audio_reads_compressed_files(library):
    y = load_audio(library / "louange" / "chant fa.m4a")
    expected = len(render_progression(F_SONG, bpm=90, repeats=3, sr=SR))
    assert abs(len(y) - expected) < SR // 2 and 0.5 < np.max(np.abs(y)) < 1.0


def test_load_audio_stops_at_max_duration(library):
    assert len(load_audio(library / "chant sol.wav", max_s=5.0)) == 5 * SR


def test_study_library_learns_resumes_and_skips(library, tmp_path):
    seen = []
    with MusicMemory(tmp_path / "memoire.sqlite") as memory:
        report = study_library(library, memory, workers=2, on_song=lambda i, n, p, o: seen.append((p.name, o)))
        assert report.found == 4 and report.studied == 2 and report.duplicates == 1
        assert [name for name, _ in report.errors] == ["abime.mp3"]
        keys = {name: o.result.pieces[0].key for name, o in seen if o.result is not None}
        assert keys == {"chant sol.wav": Key(7, False), "chant fa.m4a": Key(5, False)}
        assert memory.stats()["recordings"] == 2

        again = study_library(library, memory, workers=1)
        assert again.studied == 0 and again.skipped == 2 and again.duplicates == 1

        groups = pieces_by_source(memory)
        assert len(groups) == 2 and all(p.runs for pieces in groups.values() for p in pieces)


def test_evaluate_folds_rewards_consistent_habits():
    runs = [("0", 4.0), ("10", 4.0), ("5", 4.0)] * 20  # I bVII IV en boucle
    groups = {f"chant:{i}": [study.Piece(0, 60, Key(i % 12, False), 120, list(runs), [])] for i in range(10)}
    score = evaluate_folds(groups)
    assert score is not None and score.changes == 10 * 59
    assert score.learned_top1 > 0.9 > score.generic_top1


def test_evaluate_folds_needs_two_sources():
    assert evaluate_folds({"chant:1": []}) is None


def test_learn_library_command(library, capsys):
    from orchestre_ia.app.application import run_learning_library

    assert run_learning_library(str(library), workers=1, force=False) == 0
    out = capsys.readouterr().out
    assert "Sol majeur" in out and "Fa majeur" in out and "doublons : 1" in out
    assert "Ce que l'orchestre a appris" in out


def test_learn_library_command_without_songs(tmp_path, capsys):
    from orchestre_ia.app.application import run_learning_library

    assert run_learning_library(str(tmp_path), workers=1, force=False) == 1
    assert "Aucun chant" in capsys.readouterr().out
