"""Pont bus d'événements -> signaux Qt.

Les événements sont publiés depuis les threads audio, d'analyse et du chef
d'orchestre. Émettre un signal Qt depuis ces threads vers un QObject du thread
graphique passe par une connexion « queued » : le slot s'exécute dans le thread
graphique, sans blocage.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from orchestre_ia.analysis.events import KeyUpdate, NoteFinished, PitchUpdate, TempoUpdate
from orchestre_ia.audio.events import (
    AudioLevelEvent,
    CaptureStateChanged,
    CaptureStats,
    VoiceActivityChanged,
)
from orchestre_ia.conductor.conductor import ConductorUpdate
from orchestre_ia.core.events import EventBus
from orchestre_ia.synthesis.output import OutputStateChanged


class QtEventBridge(QObject):
    level = Signal(object)
    capture_state = Signal(object)
    voice = Signal(object)
    stats = Signal(object)
    pitch = Signal(object)
    note = Signal(object)
    key = Signal(object)
    tempo = Signal(object)
    conductor = Signal(object)
    output_state = Signal(object)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        pairs = [
            (AudioLevelEvent, self.level),
            (CaptureStateChanged, self.capture_state),
            (VoiceActivityChanged, self.voice),
            (CaptureStats, self.stats),
            (PitchUpdate, self.pitch),
            (NoteFinished, self.note),
            (KeyUpdate, self.key),
            (TempoUpdate, self.tempo),
            (ConductorUpdate, self.conductor),
            (OutputStateChanged, self.output_state),
        ]
        self._unsubscribers = [bus.subscribe(kind, signal.emit) for kind, signal in pairs]

    def disconnect_bus(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
