"""Corpus de grilles d'accords (Chordonomicon) : lecture, groupes, a priori de la mémoire."""

import csv

import pytest

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.learning import corpus
from orchestre_ia.learning.evaluation import evaluate_pieces
from orchestre_ia.learning.memory import LearnedHarmony, MusicMemory, load_learned_harmony

FIELDS = ["id", "chords", "release_date", "genres", "decade", "rock_genre", "artist_id", "main_genre",
          "spotify_song_id", "spotify_artist_id"]

# Do majeur : I–V–vi–IV, puis un refrain qui ajoute bVII (emprunt fréquent en louange)
WORSHIP = "<verse_1> C G Amin F C G Amin F <chorus_1> F G C Bb F G C Bb C"
POP = "<intro_1> G D Emin C <verse_1> G D Emin C G D Emin C"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for song_id, chords, genres, main in rows:
            writer.writerow({"id": song_id, "chords": chords, "genres": genres, "main_genre": main})
    return path


@pytest.mark.parametrize(
    "symbol, expected",
    [
        ("C", (0, False)),
        ("Amin", (9, True)),
        ("Fs7", (6, False)),
        ("Csmin7", (1, True)),
        ("Bbmaj7", (10, False)),
        ("Csus4", (0, False)),  # Do suspendu, pas Do#
        ("Cssus2", (1, False)),
        ("A/Cs", (9, False)),  # la basse n'est pas la fondamentale
        ("Eminmaj7", (4, True)),
        ("Fsno3d", None),  # accord de puissance : ni majeur ni mineur
        ("Bdim7", None),
        ("Caug", None),
        ("<verse_1>", None),
    ],
)
def test_parse_chord(symbol, expected):
    assert corpus.parse_chord(symbol) == expected


def test_progression_is_split_on_chords_without_third():
    segments = corpus.parse_progression("<intro_1> C G <verse_1> Fsno3d Amin F")
    assert segments == [[(0, False), (7, False)], [(9, True), (5, False)]]


def test_song_pieces_relative_to_key():
    pieces = corpus.song_pieces(WORSHIP)
    assert pieces[0].key == Key(0, False)
    tokens = [t for p in pieces for t, _ in p.runs]
    assert tokens[:4] == ["0", "7", "9m", "5"]  # I V vi IV
    assert "10" in tokens  # bVII
    transposed = corpus.song_pieces("D A Bmin G D A Bmin G")
    assert transposed[0].key == Key(2, False)
    assert [t for t, _ in transposed[0].runs][:4] == ["0", "7", "9m", "5"]


def test_short_fragments_are_ignored():
    assert corpus.song_pieces("C G") == []


def test_genre_groups():
    assert corpus.genre_group("pop", "'ccm' 'worship'") == corpus.LOUANGE
    assert corpus.genre_group("", "'christian afrobeat'") == corpus.LOUANGE
    assert corpus.genre_group("pop", "'afropop' 'nigerian pop'") == corpus.AFRO
    assert corpus.genre_group("rock", "'classic rock'") == "rock"
    assert corpus.genre_group("", "") == corpus.OTHER


def test_read_corpus_holds_out_one_song_in_twenty(tmp_path):
    rows = [(i, WORSHIP if i % 2 else POP, "'worship'" if i % 2 else "'pop'", "pop") for i in range(1, 41)]
    rows.append((41, "C G", "", ""))  # trop court
    imported = corpus.read_corpus(write_csv(tmp_path / "c.csv", rows))
    assert imported.rows == 41 and imported.skipped == 1
    assert sum(len(v) for v in imported.held_out.values()) == 2  # identifiants 20 et 40
    assert sum(g.songs for g in imported.train.values()) == 38
    full = imported.full_counts()
    assert full[corpus.LOUANGE].songs == 20 and full["pop"].songs == 20


def test_store_and_load_corpus_as_prior(tmp_path):
    rows = [(i, WORSHIP, "'worship'", "pop") for i in range(1, 30)]
    imported = corpus.read_corpus(write_csv(tmp_path / "c.csv", rows))
    corpus_file = tmp_path / "corpus.sqlite"
    with MusicMemory(corpus_file) as memory:
        corpus.store_corpus(memory, imported.full_counts())
        corpus.store_corpus(memory, imported.full_counts())  # réimport : remplace
        assert memory.stats()["recordings"] == 1
    prior = corpus.load_corpus_prior(corpus_file)
    assert prior is not None and prior.reliability(False) > 0.8  # 29 chants ≈ 435 changements sur 500
    assert prior.transition_probability(False, "7", "9m") > 0.4  # V -> vi
    # Pas encore de mémoire d'équipe : le corpus seul sert d'a priori
    learned = load_learned_harmony(tmp_path / "absente.sqlite", corpus=corpus_file)
    assert learned is not None and learned.prior is not None
    assert learned.transition_probability(False, "7", "9m") == pytest.approx(
        prior.transition_probability(False, "7", "9m")
    )
    assert corpus.load_corpus_prior(tmp_path / "rien.sqlite") is None


def test_team_habits_override_the_corpus():
    prior = LearnedHarmony(transitions={(False, "7", "9m"): 1000, (False, "7", "0"): 10},
                           usage={(False, "9m"): 100.0, (False, "0"): 100.0, (False, "7"): 100.0})
    few = LearnedHarmony(transitions={(False, "7", "0"): 3}, usage={(False, "0"): 10.0}, prior=prior)
    many = LearnedHarmony(transitions={(False, "7", "0"): 300}, usage={(False, "0"): 400.0}, prior=prior)
    assert few.transition_probability(False, "7", "9m") > few.transition_probability(False, "7", "0")
    assert many.transition_probability(False, "7", "0") > many.transition_probability(False, "7", "9m")
    assert few.reliability(False) == 1.0  # le corpus suffit à remplacer les règles génériques
    engine = HarmonyEngine(learned=many)
    assert engine.predict_next(Key(0, False), Chord(7, "maj"))[0].root == 0


def test_without_prior_behaviour_is_unchanged():
    learned = LearnedHarmony(transitions={(False, "7", "0"): 4}, usage={(False, "0"): 8.0, (False, "7"): 8.0})
    assert learned.prior is None
    assert learned.transition_probability(False, "7", "0") == pytest.approx((4 + 2.0 * 0.5) / (4 + 2.0))
    assert learned.reliability(False) == pytest.approx(4 / 500)


def test_corpus_improves_next_chord_guess(tmp_path):
    """Grilles de louange avec bVII : le corpus les devine mieux que les règles génériques."""
    rows = [(i, WORSHIP, "'worship'", "") for i in range(1, 81)]
    imported = corpus.read_corpus(write_csv(tmp_path / "c.csv", rows))
    held = [p for song in imported.held_out[corpus.LOUANGE] for p in song]
    score = evaluate_pieces(held, corpus.merged(list(imported.train.values())))
    assert score is not None and score.changes > 0
    assert score.learned_top1 > score.generic_top1


def test_learn_corpus_command(tmp_path, capsys):
    try:
        from orchestre_ia.app.application import main
    except OSError as exc:  # PortAudio absent (Linux sans libportaudio2)
        pytest.skip(f"application non importable : {exc}")
    rows = [(i, WORSHIP, "'worship'", "") for i in range(1, 41)]
    assert main(["--learn-corpus", str(write_csv(tmp_path / "c.csv", rows))]) == 0
    out = capsys.readouterr().out
    assert "louange" in out and "avec le corpus" in out
    assert corpus.load_corpus_prior() is not None
