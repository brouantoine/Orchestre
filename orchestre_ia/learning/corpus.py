"""Corpus de grilles d'accords : habitudes apprises sur des centaines de milliers de chants.

Source : Chordonomicon (Kantarelis et al., 2024, arXiv 2410.22046), licence MIT,
environ 680 000 grilles d'accords avec sections et genres Spotify. Aucun son :
seules les suites d'accords sont lues, comme pour les séances écoutées.

Chaque chant est ramené à sa tonalité (accords relatifs « IV », « vi », « bVII »…)
puis compté dans un groupe : « louange » (worship, christian, gospel, ccm, praise),
« afro » (afrobeats, naija, highlife…), sinon le genre principal du jeu de données.
Les compteurs vont dans `corpus.sqlite`, séparé de la mémoire de l'équipe
(`memoire.sqlite`) : le corpus sert d'a priori, les habitudes réellement entendues
l'emportent dès qu'elles sont assez nombreuses (voir `LearnedHarmony.prior`).

Un chant sur vingt (selon son identifiant) est tenu à part pendant l'import pour
mesurer, sans tricher, la part d'accords suivants devinés.
"""

from __future__ import annotations

import csv
import logging
import re
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from orchestre_ia.analysis.theory import Key
from orchestre_ia.learning.memory import LearnedHarmony, MusicMemory, count_habits, rel_token
from orchestre_ia.learning.study import FUNCTION, Piece, key_of

log = logging.getLogger(__name__)

DATASET_URL = "https://huggingface.co/datasets/ailsntua/Chordonomicon/resolve/main/chordonomicon_v2.csv"
DATASET_FILE = "chordonomicon_v2.csv"
CORPUS_FILE = "corpus.sqlite"
SOURCE_PREFIX = "chordonomicon:"

LOUANGE = "louange"
AFRO = "afro"
OTHER = "autre"
LOUANGE_WORDS = ("worship", "christian", "gospel", "ccm", "praise")
AFRO_WORDS = (
    "afro", "naija", "nigerian", "african", "congo", "highlife", "makossa", "coupe-decale",
    "zouk", "kompa", "haitian", "cameroon", "ivoir", "ivory",
)

HOLDOUT_EVERY = 20  # un chant sur 20 tenu à part pour la mesure
EVAL_SONGS_PER_GROUP = 400  # mesure bornée : environ 20 s par groupe
MIN_CHORDS = 4  # grilles plus courtes ignorées (fragments)

LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SECTION = re.compile(r"<[^>]*>")
_QUOTED = re.compile(r"'([^']+)'")


@lru_cache(maxsize=4096)
def parse_chord(symbol: str) -> tuple[int, bool] | None:
    """Accord du jeu de données -> (fondamentale 0-11, mineur), ou None s'il n'a pas de tierce nette.

    Notation : 's' = dièse, 'b' = bémol ('Fs7', 'Bbmaj7', 'Csmin'), basse après '/'.
    'Csus4' est un Do (et non un Do# « us4 »). Accords de puissance (no3d), diminués
    et augmentés : None, comme le « pas d'accord » de l'étude des séances.
    """
    head = symbol.split("/", 1)[0]
    if not head or head[0] not in LETTERS:
        return None
    root = LETTERS[head[0]]
    rest = head[1:]
    if rest.startswith("s") and not rest.startswith("sus"):
        root, rest = root + 1, rest[1:]
    elif rest.startswith("b"):
        root, rest = root - 1, rest[1:]
    if rest.startswith(("no3d", "dim", "aug")):
        return None
    return root % 12, rest.startswith("min")


def parse_progression(text: str) -> list[list[tuple[int, bool]]]:
    """Grille complète -> segments d'accords consécutifs (coupés aux accords sans tierce nette).

    Les repères de section (<verse_1>, <chorus_2>…) sont ignorés : le passage du couplet
    au refrain est un enchaînement comme un autre.
    """
    segments: list[list[tuple[int, bool]]] = [[]]
    for symbol in _SECTION.sub(" ", text).split():
        chord = parse_chord(symbol)
        if chord is None:
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(chord)
    return [s for s in segments if s]


def chord_index(chord: tuple[int, bool]) -> int:
    root, minor = chord
    return root + (12 if minor else 0)


def progression_key(chords: list[tuple[int, bool]]) -> Key:
    """Tonalité d'après le rôle des accords (même table que l'étude des séances), sans notes chantées."""
    hist = np.bincount([chord_index(c) for c in chords], minlength=24).astype(float)
    return key_of(int(np.argmax(FUNCTION @ (hist / hist.sum()))))


def song_pieces(text: str) -> list[Piece]:
    """Un chant -> un `Piece` par segment, tous dans la tonalité du chant entier.

    Le nombre de temps est inconnu : chaque accord écrit compte pour un.
    """
    segments = parse_progression(text)
    chords = [c for s in segments for c in s]
    if len(chords) < MIN_CHORDS:
        return []
    key = progression_key(chords)
    pieces = []
    for segment in segments:
        runs: list[tuple[str, float]] = []
        for root, minor in segment:
            token = rel_token(root - key.tonic, minor)
            if runs and runs[-1][0] == token:
                runs[-1] = (token, runs[-1][1] + 1.0)
            else:
                runs.append((token, 1.0))
        pieces.append(Piece(0.0, 0.0, key, 0.0, runs, []))
    return pieces


def genre_group(main_genre: str, genres: str) -> str:
    """Groupe d'un chant d'après son genre principal et les genres Spotify de l'artiste."""
    tags = _QUOTED.findall(genres or "")
    if any(word in tag for tag in tags for word in LOUANGE_WORDS):
        return LOUANGE
    if any(word in tag for tag in tags for word in AFRO_WORDS):
        return AFRO
    return (main_genre or "").strip() or OTHER


@dataclass
class GroupCounts:
    songs: int = 0
    transitions: dict[tuple[int, str, str], int] = field(default_factory=lambda: defaultdict(int))
    usage: dict[tuple[int, str], float] = field(default_factory=lambda: defaultdict(float))

    def add(self, pieces: list[Piece]) -> None:
        transitions, usage = count_habits(pieces)
        for k, n in transitions.items():
            self.transitions[k] += n
        for k, beats in usage.items():
            self.usage[k] += beats
        self.songs += 1

    def learned(self) -> LearnedHarmony:
        return LearnedHarmony(
            transitions={(bool(m), a, b): n for (m, a, b), n in self.transitions.items()},
            usage={(bool(m), t): beats for (m, t), beats in self.usage.items()},
        )


def merged(groups: list[GroupCounts]) -> LearnedHarmony:
    total = GroupCounts()
    for g in groups:
        for k, n in g.transitions.items():
            total.transitions[k] += n
        for k, beats in g.usage.items():
            total.usage[k] += beats
    return total.learned()


@dataclass
class CorpusImport:
    """Résultat d'une lecture du corpus : compteurs d'entraînement et chants tenus à part."""

    train: dict[str, GroupCounts] = field(default_factory=dict)
    held_out: dict[str, list[list[Piece]]] = field(default_factory=dict)  # groupe -> chants -> segments
    held_out_counts: dict[str, GroupCounts] = field(default_factory=dict)
    rows: int = 0
    skipped: int = 0

    def full_counts(self) -> dict[str, GroupCounts]:
        """Entraînement + chants tenus à part : ce qui est finalement rangé dans le corpus."""
        result: dict[str, GroupCounts] = {}
        for name in set(self.train) | set(self.held_out_counts):
            g = GroupCounts()
            for part in (self.train.get(name), self.held_out_counts.get(name)):
                if part is None:
                    continue
                g.songs += part.songs
                for k, n in part.transitions.items():
                    g.transitions[k] += n
                for k, beats in part.usage.items():
                    g.usage[k] += beats
            result[name] = g
        return result


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(1 << 26)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        yield from csv.DictReader(f)


def read_corpus(
    path: Path,
    limit: int | None = None,
    progress: Callable[[int], None] | None = None,
) -> CorpusImport:
    """Lit le CSV et compte les habitudes par groupe ; un chant sur `HOLDOUT_EVERY` est tenu à part."""
    result = CorpusImport()
    for row in iter_rows(path):
        result.rows += 1
        if progress and result.rows % 50_000 == 0:
            progress(result.rows)
        pieces = song_pieces(row.get("chords") or "")
        if not pieces:
            result.skipped += 1
        else:
            group = genre_group(row.get("main_genre") or "", row.get("genres") or "")
            song_id = row.get("id") or str(result.rows)
            held = song_id.isdigit() and int(song_id) % HOLDOUT_EVERY == 0
            if held:
                result.held_out_counts.setdefault(group, GroupCounts()).add(pieces)
                songs = result.held_out.setdefault(group, [])
                if len(songs) < EVAL_SONGS_PER_GROUP:
                    songs.append(pieces)
            else:
                result.train.setdefault(group, GroupCounts()).add(pieces)
        if limit is not None and result.rows >= limit:
            break
    return result


def store_corpus(memory: MusicMemory, counts: dict[str, GroupCounts]) -> None:
    """Remplace le contenu Chordonomicon du corpus (un enregistrement par groupe)."""
    for name, g in sorted(counts.items()):
        memory.store_counts(
            f"{SOURCE_PREFIX}{name}", f"{name} ({g.songs} chants)", dict(g.transitions), dict(g.usage)
        )


def corpus_path() -> Path:
    from orchestre_ia.core.paths import learning_dir

    return learning_dir() / CORPUS_FILE


def dataset_path() -> Path:
    from orchestre_ia.core.paths import learning_dir

    return learning_dir() / "jeux" / DATASET_FILE


def download_dataset(
    dest: Path,
    url: str = DATASET_URL,
    progress: Callable[[int, int], None] | None = None,
    attempts: int = 30,
) -> Path:
    """Télécharge le CSV (≈ 264 Mo) avec reprise après coupure (en-tête Range)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        done = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if done and response.status != 206:  # le serveur ignore la reprise : on repart de zéro
                    done = 0
                    part.unlink(missing_ok=True)
                length = response.headers.get("Content-Length")
                total = done + int(length) if length else 0
                with part.open("ab") as f:
                    while chunk := response.read(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            part.replace(dest)
            return dest
        except (OSError, TimeoutError) as exc:
            log.warning("Téléchargement interrompu (essai %d/%d) : %s", attempt, attempts, exc)
            time.sleep(min(30, 2 * attempt))
    raise OSError(f"téléchargement impossible après {attempts} essais : {url}")


def load_corpus_prior(path: Path | None = None) -> LearnedHarmony | None:
    """Habitudes du corpus (tous groupes), ou None si aucun corpus n'a été importé."""
    path = path or corpus_path()
    if not path.exists():
        return None
    try:
        with MusicMemory(path) as memory:
            learned = memory.learned()
    except Exception:
        log.exception("Lecture du corpus impossible")
        return None
    return None if learned.is_empty else learned
