"""Mémoire musicale locale (SQLite) : ce que l'orchestre a appris des séances écoutées.

Les accords sont mémorisés *relativement à la tonalité* (« IV », « vi », « bVII »…),
ce qui rend la leçon valable dans toutes les tonalités. Chaque séance garde ses
propres compteurs : réétudier une séance remplace ses anciens chiffres au lieu de
les additionner, et l'oubli d'une séance est une simple suppression.

Le moteur harmonique lit cette mémoire via `LearnedHarmony` (enchaînements
préférés, accords d'emprunt devenus familiers).
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from orchestre_ia.analysis.theory import Chord, Key
    from orchestre_ia.learning.study import Piece, StudyResult

log = logging.getLogger(__name__)

MEMORY_FILE = "memoire.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY,
    source TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    studied_at TEXT NOT NULL,
    duration_s REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pieces (
    id INTEGER PRIMARY KEY,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    key_tonic INTEGER NOT NULL,
    key_minor INTEGER NOT NULL,
    tempo REAL NOT NULL,
    chords TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    minor INTEGER NOT NULL,
    from_rel TEXT NOT NULL,
    to_rel TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (recording_id, minor, from_rel, to_rel)
);
CREATE TABLE IF NOT EXISTS usage (
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    minor INTEGER NOT NULL,
    rel TEXT NOT NULL,
    beats REAL NOT NULL,
    PRIMARY KEY (recording_id, minor, rel)
);
"""

ROMAN = ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII")


def rel_token(interval: int, minor_chord: bool) -> str:
    """Accord relatif à la tonique : '7' = V majeur, '9m' = vi mineur."""
    return f"{interval % 12}{'m' if minor_chord else ''}"


def chord_token(chord: Chord, key: Key) -> str:
    return rel_token(chord.root - key.tonic, chord.triad_quality == "min")


def roman(token: str) -> str:
    """'9m' -> 'vi', '10' -> 'bVII' (chiffrage chromatique depuis la tonique)."""
    minor = token.endswith("m")
    numeral = ROMAN[int(token.rstrip("m")) % 12]
    return numeral.lower() if minor else numeral


@dataclass
class LearnedHarmony:
    """Statistiques apprises, prêtes pour le moteur harmonique (lecture seule, sans verrou)."""

    transitions: dict[tuple[bool, str, str], int] = field(default_factory=dict)
    usage: dict[tuple[bool, str], float] = field(default_factory=dict)
    # au-delà, la mémoire remplace les règles génériques. Mesuré le 2026-11-08 sur 3 séances :
    # à 200, une séance inédite était moins bien devinée (26 % contre 36 %) ; à 500, jamais pire.
    full_trust_transitions: int = 500
    transition_weight: float = 0.25
    usage_weight: float = 0.35
    smoothing: float = 2.0

    def __post_init__(self) -> None:
        self._from_totals: dict[tuple[bool, str], int] = defaultdict(int)
        self._mode_transitions: dict[bool, int] = defaultdict(int)
        for (minor, src, _dst), n in self.transitions.items():
            self._from_totals[(minor, src)] += n
            self._mode_transitions[minor] += n
        self._mode_beats: dict[bool, float] = defaultdict(float)
        for (minor, _rel), beats in self.usage.items():
            self._mode_beats[minor] += beats

    @property
    def is_empty(self) -> bool:
        return not self.transitions and not self.usage

    def reliability(self, minor: bool) -> float:
        return min(1.0, self._mode_transitions.get(minor, 0) / self.full_trust_transitions)

    def usage_share(self, minor: bool, token: str) -> float:
        total = self._mode_beats.get(minor, 0.0)
        return self.usage.get((minor, token), 0.0) / total if total > 0 else 0.0

    def transition_probability(self, minor: bool, src: str, dst: str) -> float:
        """P(dst | src), lissée vers la fréquence d'usage de dst."""
        total = self._from_totals.get((minor, src), 0)
        prior = self.usage_share(minor, dst)
        return (self.transitions.get((minor, src, dst), 0) + self.smoothing * prior) / (total + self.smoothing)

    def usage_prior(self, key: Key, chord: Chord) -> float:
        return self.usage_weight * self.usage_share(key.minor, chord_token(chord, key))

    def transition_bonus(self, key: Key, current: Chord, chord: Chord) -> float:
        p = self.transition_probability(key.minor, chord_token(current, key), chord_token(chord, key))
        return self.transition_weight * p


def count_habits(pieces: Iterable[Piece]) -> tuple[dict[tuple[int, str, str], int], dict[tuple[int, str], float]]:
    """Compteurs d'enchaînements (changements d'accord) et de temps joués par accord relatif."""
    transitions: dict[tuple[int, str, str], int] = defaultdict(int)
    usage: dict[tuple[int, str], float] = defaultdict(float)
    for piece in pieces:
        minor = int(piece.key.minor)
        for token, beats in piece.runs:
            usage[(minor, token)] += beats
        for (a, _), (b, _) in zip(piece.runs, piece.runs[1:]):
            if a != b:
                transitions[(minor, a, b)] += 1
    return transitions, usage


def learned_from(pieces: Iterable[Piece], base: LearnedHarmony | None = None) -> LearnedHarmony:
    """Habitudes tirées de `pieces`, ajoutées à une mémoire existante éventuelle."""
    transitions, usage = count_habits(pieces)
    merged_t: dict[tuple[bool, str, str], int] = defaultdict(int, dict(base.transitions) if base else {})
    merged_u: dict[tuple[bool, str], float] = defaultdict(float, dict(base.usage) if base else {})
    for (m, a, b), n in transitions.items():
        merged_t[(bool(m), a, b)] += n
    for (m, t), beats in usage.items():
        merged_u[(bool(m), t)] += beats
    return LearnedHarmony(transitions=dict(merged_t), usage=dict(merged_u))


class MusicMemory:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> MusicMemory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def is_studied(self, source: str) -> bool:
        row = self._db.execute("SELECT 1 FROM recordings WHERE source = ?", (source,)).fetchone()
        return row is not None

    def store(self, source: str, label: str, result: StudyResult) -> int:
        """Enregistre (ou remplace) les leçons d'une séance. Retourne son identifiant."""
        with self._db:
            self._db.execute("DELETE FROM recordings WHERE source = ?", (source,))
            cur = self._db.execute(
                "INSERT INTO recordings (source, label, studied_at, duration_s) VALUES (?, ?, ?, ?)",
                (source, label, datetime.now().isoformat(timespec="seconds"), result.duration_s),
            )
            rid = int(cur.lastrowid or 0)
            transitions, usage = count_habits(result.pieces)
            for piece in result.pieces:
                minor = int(piece.key.minor)
                self._db.execute(
                    "INSERT INTO pieces (recording_id, start_s, end_s, key_tonic, key_minor, tempo, chords)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rid, piece.start_s, piece.end_s, piece.key.tonic, minor, piece.tempo,
                     " ".join(f"{t}:{b:g}" for t, b in piece.runs)),
                )
            self._db.executemany(
                "INSERT INTO transitions (recording_id, minor, from_rel, to_rel, count) VALUES (?, ?, ?, ?, ?)",
                [(rid, m, a, b, n) for (m, a, b), n in transitions.items()],
            )
            self._db.executemany(
                "INSERT INTO usage (recording_id, minor, rel, beats) VALUES (?, ?, ?, ?)",
                [(rid, m, t, beats) for (m, t), beats in usage.items()],
            )
        return rid

    def piece_rows(self) -> list[tuple[str, int, int, float, float, float, str]]:
        """(source, tonique, mineur, tempo, début, fin, accords) de tous les morceaux étudiés."""
        return self._db.execute(
            "SELECT r.source, p.key_tonic, p.key_minor, p.tempo, p.start_s, p.end_s, p.chords"
            " FROM pieces p JOIN recordings r ON r.id = p.recording_id ORDER BY p.id"
        ).fetchall()

    def forget(self, source: str) -> bool:
        with self._db:
            cur = self._db.execute("DELETE FROM recordings WHERE source = ?", (source,))
        return cur.rowcount > 0

    def learned(self, exclude: str | None = None) -> LearnedHarmony:
        """Habitudes de toutes les séances (sauf `exclude`, pour évaluer une séance à part)."""
        where = "WHERE recording_id NOT IN (SELECT id FROM recordings WHERE source = ?)" if exclude else ""
        params = (exclude,) if exclude else ()
        transitions = {
            (bool(m), a, b): int(n)
            for m, a, b, n in self._db.execute(
                f"SELECT minor, from_rel, to_rel, SUM(count) FROM transitions {where} GROUP BY minor, from_rel, to_rel",
                params,
            )
        }
        usage = {
            (bool(m), t): float(beats)
            for m, t, beats in self._db.execute(
                f"SELECT minor, rel, SUM(beats) FROM usage {where} GROUP BY minor, rel", params
            )
        }
        return LearnedHarmony(transitions=transitions, usage=usage)

    def stats(self) -> dict[str, float]:
        rec, dur = self._db.execute("SELECT COUNT(*), COALESCE(SUM(duration_s), 0) FROM recordings").fetchone()
        pieces, tempo = self._db.execute("SELECT COUNT(*), AVG(tempo) FROM pieces").fetchone()
        return {"recordings": rec, "hours": dur / 3600, "pieces": pieces, "avg_tempo": tempo or 0.0}

    def summary_lines(self, top: int = 6) -> list[str]:
        """Résumé lisible par un musicien de ce qui a été appris."""
        learned = self.learned()
        stats = self.stats()
        lines = [
            f"{stats['recordings']} séance(s), {stats['hours']:.1f} h écoutées, "
            f"{stats['pieces']} morceau(x) analysé(s), tempo moyen {stats['avg_tempo']:.0f} BPM"
        ]
        for minor, mode in ((False, "majeur"), (True, "mineur")):
            shares = sorted(
                ((t, learned.usage_share(minor, t)) for (m, t) in learned.usage if m == minor),
                key=lambda x: x[1],
                reverse=True,
            )
            if not shares:
                continue
            lines.append(f"Morceaux en {mode} — accords les plus joués : "
                         + ", ".join(f"{roman(t)} {s * 100:.0f} %" for t, s in shares[:top]))
            moves = sorted(
                ((a, b, n) for (m, a, b), n in learned.transitions.items() if m == minor),
                key=lambda x: x[2],
                reverse=True,
            )
            if moves:
                lines.append(f"Morceaux en {mode} — enchaînements favoris : "
                             + ", ".join(f"{roman(a)}→{roman(b)} ({n})" for a, b, n in moves[:top]))
            lines.append(f"Confiance dans ces habitudes ({mode}) : {learned.reliability(minor) * 100:.0f} %")
        return lines


def memory_path() -> Path:
    from orchestre_ia.core.paths import learning_dir

    return learning_dir() / MEMORY_FILE


def load_learned_harmony(path: Path | None = None) -> LearnedHarmony | None:
    """Mémoire apprise, ou None si rien n'a encore été étudié. Ne lève jamais d'exception."""
    path = path or memory_path()
    if not path.exists():
        return None
    try:
        with MusicMemory(path) as memory:
            learned = memory.learned()
    except Exception:
        log.exception("Lecture de la mémoire musicale impossible")
        return None
    return None if learned.is_empty else learned
