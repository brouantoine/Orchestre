"""Assemblage de l'application et ligne de commande.

    python -m orchestre_ia                   # interface graphique
    python -m orchestre_ia --list-devices    # liste des micros
    python -m orchestre_ia --test-mic 5      # diagnostic micro de 5 s en console
    python -m orchestre_ia --test-mic 5 --device 9
"""

from __future__ import annotations

import argparse
import logging
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
