"""Espace ORCHESTRE : volumes, batterie, tempo (automatique, réglé ou tapé)."""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from orchestre_ia.app.session import MusicSession
from orchestre_ia.core.config import AppConfig
from orchestre_ia.interface import theme
from orchestre_ia.interface.icons import icon
from orchestre_ia.interface.views.common import icon_label, make_card, page, scrollable, view_title
from orchestre_ia.midi.events import BASS_CHANNEL, DRUM_CHANNEL, PIANO_CHANNEL

DRUM_MODE_LABELS = {"auto": "Automatique (entre quand la pulsation est stable)", "on": "Toujours (dès le jeu rythmé)", "off": "Jamais"}


class OrchestraView(QWidget):
    def __init__(self, session: MusicSession, config: AppConfig, save_config: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._session = session
        self._config = config
        self._save_config = save_config
        self._taps: list[float] = []
        acc = config.accompaniment

        content, root = page()
        root.addWidget(view_title("Orchestre", "Réglez les instruments. Les changements s'entendent immédiatement."))

        # --- Volumes
        vol_card, vol = make_card("Mixage", "level")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        self.sliders: dict[str, QSlider] = {}
        self.volume_labels: dict[str, QLabel] = {}
        for key, label, icon_name in (("master_volume", "Général", "level"), ("piano_volume", "Piano · main droite", "piano"),
                                      ("bass_volume", "Piano · main gauche", "piano"), ("drums_volume", "Batterie", "drums")):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(round(getattr(acc, key) * 100))
            slider.valueChanged.connect(lambda v, k=key: self._on_volume(k, v))
            self.sliders[key] = slider
            value = QLabel(f"{slider.value()} %")
            value.setMinimumWidth(44)
            value.setObjectName("Dim")
            self.volume_labels[key] = value
            name = QWidget()
            name.setObjectName("Transparent")
            nrow = QHBoxLayout(name)
            nrow.setContentsMargins(0, 0, 0, 0)
            nrow.setSpacing(8)
            nrow.addWidget(icon_label(icon_name, theme.TEXT_DIM, 15))
            nrow.addWidget(QLabel(label))
            line = QWidget()
            line.setObjectName("Transparent")
            lrow = QHBoxLayout(line)
            lrow.setContentsMargins(0, 0, 0, 0)
            lrow.addWidget(slider, 1)
            lrow.addWidget(value)
            form.addRow(name, line)
        vol.addLayout(form)
        root.addWidget(vol_card)

        # --- Batterie
        drum_card, drum = make_card("Batterie", "drums")
        self.drums_combo = QComboBox()
        for key, label in DRUM_MODE_LABELS.items():
            self.drums_combo.addItem(label, key)
        self.drums_combo.setCurrentIndex(self.drums_combo.findData(acc.drums_mode))
        self.drums_combo.currentIndexChanged.connect(self._on_drums_mode)
        drum.addWidget(self.drums_combo)
        note = QLabel(
            "La batterie a besoin d'une pulsation. Si vous chantez librement, réglez le tempo ci-dessous "
            "ou tapez-le en rythme : le piano et la batterie se caleront dessus."
        )
        note.setObjectName("Dim")
        note.setWordWrap(True)
        drum.addWidget(note)
        root.addWidget(drum_card)

        # --- Tempo
        tempo_card, tempo = make_card("Tempo", "tempo")
        modes = QHBoxLayout()
        self.auto_radio = QRadioButton("Détecté sur le chant")
        self.manual_radio = QRadioButton("Réglé")
        group = QButtonGroup(self)
        group.addButton(self.auto_radio)
        group.addButton(self.manual_radio)
        (self.manual_radio if acc.tempo_mode == "manual" else self.auto_radio).setChecked(True)
        self.auto_radio.toggled.connect(self._on_tempo_mode)
        modes.addWidget(self.auto_radio)
        modes.addWidget(self.manual_radio)
        modes.addStretch(1)
        tempo.addLayout(modes)
        bpm_row = QHBoxLayout()
        self.bpm_spin = QDoubleSpinBox()
        self.bpm_spin.setRange(40, 200)
        self.bpm_spin.setDecimals(0)
        self.bpm_spin.setSuffix(" BPM")
        self.bpm_spin.setValue(acc.manual_bpm)
        self.bpm_spin.valueChanged.connect(self._on_bpm)
        self.tap_button = QPushButton("  Taper le tempo")
        self.tap_button.setIcon(icon("tap", theme.ACCENT))
        self.tap_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tap_button.clicked.connect(lambda: self.tap())
        self.tap_hint = QLabel("Cliquez 4 fois en rythme")
        self.tap_hint.setObjectName("Dim")
        bpm_row.addWidget(self.bpm_spin)
        bpm_row.addWidget(self.tap_button)
        bpm_row.addWidget(self.tap_hint)
        bpm_row.addStretch(1)
        tempo.addLayout(bpm_row)
        root.addWidget(tempo_card)
        root.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
        self._apply_all()

    def _apply_all(self) -> None:
        acc = self._config.accompaniment
        for key in self.sliders:
            self._apply_volume(key, getattr(acc, key))
        s = self._session.settings
        s.drums_mode, s.tempo_mode, s.manual_bpm = acc.drums_mode, acc.tempo_mode, acc.manual_bpm

    def _apply_volume(self, key: str, value: float) -> None:
        out = self._session.output
        if key == "master_volume":
            out.set_master_volume(value)
        else:
            channel = {"piano_volume": PIANO_CHANNEL, "bass_volume": BASS_CHANNEL, "drums_volume": DRUM_CHANNEL}[key]
            out.set_channel_volume(channel, value)

    def _on_volume(self, key: str, value: int) -> None:
        self.volume_labels[key].setText(f"{value} %")
        setattr(self._config.accompaniment, key, value / 100)
        self._apply_volume(key, value / 100)

    def _on_drums_mode(self, _i: int) -> None:
        mode = self.drums_combo.currentData()
        self._config.accompaniment.drums_mode = mode
        self._session.settings.drums_mode = mode

    def _on_tempo_mode(self, _checked: bool) -> None:
        mode = "auto" if self.auto_radio.isChecked() else "manual"
        self._config.accompaniment.tempo_mode = mode
        self._session.settings.tempo_mode = mode

    def _on_bpm(self, value: float) -> None:
        self._config.accompaniment.manual_bpm = float(value)
        self._session.settings.manual_bpm = float(value)

    def tap(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if self._taps and now - self._taps[-1] > 2.0:
            self._taps.clear()
        self._taps.append(now)
        self._taps = self._taps[-8:]
        if len(self._taps) >= 4:
            intervals = [b - a for a, b in zip(self._taps, self._taps[1:])]
            bpm = 60.0 / (sum(intervals) / len(intervals))
            self.bpm_spin.setValue(round(bpm))
            self.manual_radio.setChecked(True)
            self.tap_hint.setText(f"Tempo tapé : {bpm:.0f} BPM")
        else:
            self.tap_hint.setText(f"{len(self._taps)}/4…")
