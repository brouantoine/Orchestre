"""Session musicale : assemble capture, analyse, sortie audio et chef d'orchestre."""

from __future__ import annotations

import logging

from orchestre_ia.analysis.engine import AnalysisEngine
from orchestre_ia.audio.capture import AudioCaptureEngine, CaptureSettings
from orchestre_ia.conductor.conductor import AccompanimentSettings, Conductor, ConductorState
from orchestre_ia.core.events import EventBus
from orchestre_ia.synthesis.output import AudioOutputEngine

log = logging.getLogger(__name__)


class MusicSession:
    def __init__(
        self,
        bus: EventBus,
        capture: AudioCaptureEngine | None = None,
        output: AudioOutputEngine | None = None,
        settings: AccompanimentSettings | None = None,
    ) -> None:
        self.bus = bus
        self.capture = capture or AudioCaptureEngine(bus)
        self.analysis = AnalysisEngine(bus)
        self.output = output or AudioOutputEngine(bus)
        self.conductor = Conductor(bus, self.analysis, self.output, settings)
        self.analysis.sounding_notes = self.output.sounding_notes
        self.analysis.output_level = self.output.level_between
        self.capture.add_consumer(self.analysis.feed)
        self.accompany = False

    @property
    def settings(self) -> AccompanimentSettings:
        return self.conductor.settings

    def start(
        self,
        capture_settings: CaptureSettings,
        output_device: int | None = None,
        accompany: bool = True,
        headphones: bool = False,
    ) -> bool:
        """Démarre l'écoute, l'analyse et (si `accompany`) l'orchestre."""
        self.stop()
        self.accompany = accompany
        if not self.capture.start(capture_settings):
            self.accompany = False
            return False
        self.analysis.headphones = headphones
        self.analysis.start(self.capture.samplerate)
        if accompany:
            if not self.output.start(output_device, samplerate=48000, blocksize=512):
                log.error("Accompagnement indisponible : la sortie audio n'a pas démarré")
                self.accompany = False
                return True  # l'écoute et l'analyse continuent
            self.conductor.start()
        return True

    def pause(self) -> None:
        self.conductor.pause()

    def resume(self) -> None:
        self.conductor.resume()

    @property
    def paused(self) -> bool:
        return self.conductor.state == ConductorState.PAUSED

    def stop(self) -> None:
        self.conductor.stop()
        self.output.stop()
        self.capture.stop()
        self.analysis.stop()
