"""Assemblage de l'application et ligne de commande.

    python -m orchestre_ia                   # interface graphique
    python -m orchestre_ia --list-devices    # liste des micros
    python -m orchestre_ia --test-mic 5      # diagnostic micro de 5 s en console
    python -m orchestre_ia --test-mic 5 --device 9
    python -m orchestre_ia --learn-listen --label louange   # écoute muette pour apprendre
    python -m orchestre_ia --learn-study                    # étudie les séances écoutées
    python -m orchestre_ia --learn-corpus                   # importe ≈ 680 000 grilles d'accords
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import threading
import time
from pathlib import Path

from orchestre_ia import APP_NAME, __version__
from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.audio.devices import AudioDevice, find_device, list_input_devices, preferred_default
from orchestre_ia.audio.events import AudioLevelEvent, CaptureState, CaptureStateChanged, CaptureStats
from orchestre_ia.audio.level import SILENCE_DB
from orchestre_ia.core.config import AppConfig
from orchestre_ia.core.events import EventBus
from orchestre_ia.core.logging_setup import setup_logging
from orchestre_ia.core.paths import config_path, log_dir

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orchestre_ia", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--list-devices", action="store_true", help="liste les micros disponibles")
    parser.add_argument("--test-mic", type=float, metavar="SECONDES", help="diagnostic micro en console")
    parser.add_argument("--device", type=int, help="index du micro (voir --list-devices)")
    parser.add_argument("--accompany-file", metavar="WAV", help="accompagne un enregistrement et écrit le mixage")
    parser.add_argument("--style", default="variete", help="style d'accompagnement (variete, pop, gospel, zouglou, jazz, rnb, classique, afro, reggae, soul)")
    parser.add_argument("--tempo", type=float, help="tempo imposé en BPM (sinon détection automatique)")
    parser.add_argument("--learn-listen", action="store_true", help="écoute muette d'une séance (louange, répétition) pour apprendre ; Ctrl+C pour arrêter")
    parser.add_argument("--label", default="louange", help="nom de la séance écoutée (défaut : louange)")
    parser.add_argument("--minutes", type=float, help="durée maximale de l'écoute d'apprentissage")
    parser.add_argument("--learn-study", nargs="?", const="", metavar="DOSSIER", help="étudie les séances écoutées (toutes les nouvelles, ou un dossier / un WAV) et met à jour la mémoire musicale")
    parser.add_argument("--learn-library", nargs="?", const="", metavar="DOSSIER", help="étudie un dossier de chants (un chant par fichier : mp3, m4a, webm, wav…) ; défaut : Musique\\Orchestre chants")
    parser.add_argument("--learn-corpus", nargs="?", const="", metavar="CSV", help="importe le corpus de grilles d'accords Chordonomicon (≈ 680 000 chants, licence MIT) ; téléchargé s'il manque")
    parser.add_argument("--limit", type=int, help="avec --learn-corpus : ne lire que les N premiers chants (essai)")
    parser.add_argument("--workers", type=int, help="avec --learn-library : chants étudiés en parallèle (défaut : automatique)")
    parser.add_argument("--force", action="store_true", help="avec --learn-study / --learn-library : réétudie aussi ce qui l'a déjà été")
    parser.add_argument("--debug", action="store_true", help="journaux détaillés")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = setup_logging(log_dir(), logging.DEBUG if args.debug else logging.INFO)
    log.info("%s %s — journaux : %s", APP_NAME, __version__, log_file)
    config = AppConfig.load(config_path())

    if args.list_devices:
        return print_devices()
    if args.test_mic is not None:
        return run_mic_test(config, args.test_mic, args.device)
    if args.learn_corpus is not None:
        return run_learning_corpus(args.learn_corpus or None, args.limit)
    if args.learn_library is not None:
        return run_learning_library(args.learn_library or None, args.workers, args.force)
    if args.learn_study is not None:
        return run_learning_study(args.learn_study or None, args.force)
    if args.learn_listen:
        return run_learning_listen(config, args.device, args.label, args.minutes)
    if args.accompany_file:
        return run_accompany_file(Path(args.accompany_file), args.style, args.tempo)
    return run_gui(config)


def run_accompany_file(path: Path, style: str, tempo: float | None) -> int:
    from orchestre_ia.app.file_render import accompany_file
    from orchestre_ia.conductor.conductor import AccompanimentSettings
    from orchestre_ia.instruments.styles import STYLES

    _configure_console()
    if not path.exists():
        print(f"Fichier introuvable : {path}")
        return 1
    if style not in STYLES:
        print(f"Style inconnu : {style}. Choix : {', '.join(STYLES)}")
        return 1
    settings = AccompanimentSettings(style=style)
    if tempo:
        settings.tempo_mode, settings.manual_bpm = "manual", tempo
    out = path.with_name(f"{path.stem}_accompagne_{style}.wav")
    print(f"Accompagnement de {path.name} (style {STYLES[style].label}) en temps réel…")
    result = accompany_file(path, out, settings)
    print(f"Synthétiseur        : {result['synth']}")
    print(f"Tonalité finale     : {result['key']}")
    print(f"Accords joués       : {' → '.join(result['chord_sequence']) or 'aucun'}")
    print(f"Jeu rythmé / batterie : {result['rhythmic_used']} / {result['drums_used']}")
    print(f"Erreurs de rendu    : {result['callback_errors']}")
    print(f"Fichier mixé        : {result['output']}")
    return 0 if result["chord_sequence"] else 2


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def print_devices() -> int:
    _configure_console()
    devices = list_input_devices()
    if not devices:
        print("Aucun micro détecté.")
        return 1
    print(f"{'Index':>5}  {'Pilote':<20}  {'Canaux':>6}  {'Fréq.':>7}  Nom")
    for dev in devices:
        star = " (défaut)" if dev.is_default else ""
        print(f"{dev.index:>5}  {dev.hostapi:<20}  {dev.channels:>6}  {dev.default_samplerate:>7.0f}  {dev.name}{star}")
    return 0


def _resolve_device(config: AppConfig, index: int | None) -> AudioDevice | None:
    devices = list_input_devices()
    if index is not None:
        return next((d for d in devices if d.index == index), None)
    return find_device(devices, config.audio.input_device_name, config.audio.input_hostapi) or preferred_default(devices)


def run_mic_test(config: AppConfig, seconds: float, device_index: int | None) -> int:
    """Capture réelle pendant `seconds` et affiche un bilan. Code retour 0 = OK."""
    _configure_console()
    device = _resolve_device(config, device_index)
    if device is None:
        print("ÉCHEC : aucun micro trouvé.")
        return 1

    bus = EventBus()
    levels: list[AudioLevelEvent] = []
    stats: list[CaptureStats] = []
    states: list[CaptureStateChanged] = []
    lock = threading.Lock()

    def on_level(e: AudioLevelEvent) -> None:
        with lock:
            levels.append(e)

    bus.subscribe(AudioLevelEvent, on_level)
    bus.subscribe(CaptureStats, stats.append)
    bus.subscribe(CaptureStateChanged, states.append)

    engine = AudioCaptureEngine(bus)
    audio = config.audio
    print(f"Micro testé : [{device.index}] {device.name} — {device.hostapi}")
    ok = engine.start(
        CaptureSettings(
            device=device.index,
            device_name=device.name,
            samplerate=audio.samplerate,
            blocksize=audio.blocksize,
            gain_db=audio.gain_db,
            highpass_hz=audio.highpass_hz if audio.highpass_enabled else None,
        )
    )
    if not ok:
        print(f"ÉCHEC : {states[-1].message if states else 'ouverture impossible'}")
        return 1

    print(f"Écoute pendant {seconds:.0f} s… parlez ou chantez.")
    end = time.monotonic() + seconds
    while time.monotonic() < end and engine.state == CaptureState.RUNNING:
        time.sleep(0.5)
        with lock:
            last = levels[-1] if levels else None
        if last:
            bar = "#" * max(0, int((last.rms_db + 60) / 2))
            voice = "VOIX" if last.voice_active else "    "
            print(f"  {last.rms_db:6.1f} dBFS {voice} |{bar:<30}|")
    final_state = engine.state
    engine.stop()

    if final_state != CaptureState.RUNNING:
        print(f"ÉCHEC : la capture s'est interrompue ({states[-1].message if states else ''}).")
        return 1
    with lock:
        rms_values = [e.rms_db for e in levels]
        voice_ratio = sum(e.voice_active for e in levels) / len(levels) if levels else 0.0
    if not rms_values:
        print("ÉCHEC : aucun bloc audio reçu.")
        return 1

    last_stats = stats[-1] if stats else None
    print("\n--- Bilan ---")
    print(f"Mesures de niveau reçues : {len(rms_values)}")
    print(f"Niveau RMS min / max     : {min(rms_values):.1f} / {max(rms_values):.1f} dBFS")
    print(f"Temps avec voix détectée : {voice_ratio * 100:.0f} %")
    if last_stats:
        print(f"Format effectif          : {last_stats.samplerate} Hz, {last_stats.channels} canal(aux), bloc {last_stats.blocksize}")
        print(f"Latence d'entrée estimée : {last_stats.input_latency_ms + last_stats.block_ms:.1f} ms")
        print(f"Traitement par bloc      : moy {last_stats.processing_ms_avg:.3f} ms, max {last_stats.processing_ms_max:.3f} ms")
        print(f"Débordements / pertes    : {last_stats.input_overflows} / {last_stats.buffer_overruns}")
    if max(rms_values) <= SILENCE_DB + 1:
        print("ATTENTION : signal totalement nul. Vérifiez Paramètres Windows > Confidentialité > Microphone,")
        print("            et que le micro n'est pas coupé.")
        return 2
    print("RÉSULTAT : capture micro opérationnelle.")
    return 0


def run_learning_listen(
    config: AppConfig,
    device_index: int | None,
    label: str,
    minutes: float | None,
    stream_factory=None,
) -> int:
    """Écoute muette d'une séance entière, enregistrée par parties pour l'apprentissage."""
    from datetime import datetime

    from orchestre_ia.core.paths import listening_dir
    from orchestre_ia.learning.listening import (
        ListeningInfo,
        SegmentedRecorder,
        keep_awake,
        new_session_dir,
        save_info,
    )

    _configure_console()
    device = _resolve_device(config, device_index) if stream_factory is None else None
    if stream_factory is None and device is None:
        print("ÉCHEC : aucun micro trouvé. Essayez --list-devices puis --device N.")
        return 1
    device_name = device.name if device else "simulé"

    directory = new_session_dir(listening_dir(), label)
    info = ListeningInfo(label=label, device=device_name, started_at=datetime.now().isoformat(timespec="seconds"))
    recorder = SegmentedRecorder(directory)
    recorder.on_segment(lambda _path: _update_info(info, recorder, directory, save_info))
    save_info(directory, info)

    bus = EventBus()
    last_level: list[AudioLevelEvent | None] = [None]

    def on_level(event: AudioLevelEvent) -> None:
        last_level[0] = event

    bus.subscribe(AudioLevelEvent, on_level)
    engine = AudioCaptureEngine(bus, stream_factory=stream_factory) if stream_factory else AudioCaptureEngine(bus)
    settings = CaptureSettings(
        device=device.index if device else None,
        device_name=device_name,
        samplerate=config.audio.samplerate,
        blocksize=config.audio.blocksize,
        gain_db=0.0,  # signal brut : la séance sera analysée hors ligne
        highpass_hz=None,  # garder la basse et la grosse caisse
    )
    if not engine.start(settings):
        print("ÉCHEC : impossible d'ouvrir le micro.")
        return 1
    info.samplerate = engine.samplerate
    recorder.start()
    engine.add_consumer(recorder.write)
    keep_awake(True)

    print(f"Écoute d'apprentissage « {label} » — micro : {device_name}")
    print(f"Dossier : {directory}")
    print("Aucun son ne sera joué. Laissez l'ordinateur branché, couvercle ouvert.")
    print("Ctrl+C pour arrêter.\n")
    started = time.monotonic()
    last_restart = 0.0
    low_since: float | None = None
    try:
        while True:
            time.sleep(0.25 if stream_factory else 1.0)
            now = time.monotonic()
            elapsed = now - started
            if minutes is not None and elapsed >= minutes * 60:
                break
            if engine.state != CaptureState.RUNNING:
                if now - last_restart >= 3.0:
                    last_restart = now
                    print("\nLe micro ne répond plus, nouvelle tentative…")
                    if engine.start(settings):
                        info.restarts += 1
                        print("Micro retrouvé, l'écoute continue.")
                continue
            level = last_level[0]
            db = level.rms_db if level else SILENCE_DB
            low_since = (low_since or now) if db < -55 else None
            bar = "#" * max(0, min(30, int((db + 60) / 2)))
            h, rem = divmod(int(recorder.duration_s), 3600)
            warn = ""
            if level and level.clipping:
                warn = "  SATURE : éloignez le micro"
            elif low_since is not None and now - low_since > 20:
                warn = "  très faible : rapprochez le micro"
            print(f"\r  {h:02d}:{rem // 60:02d}:{rem % 60:02d}  {db:6.1f} dBFS |{bar:<30}|{warn:<36}", end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        recorder.stop()
        keep_awake(False)
        info.ended_at = datetime.now().isoformat(timespec="seconds")
        _update_info(info, recorder, directory, save_info)

    print("\n\n--- Écoute terminée ---")
    print(f"Durée enregistrée : {recorder.duration_s / 60:.1f} min en {len(recorder.segments)} partie(s)")
    print(f"Niveau crête      : {20 * math.log10(max(recorder.peak, 1e-9)):.1f} dBFS")
    if recorder.clipped_blocks:
        print(f"Saturation        : {recorder.clipped_blocks} blocs (micro trop près des enceintes)")
    print(f"Dossier           : {directory}")
    print("Pour que l'orchestre apprenne de cette séance :")
    print(r"  .\.venv\Scripts\python.exe -m orchestre_ia --learn-study")
    return 0 if recorder.frames_written else 1


def _hms(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h:02d}:{rem // 60:02d}:{rem % 60:02d}"


def _sessions_to_study(target: str | None) -> list[tuple[str, str, list[Path], Path | None]]:
    """(source, nom, fichiers WAV, dossier de séance ou None) pour chaque séance trouvée."""
    from orchestre_ia.core.paths import listening_dir
    from orchestre_ia.learning.listening import load_info

    def from_dir(d: Path) -> tuple[str, str, list[Path], Path | None] | None:
        parts = sorted(d.glob("partie_*.wav"))
        if not parts:
            return None
        info = load_info(d)
        return str(d.resolve()), info.label if info else d.name, parts, d

    root = Path(target) if target else listening_dir()
    if root.is_file():
        return [(str(root.resolve()), root.stem, [root], None)]
    if not root.is_dir():
        return []
    direct = from_dir(root)
    if direct:
        return [direct]
    return [s for s in (from_dir(d) for d in sorted(root.iterdir()) if d.is_dir()) if s]


def run_learning_study(target: str | None, force: bool) -> int:
    """Étudie les séances écoutées et met à jour la mémoire musicale de l'orchestre."""
    from orchestre_ia.learning.corpus import load_corpus_prior
    from orchestre_ia.learning.evaluation import evaluate_next_chord
    from orchestre_ia.learning.listening import load_info, save_info
    from orchestre_ia.learning.memory import MusicMemory, memory_path
    from orchestre_ia.learning.study import study_files

    _configure_console()
    sessions = _sessions_to_study(target)
    if not sessions:
        print("Aucune séance à étudier. Lancez d'abord une écoute : --learn-listen")
        return 1
    studied = 0
    corpus_prior = load_corpus_prior()
    if corpus_prior is not None:
        print("Corpus de grilles importé : les « habitudes apprises » ci-dessous l'incluent.")
    with MusicMemory(memory_path()) as memory:
        for source, label, parts, directory in sessions:
            name = directory.name if directory else Path(source).name
            if memory.is_studied(source) and not force:
                print(f"Déjà étudiée : {name} (--force pour recommencer)")
                continue
            info = load_info(directory) if directory else None
            if info is not None and info.ended_at is None and time.time() - parts[-1].stat().st_mtime < 30:
                print(f"Écoute en cours : {name} — elle sera étudiée une fois terminée.")
                continue
            print(f"\nÉtude de « {label} » ({name}), {len(parts)} partie(s)…")
            started = time.monotonic()
            result = study_files(parts, lambda i, n, path: print(f"  partie {i + 1}/{n} : {path.name}", flush=True))
            base = memory.learned(exclude=source)
            base.prior = corpus_prior  # mesure fidèle à ce que joue l'application
            score = evaluate_next_chord(result.pieces, base)
            memory.store(source, label, result)
            studied += 1
            if directory and info is not None:
                info.studied = True
                save_info(directory, info)
            print(f"  {result.duration_s / 60:.0f} min écoutées, étudiées en {(time.monotonic() - started) / 60:.1f} min")
            if not result.pieces:
                print("  Aucun morceau joué reconnu (trop court, trop faible ou sans instruments).")
            for i, piece in enumerate(result.pieces, 1):
                print(
                    f"  {i:>2}. {_hms(piece.start_s)} → {_hms(piece.end_s)}  {piece.key.name}, "
                    f"{piece.tempo:.0f} BPM, progression {' → '.join(piece.typical_progression())}"
                )
                names = piece.chord_names
                print(f"      accords : {' '.join(names[:12])}{' …' if len(names) > 12 else ''}")
            if score is not None:
                print(f"  Accord suivant deviné sur {score.changes} changements (1er choix / parmi 3) :")
                print(f"      règles génériques       : {score.generic_top1 * 100:3.0f} % / {score.generic_top3 * 100:3.0f} %")
                print(f"      appris + chant en cours : {score.learned_top1 * 100:3.0f} % / {score.learned_top3 * 100:3.0f} %")
        print("\n--- Ce que l'orchestre a appris ---")
        for line in memory.summary_lines():
            print(f"  {line}")
    if studied:
        print("\nL'accompagnement utilisera ces habitudes au prochain lancement de l'application.")
    return 0


def run_learning_corpus(csv_file: str | None, limit: int | None) -> int:
    """Importe le corpus de grilles d'accords et mesure ce qu'il apporte sur des chants tenus à part."""
    from orchestre_ia.learning import corpus
    from orchestre_ia.learning.evaluation import evaluate_pieces
    from orchestre_ia.learning.memory import MusicMemory

    _configure_console()
    path = Path(csv_file) if csv_file else corpus.dataset_path()
    if not path.exists():
        if csv_file:
            print(f"Fichier introuvable : {path}")
            return 1
        print(f"Téléchargement de Chordonomicon (≈ 264 Mo, licence MIT) vers {path}")

        def on_bytes(done: int, total: int) -> None:
            if total and done % (16 << 20) < (1 << 20):
                print(f"  {done / 2**20:.0f} / {total / 2**20:.0f} Mo", flush=True)

        try:
            corpus.download_dataset(path, progress=on_bytes)
        except OSError as exc:
            print(f"Échec : {exc}")
            print(f"Téléchargez le fichier à la main ({corpus.DATASET_URL}) puis : --learn-corpus <fichier>")
            return 1
        except KeyboardInterrupt:
            print("\nInterrompu. Relancez pour reprendre le téléchargement.")
            return 130

    print(f"Lecture des grilles : {path}")
    started = time.monotonic()
    try:
        imported = corpus.read_corpus(
            path, limit=limit, progress=lambda n: print(f"  {n} chants lus…", flush=True)
        )
    except KeyboardInterrupt:
        print("\nInterrompu. Rien n'a été modifié.")
        return 130
    counts = imported.full_counts()
    songs = sum(g.songs for g in counts.values())
    print(f"{songs} chants retenus sur {imported.rows} ({imported.skipped} trop courts ou illisibles), "
          f"{(time.monotonic() - started):.0f} s")
    for name, g in sorted(counts.items(), key=lambda x: -x[1].songs)[:16]:
        print(f"  {name:<12} {g.songs:>7} chants")

    learned = corpus.merged(list(imported.train.values()))
    print("\nAccord suivant deviné sur des chants tenus à part (1er choix / parmi 3) :")
    for group in (corpus.LOUANGE, corpus.AFRO, "pop", "rock"):
        held = imported.held_out.get(group)
        if not held:
            continue
        score = evaluate_pieces([p for song in held for p in song], learned)
        if score is None:
            continue
        print(f"  {group:<8} ({len(held)} chants, {score.changes} changements) : "
              f"règles génériques {score.generic_top1 * 100:3.0f} % / {score.generic_top3 * 100:3.0f} %, "
              f"corpus + chant en cours {score.learned_top1 * 100:3.0f} % / {score.learned_top3 * 100:3.0f} %")

    with MusicMemory(corpus.corpus_path()) as memory:
        corpus.store_corpus(memory, counts)
        print(f"\nCorpus rangé dans {corpus.corpus_path()}")
        for line in memory.summary_lines()[1:]:  # la 1re ligne (heures écoutées) ne concerne que les séances
            print(f"  {line}")
    print("\nL'accompagnement s'en servira au prochain lancement ; les habitudes de votre équipe "
          "(--learn-listen, --learn-study) restent prioritaires dès qu'elles sont assez nombreuses.")
    return 0


def run_learning_library(folder: str | None, workers: int | None, force: bool) -> int:
    """Étudie un dossier de chants et met à jour la mémoire musicale."""
    from orchestre_ia.core.paths import songs_dir
    from orchestre_ia.learning.evaluation import evaluate_folds, pieces_by_source
    from orchestre_ia.learning.library import default_workers, find_songs, study_library
    from orchestre_ia.learning.memory import MusicMemory, memory_path

    _configure_console()
    root = Path(folder) if folder else songs_dir()
    if not root.exists():
        if folder:
            print(f"Dossier introuvable : {root}")
            return 1
        root.mkdir(parents=True)
    count = len(find_songs(root))
    if count == 0:
        print(f"Aucun chant dans {root}")
        print("Formats acceptés : mp3, m4a, webm, opus, aac, mp4, wav, flac, ogg.")
        return 1
    workers = workers or default_workers()
    print(f"Bibliothèque : {root}")
    print(f"{count} fichier(s) audio, étude de {workers} chant(s) à la fois. Ctrl+C pour interrompre (reprise possible).\n")

    started = time.monotonic()

    def on_song(index: int, total: int, path: Path, outcome) -> None:
        elapsed = time.monotonic() - started
        remaining = elapsed / index * (total - index)
        name = path.stem if len(path.stem) <= 48 else path.stem[:47] + "…"
        prefix = f"[{index}/{total}, reste ≈ {remaining / 60:.0f} min]"
        if outcome.result is None:
            print(f"{prefix} {name} — ignoré : {outcome.error}")
        elif not outcome.result.pieces:
            print(f"{prefix} {name} — aucun accord net trouvé")
        else:
            main = max(outcome.result.pieces, key=lambda p: p.duration_s)
            print(
                f"{prefix} {name} — {main.key.name}, {main.tempo:.0f} BPM, "
                f"{' → '.join(main.typical_progression())}"
            )

    with MusicMemory(memory_path()) as memory:
        try:
            report = study_library(root, memory, workers=workers, force=force, on_song=on_song)
        except KeyboardInterrupt:
            print("\nInterrompu. Les chants déjà étudiés sont gardés ; relancez pour continuer.")
            return 130
        print(f"\n--- Bilan ({(time.monotonic() - started) / 60:.1f} min) ---")
        print(f"  Chants étudiés : {report.studied}, déjà connus : {report.skipped}, doublons : {report.duplicates}")
        if report.errors:
            print(f"  Fichiers ignorés : {len(report.errors)} (illisibles ou trop courts)")
        score = evaluate_folds(pieces_by_source(memory))
        if score is not None:
            print(f"  Accord suivant deviné sur des chants mis à part ({score.changes} changements, 1er choix / parmi 3) :")
            print(f"      règles génériques       : {score.generic_top1 * 100:3.0f} % / {score.generic_top3 * 100:3.0f} %")
            print(f"      appris + chant en cours : {score.learned_top1 * 100:3.0f} % / {score.learned_top3 * 100:3.0f} %")
        print("\n--- Ce que l'orchestre a appris ---")
        for line in memory.summary_lines():
            print(f"  {line}")
    print("\nL'accompagnement utilisera ces habitudes au prochain lancement de l'application.")
    return 0


def _update_info(info, recorder, directory: Path, save) -> None:
    info.duration_s = round(recorder.duration_s, 2)
    info.segments = [p.name for p in recorder.segments]
    info.clipped_blocks = recorder.clipped_blocks
    info.peak = round(recorder.peak, 4)
    try:
        save(directory, info)
    except OSError:
        log.exception("Écriture de seance.json impossible")


def run_gui(config: AppConfig) -> int:
    from PySide6.QtWidgets import QApplication

    from orchestre_ia.interface.main_window import MainWindow
    from orchestre_ia.interface.theme import STYLESHEET

    if sys.platform == "win32":
        # identifiant propre : Windows affiche alors notre logo dans la barre des tâches
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"OrchestreIA.App.{__version__}")
        except Exception:
            pass
    from orchestre_ia.interface.icons import logo_icon

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(logo_icon())
    app.setStyleSheet(STYLESHEET)

    from orchestre_ia.app.session import MusicSession

    bus = EventBus()
    session = MusicSession(bus)
    path = config_path()

    def save_config() -> None:
        try:
            config.save(path)
        except OSError as exc:
            log.error("Sauvegarde de la configuration impossible : %s", exc)

    window = MainWindow(bus, session, config, save_config)
    window.show()
    code = app.exec()
    session.stop()
    return code
