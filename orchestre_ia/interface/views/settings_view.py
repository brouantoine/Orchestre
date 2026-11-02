"""Espace PARAMÈTRES : format audio et conditionnement du signal."""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from orchestre_ia.audio.devices import AudioDevice, find_device, list_output_devices, preferred_default
from orchestre_ia.core.config import SUPPORTED_BLOCKSIZES, SUPPORTED_SAMPLERATES, AppConfig
from orchestre_ia.interface import theme
from orchestre_ia.interface.icons import icon
from orchestre_ia.interface.views.common import make_card, page, scrollable, view_title


class SettingsView(QWidget):
    def __init__(
        self,
        config: AppConfig,
        save_config: Callable[[], None],
        list_outputs: Callable[[], list[AudioDevice]] = list_output_devices,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._save_config = save_config
        self._list_outputs = list_outputs
        self._outputs: list[AudioDevice] = []

        content, root = page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
        root.addWidget(view_title("Paramètres", "Réglages audio. Ils s'appliquent au prochain démarrage de l'écoute."))
        card, layout = make_card("Entrée · micro", "studio")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        self.samplerate_combo = QComboBox()
        for sr in SUPPORTED_SAMPLERATES:
            self.samplerate_combo.addItem(f"{sr} Hz", sr)
        self.blocksize_combo = QComboBox()
        for bs in SUPPORTED_BLOCKSIZES:
            self.blocksize_combo.addItem(f"{bs} échantillons (≈ {bs / 48000 * 1000:.1f} ms à 48 kHz)", bs)
        form.addRow("Fréquence d'échantillonnage", self.samplerate_combo)
        form.addRow("Taille de bloc", self.blocksize_combo)

        hpf_row = QHBoxLayout()
        hpf_row.setSpacing(14)
        self.highpass_check = QCheckBox("Filtre anti-grondement")
        self.highpass_spin = QDoubleSpinBox()
        self.highpass_spin.setRange(20.0, 300.0)
        self.highpass_spin.setSuffix(" Hz")
        self.highpass_spin.setDecimals(0)
        self.highpass_check.toggled.connect(self.highpass_spin.setEnabled)
        hpf_row.addWidget(self.highpass_check)
        hpf_row.addWidget(self.highpass_spin)
        hpf_row.addStretch(1)
        form.addRow("Réduction de bruit", hpf_row)
        layout.addLayout(form)
        root.addWidget(card)

        out_card, out_layout = make_card("Sortie · orchestre", "level")
        out_row = QHBoxLayout()
        self.output_combo = QComboBox()
        self.output_combo.setMinimumWidth(340)
        self.output_refresh = QPushButton()
        self.output_refresh.setObjectName("IconButton")
        self.output_refresh.setIcon(icon("refresh", theme.TEXT_DIM))
        self.output_refresh.setToolTip("Actualiser la liste des sorties")
        self.output_refresh.clicked.connect(self.refresh_outputs)
        out_row.addWidget(self.output_combo, 1)
        out_row.addWidget(self.output_refresh)
        out_layout.addLayout(out_row)
        sf_label = QLabel(
            "Sons : FluidSynth avec la banque FluidR3Mono (licence MIT). "
            "Si FluidSynth est absent, un synthétiseur intégré plus simple prend le relais."
        )
        sf_label.setObjectName("Dim")
        sf_label.setWordWrap(True)
        out_layout.addWidget(sf_label)
        root.addWidget(out_card)

        privacy_card, privacy = make_card("Confidentialité", "lock")
        privacy_text = QLabel(
            "Vos enregistrements et réglages restent sur cet ordinateur, dans votre dossier utilisateur. "
            "Rien n'est envoyé sur Internet."
        )
        privacy_text.setObjectName("Dim")
        privacy_text.setWordWrap(True)
        privacy.addWidget(privacy_text)
        root.addWidget(privacy_card)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Enregistrer les réglages")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.apply)
        self.feedback = QLabel("")
        self.feedback.setObjectName("Dim")
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.feedback)
        buttons.addStretch(1)
        root.addLayout(buttons)
        root.addStretch(1)
        self.load_from_config()
        self.refresh_outputs()

    def load_from_config(self) -> None:
        audio = self._config.audio
        self.samplerate_combo.setCurrentIndex(self.samplerate_combo.findData(audio.samplerate))
        self.blocksize_combo.setCurrentIndex(self.blocksize_combo.findData(audio.blocksize))
        self.highpass_check.setChecked(audio.highpass_enabled)
        self.highpass_spin.setValue(audio.highpass_hz)
        self.highpass_spin.setEnabled(audio.highpass_enabled)

    def refresh_outputs(self) -> None:
        self._outputs = self._list_outputs()
        self.output_combo.clear()
        for dev in self._outputs:
            self.output_combo.addItem(dev.label, dev.index)
        acc = self._config.accompaniment
        selected = find_device(self._outputs, acc.output_device_name, acc.output_hostapi) or preferred_default(self._outputs)
        if selected is not None:
            self.output_combo.setCurrentIndex(self._outputs.index(selected))

    def apply(self) -> None:
        i = self.output_combo.currentIndex()
        if 0 <= i < len(self._outputs):
            self._config.accompaniment.output_device_name = self._outputs[i].name
            self._config.accompaniment.output_hostapi = self._outputs[i].hostapi
        audio = self._config.audio
        audio.samplerate = int(self.samplerate_combo.currentData())
        audio.blocksize = int(self.blocksize_combo.currentData())
        audio.highpass_enabled = self.highpass_check.isChecked()
        audio.highpass_hz = float(self.highpass_spin.value())
        audio.validate()
        self._save_config()
        self.feedback.setText("Enregistré. Relancez l'écoute pour appliquer.")
