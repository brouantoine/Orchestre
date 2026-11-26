"""Mesure de l'apprentissage : l'orchestre devine-t-il l'accord suivant que les musiciens jouent ?

Pour chaque changement d'accord d'un morceau étudié, on demande au moteur harmonique
(sans rien lui faire entendre) les 3 accords qu'il attend après l'accord en cours,
une fois avec les seules règles génériques, une fois avec les habitudes apprises.
Les habitudes utilisées pour juger un morceau ne viennent jamais de ce morceau :
- `evaluate_next_chord` : un morceau à part (une séance) ;
- `evaluate_folds` : un chant sur cinq mis à part, à tour de rôle (bibliothèque entière).
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.learning.memory import LearnedHarmony, MusicMemory, learned_from
from orchestre_ia.learning.study import Piece


@dataclass(frozen=True)
class PredictionScore:
    changes: int
    generic_top1: float
    generic_top3: float
    learned_top1: float
    learned_top3: float


def token_chord(token: str, key: Key) -> Chord:
    minor = token.endswith("m")
    return Chord((key.tonic + int(token.rstrip("m"))) % 12, "min" if minor else "maj")


def _same(a: Chord, b: Chord) -> bool:
    return a.root == b.root and a.triad_quality == b.triad_quality


class _Tally:
    def __init__(self) -> None:
        self.generic = HarmonyEngine()
        self.changes = 0
        self.hits = {"g1": 0, "g3": 0, "l1": 0, "l3": 0}

    def judge(self, pieces: list[Piece], learned: LearnedHarmony) -> None:
        engine = HarmonyEngine(learned=learned)
        for piece in pieces:
            for (a, _), (b, _) in zip(piece.runs, piece.runs[1:]):
                if a == b:
                    continue
                current, actual = token_chord(a, piece.key), token_chord(b, piece.key)
                self.changes += 1
                for name, candidate in (("g", self.generic), ("l", engine)):
                    guesses = candidate.predict_next(piece.key, current, top=3)
                    self.hits[f"{name}1"] += _same(guesses[0], actual)
                    self.hits[f"{name}3"] += any(_same(g, actual) for g in guesses)

    def score(self) -> PredictionScore | None:
        if not self.changes:
            return None
        n = self.changes
        h = self.hits
        return PredictionScore(n, h["g1"] / n, h["g3"] / n, h["l1"] / n, h["l3"] / n)


def evaluate_pieces(pieces: list[Piece], learned: LearnedHarmony) -> PredictionScore | None:
    """Morceaux jugés avec des habitudes apprises ailleurs (corpus : chants tenus à part)."""
    tally = _Tally()
    tally.judge(pieces, learned)
    return tally.score()


def evaluate_next_chord(pieces: list[Piece], base: LearnedHarmony | None = None) -> PredictionScore | None:
    """Chaque morceau jugé avec les habitudes des autres morceaux (+ `base`)."""
    tally = _Tally()
    for i, piece in enumerate(pieces):
        tally.judge([piece], learned_from(pieces[:i] + pieces[i + 1 :], base))
    return tally.score()


def evaluate_folds(groups: dict[str, list[Piece]], folds: int = 5) -> PredictionScore | None:
    """Validation croisée par source (chant ou séance) : chaque groupe est jugé sans lui-même."""
    sources = sorted(groups)
    folds = min(folds, len(sources))
    if folds < 2:
        return None
    tally = _Tally()
    for f in range(folds):
        test = [p for i, s in enumerate(sources) if i % folds == f for p in groups[s]]
        train = [p for i, s in enumerate(sources) if i % folds != f for p in groups[s]]
        tally.judge(test, learned_from(train))
    return tally.score()


def pieces_by_source(memory: MusicMemory) -> dict[str, list[Piece]]:
    groups: dict[str, list[Piece]] = {}
    for source, tonic, minor, tempo, start, end, chords in memory.piece_rows():
        runs = [(item.rsplit(":", 1)[0], float(item.rsplit(":", 1)[1])) for item in chords.split()]
        groups.setdefault(source, []).append(Piece(start, end, Key(tonic, bool(minor)), tempo, runs, []))
    return groups
