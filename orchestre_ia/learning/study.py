"""Étude hors ligne d'une séance écoutée (louange, répétition).

Pour chaque partie enregistrée :
1. séparation harmonique / percussive ;
2. temps forts (pulsation) sur la partie percussive, chroma (12 classes de hauteur)
   et chroma de basse sur la partie harmonique, moyennés par temps ;
3. sur toute la séance : accords par temps (24 accords + « pas d'accord »)
   lissés par Viterbi, tonalité locale lissée de même, puis seconde passe des
   accords qui avantage légèrement ceux de la tonalité (comme l'oreille d'un
   musicien : sur une prise de salle, la tierce est souvent noyée) ;
4. découpage en morceaux (changement de tonalité, longs passages sans accords :
   prière, prédication, applaudissements) ; les passages trop courts ou trop
   peu harmoniques sont ignorés.

Le résultat est une suite d'accords relatifs à la tonalité par morceau, que
`MusicMemory` transforme en habitudes (enchaînements, accords favoris).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from orchestre_ia.analysis.key import MAJOR_PROFILE, MINOR_PROFILE
from orchestre_ia.analysis.theory import Key, diatonic_chords, pc_name
from orchestre_ia.learning.memory import rel_token, roman

log = logging.getLogger(__name__)

SR = 22050
HOP = 512
BINS_PER_OCTAVE = 36
N_OCTAVES = 7
SKIP_START_S = 0.5  # déclic d'ouverture du micro

NO_CHORD = 24
CHORD_SWITCH_COST = 0.3
NO_CHORD_SCORE = 0.62
BASS_WEIGHT = 0.15
MAX_CHROMA_FLATNESS = 0.975  # bruit blanc ou grave : >= 0,98 ; louange prise au micro : 0,79-0,96
KEY_CHORD_BONUS = 0.06  # seconde passe : léger avantage aux accords de la tonalité locale
KEY_WINDOW_BEATS = 64
KEY_SWITCH_COST = 3.0
MIN_PIECE_S = 30.0
MIN_PIECE_CHORD_RATIO = 0.5
GAP_SPLIT_S = 10.0


def _chord_templates() -> np.ndarray:
    templates = np.zeros((24, 12))
    for root in range(12):
        for i, third in enumerate((4, 3)):  # 0-11 majeurs, 12-23 mineurs
            t = templates[root + 12 * i]
            t[root] = 1.0
            t[(root + third) % 12] = 1.0
            t[(root + 7) % 12] = 1.0
    return templates / np.linalg.norm(templates, axis=1, keepdims=True)


TEMPLATES = _chord_templates()


@dataclass
class BeatFeatures:
    """Descripteurs par temps, concaténés sur toute la séance."""

    times: np.ndarray = field(default_factory=lambda: np.zeros(0))  # début du temps (s)
    durations: np.ndarray = field(default_factory=lambda: np.zeros(0))  # durée du temps (s)
    chroma: np.ndarray = field(default_factory=lambda: np.zeros((12, 0)))
    bass: np.ndarray = field(default_factory=lambda: np.zeros((12, 0)))
    energy_db: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def extend(self, other: BeatFeatures, offset_s: float) -> None:
        self.times = np.concatenate([self.times, other.times + offset_s])
        self.durations = np.concatenate([self.durations, other.durations])
        self.chroma = np.concatenate([self.chroma, other.chroma], axis=1)
        self.bass = np.concatenate([self.bass, other.bass], axis=1)
        self.energy_db = np.concatenate([self.energy_db, other.energy_db])

    def __len__(self) -> int:
        return len(self.times)


@dataclass
class Piece:
    start_s: float
    end_s: float
    key: Key
    tempo: float
    runs: list[tuple[str, float]]  # (accord relatif, nombre de temps)
    chord_names: list[str]  # noms réels, dans l'ordre (consécutifs dédoublonnés)

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def typical_progression(self, n: int = 4) -> list[str]:
        """Enchaînement de `n` accords le plus répété dans le morceau (chiffrage romain)."""
        tokens = [t for t, _ in self.runs]
        if len(tokens) <= n:
            return [roman(t) for t in tokens]
        grams = Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
        best, _ = grams.most_common(1)[0]
        return [roman(t) for t in best]


@dataclass
class StudyResult:
    duration_s: float
    pieces: list[Piece]
    beats: int


# ---------------------------------------------------------------- descripteurs
def beat_features(y: np.ndarray, sr: int) -> BeatFeatures:
    """Descripteurs par temps d'un extrait mono (une partie de séance)."""
    import librosa

    y = np.asarray(y, dtype=np.float32)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    if len(y) < 4 * SR or float(np.max(np.abs(y))) < 1e-4:
        return BeatFeatures()
    y_h, y_p = librosa.effects.hpss(y)
    onset = librosa.onset.onset_strength(y=y_p, sr=SR, hop_length=HOP)
    _tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=SR, hop_length=HOP, units="frames")
    tuning = float(librosa.estimate_tuning(y=y_h, sr=SR, bins_per_octave=BINS_PER_OCTAVE))
    fmin = float(librosa.note_to_hz("C1"))
    cqt = np.abs(
        librosa.cqt(
            y_h, sr=SR, hop_length=HOP, fmin=fmin, n_bins=N_OCTAVES * BINS_PER_OCTAVE,
            bins_per_octave=BINS_PER_OCTAVE, tuning=tuning,
        )
    )
    chroma = librosa.feature.chroma_cqt(C=cqt, sr=SR, hop_length=HOP, fmin=fmin, bins_per_octave=BINS_PER_OCTAVE, norm=None)
    bass = librosa.feature.chroma_cqt(
        C=cqt[: 2 * BINS_PER_OCTAVE], sr=SR, hop_length=HOP, fmin=fmin, bins_per_octave=BINS_PER_OCTAVE, norm=None
    )
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    n_frames = min(chroma.shape[1], bass.shape[1], len(rms))

    beat_frames = np.asarray(beat_frames, dtype=int)
    beat_frames = beat_frames[(beat_frames > 0) & (beat_frames < n_frames)]
    if len(beat_frames) < 8:  # pas de pulsation claire : grille fixe d'une demi-seconde
        step = max(1, int(0.5 * SR / HOP))
        beat_frames = np.arange(step, n_frames, step)
    bounds = np.concatenate([[0], beat_frames, [n_frames]])
    bounds = np.unique(bounds)
    starts, ends = bounds[:-1], bounds[1:]

    def per_beat(feat: np.ndarray) -> np.ndarray:
        return np.stack([np.median(feat[:, a:b], axis=1) for a, b in zip(starts, ends)], axis=1)

    energy = np.array([np.sqrt(np.mean(rms[a:b] ** 2)) for a, b in zip(starts, ends)])
    times = librosa.frames_to_time(starts, sr=SR, hop_length=HOP)
    durations = (ends - starts) * HOP / SR
    return BeatFeatures(
        times=np.asarray(times, dtype=float),
        durations=np.asarray(durations, dtype=float),
        chroma=per_beat(chroma[:, :n_frames]),
        bass=per_beat(bass[:, :n_frames]),
        energy_db=20 * np.log10(energy + 1e-9),
    )


# ---------------------------------------------------------------- accords
def chord_scores(features: BeatFeatures) -> np.ndarray:
    """Score (25, n) de chaque accord par temps : cosinus chroma + bonus de basse."""
    n = len(features)
    chroma = features.chroma / (np.linalg.norm(features.chroma, axis=0, keepdims=True) + 1e-9)
    bass = features.bass / (np.max(features.bass, axis=0, keepdims=True) + 1e-9)
    scores = np.empty((25, n))
    scores[:24] = TEMPLATES @ chroma
    roots = np.arange(24) % 12
    scores[:24] += BASS_WEIGHT * bass[roots]
    scores[NO_CHORD] = NO_CHORD_SCORE
    # silence relatif (pauses, prière à voix basse) : pas d'accord
    if n:
        loud = np.percentile(features.energy_db, 90)
        quiet = features.energy_db < loud - 30
        scores[:24, quiet] = 0.0
        # bruit (souffle, applaudissements) : les 12 notes à égalité, pas d'accord
        scores[:24, chroma_flatness(features.chroma) > MAX_CHROMA_FLATNESS] = 0.0
    return scores


def chroma_flatness(chroma: np.ndarray) -> np.ndarray:
    """Moyenne géométrique / arithmétique par temps : 1 = bruit, < 0,95 = notes marquées."""
    c = chroma + 1e-9
    return np.exp(np.mean(np.log(c), axis=0)) / np.mean(c, axis=0)


def viterbi_constant_switch(scores: np.ndarray, switch_cost: float) -> np.ndarray:
    """Meilleur chemin d'états : somme des scores moins `switch_cost` par changement."""
    n_states, n = scores.shape
    if n == 0:
        return np.zeros(0, dtype=int)
    back = np.zeros((n, n_states), dtype=int)
    acc = scores[:, 0].copy()
    for t in range(1, n):
        best_prev = int(np.argmax(acc))
        switch = acc[best_prev] - switch_cost
        stay_better = acc >= switch
        back[t] = np.where(stay_better, np.arange(n_states), best_prev)
        acc = np.where(stay_better, acc, switch) + scores[:, t]
    path = np.zeros(n, dtype=int)
    path[-1] = int(np.argmax(acc))
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def recognize_chords(features: BeatFeatures) -> np.ndarray:
    """Indice d'accord par temps : 0-11 majeurs, 12-23 mineurs, 24 = aucun."""
    return viterbi_constant_switch(chord_scores(features), CHORD_SWITCH_COST)


# ---------------------------------------------------------------- tonalité
def _key_profiles() -> np.ndarray:
    profiles = np.zeros((24, 12))
    for tonic in range(12):
        profiles[tonic] = np.roll(MAJOR_PROFILE, tonic)
        profiles[12 + tonic] = np.roll(MINOR_PROFILE, tonic)
    profiles -= profiles.mean(axis=1, keepdims=True)
    return profiles / np.linalg.norm(profiles, axis=1, keepdims=True)


KEY_PROFILES = _key_profiles()


def local_keys(features: BeatFeatures, chords: np.ndarray) -> np.ndarray:
    """Tonalité par temps (0-11 majeur, 12-23 mineur), fenêtre glissante + Viterbi."""
    n = len(features)
    if n == 0:
        return np.zeros(0, dtype=int)
    weights = (chords != NO_CHORD).astype(float)
    chroma = features.chroma / (np.sum(features.chroma, axis=0, keepdims=True) + 1e-9) * weights
    half = KEY_WINDOW_BEATS // 2
    cumsum = np.concatenate([np.zeros((12, 1)), np.cumsum(chroma, axis=1)], axis=1)
    idx = np.arange(n)
    lo, hi = np.clip(idx - half, 0, n), np.clip(idx + half, 0, n)
    window = cumsum[:, hi] - cumsum[:, lo]
    window = window - window.mean(axis=0, keepdims=True)
    window = window / (np.linalg.norm(window, axis=0, keepdims=True) + 1e-9)
    profile = KEY_PROFILES @ window  # corrélation de Pearson, (24, n)
    # rôle des accords dans la même fenêtre : sans lui, la seconde passe peut s'auto-confirmer
    # (Fa–Sib–Solm–Do lu en Sol mineur, puis Do corrigé en Dom, ce qui « confirme » Sol mineur)
    voiced = np.flatnonzero(chords != NO_CHORD)
    onehot = np.zeros((24, n))
    onehot[chords[voiced], voiced] = 1.0
    ccum = np.concatenate([np.zeros((24, 1)), np.cumsum(onehot, axis=1)], axis=1)
    hist = ccum[:, hi] - ccum[:, lo]
    function = FUNCTION @ (hist / np.maximum(hist.sum(axis=0, keepdims=True), 1.0))
    return viterbi_constant_switch(function + PROFILE_WEIGHT * profile, KEY_SWITCH_COST)


def key_of(index: int) -> Key:
    return Key(index % 12, index >= 12)


def _diatonic_matrix() -> np.ndarray:
    """(24 tonalités, 24 accords) : 1 si l'accord appartient à la tonalité (V majeur inclus en mineur)."""
    matrix = np.zeros((24, 24))
    for k in range(24):
        for chord in diatonic_chords(key_of(k)):
            if chord.quality in ("maj", "min"):
                matrix[k, chord.root + (12 if chord.quality == "min" else 0)] = 1.0
    return matrix


DIATONIC = _diatonic_matrix()

# Rôle des accords pour choisir la tonalité d'un morceau entier : un vamp Lam–Sol se
# lit « i–bVII » en La mineur plutôt que « iv–bIII » en Mi mineur, comme le ferait
# un musicien. Accords relatifs (voir memory.rel_token) -> poids.
MAJOR_FUNCTION = {"0": 1.0, "7": 0.8, "5": 0.8, "9m": 0.6, "2m": 0.5, "4m": 0.4, "10": 0.3, "2": 0.2}
MINOR_FUNCTION = {"0m": 1.0, "5m": 0.8, "7": 0.7, "3": 0.6, "8": 0.6, "10": 0.6, "7m": 0.5, "5": 0.2}
OUTSIDE_FUNCTION = -0.3
PROFILE_WEIGHT = 0.3  # à 0,5, Fa–Sib–Solm–Do basculait en Sol mineur après compression m4a


def _function_matrix() -> np.ndarray:
    matrix = np.full((24, 24), OUTSIDE_FUNCTION)
    for k in range(24):
        key = key_of(k)
        table = MINOR_FUNCTION if key.minor else MAJOR_FUNCTION
        for c in range(24):
            matrix[k, c] = table.get(rel_token(c % 12 - key.tonic, c >= 12), OUTSIDE_FUNCTION)
    return matrix


FUNCTION = _function_matrix()


def piece_key(chroma: np.ndarray, chords: np.ndarray) -> Key:
    """Tonalité d'un morceau : rôle des accords joués + profil de Krumhansl des notes."""
    hist = np.bincount(chords[chords != NO_CHORD], minlength=25)[:24].astype(float)
    if hist.sum() == 0:
        return Key(0, False)
    function = FUNCTION @ (hist / hist.sum())
    total = chroma.sum(axis=1)
    centered = total - total.mean()
    profile = KEY_PROFILES @ (centered / (np.linalg.norm(centered) + 1e-9))
    return key_of(int(np.argmax(function + PROFILE_WEIGHT * profile)))


# ---------------------------------------------------------------- morceaux
def split_pieces(features: BeatFeatures, chords: np.ndarray, keys: np.ndarray) -> list[Piece]:
    n = len(features)
    if n == 0:
        return []
    # bornes : changement de tonalité, ou passage sans accord de plus de GAP_SPLIT_S
    boundaries = [0]
    gap_start: int | None = None
    for i in range(n):
        if chords[i] == NO_CHORD:
            gap_start = i if gap_start is None else gap_start
            continue
        if gap_start is not None:
            gap_s = features.times[i] - features.times[gap_start]
            if gap_s >= GAP_SPLIT_S and gap_start > boundaries[-1]:
                boundaries.extend([gap_start, i])
            gap_start = None
        if i > 0 and keys[i] != keys[i - 1] and i > boundaries[-1]:
            boundaries.append(i)
    boundaries.append(n)

    pieces = []
    for a, b in zip(boundaries, boundaries[1:]):
        if b <= a:
            continue
        seg = chords[a:b]
        voiced = seg != NO_CHORD
        start_s = float(features.times[a])
        end_s = float(features.times[b - 1] + features.durations[b - 1])
        if end_s - start_s < MIN_PIECE_S or voiced.mean() < MIN_PIECE_CHORD_RATIO:
            continue
        chroma = features.chroma[:, a:b]
        key = piece_key(chroma / (chroma.sum(axis=0, keepdims=True) + 1e-9), seg)
        runs: list[tuple[str, float]] = []
        names: list[str] = []
        for c in seg[voiced]:
            root, minor = int(c) % 12, int(c) >= 12
            token = rel_token(root - key.tonic, minor)
            name = f"{pc_name(root)}{'m' if minor else ''}"
            if runs and runs[-1][0] == token:
                runs[-1] = (token, runs[-1][1] + 1)
            else:
                runs.append((token, 1.0))
                names.append(name)
        durations = features.durations[a:b]
        tempo = float(60.0 / np.median(durations)) if len(durations) else 0.0
        pieces.append(Piece(start_s, end_s, key, round(tempo, 1), runs, names))
    return pieces


def study_features(features: BeatFeatures, duration_s: float) -> StudyResult:
    scores = chord_scores(features)
    chords = viterbi_constant_switch(scores, CHORD_SWITCH_COST)
    keys = local_keys(features, chords)
    if len(features):
        scores[:24] += KEY_CHORD_BONUS * DIATONIC[keys].T
        chords = viterbi_constant_switch(scores, CHORD_SWITCH_COST)
        keys = local_keys(features, chords)
    return StudyResult(duration_s=duration_s, pieces=split_pieces(features, chords, keys), beats=len(features))


def study_files(paths: list[Path], progress: Callable[[int, int, Path], None] | None = None) -> StudyResult:
    """Étudie des WAV successifs comme une seule séance continue."""
    import soundfile as sf

    total = BeatFeatures()
    offset = 0.0
    for i, path in enumerate(paths):
        if progress:
            progress(i, len(paths), path)
        y, sr = sf.read(path, dtype="float32", always_2d=True)
        y = y.mean(axis=1)
        skip = int(SKIP_START_S * sr) if i == 0 else 0
        try:
            feats = beat_features(y[skip:], sr)
        except Exception:
            log.exception("Étude impossible de %s", path)
            feats = BeatFeatures()
        total.extend(feats, offset + skip / sr)
        offset += len(y) / sr
    return study_features(total, offset)
