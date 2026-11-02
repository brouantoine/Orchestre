"""Espace ANALYSE : courbe de mélodie, notes, diapason, tonalité, tempo."""

from __future__ import annotations

from collections import deque

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from orchestre_ia.analysis.events import KeyUpdate, NoteFinished, PitchUpdate, TempoUpdate
from orchestre_ia.analysis.theory import note_name
from orchestre_ia.audio.events import CaptureState, CaptureStateChanged
from orchestre_ia.interface.bridge import QtEventBridge
from orchestre_ia.interface.views.common import Tile, make_card, page, scrollable, view_title
from orchestre_ia.interface.widgets.pitch_roll import PitchRollWidget


class AnalysisView(QWidget):
    def __init__(self, bridge: QtEventBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notes: deque[str] = deque(maxlen=24)
        content, root = page()
        root.addWidget(view_title("Analyse", "Ce que le logiciel comprend de votre chant, en direct."))

        roll_card, roll = make_card("Mélodie · 10 dernières secondes", "analyse")
        self.roll = PitchRollWidget()
        roll.addWidget(self.roll)
        root.addWidget(roll_card)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.tuning_tile = Tile("Diapason personnel", "note")
        self.key_tile = Tile("Tonalité et gamme", "key")
        self.tempo_tile = Tile("Tempo", "tempo")
        for i, t in enumerate((self.tuning_tile, self.key_tile, self.tempo_tile)):
            grid.addWidget(t, 0, i)
        root.addLayout(grid)

        notes_card, notes = make_card("Dernières notes chantées", "note")
        self.notes_label = QLabel("—")
        self.notes_label.setWordWrap(True)
        notes.addWidget(self.notes_label)
        self.intervals_label = QLabel("")
        self.intervals_label.setObjectName("Dim")
        self.intervals_label.setWordWrap(True)
        notes.addWidget(self.intervals_label)
        root.addWidget(notes_card)
        root.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
        self._last_midis: deque[int] = deque(maxlen=12)
        self.reset()

        bridge.pitch.connect(self._on_pitch)
        bridge.note.connect(self._on_note)
        bridge.key.connect(self._on_key)
        bridge.tempo.connect(self._on_tempo)
        bridge.capture_state.connect(self._on_capture)

    def reset(self) -> None:
        self.roll.clear()
        self._notes.clear()
        self._last_midis.clear()
        self.notes_label.setText("—")
        self.intervals_label.setText("")
        self.tuning_tile.set("—", "écart moyen par rapport au La 440 Hz")
        self.key_tile.set("—", "")
        self.tempo_tile.set("—", "")

    def _on_capture(self, e: CaptureStateChanged) -> None:
        if e.state == CaptureState.STARTING:
            self.reset()

    def _on_pitch(self, e: PitchUpdate) -> None:
        self.roll.add(e.midi)
        self.tuning_tile.set(f"{e.tuning_cents:+.0f} cents", "corrigé automatiquement pour reconnaître vos notes")

    def _on_note(self, e: NoteFinished) -> None:
        n = e.note
        self._notes.append(note_name(n.midi))
        self._last_midis.append(n.midi)
        self.notes_label.setText("  ".join(self._notes))
        m = list(self._last_midis)
        intervals = [b - a for a, b in zip(m, m[1:])]
        contour = "".join("↗" if i > 0 else "↘" if i < 0 else "→" for i in intervals)
        self.intervals_label.setText(
            f"Intervalles (demi-tons) : {' '.join(f'{i:+d}' for i in intervals)}   Contour : {contour}"
        )

    def _on_key(self, e: KeyUpdate) -> None:
        est = e.estimate
        scale = " ".join(note_name(pc + 60)[:-1] for pc in est.key.scale)
        alt = ", ".join(f"{k.name} ({s:.2f})" for k, s in est.candidates[1:3])
        self.key_tile.set(est.key.name, f"gamme : {scale}\nconfiance {est.confidence * 100:.0f} % · autres : {alt}")

    def _on_tempo(self, e: TempoUpdate) -> None:
        if e.estimate is None:
            self.tempo_tile.set("—", "pas encore assez de notes")
        else:
            est = e.estimate
            verdict = "pulsation régulière" if est.confidence >= 0.5 else "chant libre (rubato)"
            self.tempo_tile.set(f"{est.bpm:.0f} BPM", f"régularité {est.confidence * 100:.0f} % · {verdict}")
