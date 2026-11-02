"""Espace STUDIO : micro, écoute, accompagnement en direct."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from orchestre_ia.analysis.events import KeyUpdate, PitchUpdate, TempoUpdate
from orchestre_ia.analysis.theory import note_name, pc_name
from orchestre_ia.app.session import MusicSession
from orchestre_ia.audio.capture import CaptureSettings
from orchestre_ia.audio.devices import (
    AudioDevice,
    find_device,
    list_input_devices,
    list_output_devices,
    preferred_default,
)
from orchestre_ia.audio.events import AudioLevelEvent, CaptureState, CaptureStateChanged, CaptureStats
from orchestre_ia.audio.recorder import SessionRecorder
from orchestre_ia.conductor.conductor import ConductorState, ConductorUpdate
from orchestre_ia.core.config import AppConfig
from orchestre_ia.core.paths import recordings_dir
from orchestre_ia.instruments.styles import STYLES
from orchestre_ia.interface import theme
from orchestre_ia.interface.bridge import QtEventBridge
from orchestre_ia.interface.icons import icon
from orchestre_ia.interface.views.common import (
    BeatIndicator,
    Pill,
    Tile,
    icon_label,
    make_card,
    page,
    scrollable,
    view_title,
)
from orchestre_ia.interface.widgets.level_meter import LevelMeterWidget
from orchestre_ia.interface.widgets.piano_keyboard import PianoKeyboardWidget

STATE_TEXT = {
    ConductorState.IDLE: ("Arrêté", theme.TEXT_DIM),
    ConductorState.LISTENING: ("À l'écoute", theme.WARN),
    ConductorState.PLAYING: ("Joue", theme.OK),
    ConductorState.ENDING: ("Conclusion", theme.OK),
    ConductorState.PAUSED: ("En pause", theme.TEXT_DIM),
}


class StudioView(QWidget):
    def __init__(
        self,
        session: MusicSession,
        bridge: QtEventBridge,
        config: AppConfig,
        save_config: Callable[[], None],
        list_devices: Callable[[], list[AudioDevice]] = list_input_devices,
        list_outputs: Callable[[], list[AudioDevice]] = list_output_devices,
        recordings_directory: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._engine = session.capture
        self._config = config
        self._save_config = save_config
        self._list_devices = list_devices
        self._list_outputs = list_outputs
        self._devices: list[AudioDevice] = []
        self._recorder = SessionRecorder(recordings_directory or recordings_dir())
        self._remove_recorder: Callable[[], None] | None = None
        self._conductor_state = ConductorState.IDLE
        self._shows_resume = False

        content, root = page()

        pills = QWidget()
        pills_layout = QHBoxLayout(pills)
        pills_layout.setContentsMargins(0, 6, 0, 0)
        pills_layout.setSpacing(8)
        self.status_label = Pill("Micro : arrêté")
        self.orchestra_pill = Pill("Orchestre : arrêté")
        pills_layout.addWidget(self.status_label)
        pills_layout.addWidget(self.orchestra_pill)
        root.addWidget(
            view_title("Studio", "Chantez : ORCHESTRE IA écoute votre mélodie et vous accompagne en direct.", pills)
        )

        # --- Session : micro et commandes
        mic_card, mic = make_card("Session", "studio")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(icon_label("studio", theme.TEXT_DIM, 18))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(320)
        self.device_combo.setToolTip("Micro utilisé pour vous écouter")
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("IconButton")
        self.refresh_button.setIcon(icon("refresh", theme.TEXT_DIM))
        self.refresh_button.setToolTip("Actualiser la liste des micros")
        self.refresh_button.clicked.connect(self.refresh_devices)
        row.addWidget(self.device_combo, 1)
        row.addWidget(self.refresh_button)
        row.addSpacing(18)
        style_caption = QLabel("Style")
        style_caption.setObjectName("Dim")
        row.addWidget(style_caption)
        self.style_combo = QComboBox()
        self.style_combo.setMinimumWidth(150)
        for key, style in STYLES.items():
            self.style_combo.addItem(style.label, key)
        self.style_combo.setCurrentIndex(self.style_combo.findData(config.accompaniment.style))
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        row.addWidget(self.style_combo)
        mic.addLayout(row)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.start_button = QPushButton("  Écouter et accompagner")
        self.start_button.setObjectName("Primary")
        self.start_button.setIcon(icon("play", "#17130a"))
        self.start_button.clicked.connect(self.start_listening)
        self.pause_button = QPushButton("  Pause")
        self.pause_button.setObjectName("Secondary")
        self.pause_button.setIcon(icon("pause", theme.TEXT))
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("  Arrêter")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setIcon(icon("stop", theme.DANGER))
        self.stop_button.clicked.connect(self.stop_listening)
        self.stop_button.setEnabled(False)
        for b in (self.start_button, self.pause_button, self.stop_button):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        controls.addSpacing(18)
        self.headphones_check = QCheckBox("J'utilise un casque")
        self.headphones_check.setChecked(config.accompaniment.headphones)
        self.headphones_check.toggled.connect(self._on_headphones)
        self.record_check = QCheckBox("Enregistrer ma voix")
        self.record_check.setToolTip("Le fichier reste sur cet ordinateur et n'est jamais envoyé.")
        controls.addWidget(self.headphones_check)
        controls.addWidget(self.record_check)
        controls.addStretch(1)
        mic.addLayout(controls)

        rec_row = QHBoxLayout()
        self.hint_icon = icon_label("headphones", theme.WARN, 15)
        self.headphones_hint = QLabel(
            "Avec un casque, le micro n'entend pas l'orchestre : l'analyse et les accords sont plus justes."
        )
        self.headphones_hint.setObjectName("Warning")
        self.headphones_hint.setWordWrap(True)
        self.headphones_hint.setVisible(not config.accompaniment.headphones)
        self.hint_icon.setVisible(not config.accompaniment.headphones)
        self.record_label = QLabel("")
        self.record_label.setObjectName("Dim")
        self.open_folder_button = QPushButton("  Ouvrir le dossier")
        self.open_folder_button.setIcon(icon("folder", theme.TEXT_DIM))
        self.open_folder_button.clicked.connect(self._open_recordings_folder)
        self.open_folder_button.setVisible(False)
        rec_row.addWidget(self.hint_icon)
        rec_row.addWidget(self.headphones_hint, 1)
        rec_row.addWidget(self.record_label)
        rec_row.addWidget(self.open_folder_button)
        mic.addLayout(rec_row)
        root.addWidget(mic_card)

        # --- Musique en direct
        grid = QGridLayout()
        grid.setSpacing(12)
        self.chord_tile = Tile("Accord joué", "chord", accent=True)
        self.note_tile = Tile("Note chantée", "note")
        self.key_tile = Tile("Tonalité", "key")
        self.tempo_tile = Tile("Tempo", "tempo")
        self.piano_tile = Tile("Piano", "piano")
        self.drums_tile = Tile("Batterie", "drums")
        self.intensity_tile = Tile("Intensité", "level")
        self.beat_indicator = BeatIndicator()
        self.tempo_tile.head.addWidget(self.beat_indicator)
        self.chord_notes = QLabel("")
        self.chord_notes.setObjectName("ChordNotes")
        self.chord_progression = QLabel("")
        self.chord_progression.setObjectName("Progression")
        self.chord_progression.setWordWrap(True)
        self.chord_tile.body.insertWidget(3, self.chord_notes)
        self.chord_tile.body.addWidget(self.chord_progression)
        self._chord_history: list[str] = []
        grid.addWidget(self.chord_tile, 0, 0, 2, 1)
        grid.addWidget(self.note_tile, 0, 1)
        grid.addWidget(self.key_tile, 0, 2)
        grid.addWidget(self.tempo_tile, 0, 3)
        grid.addWidget(self.piano_tile, 1, 1)
        grid.addWidget(self.drums_tile, 1, 2)
        grid.addWidget(self.intensity_tile, 1, 3)
        grid.setColumnStretch(0, 5)
        for c in (1, 2, 3):
            grid.setColumnStretch(c, 4)
        root.addLayout(grid)

        kb_card, kb = make_card("Clavier", "piano")
        legend = QLabel(
            f"<span style='color:{theme.ACCENT}'>●</span> votre voix &nbsp;&nbsp; "
            f"<span style='color:{theme.OK}'>●</span> le piano"
        )
        legend.setObjectName("Dim")
        kb_card.header.addWidget(legend)  # type: ignore[attr-defined]
        self.keyboard = PianoKeyboardWidget()
        kb.addWidget(self.keyboard)
        root.addWidget(kb_card)

        # --- Niveau et diagnostic côte à côte
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        level_card, level = make_card("Niveau d'entrée", "level")
        self.meter = LevelMeterWidget()
        level.addWidget(self.meter)
        lrow = QHBoxLayout()
        self.level_value = QLabel("—")
        self.level_value.setObjectName("BigValue")
        self.voice_label = QLabel("● Silence")
        self.clip_label = QLabel("")
        lrow.addWidget(self.level_value)
        lrow.addSpacing(12)
        lrow.addWidget(self.voice_label)
        lrow.addWidget(self.clip_label)
        lrow.addStretch(1)
        level.addLayout(lrow)
        grow = QHBoxLayout()
        gain_caption = QLabel("Gain")
        gain_caption.setObjectName("Dim")
        grow.addWidget(gain_caption)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(-24, 24)
        self.gain_slider.setValue(round(config.audio.gain_db))
        self.gain_slider.valueChanged.connect(self._on_gain_changed)
        self.gain_value = QLabel(self._gain_text(self.gain_slider.value()))
        self.gain_value.setMinimumWidth(50)
        grow.addWidget(self.gain_slider, 1)
        grow.addWidget(self.gain_value)
        level.addLayout(grow)
        self.floor_label = QLabel("Bruit de fond : —")
        self.floor_label.setObjectName("Faint")
        level.addWidget(self.floor_label)
        bottom.addWidget(level_card, 3)

        diag_card, diag = make_card("Diagnostic", "chip")
        self.stats_label = QLabel("Aucune capture en cours.")
        self.stats_label.setObjectName("Dim")
        self.stats_label.setWordWrap(True)
        diag.addWidget(self.stats_label)
        self.output_label = QLabel("Orchestre : arrêté")
        self.output_label.setObjectName("Dim")
        self.output_label.setWordWrap(True)
        diag.addWidget(self.output_label)
        diag.addStretch(1)
        bottom.addWidget(diag_card, 2)
        root.addLayout(bottom)
        root.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))

        bridge.level.connect(self._on_level)
        bridge.capture_state.connect(self._on_state)
        bridge.stats.connect(self._on_stats)
        bridge.pitch.connect(self._on_pitch)
        bridge.key.connect(self._on_key)
        bridge.tempo.connect(self._on_tempo)
        bridge.conductor.connect(self._on_conductor)
        bridge.output_state.connect(self._on_output_state)
        self._reset_music_tiles()
        self.refresh_devices()

    # ------------------------------------------------------------ actions
    def refresh_devices(self) -> None:
        self._devices = self._list_devices()
        self.device_combo.clear()
        for dev in self._devices:
            self.device_combo.addItem(dev.label, dev.index)
        selected = find_device(self._devices, self._config.audio.input_device_name, self._config.audio.input_hostapi)
        selected = selected or preferred_default(self._devices)
        if selected is not None:
            self.device_combo.setCurrentIndex(self._devices.index(selected))
        has_devices = bool(self._devices)
        self.start_button.setEnabled(has_devices and not self._engine.is_running)
        if not has_devices:
            self.status_label.set_state("error", "Aucun micro détecté")

    def selected_device(self) -> AudioDevice | None:
        i = self.device_combo.currentIndex()
        return self._devices[i] if 0 <= i < len(self._devices) else None

    def _output_device(self) -> int | None:
        acc = self._config.accompaniment
        outputs = self._list_outputs()
        dev = find_device(outputs, acc.output_device_name, acc.output_hostapi) or preferred_default(outputs)
        return dev.index if dev else None

    def start_listening(self) -> None:
        device = self.selected_device()
        if device is None:
            return
        audio = self._config.audio
        audio.input_device_name = device.name
        audio.input_hostapi = device.hostapi
        self._save_config()
        self._apply_accompaniment_settings()
        started = self._session.start(
            CaptureSettings(
                device=device.index,
                device_name=device.name,
                samplerate=audio.samplerate,
                blocksize=audio.blocksize,
                gain_db=audio.gain_db,
                highpass_hz=audio.highpass_hz if audio.highpass_enabled else None,
            ),
            output_device=self._output_device(),
            accompany=True,
            headphones=self._config.accompaniment.headphones,
        )
        if started and self.record_check.isChecked():
            try:
                self._recorder.start(self._engine.samplerate)
                self._remove_recorder = self._engine.add_consumer(self._recorder.write)
                self.record_label.setText("● Enregistrement en cours…")
                self.record_label.setStyleSheet(f"color: {theme.DANGER};")
                self.open_folder_button.setVisible(False)
            except OSError as exc:
                self.record_label.setText(f"Enregistrement impossible : {exc}")

    def _apply_accompaniment_settings(self) -> None:
        acc = self._config.accompaniment
        s = self._session.settings
        s.style, s.drums_mode, s.tempo_mode, s.manual_bpm = acc.style, acc.drums_mode, acc.tempo_mode, acc.manual_bpm

    def toggle_pause(self) -> None:
        if self._session.paused:
            self._session.resume()
        else:
            self._session.pause()

    def stop_listening(self) -> None:
        self._session.stop()
        self._finish_recording()

    def shutdown(self) -> None:
        """Appelé à la fermeture de la fenêtre."""
        self._session.stop()
        self._finish_recording()

    def _finish_recording(self) -> None:
        if self._remove_recorder is not None:
            self._remove_recorder()
            self._remove_recorder = None
        if not self._recorder.is_recording:
            return
        path = self._recorder.stop()
        if path is not None:
            self.record_label.setText(f"Enregistré : {path.name} ({self._recorder.duration_s:.0f} s)")
            self.record_label.setStyleSheet(f"color: {theme.OK};")
            self.open_folder_button.setVisible(True)

    def _open_recordings_folder(self) -> None:
        self._recorder.directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._recorder.directory)))

    def _on_gain_changed(self, value: int) -> None:
        self.gain_value.setText(self._gain_text(value))
        self._config.audio.gain_db = float(value)
        self._engine.set_gain_db(float(value))

    def _on_style_changed(self, _index: int) -> None:
        key = self.style_combo.currentData()
        self._config.accompaniment.style = key
        self._session.settings.style = key  # appliqué dès le temps suivant

    def _on_headphones(self, checked: bool) -> None:
        self._config.accompaniment.headphones = checked
        self._session.analysis.headphones = checked
        self.headphones_hint.setVisible(not checked)
        self.hint_icon.setVisible(not checked)

    @staticmethod
    def _gain_text(value: int) -> str:
        return f"{value:+d} dB"

    # ------------------------------------------------------------ événements
    def _reset_music_tiles(self) -> None:
        self.note_tile.set("—", "Chantez pour voir votre note")
        self.key_tile.set("—", "Estimée après quelques secondes de chant")
        self.tempo_tile.set("—", "")
        self.chord_tile.set("—", "L'accord apparaît dès que le piano joue")
        self.chord_notes.setText("")
        self.chord_progression.setText("")
        self._chord_history = []
        self.piano_tile.set("Arrêté", "", theme.TEXT_DIM)
        self.drums_tile.set("Arrêtée", "", theme.TEXT_DIM)
        self.intensity_tile.set("—", "suit le volume de votre voix")
        self.beat_indicator.set_beat(-1)
        self.keyboard.set_sung(None)
        self.keyboard.set_played(())

    def _on_state(self, event: CaptureStateChanged) -> None:
        busy = event.state in (CaptureState.RUNNING, CaptureState.STARTING)
        self.start_button.setEnabled(not busy and bool(self._devices))
        self.stop_button.setEnabled(busy)
        self.pause_button.setEnabled(busy and self._session.accompany)
        self.device_combo.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.record_check.setEnabled(not busy)
        if event.state == CaptureState.ERROR:
            self._finish_recording()
        state = {CaptureState.RUNNING: "ok", CaptureState.ERROR: "error", CaptureState.STARTING: "warn"}.get(
            event.state, "neutral"
        )
        self.status_label.set_state(state, f"Micro : {event.state.value}")
        self.status_label.setToolTip(event.message)
        if event.state == CaptureState.ERROR:
            self.stats_label.setText(event.message)
        if event.state != CaptureState.RUNNING:
            self.meter.reset()
            self.level_value.setText("—")
            self.voice_label.setText("● Silence")
            self.voice_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
            self.clip_label.setText("")
            if event.state not in (CaptureState.STARTING, CaptureState.ERROR):
                self.stats_label.setText("Aucune capture en cours.")
            if event.state != CaptureState.STARTING:
                self._reset_music_tiles()

    def _on_level(self, event: AudioLevelEvent) -> None:
        self.meter.set_levels(event.rms_db, event.peak_db, event.held_peak_db, event.clipping)
        self.level_value.setText(f"{event.rms_db:6.1f} dBFS")
        if event.voice_active:
            self.voice_label.setText("● Voix détectée")
            self.voice_label.setStyleSheet(f"color: {theme.OK}; font-weight: 600;")
        else:
            self.voice_label.setText("● Silence")
            self.voice_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.clip_label.setText("SATURATION — baissez le gain" if event.clipping else "")
        self.clip_label.setStyleSheet(f"color: {theme.DANGER}; font-weight: 600;")
        self.floor_label.setText(f"Bruit de fond : {event.noise_floor_db:.0f} dBFS")

    def _on_pitch(self, event: PitchUpdate) -> None:
        if event.midi > 0:
            nearest = round(event.midi)
            cents = (event.midi - nearest) * 100
            self.note_tile.set(note_name(nearest), f"{event.f0:.0f} Hz · {cents:+.0f} cents", theme.ACCENT)
            self.keyboard.set_sung(nearest)
        else:
            self.keyboard.set_sung(None)
            self.note_tile.value.setStyleSheet(f"color: {theme.TEXT_DIM};")

    def _on_key(self, event: KeyUpdate) -> None:
        est = event.estimate
        others = ", ".join(k.name for k, _ in est.candidates[1:3])
        self.key_tile.set(est.key.name, f"confiance {est.confidence * 100:.0f} % · autres : {others}")

    def _on_tempo(self, event: TempoUpdate) -> None:
        if self._conductor_state in (ConductorState.PLAYING, ConductorState.ENDING):
            return  # le chef d'orchestre affiche le tempo réellement joué
        est = event.estimate
        if est is None:
            self.tempo_tile.set("—", "pas encore assez de notes")
        else:
            self.tempo_tile.set(f"{est.bpm:.0f} BPM", f"régularité {est.confidence * 100:.0f} %")

    def _on_conductor(self, u: ConductorUpdate) -> None:
        self._conductor_state = u.state
        self.pause_button.setEnabled(u.state != ConductorState.IDLE)
        text, color = STATE_TEXT[u.state]
        paused = u.state == ConductorState.PAUSED
        if paused != self._shows_resume:
            self._shows_resume = paused
            self.pause_button.setText("  Reprendre" if paused else "  Pause")
            self.pause_button.setIcon(icon("play" if paused else "pause", theme.TEXT))
        pill_state = {ConductorState.PLAYING: "ok", ConductorState.ENDING: "ok", ConductorState.LISTENING: "warn"}
        self.orchestra_pill.set_state(pill_state.get(u.state, "neutral"), f"Orchestre : {text.lower()}")
        self.beat_indicator.set_beat(u.beat_in_bar if u.rhythmic and u.state == ConductorState.PLAYING else -1)
        if u.piano_active:
            self.intensity_tile.set(f"{u.intensity * 100:.0f} %", "suit le volume de votre voix")
        if u.state == ConductorState.LISTENING:
            self.piano_tile.set(text, "entre dès que vous chantez", color)
        else:
            mode = "jeu rythmé" if u.rhythmic else "jeu libre (tempo non établi)"
            self.piano_tile.set(text, mode if u.piano_active else "", color)
        if u.drums_active:
            self.drums_tile.set("Joue", self._session.settings.style_obj.label, theme.OK)
        elif u.state == ConductorState.PLAYING and not u.rhythmic:
            self.drums_tile.set("En attente", "pulsation pas assez régulière (réglez le tempo dans Orchestre)", theme.WARN)
        elif u.state == ConductorState.PLAYING:
            self.drums_tile.set("En attente", "entre en début de mesure", theme.WARN)
        else:
            self.drums_tile.set("Arrêtée" if u.state == ConductorState.IDLE else "Silence", "", theme.TEXT_DIM)
        if u.piano_active:
            alts = ", ".join(u.alternatives[:2])
            self.chord_tile.set(u.chord, f"autres possibles : {alts}" if alts else "")
            self.chord_notes.setText("  ·  ".join(pc_name(pc) for pc in u.chord_pcs))
            if u.chord != "—" and (not self._chord_history or self._chord_history[-1] != u.chord):
                self._chord_history = (self._chord_history + [u.chord])[-6:]
                self.chord_progression.setText("Progression :  " + "  →  ".join(self._chord_history))
            source = {"libre": "libre", "détecté": "détecté", "manuel": "réglé"}[u.tempo_source]
            if u.rhythmic:
                self.tempo_tile.set(f"{u.bpm:.0f} BPM", f"{source} · mesure {u.bar + 1}, temps {u.beat_in_bar + 1}")
            else:
                self.tempo_tile.set("Libre", "le piano suit votre chant")
        self.keyboard.set_played(u.piano_notes)

    def _on_output_state(self, event) -> None:
        if event.running:
            self.output_label.setText(f"Orchestre : {event.synth_name}, latence de sortie ≈ {event.latency_ms:.0f} ms")
        else:
            msg = event.message or "arrêté"
            self.output_label.setText(f"Orchestre : {msg}")
            self.orchestra_pill.set_state("error" if event.message else "neutral", "Orchestre : arrêté")

    def _on_stats(self, event: CaptureStats) -> None:
        total = event.input_latency_ms + event.block_ms
        self.stats_label.setText(
            f"{event.samplerate} Hz · bloc {event.blocksize} ({event.block_ms:.1f} ms) · latence d'entrée ≈ {total:.0f} ms · "
            f"traitement {event.processing_ms_avg:.2f} ms/bloc · pertes : {event.input_overflows + event.buffer_overruns}"
        )
