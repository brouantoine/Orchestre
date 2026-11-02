"""Chef d'orchestre IA.

Boucle de décision (thread dédié, toutes les 10 ms) :

    ÉCOUTE ──(≥ 2,5 s de chant)──► JEU ──(silence prolongé)──► CONCLUSION ──► ÉCOUTE
                                    │
                         libre (tempo inconnu) ⇄ rythmé (tempo sûr ou réglé)

- Les temps sont planifiés ~200 ms à l'avance sur l'horloge commune : piano et
  batterie partagent exactement la même grille.
- L'accord n'est réévalué qu'à des points choisis (temps 1 et 3 en rythmé,
  chaque temps en jeu libre, au moins 2 temps par accord) : décisions stables.
- La batterie n'entre qu'en jeu rythmé, en début de mesure, après 2 mesures de chant.
- L'intensité suit le volume du chant ; l'accompagnement s'allège pendant les silences.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from orchestre_ia.analysis.engine import AnalysisEngine, AnalysisSnapshot
from orchestre_ia.analysis.theory import Chord, Key
from orchestre_ia.conductor.harmony import HarmonyEngine
from orchestre_ia.core.events import Event, EventBus
from orchestre_ia.instruments.base import PlayContext
from orchestre_ia.instruments.drums import DrumEngine
from orchestre_ia.instruments.piano import PianoEngine
from orchestre_ia.instruments.styles import DEFAULT_STYLE, STYLES, Style
from orchestre_ia.synthesis.output import AudioOutputEngine

log = logging.getLogger(__name__)

FREE_BPM = 60.0  # grille interne du jeu libre (1 temps = 1 s)


class ConductorState(Enum):
    IDLE = "inactif"
    LISTENING = "écoute"
    PLAYING = "joue"
    ENDING = "conclusion"
    PAUSED = "pause"


@dataclass
class AccompanimentSettings:
    style: str = DEFAULT_STYLE
    drums_mode: str = "auto"  # auto | on | off
    tempo_mode: str = "auto"  # auto | manual
    manual_bpm: float = 90.0
    start_after_s: float = 2.5
    tempo_confidence_threshold: float = 0.5
    silence_bars_to_end: float = 2.0
    free_silence_to_end_s: float = 6.0

    @property
    def style_obj(self) -> Style:
        return STYLES.get(self.style, STYLES[DEFAULT_STYLE])


@dataclass(frozen=True, slots=True)
class ConductorUpdate(Event):
    state: ConductorState
    rhythmic: bool
    chord: str
    alternatives: tuple[str, ...]
    key: str
    key_confidence: float
    bpm: float
    tempo_source: str  # "libre" | "détecté" | "manuel"
    piano_active: bool
    drums_active: bool
    intensity: float
    bar: int
    beat_in_bar: int
    piano_notes: tuple[int, ...] = field(default=())
    chord_pcs: tuple[int, ...] = field(default=())


class Conductor:
    def __init__(
        self,
        bus: EventBus,
        analysis: AnalysisEngine,
        output: AudioOutputEngine,
        settings: AccompanimentSettings | None = None,
        lookahead_s: float = 0.2,
    ) -> None:
        self._bus = bus
        self.analysis = analysis
        self.output = output
        self.settings = settings or AccompanimentSettings()
        self.lookahead_s = lookahead_s
        self.harmony = HarmonyEngine()
        self.piano = PianoEngine()
        self.drums = DrumEngine()
        self.state = ConductorState.IDLE
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._reset_performance()

    def _reset_performance(self) -> None:
        self.rhythmic = False
        self.chord: Chord | None = None
        self.alternatives: tuple[Chord, ...] = ()
        self._chord_since_beat = -100
        self._next_beat = 0
        self._drums_on = False
        self._drums_eligible_since: float | None = None
        self.intensity = 0.5
        self._bpm = FREE_BPM
        self._tempo_source = "libre"
        self._sung_at_listen = 0.0
        self._end_beat: int | None = None
        self.harmony.reset()

    # ------------------------------------------------------------ contrôle
    def start(self) -> None:
        self.stop()
        with self._lock:
            self._reset_performance()
            self._set_state(ConductorState.LISTENING)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="conductor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self.output.silence()
        if self.state != ConductorState.IDLE:
            self._set_state(ConductorState.IDLE)

    def pause(self) -> None:
        with self._lock:
            if self.state in (ConductorState.PLAYING, ConductorState.ENDING, ConductorState.LISTENING):
                self.output.silence()
                self.piano.release_all(0)
                self._set_state(ConductorState.PAUSED)

    def resume(self) -> None:
        with self._lock:
            if self.state == ConductorState.PAUSED:
                self._begin_listening()

    def _set_state(self, state: ConductorState) -> None:
        if state != self.state:
            log.info("Chef d'orchestre : %s", state.value)
        self.state = state
        self._publish()

    def _begin_listening(self) -> None:
        self._sung_at_listen = self.analysis.snapshot().sung_seconds
        self._drums_on = False
        self._set_state(ConductorState.LISTENING)

    # ------------------------------------------------------------ boucle
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._tick(time.monotonic())
            except Exception:
                log.exception("Erreur du chef d'orchestre")
            self._stop.wait(0.01)

    def _tick(self, now: float) -> None:
        if not self.output.running or self.state in (ConductorState.IDLE, ConductorState.PAUSED):
            return
        snap = self.analysis.snapshot()
        self._update_intensity(snap, now)

        if self.state == ConductorState.LISTENING:
            voice_now = now - snap.last_voice_monotonic < 0.4
            if voice_now and snap.sung_seconds - self._sung_at_listen >= self.settings.start_after_s:
                self._start_playing(snap, now)
            return

        self._maybe_switch_mode(snap, now)
        clock = self.output.clock
        while clock.monotonic_at_beat(self._next_beat) < now + self.lookahead_s:
            self._plan_beat(self._next_beat, snap, now)
            self._next_beat += 1
            if self.state == ConductorState.LISTENING:
                return

    # ------------------------------------------------------- décisions
    def _tempo_decision(self, snap: AnalysisSnapshot) -> tuple[bool, float, str]:
        if self.settings.tempo_mode == "manual":
            return True, self.settings.manual_bpm, "manuel"
        t = snap.tempo
        if t is not None and t.confidence >= self.settings.tempo_confidence_threshold:
            return True, t.bpm, "détecté"
        return False, FREE_BPM, "libre"

    def _start_playing(self, snap: AnalysisSnapshot, now: float) -> None:
        rhythmic, bpm, source = self._tempo_decision(snap)
        self._apply_mode(rhythmic, bpm, source, snap)
        # comme un accompagnateur, l'orchestre s'accorde sur la voix (et non l'inverse)
        self.output.set_tuning(snap.tuning_cents)
        self.chord = None
        self._end_beat = None
        self._set_state(ConductorState.PLAYING)
        log.info("Entrée de l'accompagnement : %s, %.0f BPM (%s)", "rythmé" if rhythmic else "libre", bpm, source)

    def _apply_mode(self, rhythmic: bool, bpm: float, source: str, snap: AnalysisSnapshot) -> None:
        clock = self.output.clock
        current = math.ceil(clock.current_beat() + 0.25)
        # on démarre en début de mesure pour que les temps forts tombent juste
        start_beat = current + (-current) % clock.beats_per_bar
        if rhythmic and source == "détecté" and snap.tempo is not None:
            clock.align(bpm, snap.tempo.phase_s, start_beat)
        else:
            clock.set_tempo(bpm)
            start_beat = math.ceil(clock.current_beat() + 0.25)
            start_beat += (-start_beat) % clock.beats_per_bar
        self.rhythmic, self._bpm, self._tempo_source = rhythmic, bpm, source
        self._next_beat = start_beat
        self._chord_since_beat = -100

    def _maybe_switch_mode(self, snap: AnalysisSnapshot, now: float) -> None:
        if self.state != ConductorState.PLAYING:
            return
        rhythmic, bpm, source = self._tempo_decision(snap)
        changed_kind = rhythmic != self.rhythmic or source != self._tempo_source
        manual_bpm_changed = source == "manuel" and abs(bpm - self._bpm) > 0.5
        if changed_kind or manual_bpm_changed:
            if manual_bpm_changed and not changed_kind:
                self.output.clock.set_tempo(bpm)
                self._bpm = bpm
                return
            log.info("Changement de mode : %s %.0f BPM (%s)", "rythmé" if rhythmic else "libre", bpm, source)
            self.output.silence()
            self.piano.release_all(0)
            self._drums_on = False
            self._apply_mode(rhythmic, bpm, source, snap)

    def _update_intensity(self, snap: AnalysisSnapshot, now: float) -> None:
        silent_for = now - snap.last_voice_monotonic
        if silent_for > 1.0:
            target = 0.2
        else:
            # -45 dBFS (doux) -> 0,25 ; -18 dBFS (fort) -> 1,0
            target = min(1.0, max(0.25, (snap.voice_level_db + 45) / 27 * 0.75 + 0.25))
        self.intensity += (target - self.intensity) * 0.01  # lissage ~1 s

    def _plan_beat(self, beat: int, snap: AnalysisSnapshot, now: float) -> None:
        clock = self.output.clock
        bpb = clock.beats_per_bar
        beat_in_bar = beat % bpb
        bar = beat // bpb
        key = snap.key.key if snap.key else None
        key_conf = snap.key.confidence if snap.key else 0.0
        style = self.settings.style_obj
        beat_s = 60.0 / clock.bpm
        silent_for = now - snap.last_voice_monotonic

        if self.state == ConductorState.ENDING:
            if self._end_beat is not None and beat >= self._end_beat + 4:
                self._begin_listening()
            return

        # fin : silence prolongé -> accord de conclusion en début de mesure
        end_after = self.settings.silence_bars_to_end * bpb * beat_s if self.rhythmic else self.settings.free_silence_to_end_s
        if silent_for > end_after and beat_in_bar == 0:
            self._conclude(beat, key)
            return

        # harmonie : points de décision stables
        changed = False
        can_change = (beat_in_bar in (0, 2)) if self.rhythmic else True
        if self.chord is None or (can_change and beat - self._chord_since_beat >= 2):
            evidence = self.analysis.evidence(now - 2.5 * max(beat_s, 0.6), now, half_life_s=max(beat_s, 0.6))
            # La meilleure hypothèse de tonalité guide l'harmonie dès qu'elle existe,
            # même peu sûre : elle se trompe rarement de beaucoup (relative/homonyme).
            decision = self.harmony.decide(evidence, key, max(key_conf, 0.5) if key else 0.0)
            if decision is not None and (self.chord is None or decision.chord != self.chord):
                changed = True
                self.chord = decision.chord
                self.alternatives = tuple(c for c, _ in decision.alternatives)
                self._chord_since_beat = beat
            elif decision is None and self.chord is None:
                return  # pas encore assez d'indices : on attend le temps suivant

        # batterie : entrée en début de mesure quand la pulsation est stable
        self._update_drums(beat_in_bar, snap, now, silent_for, beat_s, style)

        ctx = PlayContext(
            beat=beat,
            beat_in_bar=beat_in_bar,
            bar=bar,
            chord=self.chord,
            chord_changed=changed,
            key=key,
            style=style,
            intensity=self.intensity,
            rhythmic=self.rhythmic,
            fill=self.rhythmic and bar % 4 == 3,
            phrase_start=self.rhythmic and bar % 4 == 0,
        )
        notes, offs = self.piano.play_beat(ctx)
        if self._drums_on:
            drum_notes, _ = self.drums.play_beat(ctx)
            notes += drum_notes
        scheduler = self.output.scheduler
        for off in offs:
            scheduler.add_off(off.channel, off.note, off.beat)
        for n in notes:
            scheduler.add_note(n)
        self._publish(bar=bar, beat_in_bar=beat_in_bar)

    def _update_drums(self, beat_in_bar: int, snap, now: float, silent_for: float, beat_s: float, style: Style) -> None:
        mode = self.settings.drums_mode
        allowed = self.rhythmic and bool(style.drums) and mode != "off"
        if mode == "auto":
            allowed = allowed and style.drums_by_default
        if not allowed:
            self._drums_on = False
            self._drums_eligible_since = None
            return
        if silent_for > 4 * beat_s:
            self._drums_on = False  # la batterie se retire pendant un long silence
            self._drums_eligible_since = None
            return
        if self._drums_on:
            return
        if mode == "on":
            wait = 0.0
        else:
            wait = 2 * 4 * beat_s  # 2 mesures de chant stable
        if self._drums_eligible_since is None:
            self._drums_eligible_since = now
        if now - self._drums_eligible_since >= wait and beat_in_bar == 0:
            self._drums_on = True
            log.info("Entrée de la batterie")

    def _conclude(self, beat: int, key: Key | None) -> None:
        offs = self.piano.release_all(beat - 0.02)
        for off in offs:
            self.output.scheduler.add_off(off.channel, off.note, off.beat)
        if key is not None:
            final = Chord(key.tonic, "min" if key.minor else "maj", 1)
        else:
            final = self.chord
        if final is not None:
            for n in self.piano.ending(beat, final, min(self.intensity, 0.5)):
                self.output.scheduler.add_note(n)
        self._drums_on = False
        self._end_beat = beat
        self.chord = final
        self.harmony.reset()
        self._set_state(ConductorState.ENDING)

    # ---------------------------------------------------------- publication
    def _publish(self, bar: int = 0, beat_in_bar: int = 0) -> None:
        snap = self.analysis.snapshot()
        self._bus.publish(
            ConductorUpdate(
                state=self.state,
                rhythmic=self.rhythmic,
                chord=self.chord.name if self.chord else "—",
                alternatives=tuple(c.name for c in self.alternatives),
                key=snap.key.key.name if snap.key else "—",
                key_confidence=snap.key.confidence if snap.key else 0.0,
                bpm=self._bpm,
                tempo_source=self._tempo_source,
                piano_active=self.state in (ConductorState.PLAYING, ConductorState.ENDING),
                drums_active=self._drums_on,
                intensity=self.intensity,
                bar=bar,
                beat_in_bar=beat_in_bar,
                piano_notes=tuple(self.piano.last_played) if self.state == ConductorState.PLAYING else (),
                chord_pcs=self.chord.pcs if self.chord else (),
            )
        )
